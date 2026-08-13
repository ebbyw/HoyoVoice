#!/usr/bin/env python3
"""UI anchors: find game chrome by pixels, before (and without) OCR.

An anchor is a small grayscale template of chrome the game draws
pixel-identically on every frame of a screen kind — Star Rail's ✕-circle
next to 'Continue', Genshin's auto-play toggle. It is matched by
normalized cross-correlation inside a small fixed search region on a
half-scale grayscale decode of the frame (the same draft-mode decode the
change gate uses). Design and the coordinate-space gotcha table:
plans/ANCHORS.md.

Presence of an anchor is strong evidence; absence is weak (motion blur or
a fade dents a score for a frame) — anchors may gate COST, never speech.
Phase (a) made matches log-only evidence; phase (b) adds the cost gate:
an anchor can carry an `roi` — the union of every band its screen kind
needs — and live.py (behind settings.anchor_roi) then OCRs only that
crop, remapping the returned boxes to full-frame coordinates before
anything downstream sees them. No match → full frame, today's behavior.

Spec file, one per game (tools/profiles/anchors/<game>.json):

    {"anchors": [{"name": "continue",
                  "template": "hsr/continue.png",
                  "cut": {"x": [0.9045, 0.9215], "y": [0.0074, 0.0407]},
                  "search": {"x": [0.86, 1.0], "y": [0.0, 0.10]},
                  "threshold": 0.75,
                  "ref": [960, 540],
                  "roi": {"x": [0.0, 1.0], "y": [0.0, 0.62]}}]}

`search` is Vision-normalized (origin bottom-left, 0-1) like every band
in tools/profiles/. `ref` is the half-scale decode size the template was
cut at; a frame decoding to a different size stands the anchor down
rather than matching at the wrong scale — NCC across scales fails
quietly with mid scores, and a mid score against a threshold is a
coin-flip.

Template PNGs do NOT ship in the repo — they are crops of the games' own
chrome, and the games' pixels are HoYoverse's. The spec ships the `cut`
rect instead, and the pack SELF-CALIBRATES: an entry whose template is
missing is `pending`, and maybe_bootstrap() cuts the template from the
user's own capture the first time the classifier trusts the game's
dialogue chrome (the same OCR-text ground truth the shipped thresholds
were measured against), holds it for a few trusted frames, verifies it
matches a LATER trusted frame at the shipped threshold, and only then
persists it to the user dir (captures/anchors/, gitignored) with a
sidecar recording the decode size it was cut at. A verify miss throws
the candidate away and starts over — a template cut from a fade or a
motion-blurred frame must never be committed. Validated on the
regression recordings: self-cut templates score 0.985+ on later frames
of their own game and ≤0.47 on the other game's — the same margins as
the originally shipped, hand-measured templates.

CLI:
    python tools/anchors.py extract <game> <name> <frame.jpg> x0 x1 y0 y1
        cut a template from a frame (region Vision-normalized); pads the
        search region by the template size and writes/updates the spec
    python tools/anchors.py match <game> <frame.jpg> [...]
        print scores for every anchor against the frame(s)
"""
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ANCHOR_DIR = Path(__file__).resolve().parent / "profiles" / "anchors"
DRAFT_SCALE = 2          # same half-scale draft decode as the change gate
# Search regions are padded by this much of the template's own size on
# each side at extract time, so chrome that shifts a few pixels between
# sessions (aspect letterboxing, capture cropping) stays inside the box.
SEARCH_PAD = 1.0


