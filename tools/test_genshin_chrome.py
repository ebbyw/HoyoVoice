"""Pins the two things a Genshin frame draws that are NOT speech: the role
line under a nameplate, and a menu's button hints.

Both were read aloud. A shopkeeper's title arrived from Vision in two
pieces ("Shopkeeper," + the store name), and a piece of a centered line
is not itself centered, so the per-box axis test cleared neither and the
title was spoken as the opening words of the dialogue under it. The
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
          block("UID: 100000000", 0.900, 0.040, w=0.09, h=0.016)]
PLATE = block("Blanche", 0.500, 0.229, w=0.055, h=0.027)
LINE = block("Please have a look around.", 0.500, 0.167, w=0.20, h=0.031)

# (name, frame, expected speaker, expected dialogue)
FRAMES = [
    ("title read whole",
     [PLATE, block("Shopkeeper, Harborside General Goods", 0.498, 0.198,
                   w=0.19, h=0.019), LINE] + CHROME,
     "Blanche", "Please have a look around."),
    ("title split by Vision",
     [PLATE, block("Shopkeeper,", 0.430, 0.198, w=0.055, h=0.019),
      block("Harborside General Goods", 0.530, 0.198, w=0.125, h=0.019),
      LINE] + CHROME,
     "Blanche", "Please have a look around."),
    # no role line at all: the line under the plate is still the line
    ("plain nameplate", [PLATE, LINE] + CHROME,
     "Blanche", "Please have a look around."),
    # a two-row line: the row under the role line is NOT swallowed with it
    ("title above a two-row line",
     [PLATE, block("Shopkeeper,", 0.430, 0.198, w=0.055, h=0.019),
      block("Harborside General Goods", 0.530, 0.198, w=0.125, h=0.019),
      block("Hey there! We have quality rope", 0.500, 0.170, w=0.24),
      block("at honest prices!", 0.500, 0.140, w=0.14)] + CHROME,
     "Blanche", "Hey there! We have quality rope at honest prices!"),
    # --- world dialogue: a companion talking while you walk ---------------
    # No box, no Auto/Confirm, full HUD on screen, and the nameplate drawn
    # LOWER than the boxed layout's. Measured off captures\shots\98.json
    # (and 100/101/102, which agree to 0.0005): plate cy=0.2097 h=0.0324,
    # line cy=0.1718 h=0.0306, level readout "Lv.90" at cy=0.0819.
    #
    # Under the old 0.21 plate floor the plate missed by 0.0003, the line
    # fell through to the plate-less band — which reaches to 0.21 and so
    # took the nameplate in as WORDS — and the whole thing was then dropped
    # as an unknown speaker, because there is no chrome here either.
    ("world dialogue (no box, no chrome)",
     [block("Paimon", 0.5003, 0.2097, w=0.0557, h=0.0324),
      block("These bobbing lil' buoys... They won't tip us over out of "
            "nowhere, will they?", 0.5008, 0.1718, w=0.4505, h=0.0306),
      block("Lv.90", 0.4198, 0.0819, w=0.025, h=0.0194),
      block("Chat", 0.0807, 0.0597, w=0.024, h=0.0231),
      block("UID: 100000000", 0.9221, 0.0153, w=0.0974, h=0.0269)],
     "Paimon", "These bobbing lil' buoys... They won't tip us over out of "
     "nowhere, will they?"),
    # The line sits 0.0370 below the plate's baseline against a
    # SUBTITLE_MAX_DROP of 0.0360, is centred on the plate to 0.0005, and on
    # this frame reads SHORTER than SUBTITLE_MAX_H — so all that kept it out
    # of the role-line test was a margin of 0.001. It is the plate's own
    # height that rules the test out now: role lines belong to the boxed
    # layout. Eaten, the line would vanish with no log at all, because
    # Genshin does not re-parse a plate that has nothing under it.
    ("a world-dialogue line is not a role subtitle",
     [block("Paimon", 0.5003, 0.2097, w=0.0557, h=0.0324),
      block("Where are we now..?", 0.5003, 0.1718, w=0.14, h=0.0300),
      block("UID: 100000000", 0.9221, 0.0153, w=0.0974, h=0.0269)],
     "Paimon", "Where are we now..?"),
    # The Convert screen: a banner in the plate band, an item grid under it,
    # and menu verbs where the story chrome would be.
    ("convert menu",
     [block("Conversion Material", 0.466, 0.273, w=0.096, h=0.020),
      block("Change", 0.898, 0.273, w=0.045, h=0.020),
      block("Shard of…", 0.082, 0.180, w=0.055, h=0.018),
      block("Driftwood…", 0.145, 0.180, w=0.055, h=0.018),
      block("9/1", 0.551, 0.177, w=0.020, h=0.016),
      block("1/1", 0.610, 0.177, w=0.020, h=0.016),
      block("Item Details", 0.752, 0.079, w=0.065, h=0.018),
      block("Convert", 0.855, 0.079, w=0.045, h=0.018),
      block("Leave", 0.928, 0.079, w=0.035, h=0.018),
      block("UID: 100000000", 0.900, 0.040, w=0.09, h=0.016)],
     None, ""),
]


# The chat-bubble glyph on a choice option fuses into the first OCR block
# and reads as a stray symbol — shot #35 (2026-08-12) said '® Feeling
# better now?' aloud ("registered sign feeling better now"); the shots
# corpus also holds '® Inspection?' and '# Goodbye.', so the misread
# varies and the strip must be by symbol class, not by literal glyph.
# Leading quotes, ellipses and parens are real option text and survive.
# Geometry is shot #35's: option at x=0.669 y=0.264 with a Paimon line
# under it.
CHOICE_ICON_CASES = [
    ("® Feeling better now?", "Feeling better now?"),
    ("# Goodbye.", "Goodbye."),
    ("...Is that so?", "...Is that so?"),
    ("(Say nothing)", "(Say nothing)"),
    ('"You\'re welcome."', '"You\'re welcome."'),
]


def choice_frame(option_text):
    return [
        block("Paimon", 0.5, 0.212, w=0.057, h=0.028),
        block("Looks like we get what we haul in, huh!",
              0.5, 0.155, w=0.45, h=0.033),
        {"text": option_text, "confidence": 1.0,
         "x": 0.669, "y": 0.25, "w": 0.15, "h": 0.028},
        block("• Auto", 0.836, 0.064, w=0.052, h=0.033),
        block("Confirm", 0.911, 0.062, w=0.054, h=0.025),
    ]


def main():
    bad = 0
    for raw, want in CHOICE_ICON_CASES:
        got = GENSHIN.classify(choice_frame(raw))["choices"]
        if got != [want]:
            print(f"FAIL choice icon {raw!r}: want [{want!r}], got {got}")
            bad += 1
    for name, blocks, speaker, dialogue in FRAMES:
        state = GENSHIN.classify(blocks)
        got = (state["speaker"], state["dialogue"])
        if got != (speaker, dialogue):
            print(f"FAIL {name}: want {(speaker, dialogue)}, got {got}")
            bad += 1
    # A menu must not be trusted as story either — that gate is what lets an
    # unknown speaker's line be read at all. World dialogue is NOT trusted
    # and must not be: it carries no story chrome, so the only thing that
    # can get it read is finding its nameplate and recognizing the
    # character. That is exactly what the frames above pin.
    UNTRUSTED = {"convert menu",
                 "world dialogue (no box, no chrome)",
                 "a world-dialogue line is not a role subtitle"}
    for name, blocks, _, _ in FRAMES:
        want = name not in UNTRUSTED
        if GENSHIN.trusts_dialogue(blocks) is not want:
            print(f"FAIL trust {name}: want {want}")
            bad += 1
    total = 2 * len(FRAMES) + len(CHOICE_ICON_CASES)
    print(f"{total - bad}/{total} ok")
    return 1 if bad else 0


def test_genshin_chrome():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
