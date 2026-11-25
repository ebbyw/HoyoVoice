#!/usr/bin/env python3
"""HoyoVoice OCR daemon (Windows) — protocol-compatible with tools/ocrd.

Reads one request per line on stdin — an image path, optionally followed
by a TAB and a region of interest "x y w h" — and emits one single-line
JSON array of {text, confidence, x, y, w, h} per line on stdout.
Coordinates are normalized 0-1 with a BOTTOM-LEFT origin (Apple Vision
convention) so classify.py works unchanged, and the region is given in
that same space. With a region only that part of the frame is flattened
and recognized, and the boxes still come back normalized to the WHOLE
frame: the caller never sees region-relative coordinates. (Before this,
live.py cut the region to a PNG and handed that path over — a full
decode and a 1.3MB write per fresh frame, then a PNG decode here, for
the same pixels.)

Engines (HOYOVOICE_OCR_ENGINE = auto | rapid | windows, default auto):
  rapid    RapidOCR (ONNX). Line boxes + real confidence scores — the
           closest match to Vision output. ~15 MB of models, pure
           onnxruntime (already a project dependency).
  windows  Windows.Media.Ocr via the winsdk package. Built into Windows
           10/11, nothing to download, but exposes no confidence (reported
           as WIN_CONF, a neutral 0.90) and only word-level rects (unioned
           per line).
  auto     rapid if importable, else windows.

argv[1] (optional): custom-words file. Apple Vision uses it as a
recognition lexicon; neither Windows engine supports that, so here it is
accepted for protocol compatibility and ignored (live.py's fuzzy speaker
matching and text_fixes cover the same ground downstream).
"""
import io
import json
import os
import random
import sys
import time


def directml_available():
    """Single probe used by both engine selection and the startup hint."""
    try:
        import onnxruntime as ort
        return "DmlExecutionProvider" in ort.get_available_providers()
    except Exception:
        return False


# Reply vocabulary, shared with tools/ocrd (the Apple Vision daemon):
#   [ ... ]            blocks (possibly none: the image, or the region, held
#                      no text)
#   null               the file could not be read as a complete image (torn
#                      mid-rewrite, missing) — a lost frame, not an empty one
#   [{"protocol": 2}]  the answer to an empty request line: this daemon
#                      understands regions. The client probes once; a daemon
#                      built before regions answers [] and gets whole frames.
PROTOCOL = [{"protocol": 2}]


def out(blocks):
    print(json.dumps(blocks, sort_keys=True), flush=True)


def parse_request(line):
    """(path, roi) from one stdin line; roi is (x, y, w, h) Vision-
    normalized or None. A malformed or empty region reads the whole
    frame — the fail-safe direction, same as a torn frame."""
    import math
    path, _, rest = line.rstrip("\r\n").partition("\t")
    roi = None
    if rest:
        try:
            x, y, w, h = (float(v) for v in rest.split())
        except ValueError:
            return path, None
        if not all(math.isfinite(v) for v in (x, y, w, h)):
            return path, None       # nan clips to a partial region otherwise
        x0, y0 = max(0.0, x), max(0.0, y)
        x1, y1 = min(1.0, x + w), min(1.0, y + h)
        if x1 > x0 and y1 > y0:
            roi = (x0, y0, x1 - x0, y1 - y0)
    return path, roi


def roi_px(roi, W, H):
    """A Vision-normalized region → (x0, y0, x1, y1) pixel rect with a
    TOP-LEFT origin (the y flip), or None when it would be degenerate
    (under 8px a side: nothing legible fits, and the engines choke on
    near-empty input). Both edges truncate — the same rule as tools/ocrd —
    and px_roi() is its exact inverse, so a remap through the pair is
    exact under the truncation."""
    if roi is None:
        return None
    x, y, w, h = roi
    x0, x1 = max(0, int(x * W)), min(W, int((x + w) * W))
    y0, y1 = max(0, int((1.0 - y - h) * H)), min(H, int((1.0 - y) * H))
    if x1 - x0 < 8 or y1 - y0 < 8:
        return None
    return x0, y0, x1, y1


