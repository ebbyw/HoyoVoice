"""Pins the ghost-duplicate filter on the boxes' real geometry.

Vision sometimes returns the same drawn text twice: the full reading, plus
a second box re-reading part of it. When the ghost lands on the same row
the old row-bucket filter caught it — but the ghost from
rec_20260812_083939 (shot #289) was a double-height re-read of row one
sitting BETWEEN the two real rows, so LINE_H quantization filed it in the
second row's bucket, where it overlapped nothing horizontally and sailed
into the middle of the assembled line: "…leave Paimon Wow, its so majestic
Just Flyin out of breath". The filter has to judge overlap where the boxes
actually are, not which bucket they round to. Run directly or under pytest:

    python tools/test_ghost_boxes.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profiles import get_profile                # noqa: E402

GENSHIN = get_profile("genshin")

# Shot #289 verbatim (Vision coordinates, origin bottom-left): the plate,
# row one split in two, the straddling ghost, row two, and the chrome.
GHOST_FRAME = [
    {"text": "Paimon", "confidence": 1,
     "x": 0.4709, "y": 0.2119, "w": 0.0567, "h": 0.0284},
    {"text": "Wow, it", "confidence": 1,
     "x": 0.1860, "y": 0.1676, "w": 0.0596, "h": 0.0288},
    {"text": "Wow, its so majestic Just Flyin", "confidence": 1,
     "x": 0.1833, "y": 0.1556, "w": 0.2292, "h": 0.0370},
    {"text": "s so majestic! Just flying from one side to the other would"
     " probably leave Paimon", "confidence": 1,
     "x": 0.2398, "y": 0.1654, "w": 0.5741, "h": 0.0310},
    {"text": "out of breath...", "confidence": 1,
     "x": 0.4448, "y": 0.1370, "w": 0.1090, "h": 0.0288},
    {"text": "AutO", "confidence": 1,
     "x": 0.8328, "y": 0.0594, "w": 0.0262, "h": 0.0155},
    {"text": "Confirm", "confidence": 1,
     "x": 0.8982, "y": 0.0562, "w": 0.0481, "h": 0.0219},
    {"text": "603275577", "confidence": 1,
     "x": 0.9026, "y": 0.0022, "w": 0.0684, "h": 0.0240},
]

WANT = ("Wow, it s so majestic! Just flying from one side to the other"
        " would probably leave Paimon out of breath...")

# The same frame without the ghost — the fix must not disturb a clean read,
# and in particular must keep row fragments that tile side by side.
CLEAN_FRAME = [b for b in GHOST_FRAME
               if not b["text"].startswith("Wow, its so majestic")]


def main():
    bad = 0
    for label, frame in (("ghost dropped", GHOST_FRAME),
                         ("clean frame untouched", CLEAN_FRAME)):
        state = GENSHIN.classify(frame)
        if state["speaker"] != "Paimon" or state["dialogue"] != WANT:
            print(f"FAIL {label}:\n  want {WANT!r}\n  got  "
                  f"[{state['speaker']}] {state['dialogue']!r}")
            bad += 1
    print(f"{2 - bad}/2 ok")
    return 1 if bad else 0


def test_ghost_boxes():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
