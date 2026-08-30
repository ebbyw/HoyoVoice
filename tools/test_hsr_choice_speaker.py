"""Pins the Star Rail rule for when a choice prompt is real: a speaker
beside it, or the story chrome above it.

Menus kept landing one or two blocks in the choice band and reading them
aloud as Trailblazer: the Currency Wars team-setup tooltip (shot #132,
2026-08-24 — four wrapped rows at left edge 0.738-0.757), combat-screen
effect names, nav labels ("Data Bank", "Back"), and the Battle
Preparations enemy-team title (frames 268-272 of rec_20260726_121902).
Every genuine prompt in the same corpus kept its nameplate on the box
below the bubbles (frames 111, 482-490, 547-549), so the plate was the
first discriminator \u2014 until a cutscene handed the player a lone option
with no dialogue box under it to plate at all (shot #155, 2026-08-30),
which the plate rule dropped. '\u2715 Continue' bottom-right separates the
two: story screens draw it, menus draw Confirm / Back / Start Challenge.
Geometry here is measured off those frames; the words are invented,
except shot #155's, which is the reported line. Run directly or under
pytest:

    python tools/test_hsr_choice_speaker.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profiles import get_profile                # noqa: E402

HSR = get_profile("hsr")


def block(text, x, y, w=0.12, h=0.028, conf=1.0):
    """A block by its LEFT edge, the way the choice band measures them."""
    return {"text": text, "confidence": conf, "x": x, "y": y, "w": w, "h": h}


# A genuine prompt, measured off frame 482 of rec_20260726_121902: two
# option bubbles at left edge ~0.71, the speaker's plate still on the
# dialogue box below them (cx=0.50, cy=0.24), the line under it.
PROMPT = [
    block("Any sign of the missing cart?", 0.711, 0.395, w=0.156, h=0.029),
    block("Maybe it rolled away.", 0.711, 0.305, w=0.174, h=0.029),
    block("Cartwright", 0.443, 0.222, w=0.115, h=0.034),
    block("That hill has swallowed wheels before, you know.",
          0.276, 0.173, w=0.448, h=0.029),
    block("Continue", 0.927, 0.016, w=0.048, h=0.018),
]

# The team-setup tooltip, measured off shot #132 (2026-08-24): wrapped
# rows at left edge 0.738-0.757, Confirm/Back hints bottom-right, no
# plate anywhere near the plate band.
TOOLTIP = [
    block("Raises the morale of the crew.", 0.740, 0.366, w=0.184, h=0.021),
    block("When resting, hands a snack to", 0.738, 0.337, w=0.216, h=0.029),
    block("whoever is hungriest. Neighbors", 0.739, 0.314, w=0.203, h=0.024),
    block("also get a snack.", 0.739, 0.290, w=0.128, h=0.023),
    block("Suggested", 0.749, 0.241, w=0.069, h=0.021),
    block("Provisions", 0.757, 0.220, w=0.052, h=0.025),
    block("Confirm", 0.856, 0.010, w=0.049, h=0.029),
    block("Back", 0.935, 0.011, w=0.031, h=0.028),
]

# The enemy-team title on the battle-prep board (frame 268): one short
# block in the band, hints bottom-right, no plate.
BOARD = [
    block("Curious Onlookers", 0.712, 0.328, w=0.14, h=0.031),
    block("Start Challenge!", 0.458, 0.062, w=0.12, h=0.026),
    block("Back", 0.938, 0.016, w=0.031, h=0.018),
]

# The reported cutscene, verbatim from shot #155 (2026-08-30 12:23,
# Windows): one option bubble, the story chrome bottom-right, the UID
# strip bottom-left, and nothing else on screen \u2014 no dialogue box, so no
# plate to find.
CUTSCENE = [
    block("I will not back down.", 0.710, 0.285, w=0.141, h=0.028, conf=0.974),
    block("UID:603150536", 0.020, 0.015, w=0.065, h=0.020),
    block("Continue", 0.927, 0.010, w=0.051, h=0.028),
]

# (name, frame, expected speaker, expected choices)
FRAMES = [
    ("prompt with plate", PROMPT, "Cartwright",
     ["Any sign of the missing cart?", "Maybe it rolled away."]),
    ("menu tooltip", TOOLTIP, None, []),
    ("battle-prep board", BOARD, None, []),
    ("plateless cutscene prompt", CUTSCENE, None, ["I will not back down."]),
]


def main():
    failures = []
    for name, frame, want_speaker, want_choices in FRAMES:
        state = HSR.classify(frame)
        if state["speaker"] != want_speaker:
            failures.append(f"{name}: speaker {state['speaker']!r}, "
                            f"wanted {want_speaker!r}")
        if state["choices"] != want_choices:
            failures.append(f"{name}: choices {state['choices']!r}, "
                            f"wanted {want_choices!r}")
    for f in failures:
        print("FAIL", f)
    print(f"{len(FRAMES) - len(set(f.split(':')[0] for f in failures))}"
          f"/{len(FRAMES)} frames as pinned")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())


def test_hsr_choice_speaker():
    assert main() == 0