def px_roi(box, W, H):
    """The region a pixel rect actually covers, Vision-normalized — what a
    box read from that rect must be remapped with (not the requested
    floats, which the truncation in roi_px moved by up to a pixel)."""
    x0, y0, x1, y1 = box
    return (x0 / W, (H - y1) / H, (x1 - x0) / W, (y1 - y0) / H)


def to_full(block, roi):
    """A block normalized to a region → normalized to the whole frame.
    Same arithmetic as tools/anchors.py remap_box, kept here because the
    daemon has no tools/ on its path."""
    if roi is None:
        return block
    rx, ry, rw, rh = roi
    b = dict(block)
    b["x"] = rx + block["x"] * rw
    b["y"] = ry + block["y"] * rh
    b["w"] = block["w"] * rw
    b["h"] = block["h"] * rh
    return b


# Background flattening. Game subtitles are light text that can sit over a
# blown-out sky, where the detector loses them entirely: on a real capture
# only 12/37 frames of one line were detected, so stabilization (which needs
# consecutive reads) stalled for ~40s. Text is high-frequency and
# backgrounds are smooth, so subtracting a blurred copy makes light text pop
# on ANY background — measured 30/37 on the same frames, and the full line
# is read instead of a truncated one. Signed (not absolute) difference:
# taking abs() picks up faint UI edges that break the "no chrome" test used
# to spot lore cards.
#
# Two limits of feeding that flattened image straight to BOTH det and rec:
#   1. HP_GAIN=3.0 clips antialiased glyph edges to 255 — measured 2.52x
#      more pure-white pixels in the dialogue band on captures/frame_001.png,
#      thickening strokes and closing inter-word spaces right before the
#      recognizer runs. Decoupling det (on flat) from rec (cropped from the
#      clean unflattened frame) keeps bright-sky detection without the bloat.
#   2. Dark-text-on-light panels (HSR Messages, Furbobocom cards, daytime
#      loading screens, parchment books) are crushed from ~222 contrast raw
#      down to ~58 flattened (measured on captures/shots/527.jpg), and a
#      single white badge/UID prevents the empty-frame safety net from firing.
#      Measured across 300 real shots: light UI panels sit at median>=224,
#      p25>=178 while the brightest outdoor dialogue sits at median<=187,
#      p25<=130. When a full-frame read clears LIGHT_PANEL_*, detect on the
#      clean frame first instead.
HP_RADIUS, HP_GAIN, HP_OFFSET = 12, 3.0, 40
LIGHT_PANEL_MEDIAN = 200
LIGHT_PANEL_P25 = 160
# Default detector size cap: rapidocr_onnxruntime defaults to limit_type="min",
# limit_side_len=736, which runs DBNet at full 1920x1088 (2.09 MP) and
# UPSCALES cropped ROIs (1920x670 -> 2112x736). Capping the long edge at 1280
# cuts detector area 2.2x-3x while rec still crops from full 1080p pixels.
DEFAULT_DET_LIMIT_TYPE = "max"
DEFAULT_DET_LIMIT_SIDE_LEN = 1280
# Minimum recognition confidence kept by the decoupled det->rec path. Sits
# below Genshin's PLATE_MIN_CONF (0.3) so stylized nameplates still reach the
# profile while pure garbage is dropped.
DECOUPLED_MIN_SCORE = 0.25


