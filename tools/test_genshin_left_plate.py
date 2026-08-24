"""Pins the left-anchored dialogue nameplate (Snezhnaya 6.x).

Ordinary boxed dialogue — Auto/Confirm chrome and all — but the whole box
is left-aligned: the nameplate at cx=0.223 with the rows under it sharing
its left edge. find_plate's centered band can't take a plate there and
comms owns cx 0.30-0.45, so the speaker was lost and the line read in the
narrator's voice (shots #32-#34, 2026-08-23 18:08 — shot #32 is embedded
verbatim). Run directly or under pytest:

    python tools/test_genshin_left_plate.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profiles import get_profile                # noqa: E402

GENSHIN = get_profile("genshin")

SHOT_32 = [
    {"text": "Eye of Graeae", "confidence": 0.9785,
     "x": 0.1797, "y": 0.2176, "w": 0.0865, "h": 0.0296},
    {"text": "I think.. Maybe we should gather at least some of the power that has been split up, and try", "confidence": 0.9856,
     "x": 0.1786, "y": 0.1657, "w": 0.6385, "h": 0.0352},
    {"text": "to make him as complete as possible. Then we ca", "confidence": 0.9829,
     "x": 0.1797, "y": 0.1380, "w": 0.3427, "h": 0.0315},
    {"text": "C", "confidence": 0.5762,
     "x": 0.1323, "y": 0.0556, "w": 0.0187, "h": 0.0204},
    {"text": "L.3", "confidence": 0.7000,
     "x": 0.1641, "y": 0.0481, "w": 0.0422, "h": 0.0315},
    {"text": "Auto", "confidence": 0.9996,
     "x": 0.8307, "y": 0.0537, "w": 0.0297, "h": 0.0259},
    {"text": "Confirm", "confidence": 0.9987,
     "x": 0.8979, "y": 0.0537, "w": 0.0479, "h": 0.0250},
    {"text": "UID:603275577", "confidence": 0.9627,
     "x": 0.8755, "y": 0.0028, "w": 0.0958, "h": 0.0231},
]


def moved(frame, dx):
    """The nameplate moved horizontally by dx, everything else as-is."""
    out = []
    for b in frame:
        b = dict(b)
        if b["text"] == "Eye of Graeae":
            b["x"] += dx
        out.append(b)
    return out


CASES = [
    ("left-anchored plate claims the line", SHOT_32, "Eye of Graeae"),
    # pushed into the comms band: not this layout's plate, and with story
    # chrome on screen the comms path never runs either — narrator
    ("comms-band plate is not a left plate", moved(SHOT_32, 0.15), None),
    # still inside the x-band (cx=0.293) but 0.071 right of the rows'
    # edge, past the 0.06 alignment ceiling: a stray world label
    ("unaligned plate is not a left plate", moved(SHOT_32, 0.07), None),
    ("no plate at all stays narrator",
     [b for b in SHOT_32 if b["text"] != "Eye of Graeae"], None),
]


def main():
    bad = 0
    for label, frame, want in CASES:
        got = GENSHIN.classify(frame)["speaker"]
        if got != want:
            print(f"FAIL {label}: want {want!r}, got {got!r}")
            bad += 1
    print(f"{len(CASES) - bad}/{len(CASES)} ok")
    return 1 if bad else 0


def test_genshin_left_plate():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
