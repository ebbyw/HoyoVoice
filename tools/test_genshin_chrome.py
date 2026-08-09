"""Pins the two things a Genshin frame draws that are NOT speech: the role
line under a nameplate, and a menu's button hints.

Both were read aloud. Blanche's title arrived from Vision in two pieces
("Shopkeeper," + "Mondstadt General Goods"), and a piece of a centered line
is not itself centered, so the per-box axis test cleared neither and the
title was spoken as the opening words of "Please have a look around." The
Convert screen has no such tell at all: its "Conversion Material" banner
sits in the plate band and the item grid under it reads as dialogue rows,
leaving only the bottom-right hints ("Item Details", "Convert", "Leave") to
say it is a menu. Run directly or under pytest:

    python tools/test_genshin_chrome.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profiles import get_profile                # noqa: E402

GENSHIN = get_profile("genshin")


def block(text, cx, cy, w=0.12, h=0.026, conf=1.0):
    """A block by CENTER, the way frames are measured off a screenshot."""
    return {"text": text, "confidence": conf,
            "x": cx - w / 2, "y": cy - h / 2, "w": w, "h": h}


# The Blanche frame, measured off the 1080p capture: nameplate at cy=0.229,
# role line 0.031 under it, first dialogue row 0.062 under it, Auto/Confirm
# in the hint strip.
CHROME = [block("Auto", 0.844, 0.067, w=0.03, h=0.018),
          block("Confirm", 0.910, 0.067, w=0.05, h=0.018),
          block("UID: 603275577", 0.900, 0.040, w=0.09, h=0.016)]
PLATE = block("Blanche", 0.500, 0.229, w=0.055, h=0.027)
LINE = block("Please have a look around.", 0.500, 0.167, w=0.20, h=0.031)

# (name, frame, expected speaker, expected dialogue)
FRAMES = [
    ("title read whole",
     [PLATE, block("Shopkeeper, Mondstadt General Goods", 0.498, 0.198,
                   w=0.19, h=0.019), LINE] + CHROME,
     "Blanche", "Please have a look around."),
    ("title split by Vision",
     [PLATE, block("Shopkeeper,", 0.430, 0.198, w=0.055, h=0.019),
      block("Mondstadt General Goods", 0.530, 0.198, w=0.125, h=0.019),
      LINE] + CHROME,
     "Blanche", "Please have a look around."),
    # no role line at all: the line under the plate is still the line
    ("plain nameplate", [PLATE, LINE] + CHROME,
     "Blanche", "Please have a look around."),
    # a two-row line: the row under the role line is NOT swallowed with it
    ("title above a two-row line",
     [PLATE, block("Shopkeeper,", 0.430, 0.198, w=0.055, h=0.019),
      block("Mondstadt General Goods", 0.530, 0.198, w=0.125, h=0.019),
      block("Hey there! We have quality goods", 0.500, 0.170, w=0.24),
      block("at honest prices!", 0.500, 0.140, w=0.14)] + CHROME,
     "Blanche", "Hey there! We have quality goods at honest prices!"),
    # The Convert screen: a banner in the plate band, an item grid under it,
    # and menu verbs where the story chrome would be.
    ("convert menu",
     [block("Conversion Material", 0.466, 0.273, w=0.096, h=0.020),
      block("Change", 0.898, 0.273, w=0.045, h=0.020),
      block("Shadow of…", 0.082, 0.180, w=0.055, h=0.018),
      block("Dragon Lo…", 0.145, 0.180, w=0.055, h=0.018),
      block("9/1", 0.551, 0.177, w=0.020, h=0.016),
      block("1/1", 0.610, 0.177, w=0.020, h=0.016),
      block("Item Details", 0.752, 0.079, w=0.065, h=0.018),
      block("Convert", 0.855, 0.079, w=0.045, h=0.018),
      block("Leave", 0.928, 0.079, w=0.035, h=0.018),
      block("UID: 603275577", 0.900, 0.040, w=0.09, h=0.016)],
     None, ""),
]


def main():
    bad = 0
    for name, blocks, speaker, dialogue in FRAMES:
        state = GENSHIN.classify(blocks)
        got = (state["speaker"], state["dialogue"])
        if got != (speaker, dialogue):
            print(f"FAIL {name}: want {(speaker, dialogue)}, got {got}")
            bad += 1
    # A menu must not be trusted as story either — that gate is what lets an
    # unknown speaker's line be read at all.
    for name, blocks, _, _ in FRAMES:
        want = name != "convert menu"
        if GENSHIN.trusts_dialogue(blocks) is not want:
            print(f"FAIL trust {name}: want {want}")
            bad += 1
    total = 2 * len(FRAMES)
    print(f"{total - bad}/{total} ok")
    return 1 if bad else 0


def test_genshin_chrome():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