def _flatten_gray(g):
    """PIL mode-'L' image → uint8 ndarray with smooth background removed.

    Estimates the radius-12 low-frequency background at 1/4 scale (radius 3)
    when the image is large enough: ~4x faster blur with mean pixel diff
    < 0.8/255 against full-res GaussianBlur(12).

    In-place arithmetic on one int16 buffer: the expression form allocated
    five full-frame float intermediates (~40 MB per 1080p frame at 6 fps).
    Every intermediate is an exact integer — the difference spans [-255, 255],
    ×3 spans [-765, 765], +40, clip to 0-255."""
    from PIL import Image, ImageFilter
    import numpy as np
    w, h = g.size
    if w >= 32 and h >= 32:
        bg = (g.resize((w // 4, h // 4), Image.Resampling.BILINEAR)
               .filter(ImageFilter.GaussianBlur(HP_RADIUS / 4.0))
               .resize((w, h), Image.Resampling.BILINEAR))
    else:
        bg = g.filter(ImageFilter.GaussianBlur(HP_RADIUS))
    a = np.asarray(g, dtype=np.int16)            # dtype conversion = a copy
    np.subtract(a, np.asarray(bg, dtype=np.int16), out=a)
    np.multiply(a, int(HP_GAIN), out=a)
    np.add(a, HP_OFFSET, out=a)
    np.clip(a, 0, 255, out=a)
    return a.astype(np.uint8)


def _flatten_background(data, box=None):
    """Bytes of an image → grayscale ndarray with the background removed;
    of just `box` (top-left pixel rect) when given. Cropped BEFORE the
    blur, so a region's pixels are exactly what the old PNG-crop path
    produced (the blur saw the crop's own edges there too) — and the
    blur is paid on the region, not the frame."""
    from PIL import Image
    with Image.open(io.BytesIO(data)) as img:
        g = img.convert("L")
        if box is not None:
            g = g.crop(box)
        return _flatten_gray(g)


def _is_light_panel(raw_gray, np):
    """True when the frame is a light-background UI panel (dark text on
    white/cream) that signed light-on-dark flattening would crush."""
    # Subsample stride 4: median/p25 over ~130k pixels is identical to 2M
    # pixels to within <1 count and takes <0.5 ms instead of ~8 ms.
    sample = raw_gray[::4, ::4]
    return (float(np.median(sample)) >= LIGHT_PANEL_MEDIAN
            and float(np.percentile(sample, 25)) >= LIGHT_PANEL_P25)


def _crop_for_rec(raw_bgr, box_pts, np):
    """Slice one horizontal text-line crop from the clean unflattened frame.

    Pads by 2px so tight DBNet boxes don't clip ascenders or edge serifs.
    Only stretches contrast on genuinely low-contrast crops (e.g. white text
    over a bright sky), linearly over [p2, p98] without hard-clipping
    antialiased edges."""
    H, W = raw_bgr.shape[:2]
    xs = [p[0] for p in box_pts]
    ys = [p[1] for p in box_pts]
    x0 = max(0, int(min(xs)) - 2)
    y0 = max(0, int(min(ys)) - 2)
    x1 = min(W, int(max(xs)) + 3)
    y1 = min(H, int(max(ys)) + 3)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return None
    crop = raw_bgr[y0:y1, x0:x1]
    lo, hi = np.percentile(crop, (2, 98))
    if 0 < hi - lo < 80:
        scaled = (crop.astype(np.float32) - lo) * (255.0 / (hi - lo))
        return np.clip(scaled, 0, 255).astype(np.uint8)
    return crop


def _complete_image(data):
    """True if these bytes are a whole image, not a half-written one."""
    if len(data) < 1024:
        return False
    return ((data[:2] == b"\xff\xd8" and data[-2:] == b"\xff\xd9")      # JPEG
            or (data[:8] == b"\x89PNG\r\n\x1a\n"
                and data[-8:-4] == b"IEND"))                            # PNG


def read_frame_bytes(path, tries=12):
    """ffmpeg rewrites the frame file continuously, so a naive read can
    catch it half-written — on Windows that surfaces as a flood of
    'The image is unrecognized' (WinError -2003292320) and nearly every
    frame is lost. Retry with jittered backoff (fixed delays alias
    against the writer's cycle) until the bytes are a complete image.
    Total worst case stays under one 6fps frame interval."""
    delay = 0.004
    for _ in range(tries):
        try:
            with open(path, "rb") as f:
                data = f.read()
            if _complete_image(data):
                return data
        except OSError:                    # sharing violation mid-swap
            pass
        time.sleep(delay * random.uniform(0.6, 1.4))
        delay = min(delay * 1.5, 0.02)
    return None


def _rec_override():
    """Optional recognition-model swap → {} or RapidOCR kwargs.

    The bundled rec model is Chinese-trained; its known failure mode on
    English game text is dropped spaces and word fusions ("fora"), which
    live.py then has to repair statistically. An English-trained rec model
    (en_PP-OCRv5_mobile_rec, converted to ONNX) fixes that at the source.
    Detection is untouched, so box geometry and classify.py behavior are
    identical.

    Resolution order: HOYOVOICE_REC_MODEL (+ HOYOVOICE_REC_KEYS) env vars,
    else models/rec_en.onnx + models/rec_en_dict.txt in the repo root
    (setup.ps1 downloads them there). A rec model decoded with the wrong
    character dict reads garbage, so the override applies only when BOTH
    files exist — otherwise the bundled default stays and we say why."""
    model = os.environ.get("HOYOVOICE_REC_MODEL")
    keys = os.environ.get("HOYOVOICE_REC_KEYS")
    if not model:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model = os.path.join(root, "models", "rec_en.onnx")
        keys = keys or os.path.join(root, "models", "rec_en_dict.txt")
        if not os.path.exists(model):
            return {}
    elif not keys:
        keys = os.path.splitext(model)[0] + "_dict.txt"
    missing = [p for p in (model, keys) if not os.path.exists(p)]
    if missing:
        print(f"[ocrd_win] rec override ignored — missing {missing}",
              file=sys.stderr, flush=True)
        return {}
    return {"rec_model_path": model, "rec_keys_path": keys}


def _det_override():
    """Optional detection-model swap → {} or RapidOCR kwargs.

    Resolution order: HOYOVOICE_DET_MODEL env var, else models/det_v5.onnx
    in the repo root. Allows dropping in a PP-OCRv5 detector without code
    changes while keeping the bundled detector as the zero-config default."""
    model = os.environ.get("HOYOVOICE_DET_MODEL")
    if not model:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        model = os.path.join(root, "models", "det_v5.onnx")
        if not os.path.exists(model):
            return {}
    elif not os.path.exists(model):
        print(f"[ocrd_win] det override ignored — missing {model}",
              file=sys.stderr, flush=True)
        return {}
    return {"det_model_path": model}


def _det_tuning():
    """Detector sizing kwargs: cap the long edge at 1280 by default so
    1080p frames don't run DBNet at 2 MP and cropped ROIs aren't upscaled
    past 2000px wide by rapidocr's limit_type='min' default."""
    limit_type = os.environ.get("HOYOVOICE_DET_LIMIT_TYPE",
                                DEFAULT_DET_LIMIT_TYPE)
    try:
        side = int(os.environ.get("HOYOVOICE_DET_LIMIT_SIDE_LEN",
                                  str(DEFAULT_DET_LIMIT_SIDE_LEN)))
    except ValueError:
        side = DEFAULT_DET_LIMIT_SIDE_LEN
    kw = {"det_limit_type": limit_type, "det_limit_side_len": side}
    unclip = os.environ.get("HOYOVOICE_DET_UNCLIP_RATIO")
    if unclip:
        try:
            kw["det_unclip_ratio"] = float(unclip)
        except ValueError:
            pass
    return kw


def _init_rapid(RapidOCR, base_kw, tune_kw):
    """Instantiate RapidOCR with tuning kwargs, falling back to base_kw if
    an older package version doesn't accept a tuning key."""
    try:
        return RapidOCR(**base_kw, **tune_kw)
    except TypeError:
        print("[ocrd_win] engine rejected det tuning kwargs — using defaults",
              file=sys.stderr, flush=True)
        return RapidOCR(**base_kw)


class RapidEngine:
    """RapidOCR (ONNX). Uses DirectML when available — on a gaming PC this
    is the difference between ~4s and a fraction of a second per frame,
    with materially better accuracy than the built-in Windows engine."""

    def __init__(self):
        from rapidocr_onnxruntime import RapidOCR
        from PIL import Image
        import numpy as np
        self.Image = Image
        self.np = np
        self.mode = "cpu"
        self.empty_run = 0        # consecutive frames both passes read nothing
        # 2-D gray input: the flattened frame is one gray plane stacked
        # into RGB purely because that shape is known-good. Whether THIS
        # machine's RapidOCR reads the bare 2-D array identically is
        # checked on the first GRAY_TRIALS texty frames (double OCR cost
        # on just those frames): byte-identical results flip gray_ok True
        # and the ~6 MB stack copy is dropped for the session; any
        # difference or error locks the stack in. Stacked is always the
        # answer handed back while undecided — the trial can only ever
        # remove a copy, never change what the caller sees.
        self.gray_ok = None
        self.gray_trials = 0
        self._cls_kw = None       # decided on the first engine call
        self._decoupled = os.environ.get("HOYOVOICE_OCR_DECOUPLED", "1") != "0"
        kw = _rec_override()
        kw.update(_det_override())
        if "rec_model_path" in kw:
            print(f"[ocrd_win] rec model: "
                  f"{os.path.basename(kw['rec_model_path'])}",
                  file=sys.stderr, flush=True)
        if "det_model_path" in kw:
            print(f"[ocrd_win] det model: "
                  f"{os.path.basename(kw['det_model_path'])}",
                  file=sys.stderr, flush=True)
        tune = _det_tuning()
        # cls (the per-row angle classifier) is disabled at every call
        # below: game UI text is always drawn upright, so the classifier
        # can only ever hurt — and on DirectML it does, intermittently
        # flipping a row and reading it rotated 180°. Session shots from
        # 2026-08-13 caught 'golden glow of "friendship."' coming back as
        # 'ajuspuerd. do Mons uapios' at conf 0.6 on a frame whose
        # neighbors read it upright at 0.96 — the same class of one-row
        # garbage ("Culld.", "hum") the book reader has been speaking.
        # No cls_use_dml either: the session would be built and never run.
        if directml_available():
            try:
                self.ocr = _init_rapid(
                    RapidOCR,
                    dict(det_use_dml=True, rec_use_dml=True, **kw), tune)
                self.mode = "directml"
                return
            except Exception as e:
                print(f"[ocrd_win] DirectML init failed ({e}) — using CPU",
                      file=sys.stderr, flush=True)
        self.ocr = _init_rapid(RapidOCR, kw, tune)

    # Texty frames the 2-D gray result must match the stacked result on,
    # identically, before the stack copy is dropped. Three, not one: a
    # single frame can't tell "identical path" from "identical by luck on
    # easy text".
    GRAY_TRIALS = 3

    def _call(self, img):
        """One engine call with cls off (see __init__). An engine too old
        to take use_cls keeps cls instead of killing the daemon: the
        first TypeError locks the plain call in for the session."""
        if self._cls_kw is None:
            self._cls_kw = {"use_cls": False}
            try:
                return self.ocr(img, **self._cls_kw)
            except TypeError:
                self._cls_kw = {}
                print("[ocrd_win] engine too old for use_cls=False — "
                      "angle classifier stays on", file=sys.stderr,
                      flush=True)
        return self.ocr(img, **self._cls_kw)

    def _detect(self, flat):
        """One detector pass over the flattened frame — through the 2-D
        gray array once this machine's engine has proven it reads that
        identically, through the 3-channel stack until then (and forever,
        on the first disagreement)."""
        np = self.np
        if self.gray_ok is True:
            result, _ = self._call(flat)
            return result
        result, _ = self._call(np.stack([flat] * 3, axis=-1))
        if self.gray_ok is None and result:
            try:
                gray, _ = self._call(flat)
            except Exception:
                gray = None
            # float(): some engine versions report the score as a string,
            # and this comparison sits outside the try above — a bare
            # subtraction was an uncaught TypeError that killed the daemon
            same = (gray is not None and len(gray) == len(result)
                    and all(t1 == t2
                            and abs(float(s1) - float(s2)) < 1e-6
                            and np.array_equal(np.asarray(b1),
                                               np.asarray(b2))
                            for (b1, t1, s1), (b2, t2, s2)
                            in zip(gray, result)))
            if same:
                self.gray_trials += 1
                if self.gray_trials >= self.GRAY_TRIALS:
                    self.gray_ok = True
                    print("[ocrd_win] gray input verified identical on "
                          f"{self.GRAY_TRIALS} frames — dropping the RGB "
                          "stack copy", file=sys.stderr, flush=True)
            else:
                self.gray_ok = False
                print("[ocrd_win] gray input differs — keeping the RGB "
                      "stack", file=sys.stderr, flush=True)
        return result

    def _can_decouple(self):
        """True when the underlying RapidOCR instance exposes text_det and
        text_rec so detection (flattened) can be decoupled from recognition
        (clean unflattened crops)."""
        return (getattr(self, "_decoupled", False)
                and callable(getattr(self.ocr, "text_det", None))
                and callable(getattr(self.ocr, "text_rec", None)))

    def _run_decoupled(self, det_img, raw_bgr):
        """Run text_det on det_img, then crop each detected line from the
        clean unflattened raw_bgr for text_rec. Avoids feeding 2.5x bloated
        high-pass strokes to the recognizer while keeping bright-sky
        detection intact. Returns None on unexpected API mismatch so the
        caller falls back to the classic combined call."""
        np = self.np
        try:
            det_in = (det_img if det_img.ndim == 3
                      else np.stack([det_img] * 3, axis=-1))
            dt_out = self.ocr.text_det(det_in)
            dt_boxes = dt_out[0] if isinstance(dt_out, tuple) else dt_out
            if hasattr(dt_boxes, "boxes"):
                dt_boxes = dt_boxes.boxes
            if dt_boxes is None or len(dt_boxes) == 0:
                return []
            # Reading order: top-to-bottom, left-to-right (matches RapidOCR's
            # sorted_boxes so downstream order stays consistent).
            boxes = sorted(dt_boxes,
                           key=lambda b: (round(float(min(p[1] for p in b)) / 10),
                                          float(min(p[0] for p in b))))
            crops, kept_boxes = [], []
            for b in boxes:
                c = _crop_for_rec(raw_bgr, b, np)
                if c is not None:
                    crops.append(c)
                    kept_boxes.append(b)
            if not crops:
                return []
            rec_out = self.ocr.text_rec(crops)
            rec_res = rec_out[0] if isinstance(rec_out, tuple) else rec_out
            out = []
            for b, item in zip(kept_boxes, rec_res or []):
                text, score = item[0], float(item[1])
                if text and score >= DECOUPLED_MIN_SCORE:
                    out.append((b, text, score))
            return out
        except (AttributeError, TypeError, IndexError) as e:
            self._decoupled = False
            print(f"[ocrd_win] decoupled det/rec unavailable ({e}) — "
                  "using combined OCR pass", file=sys.stderr, flush=True)
            return None

    def recognize(self, path, roi=None):
        data = read_frame_bytes(path)
        if data is None:
            return None             # not a complete image: a lost frame
        np = self.np
        # Decode the frame ONCE into both RGB (for clean rec crops) and L
        # (for flattening and light-panel polarity detection).
        with self.Image.open(io.BytesIO(data)) as img:
            W, H = img.size
            box = roi_px(roi, W, H)
            cropped = img.crop(box) if box is not None else img
            g = cropped.convert("L")
            raw_gray = np.asarray(g)
            # Only pay RGB conversion when decoupled rec will actually crop it
            raw_bgr = (np.asarray(cropped.convert("RGB"))[..., ::-1]
                       if self._can_decouple() else None)
            flat = _flatten_gray(g)
        # the region's pixel origin, so boxes are built in FULL-frame
        # pixels below and nothing region-relative ever leaves here
        ox, oy = (box[0], box[1]) if box else (0, 0)
        # Light-background UI panels (dark text on white/cream) lose 4x
        # contrast under signed light-on-dark flattening. Detect on the clean
        # frame first when the whole frame is bright (dialogue anchors always
        # pass a box and are light-on-dark).
        light = box is None and _is_light_panel(raw_gray, np)
        if raw_bgr is not None:
            primary = raw_bgr if light else flat
            result = self._run_decoupled(primary, raw_bgr)
            if result is None:
                # Decoupled path disabled itself on API mismatch — fall back
                result = self._detect(flat)
            elif not result:
                if self.empty_run % 4 == 0:
                    alt = flat if light else raw_bgr
                    result = self._run_decoupled(alt, raw_bgr) or []
                self.empty_run = 0 if result else self.empty_run + 1
            else:
                self.empty_run = 0
        else:
            if light:
                result, _ = self._call(data)
            else:
                result = self._detect(flat)
            if not result:
                # Safety net for screens the primary pass hurts — throttled
                # to every 4th empty frame so textless runs don't pay 2x.
                if self.empty_run % 4 == 0:
                    if light:
                        result = self._detect(flat)
                    else:
                        result, _ = self._call(
                            data if box is None
                            else np.stack([raw_gray] * 3, axis=-1))
                self.empty_run = 0 if result else self.empty_run + 1
            else:
                self.empty_run = 0
        blocks = []
        for pts, text, score in result or []:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            x0, x1 = ox + min(xs), ox + max(xs)
            y0, y1 = oy + min(ys), oy + max(ys)   # pixel, top-left origin
            blocks.append({
                "text": text,
                "confidence": float(score),
                "x": x0 / W, "w": (x1 - x0) / W,
                "y": 1.0 - y1 / H,           # → bottom-left origin
                "h": (y1 - y0) / H,
            })
        return blocks


# Windows.Media.Ocr exposes no confidence. Reporting 1.0 made live.py's
# confidence-aware stabilization treat every read as vouched-for (its
# CONF_TRUSTED path skips the sentence-streaming cushion read), on the
# *least* accurate engine we ship. 0.90 sits in the neutral band — below
# CONF_TRUSTED (0.97), above CONF_SHAKY (0.85) — so the default cushions
# apply and no confidence rule ever fires on a made-up number.
WIN_CONF = 0.90


class WindowsEngine:
    def __init__(self):
        import asyncio
        from winsdk.windows.globalization import Language
        from winsdk.windows.graphics import imaging
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.storage import FileAccessMode, StorageFile
        self.asyncio = asyncio
        self.imaging = imaging
        self.StorageFile = StorageFile
        self.FileAccessMode = FileAccessMode
        self.engine = (OcrEngine.try_create_from_language(Language("en-US"))
                       or OcrEngine.try_create_from_user_profile_languages())
        if self.engine is None:
            raise RuntimeError("no OCR language pack available "
                               "(install English in Windows language settings)")
        try:
            self.max_dim = int(OcrEngine.max_image_dimension)
        except Exception:
            self.max_dim = 2600
        self.loop = asyncio.new_event_loop()

    @staticmethod
    def _flattened_png(data, box=None):
        """This engine decodes from bytes, so re-encode after flattening
        (of just `box` when given). Falls back to the original frame if
        anything goes wrong — whole, so the caller must not remap then."""
        try:
            from PIL import Image
            buf = io.BytesIO()
            # compress_level=0: the buffer's only consumer is the decoder
            # two lines later — PIL's default level 6 spent ~46ms
            # compressing bytes nobody stores (level 0: ~6ms, lossless)
            Image.fromarray(_flatten_background(data, box)).save(
                buf, format="PNG", compress_level=0)
            return buf.getvalue(), box is not None
        except Exception:
            return data, False

    async def _decode_stream(self, data):
        """Decode from memory — reading the file directly races ffmpeg's
        rewrite and yields 'The image is unrecognized' on most frames."""
        from winsdk.windows.storage.streams import (DataWriter,
                                                    InMemoryRandomAccessStream)
        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(data)
        await writer.store_async()
        await writer.flush_async()
        writer.detach_stream()
        stream.seek(0)
        return stream

    async def _run(self, path, roi=None):
        img = self.imaging
        data = read_frame_bytes(path)
        if data is None:
            return None             # not a complete image: a lost frame
        box, size = None, None
        if roi is not None:
            from PIL import Image
            with Image.open(io.BytesIO(data)) as im:
                size = im.size
                box = roi_px(roi, *size)
        data, cropped = self._flattened_png(data, box)
        stream = await self._decode_stream(data)
        decoder = await img.BitmapDecoder.create_async(stream)
        w0, h0 = decoder.pixel_width, decoder.pixel_height
        # upscale toward the engine's size limit: Windows OCR is markedly
        # more accurate on small game fonts when the text is larger
        scale = min(2.0, (self.max_dim - 4) / max(w0, h0, 1))
        if scale > 1.05:
            transform = img.BitmapTransform()
            transform.scaled_width = int(w0 * scale)
            transform.scaled_height = int(h0 * scale)
            transform.interpolation_mode = img.BitmapInterpolationMode.CUBIC
            bmp = await decoder.get_software_bitmap_async(
                img.BitmapPixelFormat.BGRA8,
                img.BitmapAlphaMode.PREMULTIPLIED,
                transform,
                img.ExifOrientationMode.IGNORE_EXIF_ORIENTATION,
                img.ColorManagementMode.DO_NOT_COLOR_MANAGE)
        else:
            bmp = await decoder.get_software_bitmap_async()
        W, H = bmp.pixel_width, bmp.pixel_height
        result = await self.engine.recognize_async(bmp)
        blocks = []
        for line in result.lines:
            rects = [w.bounding_rect for w in line.words]
            if not rects:
                continue
            x0 = min(r.x for r in rects)
            y0 = min(r.y for r in rects)
            x1 = max(r.x + r.width for r in rects)
            y1 = max(r.y + r.height for r in rects)
            blocks.append({
                "text": line.text,
                "confidence": WIN_CONF,      # engine exposes none — see above
                "x": x0 / W, "w": (x1 - x0) / W,
                "y": 1.0 - y1 / H,           # → bottom-left origin
                "h": (y1 - y0) / H,
            })
        # the bitmap was the region, so its boxes are region-normalized
        # until this remap — through the pixel rect that was cut, not the
        # requested floats; the whole-frame fallback above skips it
        if not cropped:
            return blocks
        cut = px_roi(box, *size)
        return [to_full(b, cut) for b in blocks]

    def recognize(self, path, roi=None):
        return self.loop.run_until_complete(self._run(path, roi))


# auto mode: rapid must OCR a full frame this fast to keep up with the
# live loop (6 fps sampling, 2-read stabilization); otherwise use the
# native engine, which is far faster on weak CPUs
AUTO_MAX_MS = 1200


def _benchmark(engine):
    """Time one warmed-up recognize() on a synthetic 1080p frame."""
    import tempfile
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1920, 1080), "black")
    d = ImageDraw.Draw(img)
    d.text((760, 240), "Rin Tohsaka", fill="white")
    d.text((650, 300), "The informant is right here in your agency?",
           fill="white")
    path = os.path.join(tempfile.gettempdir(), "hoyovoice_ocr_bench.png")
    img.save(path)
    engine.recognize(path)              # first call pays model warm-up
    t0 = time.time()
    engine.recognize(path)
    return int((time.time() - t0) * 1000)


