"""Pins the RapidOCR 2-D gray-input trial (tools/ocrd_win.py).

The flattened frame is one gray plane stacked into RGB purely because
that shape is known-good; whether an engine reads the bare 2-D array
identically varies by machine and rapidocr version, so _detect proves it
per session: three texty frames must match byte-for-byte before the
stack copy is dropped, any difference or error locks the stack in, and
the caller is always handed the stacked result while undecided. What is
pinned here is that DECISION logic, with a stubbed engine — the real
engine only exists on Windows, and the trial is exactly the mechanism
that keeps machine-to-machine variation from ever changing what the
caller sees. Run directly or under pytest:

    python tools/test_gray_input.py
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ocrd_win import RapidEngine                # noqa: E402

BOX = [[0, 0], [10, 0], [10, 10], [0, 10]]
FLAT = np.zeros((540, 960), dtype=np.uint8)


def engine(ocr):
    e = RapidEngine.__new__(RapidEngine)
    e.np, e.ocr, e.gray_ok, e.gray_trials = np, ocr, None, 0
    return e


def test_identical_results_drop_the_stack():
    calls = {"gray": 0, "rgb": 0}

    def ocr(img):
        calls["gray" if img.ndim == 2 else "rgb"] += 1
        return [(BOX, "hello", 0.9)], None

    e = engine(ocr)
    for _ in range(RapidEngine.GRAY_TRIALS):
        assert e._detect(FLAT) == [(BOX, "hello", 0.9)]
    assert e.gray_ok is True and e.gray_trials == RapidEngine.GRAY_TRIALS
    n_rgb = calls["rgb"]
    e._detect(FLAT)
    e._detect(FLAT)
    assert calls["rgb"] == n_rgb          # the stack copy is gone


def test_mismatch_locks_the_stack_in():
    def ocr(img):
        text = "hello" if img.ndim == 3 else "hallo"
        return [(BOX, text, 0.9)], None

    e = engine(ocr)
    # the caller sees the STACKED result even on the trial frame
    assert e._detect(FLAT) == [(BOX, "hello", 0.9)]
    assert e.gray_ok is False
    calls = {"gray": 0}

    def counting(img):
        if img.ndim == 2:
            calls["gray"] += 1
        return [(BOX, "hello", 0.9)], None

    e.ocr = counting
    e._detect(FLAT)
    assert calls["gray"] == 0             # never retried after lock-in


def test_gray_exception_locks_the_stack_in():
    def ocr(img):
        if img.ndim == 2:
            raise ValueError("no 2-D support")
        return [(BOX, "hello", 0.9)], None

    e = engine(ocr)
    assert e._detect(FLAT) == [(BOX, "hello", 0.9)]
    assert e.gray_ok is False


def test_empty_frames_spend_no_trial():
    e = engine(lambda img: (None, None))
    e._detect(FLAT)
    assert e.gray_ok is None and e.gray_trials == 0


def main():
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok {name}")
    print("all gray-input tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
