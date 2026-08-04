"""Pixel change gate: skip OCR when the text region provably hasn't changed.

ffmpeg rewrites the frame file continuously, so mtime alone can't tell a
static dialogue from a new one — the loop was paying a full OCR call per
sampled frame (~154ms on DirectML) even while a line sat unchanged on
screen. The gate decodes the frame cheaply (JPEG draft mode, ~quarter
scale), crops to the padded union box of the PREVIOUS read's blocks, and
compares text pixels between consecutive frames: mean absolute difference
over pixels bright in EITHER frame. Game text is light-on-dark, so the
animated world behind a static line moves mostly dark pixels, while any
text change moves bright ones — including brand-new text, which is bright
in the current frame only and therefore lands in the mask.

Contract with the caller (live.py):
  * "unchanged" means the previous blocks must be REPLAYED through the
    normal pipeline, never skipped — stabilization counts reads, and a
    silent skip would stall candidate_count at the exact moment a line is
    trying to stabilize.
  * False ("changed") is the fail-safe verdict everywhere: torn frame,
    decode error, no previous baseline, moved text box, too few bright
    pixels. The cost of a false "changed" is one OCR call — yesterday's
    behavior. A false "unchanged" would swallow a new line, so it takes
    near-identical text pixels to earn one.

The padding leans RIGHT and DOWN: the typewriter grows text rightward and
wraps onto new rows below, and growth has to land inside the crop to be
seen. A whole new visual row makes the next OCR read expand the union box,
which changes the crop key and re-baselines the gate (costing one extra
OCR call per line change — negligible at 6 fps sampling).
"""
import io

import numpy as np
from PIL import Image

# normalized padding around the union box (top-left-origin space)
PAD_LEFT, PAD_RIGHT = 0.015, 0.08
PAD_TOP, PAD_BOTTOM = 0.015, 0.06
BRIGHT = 160          # a pixel this light is (potential) text, not backdrop
MIN_MASK = 40         # fewer bright pixels than this → nothing to compare
# JPEG draft decode at 1/2 (~960px wide). Measured on real HSR captures:
# a dialogue row keeps 139-232 pixels >= BRIGHT at 1/2 but only 2-8 at 1/4
# — the antialiased strokes blur into the backdrop — so 1/4 would leave
# the mask under MIN_MASK and disable the gate on exactly the frames it
# exists for. Decode at 1/2 is still a few ms.
DRAFT_SCALE = 2


class ChangeGate:
    def __init__(self, mad_threshold=6.0, enabled=True):
        self.mad = float(mad_threshold)
        self.enabled = bool(enabled)
        self.prev = None          # previous frame's crop (float array)
        self.key = None           # its crop rectangle — a move re-baselines
        self.skips = 0            # verdicts that saved an OCR call

    def reset(self):
        self.prev = self.key = None

    def _decode(self, data):
        """Complete-JPEG check + draft-mode grayscale decode, or None."""
        if not (len(data) > 1024 and data[:2] == b"\xff\xd8"
                and data[-2:] == b"\xff\xd9"):
            return None                        # torn mid-rewrite → let OCR retry
        img = Image.open(io.BytesIO(data))
        img.draft("L", (max(1, img.width // DRAFT_SCALE),
                        max(1, img.height // DRAFT_SCALE)))
        return np.asarray(img.convert("L"), dtype=np.float32)

    def unchanged(self, path, blocks):
        """True only when the text region matches the previous frame.

        `blocks` are the previous read's OCR blocks (normalized coords,
        bottom-left origin, the daemon convention). Always feeds its own
        baseline forward, so the comparison is strictly frame-to-frame.
        """
        if not (self.enabled and blocks):
            return False
        try:
            with open(path, "rb") as f:
                data = f.read()
            g = self._decode(data)
        except Exception:
            g = None
        if g is None:
            self.reset()          # can't trust a baseline we couldn't decode
            return False
        H, W = g.shape
        x0n = min(b["x"] for b in blocks) - PAD_LEFT
        x1n = max(b["x"] + b["w"] for b in blocks) + PAD_RIGHT
        # bottom-left origin → top-left: top edge is 1-(y+h)
        y0n = min(1.0 - b["y"] - b["h"] for b in blocks) - PAD_TOP
        y1n = max(1.0 - b["y"] for b in blocks) + PAD_BOTTOM
        x0, x1 = max(0, int(x0n * W)), min(W, int(x1n * W))
        y0, y1 = max(0, int(y0n * H)), min(H, int(y1n * H))
        key = (x0, y0, x1, y1)
        crop = g[y0:y1, x0:x1]
        prev, prev_key = self.prev, self.key
        self.prev, self.key = crop, key
        if prev is None or prev_key != key or crop.size == 0:
            return False
        mask = (prev >= BRIGHT) | (crop >= BRIGHT)
        n = int(mask.sum())
        if n < MIN_MASK:
            return False
        if float(np.abs(crop - prev)[mask].mean()) >= self.mad:
            return False
        self.skips += 1
        return True
