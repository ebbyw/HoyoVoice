#!/usr/bin/env python3
"""HoyoVoice OCR daemon (Windows) — protocol-compatible with tools/ocrd.

Reads an image path per line on stdin, emits one single-line JSON array of
{text, confidence, x, y, w, h} per line on stdout. Coordinates are
normalized 0-1 with a BOTTOM-LEFT origin (Apple Vision convention) so
classify.py works unchanged.

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


def out(blocks):
    print(json.dumps(blocks, sort_keys=True), flush=True)


# Background flattening. Game subtitles are light text that can sit over a
# blown-out sky, where the detector loses them entirely: on a real capture
# only 12/37 frames of one line were detected, so stabilization (which needs
# consecutive reads) stalled for ~40s. Text is high-frequency and
# backgrounds are smooth, so subtracting a blurred copy makes light text pop
# on ANY background — measured 30/37 on the same frames, and the full line
# is read instead of a truncated one. Signed (not absolute) difference:
# taking abs() picks up faint UI edges that break the "no chrome" test used
# to spot lore cards. Dark-text-on-light is therefore not enhanced; game
# dialogue is always light on dark.
HP_RADIUS, HP_GAIN, HP_OFFSET = 12, 3.0, 40


def _flatten_background(data):
    """Bytes of an image → grayscale ndarray with the background removed."""
    from PIL import Image, ImageFilter
    import numpy as np
    with Image.open(io.BytesIO(data)) as img:
        g = img.convert("L")
        bg = g.filter(ImageFilter.GaussianBlur(HP_RADIUS))
        a = (np.asarray(g, dtype=np.float32)
             - np.asarray(bg, dtype=np.float32))
    return np.clip(a * HP_GAIN + HP_OFFSET, 0, 255).astype(np.uint8)


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
        kw = _rec_override()
        if kw:
            print(f"[ocrd_win] rec model: "
                  f"{os.path.basename(kw['rec_model_path'])}",
                  file=sys.stderr, flush=True)
        if directml_available():
            try:
                self.ocr = RapidOCR(det_use_dml=True, cls_use_dml=True,
                                    rec_use_dml=True, **kw)
                self.mode = "directml"
                return
            except Exception as e:
                print(f"[ocrd_win] DirectML init failed ({e}) — using CPU",
                      file=sys.stderr, flush=True)
        self.ocr = RapidOCR(**kw)

    def recognize(self, path):
        data = read_frame_bytes(path)
        if data is None:
            return []
        with self.Image.open(io.BytesIO(data)) as img:
            W, H = img.size
        # RapidOCR takes an ndarray directly, so no re-encode round trip
        flat = _flatten_background(data)
        result, _ = self.ocr(self.np.stack([flat] * 3, axis=-1))
        if not result:
            # Safety net for screens the flattening filter hurts — but not
            # on every frame. Textless frames arrive in long runs (loading,
            # fades, overworld at night), and an unconditional second pass
            # doubled the per-frame cost exactly there. Throttle it to every
            # 4th empty frame: a filter-hurt screen is still seen within 3
            # frames (~0.5s at 6fps sampling, under the 2-read stabilization
            # it needs anyway), and the bound means a persistent empty run
            # can never latch the net shut — same medicine as the change
            # gate's MAX_SKIP_RUN.
            if self.empty_run % 4 == 0:
                result, _ = self.ocr(data)
            self.empty_run = 0 if result else self.empty_run + 1
        else:
            self.empty_run = 0
        blocks = []
        for box, text, score in result or []:
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            x0, x1 = min(xs), max(xs)
            y0, y1 = min(ys), max(ys)        # pixel coords, top-left origin
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
    def _flattened_png(data):
        """This engine decodes from bytes, so re-encode after flattening.
        Falls back to the original frame if anything goes wrong."""
        try:
            from PIL import Image
            buf = io.BytesIO()
            Image.fromarray(_flatten_background(data)).save(buf, format="PNG")
            return buf.getvalue()
        except Exception:
            return data

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

    async def _run(self, path):
        img = self.imaging
        data = read_frame_bytes(path)
        if data is None:
            return []
        data = self._flattened_png(data)
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
        return blocks

    def recognize(self, path):
        return self.loop.run_until_complete(self._run(path))


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
        path = line.strip()
        if not path:
            out([])
            continue
        try:
            out(engine.recognize(path))
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
