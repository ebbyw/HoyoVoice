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
                     crop_frame, decode_half, remap_box)


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
    assert pack.roi_for(()) is None


def test_bootstrap_cut_verify_persist():
    """The self-calibration lifecycle: a pending entry is held for
    BOOT_HOLD trusted frames, cut, verified against a LATER frame, and
    only then persisted (PNG + ref sidecar) and armed. An untrusted frame
    resets the hold; a verify miss throws the candidate away."""
    import json as _json
    import tempfile
    from anchors import BOOT_HOLD
    frame, _ = make_frame()
    user = Path(tempfile.mkdtemp())
    entry = {"name": "g", "template": "test/g.png",
             # the glyph planted by make_frame: x 0.90-0.94, y 0.02-0.06
             # (22px at 960x540 ≈ 0.0229 x 0.0407 — cut a hair inside)
             "cut": {"x": [0.901, 0.921], "y": [0.025, 0.058]},
             "search": {"x": [0.88, 0.96], "y": [0.0, 0.10]},
             "threshold": 0.75, "ref": [960, 540]}
    pack = AnchorPack("no-such-game", user_dir=user)
    pack.pending = [dict(entry)]

    # untrusted frames do nothing and reset the hold
    assert pack.maybe_bootstrap(frame, False) is None and pack.pending
    for _i in range(BOOT_HOLD - 1):
        assert pack.maybe_bootstrap(frame, True) is None
    assert pack.maybe_bootstrap(frame, False) is None    # reset
    # hold, cut (frame BOOT_HOLD), verify (the next one), commit
    for _i in range(BOOT_HOLD):
        assert pack.maybe_bootstrap(frame, True) is None
    msg = pack.maybe_bootstrap(frame, True)
    assert msg and "self-calibrated" in msg, msg
    assert not pack.pending and len(pack.anchors) == 1
    score, ok = pack.anchors[0].match(frame)
    assert ok and score > 0.98, score
    png, meta = user / "test/g.png", user / "test/g.json"
    assert png.exists() and _json.loads(meta.read_text())["ref"] == [960, 540]

    # a fresh pack finds the persisted template and has nothing pending
    pack2 = AnchorPack("no-such-game", user_dir=user)
    tmpl2, ref2 = pack2._load_template(entry)
    assert tmpl2 is not None and ref2 == (960, 540)

    # a flat cut (fade) is never even held
    pack3 = AnchorPack("no-such-game", user_dir=user)
    pack3.pending = [dict(entry, template="test/h.png")]
    black = np.zeros((540, 960), dtype=np.float32)
    for _i in range(BOOT_HOLD + 3):
        assert pack3.maybe_bootstrap(black, True) is None
    assert pack3.pending and pack3._candidate is None
    import shutil
    shutil.rmtree(user, ignore_errors=True)   # written PNGs + sidecars


def test_roi_for_union_and_absence():
    _, glyph = make_frame()
    pack = AnchorPack("no-such-game")
    pack.anchors = [
        Anchor("a", glyph, {"x": (0, 1), "y": (0, 1)}, 0.9, (960, 540),
               roi={"x": [0.0, 0.5], "y": [0.0, 0.62]}),
        Anchor("b", glyph, {"x": (0, 1), "y": (0, 1)}, 0.9, (960, 540),
               roi={"x": [0.4, 1.0], "y": [0.1, 0.7]}),
        Anchor("c", glyph, {"x": (0, 1), "y": (0, 1)}, 0.9, (960, 540)),
    ]
    # union keeps every matched voter's bands visible
    assert pack.roi_for(("a", "b")) == {"x": (0.0, 1.0), "y": (0.0, 0.7)}
    assert pack.roi_for(("a",)) == {"x": (0.0, 0.5), "y": (0.0, 0.62)}
    # an anchor without an ROI implies nothing — even when matched
    assert pack.roi_for(("c",)) is None
    assert pack.roi_for(()) is None


def test_crop_frame_rect_matches_remap():
    """The rect crop_frame returns must be the exact inverse of the
    daemon's crop-normalization: a feature at a known full-frame position,
    OCR'd inside the crop, must remap to that same position."""
    import tempfile
    W, H = 1920, 1080
    rng = np.random.default_rng(11)
    frame = rng.integers(0, 80, (H, W)).astype(np.uint8)
    d = Path(tempfile.mkdtemp())
    src, out = d / "frame.jpg", d / "crop.png"
    Image.fromarray(frame).save(src, format="JPEG", quality=90)
    roi = {"x": (0.0, 1.0), "y": (0.0, 0.62)}
    crop = crop_frame(src, roi, out)
    assert crop is not None
    cx0, cy0, cw, ch = crop
    # bottom 62% of the frame: crop rect sits on the bottom edge
    assert cx0 == 0.0 and cy0 == 0.0 and cw == 1.0
    assert abs(ch - 0.62) < 2.0 / H          # int() rounding, at most a px
    px_w, px_h = Image.open(out).size
    assert (px_w, px_h) == (W, H - int((1 - 0.62) * H))
    # a block filling the crop's top-left quarter, as the daemon would
    # normalize it to the CROP, remaps into the ROI's own top-left quarter
    b = remap_box({"text": "t", "confidence": 1.0,
                   "x": 0.0, "y": 0.5, "w": 0.5, "h": 0.5}, crop)
    assert b["x"] == cx0 and abs(b["y"] - (cy0 + 0.5 * ch)) < 1e-9
    assert abs(b["w"] - 0.5 * cw) < 1e-9 and abs(b["h"] - 0.5 * ch) < 1e-9
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def test_crop_frame_refuses_torn_and_degenerate():
    import tempfile
    W, H = 1920, 1080
    rng = np.random.default_rng(13)
    frame = rng.integers(0, 80, (H, W)).astype(np.uint8)
    d = Path(tempfile.mkdtemp())
    src, out = d / "frame.jpg", d / "crop.png"
    Image.fromarray(frame).save(src, format="JPEG", quality=90)
    torn = d / "torn.jpg"
    torn.write_bytes(src.read_bytes()[:-100])
    roi = {"x": (0.0, 1.0), "y": (0.0, 0.62)}
    assert crop_frame(torn, roi, out) is None       # torn → full-frame OCR
    assert crop_frame(d / "gone.jpg", roi, out) is None
    tiny = {"x": (0.5, 0.5005), "y": (0.0, 0.62)}   # degenerate width
    assert crop_frame(src, tiny, out) is None
    import shutil
    shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
    print("all anchor tests passed")
