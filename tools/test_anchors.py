#!/usr/bin/env python3
"""Pin the anchor matcher's invariants (tools/anchors.py).

Synthetic frames, no hardware, no template files. What is pinned is
behaviour, not scores: the coordinate flip between Vision-normalized and
pixel space, the crop remap that classify() depends on never seeing
crop-normalized boxes, the stand-down on a frame at the wrong scale, and
the refusal to judge a torn JPEG. Each of those failing is silent in
production — a wrong flip just searches the wrong corner and reports
"no match" forever.
"""
import io
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from anchors import (Anchor, AnchorPack, _ncc, _to_px,  # noqa: E402
                     decode_half, remap_box)


def make_frame(W=960, H=540):
    """Noise frame with a distinctive glyph stamped bottom-right, in the
    pixel region Vision-normalized (0.90-0.94, 0.02-0.06) maps to."""
    rng = np.random.default_rng(7)
    frame = rng.integers(0, 80, (H, W)).astype(np.float32)
    glyph = np.zeros((22, 22), dtype=np.float32)
    glyph[3:19, 3:19] = 255.0
    glyph[8:14, 8:14] = 0.0          # a hollow square, not a blob
    x0, y0 = int(0.90 * W), int((1.0 - 0.06) * H)
    frame[y0:y0 + 22, x0:x0 + 22] = glyph
    return frame, glyph


def test_to_px_flips_y():
    # normalized y is measured UP from the bottom; a band at the BOTTOM of
    # the screen (y 0.0-0.1) must map to the LAST pixel rows
    x0, y0, x1, y1 = _to_px({"x": (0.0, 1.0), "y": (0.0, 0.1)}, 960, 540)
    assert y1 == 540 and y0 == int(0.9 * 540), (y0, y1)


def test_ncc_finds_planted_glyph():
    frame, glyph = make_frame()
    score, (dx, dy) = _ncc(frame[480:540, 850:960], glyph)
    assert score > 0.99, score
    # planted at x=864, y=507 → offsets inside the window slice
    assert (850 + dx, 480 + dy) == (int(0.90 * 960), int(0.94 * 540))
    # the same glyph is nowhere in a pure-noise region
    score2, _ = _ncc(frame[0:100, 0:200], glyph)
    assert score2 < 0.6, score2


def test_flat_template_matches_nothing():
    frame, _ = make_frame()
    flat = np.full((10, 10), 128.0, dtype=np.float32)
    score, _ = _ncc(frame[0:60, 0:60], flat)
    assert score == -1.0


def test_anchor_scale_standdown():
    frame, glyph = make_frame()
    a = Anchor("g", glyph, {"x": (0.88, 0.96), "y": (0.0, 0.10)},
               0.9, (960, 540))
    score, ok = a.match(frame)
    assert ok and score > 0.99, (score, ok)
    # same content at a different decode size: stand down, don't guess
    other = np.zeros((1080 // 2 + 6, 1920 // 2 + 8), dtype=np.float32)
    score, ok = a.match(other)
    assert not ok and score == -1.0


def test_remap_box_roundtrip():
    # a crop covering the bottom-left quarter: (0, 0, 0.5, 0.5) in
    # full-frame Vision space. A box in the middle of the crop lands in
    # the middle of that quarter, at half its crop-relative size.
    crop = (0.0, 0.0, 0.5, 0.5)
    box = {"text": "hi", "confidence": 1.0,
           "x": 0.4, "y": 0.2, "w": 0.2, "h": 0.1}
    out = remap_box(box, crop)
    assert abs(out["x"] - 0.2) < 1e-9 and abs(out["y"] - 0.1) < 1e-9
    assert abs(out["w"] - 0.1) < 1e-9 and abs(out["h"] - 0.05) < 1e-9
    assert out["text"] == "hi" and box["x"] == 0.4     # input untouched


def test_decode_half_rejects_torn_jpeg():
    frame, _ = make_frame()
    buf = io.BytesIO()
    Image.fromarray(frame.astype(np.uint8)).save(buf, format="JPEG",
                                                 quality=90)
    whole = buf.getvalue()
    assert decode_half(whole) is not None
    assert decode_half(whole[:-100]) is None       # truncated mid-rewrite
    assert decode_half(b"\x89PNG" + whole) is None  # not a JPEG at all


def test_pack_without_data_is_empty():
    pack = AnchorPack("no-such-game")
    assert pack.anchors == [] and pack.match(None) == {}


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
    print("all anchor tests passed")
