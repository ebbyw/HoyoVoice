"""Pins the 📷 Screenshot button: one frame into the recordings folder.

The file must be the frame the OCR engine read, byte for byte — a
re-encode would make a classifier fix measured on it measure a different
input. Two presses inside one second must not overwrite each other, the
OCR blocks must ride along, and a press before the capture's first frame
lands must log a failure rather than raise on the loop thread. Run
directly or under pytest:

    python tools/test_screenshot.py
"""
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import live                                    # noqa: E402
import webui                                   # noqa: E402


def check(name, ok, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'}  {name}{'' if ok else '  ' + detail}")
    return 0 if ok else 1


def main():
    bad = 0
    saved_frame, saved_dir = live.FRAME, live.REC_DIR["path"]
    saved_blocks = live.latest_ocr["blocks"]
    with tempfile.TemporaryDirectory(prefix="hv_shot_") as tmp:
        tmp = Path(tmp)
        try:
            live.FRAME = tmp / "live_frame.jpg"
            live.REC_DIR["path"] = tmp / "out"
            live.events.clear()

            live.latest_ocr["blocks"] = None
            live.take_screenshot()
            bad += check("a press before the first frame logs a failure",
                         live.events and "FAILED" in live.events[-1]["action"],
                         str(list(live.events)[-1:]))

            frame = b"\xff\xd8 not really a jpeg \xff\xd9"
            live.FRAME.write_bytes(frame)
            live.latest_ocr["blocks"] = [{"text": "placeholder", "conf": 0.9}]
            live.take_screenshot()
            live.take_screenshot()
            shots = sorted((tmp / "out").glob("shot_*.jpg"))
            bad += check("two quick presses make two files", len(shots) == 2,
                         str(shots))
            bad += check("the frame is copied byte for byte",
                         all(p.read_bytes() == frame for p in shots))
            dump = json.loads(shots[0].with_suffix(".json").read_text(encoding="utf-8"))
            bad += check("the OCR blocks ride along",
                         dump["blocks"] == live.latest_ocr["blocks"]
                         and isinstance(dump["game"], str), str(dump))

            (tmp / "out" / "rec_20000101_000000.mp4").write_bytes(b"x")
            webui._REC_CACHE = (None, [])
            names = [r["name"] for r in webui._recordings(
                {"rec_dir": live.REC_DIR,
                 "recording": {"on": False, "raw": None}})]
            bad += check("screenshots are listed, json dumps are not",
                         len(names) == 3 and not any(n.endswith(".json")
                                                     for n in names), str(names))
            bad += check("the list is newest first across kinds",
                         names[-1].startswith("rec_"), str(names))
        finally:
            live.FRAME, live.REC_DIR["path"] = saved_frame, saved_dir
            live.latest_ocr["blocks"] = saved_blocks
    return bad


if __name__ == "__main__":
    raise SystemExit(main())
