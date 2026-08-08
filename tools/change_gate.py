"""Pixel change gate: skip OCR when the text region provably hasn't changed.

ffmpeg rewrites the frame file continuously, so mtime alone can't tell a
static dialogue from a new one — the loop was paying a full OCR call per
sampled frame (~115ms on DirectML) even while a line sat unchanged on
screen. The gate decodes the frame cheaply (JPEG draft mode, half scale)
and compares the pixels under the PREVIOUS read's blocks between
consecutive frames.

Two decisions here are what make it safe, and both were learned the hard
way on a real Genshin session:

  * **Per block, not one union box.** The caller hands us every block on
    the frame, which includes HUD chrome top-left and — in Genshin — the
    UID that is on screen permanently, bottom-right. Their union is
    essentially the whole screen, so the comparison ended up judging the
    animated game world instead of the text.
  * **Count the pixels that moved; don't average them.** A mean absolute
    difference over a region is diluted by everything in that region that
    didn't change: on a daylit outdoor scene a few hundred new glyph
    pixels averaged out to ~0.06 against a threshold of 6.0, so the gate
    called a line "unchanged" while the typewriter was still typing it.
    The blocks then replayed stale, stabilization counted those replays
    as real sightings, and lines were spoken mid-word ("…friends with the
    great sh"). Counting bright pixels whose value moved is the same test
    at any region size and any scene brightness.

Contract with the caller (live.py):
  * "unchanged" means the previous blocks must be REPLAYED through the
    normal pipeline, never skipped — stabilization counts reads, and a
    silent skip would stall candidate_count at the exact moment a line is
    trying to stabilize.
  * False ("changed") is the fail-safe verdict everywhere: torn frame,
    decode error, no previous baseline, moved boxes, no box with enough
    text in it to judge. The cost of a false "changed" is one OCR call —
    yesterday's behavior. A false "unchanged" swallows part of a line, so
    it takes near-identical text pixels in every box to earn one.

The padding leans RIGHT and DOWN: the typewriter grows text rightward and
wraps onto new rows below, and growth has to land inside a crop to be
seen. A whole new visual row makes the next OCR read change the box set,
which re-baselines the gate (costing one extra OCR call per line change —
negligible at 6 fps sampling).
"""
import io

import numpy as np
from PIL import Image

# normalized padding around each block (top-left-origin space)
PAD_LEFT, PAD_RIGHT = 0.015, 0.08
PAD_TOP, PAD_BOTTOM = 0.015, 0.06
BRIGHT = 160          # a pixel this light is (potential) text, not backdrop
MIN_MASK = 40         # fewer bright pixels than this → box holds no text
# A bright pixel counts as "moved" at this much difference. JPEG ringing and
# antialiasing shimmer on a static glyph stay well under it; a glyph
# appearing or vanishing swings the full text-to-backdrop range (~200).
MOVED = 48
# How many bright pixels may move before the box is "changed". A single new
# glyph is ~20-60 bright pixels at half scale, and every bound here sits
# under one glyph: the fraction carries wide boxes, the floor covers narrow
# ones, and the CAP is what stops a box full of bright scenery (daylit sky
# behind the HUD) from buying itself an allowance bigger than the text
# change it is supposed to notice — the same dilution as averaging, one
# level up.
MOVED_FRAC = 0.01
MOVED_FLOOR = 6
MOVED_CAP = 20
# A padded box this large can't be telling us about text — something in the
# block list is wrong, so don't pretend to judge it.
MAX_BOX_FRAC = 0.35
# JPEG draft decode at 1/2 (~960px wide). Measured on real HSR captures:
# a dialogue row keeps 139-232 pixels >= BRIGHT at 1/2 but only 2-8 at 1/4
# — the antialiased strokes blur into the backdrop — so 1/4 would leave
# the mask under MIN_MASK and disable the gate on exactly the frames it
# exists for. Decode at 1/2 is still a few ms.
DRAFT_SCALE = 2


class ChangeGate:
    def __init__(self, enabled=True, moved_frac=MOVED_FRAC):
        self.frac = float(moved_frac)
        self.enabled = bool(enabled)
        self.prev = None          # previous frame's crops, one per block
        self.key = None           # their rectangles — a move re-baselines
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

    @staticmethod
    def _box(block, W, H):
        """Padded pixel rect for one block, or None if it can't be judged."""
        # bottom-left origin → top-left: top edge is 1-(y+h)
        x0 = max(0, int((block["x"] - PAD_LEFT) * W))
        x1 = min(W, int((block["x"] + block["w"] + PAD_RIGHT) * W))
        y0 = max(0, int((1.0 - block["y"] - block["h"] - PAD_TOP) * H))
        y1 = min(H, int((1.0 - block["y"] + PAD_BOTTOM) * H))
        if x1 <= x0 or y1 <= y0:
            return None
        if (x1 - x0) * (y1 - y0) > MAX_BOX_FRAC * W * H:
            return None
        return (x0, y0, x1, y1)

    def _box_verdict(self, prev, cur):
        """'same', 'differs', or 'empty' (no text in either frame)."""
        mask = (prev >= BRIGHT) | (cur >= BRIGHT)
        n = int(mask.sum())
        if n < MIN_MASK:
            # Nothing bright in EITHER frame: no text here now, none before.
            # Text arriving in this box would be bright in `cur` and so would
            # push n over the floor — this branch cannot hide a new line.
            return "empty"
        moved = int(((np.abs(cur - prev) >= MOVED) & mask).sum())
        allowance = max(MOVED_FLOOR, min(MOVED_CAP, self.frac * n))
        return "same" if moved <= allowance else "differs"

    def unchanged(self, path, blocks):
        """True only when the text under every block matches the last frame.

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
        # sorted + deduplicated so the box set is a stable identity across
        # frames: the daemon does not promise a stable block order
        boxes = sorted({b for b in (self._box(x, W, H) for x in blocks)
                        if b is not None})
        crops = [g[y0:y1, x0:x1] for (x0, y0, x1, y1) in boxes]
        prev_boxes, prev_crops = self.key, self.prev
        self.key, self.prev = boxes, crops
        if not boxes or prev_boxes != boxes:
            return False          # first frame, or the layout moved
        judged = 0
        for prev, cur in zip(prev_crops, crops):
            verdict = self._box_verdict(prev, cur)
            if verdict == "differs":
                return False
            judged += verdict == "same"
        if not judged:
            return False          # every box was empty — nothing was compared
        self.skips += 1
        return True
