"""Pins the OCR daemon request line and the region remap (hv_platform/base.py,
tools/ocrd_win.py).

A request is "<path>" or "<path>\\t<x> <y> <w> <h>" (Vision-normalized,
bottom-left origin). With a region the daemon reads only that part of the
frame and answers with boxes normalized to the WHOLE frame — the caller
never remaps. What is pinned here is that contract on the Python side: the
line builder, the parser's fail-safe (anything malformed reads the whole
frame), the pixel rect's y flip, and the RapidOCR engine building its boxes
in full-frame pixels from a region read — with a stubbed engine, since the
real one only exists on Windows. The Apple Vision daemon's remap was
measured by hand (tools/ocrd.swift). Run directly or under pytest:

    python tools/test_ocrd_protocol.py
"""
import io
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from hv_platform.base import request_line          # noqa: E402
import ocrd_win                                     # noqa: E402

ROI = {"x": (0.0, 1.0), "y": (0.0, 0.66)}


def test_request_line_roundtrips_through_parse():
    line = request_line("/a dir/with spaces/frame.jpg", ROI)
    assert line.endswith("\n") and line.count("\t") == 1
    path, roi = ocrd_win.parse_request(line)
    assert path == "/a dir/with spaces/frame.jpg"
    assert roi is not None and np.allclose(roi, (0.0, 0.0, 1.0, 0.66))
    path, roi = ocrd_win.parse_request(request_line("/plain.jpg"))
    assert (path, roi) == ("/plain.jpg", None)


def test_parse_request_fails_safe_to_whole_frame():
    # malformed, empty, and off-frame regions all read the whole frame;
    # an oversized one is clipped to it
    assert ocrd_win.parse_request("/x.jpg\tjunk\n") == ("/x.jpg", None)
    assert ocrd_win.parse_request("/x.jpg\t0 0 1\n") == ("/x.jpg", None)
    assert ocrd_win.parse_request("/x.jpg\t0 0 0 0.5\n") == ("/x.jpg", None)
    assert ocrd_win.parse_request("/x.jpg\t1.5 0 1 1\n") == ("/x.jpg", None)
    assert ocrd_win.parse_request("/x.jpg\t0.5 0.5 1 1\n") == (
        "/x.jpg", (0.5, 0.5, 0.5, 0.5))
    assert ocrd_win.parse_request("\n") == ("", None)
    # nan and inf parse as floats and would clip to a PARTIAL region —
    # min(1.0, x + nan) is 1.0 — which is not the whole frame
    for bad in ("nan 0 1 1", "0 0 nan 1", "0 0 1 inf", "-inf 0 1 1"):
        assert ocrd_win.parse_request(f"/x.jpg\t{bad}\n") == ("/x.jpg", None)


def test_px_roi_inverts_roi_px():
    # the remap must go through the rect that was CUT, which truncation
    # moved off the requested floats by up to a pixel per edge
    roi = (0.1234, 0.0567, 0.8, 0.66)
    box = ocrd_win.roi_px(roi, 1920, 1080)
    cut = ocrd_win.px_roi(box, 1920, 1080)
    assert ocrd_win.roi_px(cut, 1920, 1080) == box
    assert cut != roi and all(abs(a - b) < 1 / 1080 for a, b in zip(cut, roi))


def test_roi_px_flips_y_and_refuses_degenerate():
    # bottom 66% of a 1920x1080 frame is rows 367..1080 (top-left origin)
    assert ocrd_win.roi_px((0.0, 0.0, 1.0, 0.66), 1920, 1080) == (
        0, 367, 1920, 1080)
    assert ocrd_win.roi_px((0.9, 0.9, 0.001, 0.001), 1920, 1080) is None
    assert ocrd_win.roi_px(None, 1920, 1080) is None


def test_to_full_matches_remap_box():
    from anchors import remap_box
    block = {"text": "t", "confidence": 1.0,
             "x": 0.25, "y": 0.5, "w": 0.1, "h": 0.2}
    roi = (0.1, 0.0, 0.8, 0.66)
    assert ocrd_win.to_full(block, roi) == remap_box(block, roi)
    assert ocrd_win.to_full(block, None) is block


def _frame(tmp):
    img = Image.new("RGB", (1920, 1080), "black")
    path = Path(tmp) / "frame.jpg"
    img.save(path, quality=90)
    return path


def _engine(seen):
    """A RapidEngine whose engine records the array it was handed and
    answers one box at pixel (100, 50)-(300, 80) OF THAT ARRAY."""
    e = ocrd_win.RapidEngine.__new__(ocrd_win.RapidEngine)
    e.Image, e.np = Image, np
    e.gray_ok, e.gray_trials, e._cls_kw = True, 3, {"use_cls": False}
    e.mode, e.empty_run = "cpu", 0

    def ocr(img, **kw):
        seen.append(img.shape)
        return [([[100, 50], [300, 50], [300, 80], [100, 80]], "hi", 0.9)], None
    e.ocr = ocr
    return e