def _engine_note():
    """One-line hint about what would make OCR better on this machine."""
    if not directml_available():
        return ("[ocrd_win] tip: install onnxruntime-directml for "
                "GPU-accelerated, more accurate OCR")
    return None


def make_engine():
    want = os.environ.get("HOYOVOICE_OCR_ENGINE", "auto").lower()
    errors = []
    if want in ("auto", "rapid"):
        try:
            eng = RapidEngine()
            if want == "rapid":
                print(f"[ocrd_win] engine: rapid ({eng.mode})",
                      file=sys.stderr, flush=True)
                return eng
            ms = _benchmark(eng)
            if ms <= AUTO_MAX_MS:
                print(f"[ocrd_win] engine: rapid ({eng.mode}, {ms}ms/frame)",
                      file=sys.stderr, flush=True)
                return eng
            print(f"[ocrd_win] rapid too slow here ({eng.mode}, {ms}ms/frame)"
                  " — falling back to the native Windows engine. For better "
                  "accuracy install DirectML: "
                  ".venv\\Scripts\\pip install onnxruntime-directml",
                  file=sys.stderr, flush=True)
            errors.append(f"rapid: {ms}ms/frame > {AUTO_MAX_MS}ms")
        except Exception as e:
            errors.append(f"rapid: {e}")
            if want == "rapid":
                raise
    try:
        eng = WindowsEngine()
        print("[ocrd_win] engine: windows", file=sys.stderr, flush=True)
        return eng
    except Exception as e:
        errors.append(f"windows: {e}")
        raise RuntimeError("no OCR engine available — " + "; ".join(errors))


def main():
    engine = make_engine()
    note = _engine_note()
    if note:
        print(note, file=sys.stderr, flush=True)
    for line in sys.stdin:
        path, roi = parse_request(line)
        if not path:
            out(PROTOCOL)           # the client's one-time capability probe
            continue
        try:
            out(engine.recognize(path, roi))
        except BrokenPipeError:
            return                      # parent exited — quiet shutdown
        except Exception as e:
            print(f"[ocrd_win] {e}", file=sys.stderr, flush=True)
            try:
                out([])
            except BrokenPipeError:
                return


if __name__ == "__main__":
    try:
        main()
    except (BrokenPipeError, KeyboardInterrupt):
        pass
