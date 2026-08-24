"""Pins the comms-message detector (Snezhnaya 6.x, "Eye of Graeae").

A comms message floats over the live HUD with no story chrome at all, so
the geometry is the trust signal: one plate-shaped block anchored to the
left edge of the dialogue rows below it, nothing else in the plate band.
The frame is shot #127 (2026-08-12) verbatim — the stylized sender font
reads at conf 0.5 and misreads "Graeae" as "Gnaeae"; the plate slot takes
the weak read (PLATE_MIN_CONF) and the caster's fuzzy speaker match owns
the misspelling. Run directly or under pytest:

    python tools/test_genshin_comms.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profiles import get_profile                # noqa: E402

GENSHIN = get_profile("genshin")

# Shot #127's geometry, verbatim (Vision coordinates, origin bottom-left):
# the comms plate and line, plus the open-world HUD that surrounds a comms
# message — quest tracker, world nameplate, party list, HP readout, chat
# tab. HUD strings here are functional UI text; the system-notice line is
# the game's stock template shape, not story prose.
COMMS_FRAME = [
    {"text": "Go to the elevator", "confidence": 1,
     "x": 0.0669, "y": 0.7545, "w": 0.1003, "h": 0.0207},
    {"text": "Chat", "confidence": 1,
     "x": 0.0698, "y": 0.0543, "w": 0.0218, "h": 0.0129},
    {"text": "Adventure", "confidence": 1,
     "x": 0.4738, "y": 0.9533, "w": 0.0524, "h": 0.0185},
    {"text": "Rank", "confidence": 1,
     "x": 0.4855, "y": 0.9302, "w": 0.0276, "h": 0.0181},
    {"text": "59", "confidence": 1,
     "x": 0.4869, "y": 0.8941, "w": 0.0262, "h": 0.0336},
    {"text": "Laktionoy", "confidence": 0.5,
     "x": 0.2224, "y": 0.6408, "w": 0.0610, "h": 0.0258},
    {"text": "Eye of Gnaeae", "confidence": 0.5,
     "x": 0.3605, "y": 0.2016, "w": 0.0814, "h": 0.0234},
    {"text": "A fresh dispatch from the Eye of Graeae awaits....",
     "confidence": 1,
     "x": 0.3372, "y": 0.1546, "w": 0.3256, "h": 0.0288},
    {"text": "768 / 41195", "confidence": 1,
     "x": 0.4840, "y": 0.0775, "w": 0.0422, "h": 0.0132},
    {"text": "Columbina v", "confidence": 1,
     "x": 0.8270, "y": 0.6278, "w": 0.0552, "h": 0.0157},
    {"text": "Nicole", "confidence": 1,
     "x": 0.8532, "y": 0.5633, "w": 0.0349, "h": 0.0155},
    {"text": "Furina", "confidence": 1,
     "x": 0.8532, "y": 0.4884, "w": 0.0349, "h": 0.0207},
    {"text": "UD: 100000000", "confidence": 1,
     "x": 0.8750, "y": 0.0052, "w": 0.0959, "h": 0.0208},
]

WANT = ("Eye of Gnaeae",
        "A fresh dispatch from the Eye of Graeae awaits....")


def shift(frame, dx):
    """The comms plate moved horizontally by dx, everything else as-is."""
    out = []
    for b in frame:
        b = dict(b)
        if b["text"] == "Eye of Gnaeae":
            b["x"] += dx
        out.append(b)
    return out


# A shop board fills the plate band with more than one block — distilled
# from shot #120 (same session): two item labels in the band, item text
# below them, menu hints bottom-right.
BOARD_FRAME = [
    {"text": "Ethereal", "confidence": 1,
     "x": 0.3920, "y": 0.2060, "w": 0.0500, "h": 0.0200},
    {"text": "Saurian-Crowned", "confidence": 1,
     "x": 0.8050, "y": 0.2070, "w": 0.0900, "h": 0.0200},
    {"text": "Crystalscale Stone", "confidence": 1,
     "x": 0.3570, "y": 0.1640, "w": 0.1000, "h": 0.0200},
    {"text": "Confirm", "confidence": 1,
     "x": 0.8150, "y": 0.0650, "w": 0.0480, "h": 0.0180},
    {"text": "Leave", "confidence": 1,
     "x": 0.9030, "y": 0.0670, "w": 0.0350, "h": 0.0180},
    {"text": "UID: 100000000", "confidence": 1,
     "x": 0.8750, "y": 0.0050, "w": 0.0959, "h": 0.0208},
]

# A comms message that expects an answer floats the player's reply option
# to the right of the line, and the bubble's lower row lands inside the
# plate band — where the nothing-else-in-the-band rule read it as a board
# label and vetoed the sender. Shot #1343 (2026-08-23) verbatim: the frame
# the "Compassion is something to be respected" line went unread on.
REPLY_FRAME = [
    {"text": "They've been carrying out this", "confidence": 0.9986,
     "x": 0.6885, "y": 0.2722, "w": 0.1786, "h": 0.0306},
    {"text": "\"ritual\" again and again.", "confidence": 0.9901,
     "x": 0.6859, "y": 0.2444, "w": 0.1417, "h": 0.0370},
    {"text": "Eye of Graeae", "confidence": 0.9721,
     "x": 0.3068, "y": 0.2167, "w": 0.0865, "h": 0.0296},
    {"text": "Compassion is something to be respected, Miss Paimon.",
     "confidence": 0.9971,
     "x": 0.3063, "y": 0.1676, "w": 0.3859, "h": 0.0315},
    {"text": "UID: 603275577", "confidence": 0.9941,
     "x": 0.8745, "y": 0.0028, "w": 0.0953, "h": 0.0259},
]

REPLY_WANT = ("Eye of Graeae",
              "Compassion is something to be respected, Miss Paimon.")


CASES = [
    ("comms message detected", COMMS_FRAME, WANT),
    ("reply bubble does not veto the sender", REPLY_FRAME, REPLY_WANT),
    # a CENTERED plate is ordinary dialogue: find_plate's territory, and
    # the no-chrome gate must keep judging it
    ("centered plate is not comms", shift(COMMS_FRAME, 0.10), None),
    # anchored nowhere near the line's left edge — a stray world label
    ("unanchored plate is not comms", shift(COMMS_FRAME, -0.08), None),
    ("shop board is not comms", BOARD_FRAME, None),
    ("empty frame", [], None),
]


def main():
    bad = 0
    for label, frame, want in CASES:
        got = GENSHIN.classify_comms(frame)
        got = tuple(got) if got else None
        if got != want:
            print(f"FAIL {label}: want {want!r}, got {got!r}")
            bad += 1
    print(f"{len(CASES) - bad}/{len(CASES)} ok")
    return 1 if bad else 0


def test_genshin_comms():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