def decode_half(path_or_bytes):
    """Half-scale grayscale decode, or None for a torn/partial JPEG.
    Same contract as the change gate's _decode: None means 'can't judge',
    never 'empty screen'."""
    data = (path_or_bytes if isinstance(path_or_bytes, bytes)
            else Path(path_or_bytes).read_bytes())
    if not (len(data) > 1024 and data[:2] == b"\xff\xd8"
            and data[-2:] == b"\xff\xd9"):
        return None
    img = Image.open(io.BytesIO(data))
    img.draft("L", (max(1, img.width // DRAFT_SCALE),
                    max(1, img.height // DRAFT_SCALE)))
    return np.asarray(img.convert("L"), dtype=np.float32)


def _to_px(region, W, H):
    """Vision-normalized region → pixel rect (x0, y0, x1, y1), top-left
    origin. The Y flip: normalized y is measured up from the bottom."""
    (nx0, nx1), (ny0, ny1) = region["x"], region["y"]
    return (max(0, int(nx0 * W)), max(0, int((1.0 - ny1) * H)),
            min(W, int(nx1 * W)), min(H, int((1.0 - ny0) * H)))


def _ncc(window, tmpl):
    """Peak normalized cross-correlation of tmpl over window, and where.
    Plain numpy sliding windows: regions are small (a few thousand
    positions), so this stays a few ms without OpenCV."""
    th, tw = tmpl.shape
    wh, ww = window.shape
    if wh < th or ww < tw:
        return -1.0, (0, 0)
    t = tmpl - tmpl.mean()
    tn = np.sqrt((t * t).sum())
    if tn < 1e-6:
        return -1.0, (0, 0)          # flat template matches anything
    views = np.lib.stride_tricks.sliding_window_view(window, (th, tw))
    v = views - views.mean(axis=(2, 3), keepdims=True)
    denom = np.sqrt((v * v).sum(axis=(2, 3))) * tn
    with np.errstate(invalid="ignore", divide="ignore"):
        scores = np.where(denom > 1e-6,
                          (v * t).sum(axis=(2, 3)) / denom, -1.0)
    idx = np.unravel_index(np.argmax(scores), scores.shape)
    return float(scores[idx]), (int(idx[1]), int(idx[0]))


def crop_frame(path, roi, out_path, scale=1):
    """Write the ROI of a full-res frame to out_path and return the crop
    rect (cx0, cy0, cw, ch) in full-frame Vision space — the exact rect
    remap_box() needs — or None when the frame can't be read whole (torn
    mid-rewrite) or the crop would be degenerate. None means "OCR the full
    frame", never "skip OCR".

    PNG, not JPEG: the frame is already one lossy generation old, and a
    second pass softens exactly the small glyphs the crop exists to read.
    compress_level=1 keeps the encode a few ms. The returned rect is
    re-normalized from the PIXEL rect, so remap stays exact under the
    int() rounding of the crop edges.

    `scale` enlarges what is written. Both recognizers work from a fixed
    internal resolution, and a 1080p capture spends its pixels on the game
    world — a Genshin dialogue row is ~33px tall — so handing them a bigger
    image is the cheapest accuracy lever there is: no new engine, no new
    dependency, one resize. It costs nothing in remapping, because the
    daemon normalizes to the image it was handed and the returned rect
    describes the CROP, not its pixels. Lanczos rather than bicubic:
    stroke edges are what separates an "l" from an "I", and bicubic softens
    them. Measured by tools/ocr_bench.py."""
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if not (len(data) > 1024 and data[:2] == b"\xff\xd8"
            and data[-2:] == b"\xff\xd9"):
        return None
    try:
        img = Image.open(io.BytesIO(data))
        W, H = img.size
        x0, y0, x1, y1 = _to_px(roi, W, H)
        if x1 - x0 < 8 or y1 - y0 < 8:
            return None
        crop = img.crop((x0, y0, x1, y1))
        if scale != 1:
            crop = crop.resize((crop.width * scale, crop.height * scale),
                               Image.Resampling.LANCZOS)
        crop.save(out_path, format="PNG", compress_level=1)
    except Exception:
        return None
    return (x0 / W, (H - y1) / H, (x1 - x0) / W, (y1 - y0) / H)


def remap_box(block, crop):
    """A daemon box normalized to a CROP → full-frame normalized.
    `crop` is (cx0, cy0, cw, ch) in full-frame Vision space. The daemons
    normalize to whatever image they are handed, so every box that came
    from a cropped frame must pass through here before classify() sees
    it. Pinned by tools/test_anchors.py."""
    cx0, cy0, cw, ch = crop
    out = dict(block)
    out["x"] = cx0 + block["x"] * cw
    out["y"] = cy0 + block["y"] * ch
    out["w"] = block["w"] * cw
    out["h"] = block["h"] * ch
    return out


class Anchor:
    def __init__(self, name, template, search, threshold, ref, roi=None):
        self.name = name
        self.template = template          # float32 gray, half-scale px
        self.search = search              # Vision-normalized region
        self.threshold = float(threshold)
        self.ref = tuple(ref)             # (W, H) the template was cut at
        self.roi = roi                    # screen kind's OCR band union, or None
        self.scale_warned = False

    def match(self, gray):
        """(score, matched) against a half-scale gray frame. A frame at a
        different decode size than the template's reference stands down
        (score -1) instead of matching at the wrong scale."""
        H, W = gray.shape
        if (W, H) != self.ref:
            return -1.0, False
        x0, y0, x1, y1 = _to_px(self.search, W, H)
        score, _ = _ncc(gray[y0:y1, x0:x1], self.template)
        return score, score >= self.threshold


# Trusted frames a bootstrap candidate is held for before it is cut, and
# the cut is then verified against a LATER trusted frame — two chances for
# a fade or blur to be caught before anything is committed.
BOOT_HOLD = 3


class AnchorPack:
    """Every anchor for one game, or an empty pack if none are defined —
    a game without anchor data must behave exactly as before.

    `user_dir` is where self-calibrated templates live (and are looked
    for): a spec entry whose template exists in neither the repo dir nor
    there becomes `pending` if it carries a `cut` rect, awaiting
    maybe_bootstrap()."""

    def __init__(self, game, user_dir=None):
        self.game = game
        self.user_dir = Path(user_dir) if user_dir else None
        self.anchors = []
        self.pending = []
        self._boot_run = 0
        self._candidate = None
        spec = ANCHOR_DIR / f"{game}.json"
        if not spec.exists():
            return
        for a in json.loads(spec.read_text()).get("anchors", []):
            # a broken entry (missing/corrupt PNG, malformed spec) drops
            # that one anchor, never the app: this runs inside the main
            # loop on first use, where an uncaught error would kill it
            try:
                tmpl, ref = self._load_template(a)
                if tmpl is not None:
                    self.anchors.append(Anchor(a["name"], tmpl, a["search"],
                                               a["threshold"], ref,
                                               a.get("roi")))
                elif a.get("cut"):
                    self.pending.append(a)
                else:
                    print(f"[anchors] {game}/{a['name']}: no template and "
                          f"no cut rect — skipped", flush=True)
            except Exception as e:
                print(f"[anchors] {game}/{a.get('name', '?')} unloadable "
                      f"({e}) — skipped", flush=True)

    def _load_template(self, a):
        """(template, ref) from the repo dir, else the user dir (whose
        sidecar carries the decode size IT was cut at), else (None, None)."""
        png = ANCHOR_DIR / a["template"]
        if png.exists():
            return (np.asarray(Image.open(png).convert("L"),
                               dtype=np.float32), tuple(a["ref"]))
        if self.user_dir:
            up = self.user_dir / a["template"]
            meta = up.with_suffix(".json")
            if up.exists() and meta.exists():
                ref = tuple(json.loads(meta.read_text())["ref"])
                return (np.asarray(Image.open(up).convert("L"),
                                   dtype=np.float32), ref)
        return None, None

    def maybe_bootstrap(self, gray, trusted):
        """Cut pending templates from the user's own capture.

        Call on fresh-OCR frames with `trusted` = the classifier trusted
        this game's dialogue chrome on the frame's OCR text. After
        BOOT_HOLD consecutive trusted frames the templates are cut; on the
        NEXT trusted frame each cut is verified at the spec's threshold —
        chrome is pixel-identical frame to frame, so anything below it
        means the cut caught a fade or blur, and the candidate is thrown
        away to try again. Returns a log line when templates are
        committed, else None. Never raises: anchors gate cost, not speech.
        """
        if not self.pending or gray is None:
            return None
        if not trusted:
            self._boot_run = 0
            self._candidate = None
            return None
        self._boot_run += 1
        H, W = gray.shape
        try:
            if self._candidate is None:
                if self._boot_run < BOOT_HOLD:
                    return None
                cand = []
                for a in self.pending:
                    x0, y0, x1, y1 = _to_px(
                        {"x": tuple(a["cut"]["x"]),
                         "y": tuple(a["cut"]["y"])}, W, H)
                    t = gray[y0:y1, x0:x1].copy()
                    # a flat cut can never carry an NCC match (and a fade
                    # is flat): don't even hold it
                    if t.size == 0 or t.std() < 5.0:
                        return None
                    cand.append((a, t))
                self._candidate = (cand, (W, H))
                return None
            cand, ref = self._candidate
            if (W, H) != ref:
                self._candidate, self._boot_run = None, 0
                return None
            staged = []
            for a, t in cand:
                anchor = Anchor(a["name"], t, a["search"], a["threshold"],
                                ref, a.get("roi"))
                score, ok = anchor.match(gray)
                if not ok:
                    self._candidate, self._boot_run = None, 0
                    return None
                staged.append((a, t, anchor, score))
            for a, t, anchor, score in staged:
                if self.user_dir:
                    up = self.user_dir / a["template"]
                    up.parent.mkdir(parents=True, exist_ok=True)
                    Image.fromarray(t.astype(np.uint8)).save(up)
                    up.with_suffix(".json").write_text(
                        json.dumps({"ref": list(ref)}) + "\n")
                self.anchors.append(anchor)
            self.pending = []
            names = "  ".join(f"{s[0]['name']}={s[3]:.2f}" for s in staged)
            self._candidate = None
            return f"self-calibrated from this capture: {names}"
        except Exception as e:
            # malformed cut rect, unwritable user dir — stand down for the
            # session rather than retrying a failure every frame
            self.pending = []
            self._candidate = None
            return f"self-calibration failed ({e}) — anchors off this session"

    def match(self, gray):
        """{name: score} for matched anchors only. `gray` from
        decode_half(); None (torn frame) matches nothing."""
        if gray is None:
            return {}
        out = {}
        for a in self.anchors:
            score, ok = a.match(gray)
            if ok:
                out[a.name] = score
        return out

    def roi_for(self, names):
        """Union ROI the matched anchor set implies, or None. Presence is
        strong evidence, so every matched anchor with an ROI votes and the
        union keeps each voter's bands visible; an anchor without an ROI
        (or an empty match set) implies nothing and the frame stays whole."""
        rois = [a.roi for a in self.anchors if a.name in names and a.roi]
        if not rois:
            return None
        return {"x": (min(r["x"][0] for r in rois),
                      max(r["x"][1] for r in rois)),
                "y": (min(r["y"][0] for r in rois),
                      max(r["y"][1] for r in rois))}


# ---------------------------------------------------------------------
# CLI: template extraction and offline matching
# ---------------------------------------------------------------------

def _extract(game, name, frame, nx0, nx1, ny0, ny1):
    gray = decode_half(frame)
    if gray is None:
        sys.exit(f"can't decode {frame}")
    H, W = gray.shape
    x0, y0, x1, y1 = _to_px({"x": (nx0, nx1), "y": (ny0, ny1)}, W, H)
    tmpl = gray[y0:y1, x0:x1]
    out = ANCHOR_DIR / game
    out.mkdir(parents=True, exist_ok=True)
    png = out / f"{name}.png"
    Image.fromarray(tmpl.astype(np.uint8)).save(png)
    # search region: the extraction region padded by the template's own
    # size, so chrome that shifts a few px between sessions stays inside
    pw, ph = (nx1 - nx0) * SEARCH_PAD, (ny1 - ny0) * SEARCH_PAD
    search = {"x": [round(max(0.0, nx0 - pw), 4),
                    round(min(1.0, nx1 + pw), 4)],
              "y": [round(max(0.0, ny0 - ph), 4),
                    round(min(1.0, ny1 + ph), 4)]}
    spec_path = ANCHOR_DIR / f"{game}.json"
    spec = (json.loads(spec_path.read_text()) if spec_path.exists()
            else {"anchors": []})
    spec["anchors"] = [a for a in spec["anchors"] if a["name"] != name]
    spec["anchors"].append({"name": name, "template": f"{game}/{name}.png",
                            # the cut rect ships so OTHER installs can
                            # self-calibrate the template from their own
                            # capture — the PNG itself never ships
                            "cut": {"x": [round(nx0, 4), round(nx1, 4)],
                                    "y": [round(ny0, 4), round(ny1, 4)]},
                            "search": search,
                            "threshold": 0.75,     # placeholder — measure!
                            "ref": [W, H]})
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"{png} {tmpl.shape[1]}x{tmpl.shape[0]}px search={search}"
          f" — threshold is a PLACEHOLDER; measure score distributions"
          f" (tools/anchors.py match) before trusting it")


def _match_cli(game, frames):
    pack = AnchorPack(game)
    if not pack.anchors:
        sys.exit(f"no anchor pack for {game}")
    for f in frames:
        gray = decode_half(f)
        if gray is None:
            print(f"{f}: torn/undecodable")
            continue
        scores = {a.name: a.match(gray)[0] for a in pack.anchors}
        print(f"{f}: " + "  ".join(f"{n}={s:.3f}" for n, s in scores.items()))


if __name__ == "__main__":
    if len(sys.argv) >= 9 and sys.argv[1] == "extract":
        _extract(sys.argv[2], sys.argv[3], sys.argv[4],
                 *map(float, sys.argv[5:9]))
    elif len(sys.argv) >= 4 and sys.argv[1] == "match":
        _match_cli(sys.argv[2], sys.argv[3:])
    else:
        sys.exit(__doc__)
