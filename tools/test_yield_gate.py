"""Pins the evidence bar for cutting our own playback short.

The mid-play yield exists so the game's voice never has ours talking over
it, and its failure mode is the opposite one: a line cut off mid-sentence
with nothing audible taking over. Both directions are checked here, at the
two priors — a speaker the game usually voices (weaker evidence is enough)
and one it never has (only sustained speech will do). Run directly or under
pytest:

    python tools/test_yield_gate.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live                                    # noqa: E402


def hits(probs, t0=1000.0):
    """Load the VAD history with one 32ms chunk per probability."""
    live.vad_history.clear()
    for i, p in enumerate(probs):
        live.vad_history.append((t0 + i * 0.032, p))
    return t0 - 1


# (label, probabilities heard since playback started, soft, firm, voiced?)
CASES = [
    # The incident: rec_20260808_161001, Paimon cut 0.8s into "Can you
    # please just start already!?" on three chunks peaking at 0.66, in a
    # session whose capture held no game speech at all.
    ("blip does not cut a never-voiced speaker",
     [0.02, 0.55, 0.66, 0.51, 0.10, 0.03], False, True, False),
    ("...but the same blip is evidence for anyone else",
     [0.02, 0.55, 0.66, 0.51, 0.10, 0.03], False, False, True),
    ("sustained speech cuts even a never-voiced speaker",
     [0.6, 0.7, 0.8, 0.75, 0.7, 0.65, 0.6], False, True, True),
    ("a decisive spike counts too (robot voices)",
     [0.02, 0.9, 0.05], False, True, True),
    # the soft prior is unchanged: a usually-voiced speaker stands down on
    # the faintest hint
    ("soft prior still yields on weak evidence",
     [0.14, 0.15, 0.13], True, False, True),
    ("silence is never evidence", [0.0, 0.01, 0.0], False, False, False),
]

# (voiced, spoken) -> does the never-voiced prior apply yet?
PRIORS = [
    ((0, 12), True),      # a dozen lines, the game voiced none of them
    ((0, 3), True),       # three is enough — a silent scene says so early
    ((0, 2), False),      # too few to call
    ((1, 30), False),     # it HAS voiced them once — not this prior
    ((0, 0), False),      # nothing known
]


def main():
    bad = 0
    for label, probs, soft, firm, want in CASES:
        since = hits(probs)
        got = live.is_voiced(since, soft=soft, firm=firm)
        if got != want:
            print(f"FAIL {label}: want voiced={want}, got {got}")
            bad += 1
    live.vad_history.clear()
    for (v, s), want in PRIORS:
        live.voiced_history["Test"] = [v, s]
        got = live.never_voiced("Test")
        if got != want:
            print(f"FAIL never_voiced({v} voiced, {s} spoken): "
                  f"want {want}, got {got}")
            bad += 1
    live.voiced_history.pop("Test", None)
    total = len(CASES) + len(PRIORS)
    print(f"{total - bad}/{total} ok")
    return 1 if bad else 0


def test_yield_gate():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