def test_rapid_region_read_reports_full_frame_boxes():
    seen = []
    with tempfile.TemporaryDirectory() as tmp:
        path = _frame(tmp)
        eng = _engine(seen)
        whole = eng.recognize(path)
        part = eng.recognize(path, (0.0, 0.0, 1.0, 0.66))
    # the engine saw the whole frame, then only the region's rows
    assert seen[0][:2] == (1080, 1920)
    assert seen[1][:2] == (1080 - 367, 1920)
    # same engine pixel box, but from the region it sits 367 rows lower
    # in the frame: x unchanged, y (bottom-left) shifted by the offset
    assert abs(whole[0]["x"] - 100 / 1920) < 1e-9
    assert abs(part[0]["x"] - 100 / 1920) < 1e-9
    assert abs(whole[0]["y"] - (1.0 - 80 / 1080)) < 1e-9
    assert abs(part[0]["y"] - (1.0 - (367 + 80) / 1080)) < 1e-9
    assert part[0]["w"] == whole[0]["w"] and part[0]["h"] == whole[0]["h"]


def test_unreadable_frame_is_none_not_empty():
    # a file that is not a complete image is a LOST frame (None → the
    # daemon answers null), never an empty region read ([])
    seen = []
    with tempfile.TemporaryDirectory() as tmp:
        torn = Path(tmp) / "torn.jpg"
        torn.write_bytes(_frame(tmp).read_bytes()[:-64])
        eng = _engine(seen)
        assert eng.recognize(torn) is None
        assert eng.recognize(torn, (0.0, 0.0, 1.0, 0.66)) is None
    assert seen == []                      # the engine never ran


def test_safety_net_region_pass_is_gray_stack():
    # the detector finds nothing on the flattened region → the safety net
    # reruns on the ORIGINAL pixels of the region, as a gray stack (the
    # crop file this replaced was a grayscale PNG); the whole-frame
    # safety net still gets the original bytes
    seen = []
    e = ocrd_win.RapidEngine.__new__(ocrd_win.RapidEngine)
    e.Image, e.np = Image, np
    e.gray_ok, e.gray_trials, e._cls_kw = True, 3, {"use_cls": False}
    e.mode, e.empty_run = "cpu", 0
    calls = {"n": 0}

    def ocr(img, **kw):
        calls["n"] += 1
        seen.append(img)
        return ([], None) if calls["n"] % 2 else (
            [([[0, 0], [10, 0], [10, 10], [0, 10]], "x", 0.9)], None)
    e.ocr = ocr
    with tempfile.TemporaryDirectory() as tmp:
        path = _frame(tmp)
        e.recognize(path, (0.0, 0.0, 1.0, 0.66))
        e.recognize(path)
    flat, raw, flat_whole, raw_whole = seen
    assert raw.shape == (1080 - 367, 1920, 3)
    assert np.array_equal(raw[..., 0], raw[..., 1])
    assert np.array_equal(raw[..., 1], raw[..., 2])
    assert isinstance(raw_whole, bytes)    # whole frame: bytes, as before


def test_windows_flatten_falls_back_whole():
    # the Windows engine's flatten failure hands back the ORIGINAL bytes
    # and says so, so the caller must not remap region-normalized boxes
    # that were in fact read from the whole frame
    saved = ocrd_win._flatten_background
    ocrd_win._flatten_background = lambda *a: (_ for _ in ()).throw(
        RuntimeError("boom"))
    try:
        out = ocrd_win.WindowsEngine._flattened_png(b"\xff\xd8data", (0, 0, 8, 8))
    finally:
        ocrd_win._flatten_background = saved
    assert out == (b"\xff\xd8data", False)
    out = ocrd_win.WindowsEngine._flattened_png(
        _png_bytes(), (0, 0, 8, 8))
    assert out[1] is True and out[0][:8] == b"\x89PNG\r\n\x1a\n"


def _png_bytes():
    buf = io.BytesIO()
    Image.new("L", (32, 32), 0).save(buf, format="PNG")
    return buf.getvalue()


class _FakeProc:
    """A daemon's pipes: what it answers to the probe, and what it saw."""
    def __init__(self, reply):
        self.stdin, self.stdout = io.StringIO(), io.StringIO(reply)


def test_probe_regions_tells_new_daemon_from_old(capsys=None):
    from hv_platform.base import probe_regions

    class D:
        regions = None
    d = D(); d.proc = _FakeProc('[{"protocol": 2}]\n')
    assert probe_regions(d) is True and d.regions is True
    assert d.proc.stdin.getvalue() == "\n"        # the probe is an empty line
    d.proc = _FakeProc("should not be read\n")
    assert probe_regions(d) is True                # cached: no second probe
    assert d.proc.stdin.getvalue() == ""
    old = D(); old.proc = _FakeProc("[]\n")         # a pre-region build
    assert probe_regions(old) is False and old.regions is False
    dead = D(); dead.proc = _FakeProc("")           # no answer: ask again later
    assert probe_regions(dead) is False and dead.regions is None


def test_flatten_crops_before_blur():
    # a region's pixels are the crop's own flattening (blur sees the
    # crop's edges), not a slice of the whole frame's — the old PNG-crop
    # path behaved that way and the gate thresholds were measured on it
    img = Image.new("L", (400, 200), 0)
    px = img.load()
    for x in range(400):
        px[x, 99] = 255            # a bright row right at the crop edge
    buf = io.BytesIO(); img.save(buf, format="PNG"); data = buf.getvalue()
    whole = ocrd_win._flatten_background(data)[100:, :]
    crop = ocrd_win._flatten_background(data, (0, 100, 400, 200))
    assert crop.shape == whole.shape == (100, 400)
    assert not np.array_equal(crop, whole)
    sliced = Image.open(io.BytesIO(data)).crop((0, 100, 400, 200))
    buf2 = io.BytesIO(); sliced.save(buf2, format="PNG")
    assert np.array_equal(crop, ocrd_win._flatten_background(buf2.getvalue()))


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
