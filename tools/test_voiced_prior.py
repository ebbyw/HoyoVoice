"""Pins the per-speaker voiced prior — no hardware, no audio, <1s.

The prior decides two things: whether much weaker audio evidence is enough
to stay quiet for a speaker (soft), and whether cutting our own playback for
them needs sustained speech rather than a blip (firm). Both used to read a
speaker's whole recorded life, which cannot describe a character whose
voicing changes per quest — the failure this file exists to keep fixed.

    python tools/test_voiced_prior.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live                                                      # noqa: E402
from live import (PRIOR_WINDOW, SOFT_GATE_MIN_VOICED,            # noqa: E402
                  FIRM_GATE_MIN_SPOKEN, model_deaf, never_voiced,
                  record_voiced, seed_window, usually_voiced)

fails = []


def reset(builtin=False, **priors):
    """Clear the record and start from the named priors given.

    The built-in MODEL_DEAF list is switched off unless asked for: the
    record-driven half of this file is written about Paimon, who is on it.
    """
    live.voiced_history.clear()
    live.voiced_recent.clear()
    live.scene_vo.clear()
    off = {} if builtin else {name: "" for name in live.MODEL_DEAF}
    live.VOICES.setdefault("settings", {})["gate_prior"] = dict(off, **priors)


def feed(speaker, outcomes):
    for c in outcomes:
        record_voiced(speaker, c == "v")


def check(want, got, why):
    if want != got:
        fails.append(f"  want {want}, got {got} — {why}")


# --- the reported failure, line for line -----------------------------------
# Paimon: hundreds of unvoiced lines, then a quest that voices every one.
# The lifetime rule could never reach 0.75 again; the window does.
reset()
feed("Paimon", "s" * 300)
check(True, never_voiced("Paimon"), "300 unvoiced lines: firm gate armed")
check(False, usually_voiced("Paimon"), "...and nowhere near the soft gate")

feed("Paimon", "v")          # the quest starts voicing her
check(False, never_voiced("Paimon"), "one voiced line disarms the firm gate")
feed("Paimon", "vvvvv")      # six voiced in the window now
check(True, usually_voiced("Paimon"),
      "six of eight voiced: the soft gate is reachable again")

# and back: the quest ends, she is unvoiced again
feed("Paimon", "sss")
check(False, usually_voiced("Paimon"),
      "three unvoiced lines drop her below the ratio")
feed("Paimon", "sssss")
check(True, never_voiced("Paimon"),
      "a full window of unvoiced lines re-arms the firm gate")

# --- the window is a window ------------------------------------------------
reset()
feed("A", "v" * PRIOR_WINDOW)
check(True, usually_voiced("A"), "a full voiced window")
feed("A", "s" * PRIOR_WINDOW)
check(True, never_voiced("A"), "fully overwritten by unvoiced observations")
check([0, PRIOR_WINDOW], live.voiced_history["A"], "counts track the window")

# --- the thresholds still mean what they meant -----------------------------
reset()
feed("B", "v" * (SOFT_GATE_MIN_VOICED - 1))
check(False, usually_voiced("B"), "under the minimum, however clean the ratio")
feed("B", "v")
check(True, usually_voiced("B"), "at the minimum")

reset()
feed("C", "s" * (FIRM_GATE_MIN_SPOKEN - 1))
check(False, never_voiced("C"), "under the minimum spoken lines")
feed("C", "s")
check(True, never_voiced("C"), "at the minimum")

reset()
feed("D", "vvvvvvss")        # 6 of 8 = exactly 0.75
check(True, usually_voiced("D"), "exactly at the ratio")
reset()
feed("E", "vvvvvsss")        # 5 of 8 after the window rolls
check(False, usually_voiced("E"), "a hair under the ratio")

# --- an unknown speaker asserts nothing ------------------------------------
reset()
check(False, usually_voiced("nobody"), "no history: not usually voiced")
check(False, never_voiced("nobody"), "no history: not never-voiced either")

# --- legacy state seeds by the ratio it implies ----------------------------
reset()
seed_window("Paimon", 2, 400)          # the real shape of her old tally
check(True, never_voiced("Paimon"),
      "a long unvoiced record seeds an all-spoken window, firm gate armed")
reset()
seed_window("Sigewinne", 13, 1)        # reliably voiced, short history
check(True, usually_voiced("Sigewinne"),
      "a reliably voiced record keeps its soft gate across the upgrade")
reset()
seed_window("Fresh", 0, 0)
check(False, never_voiced("Fresh"), "an empty tally seeds an empty window")
check([0, 0], live.voiced_history["Fresh"], "...and empty counts")

# --- named priors: the record is not the only way in ------------------------
# The whole prior above is derived from the VAD's verdicts, so a character
# the VAD cannot hear can never earn one. Naming them supplies it.
reset(builtin=True)
feed("Sparxie", "s" * 300)             # 300 talk-overs, every one a mis-hear
check(True, model_deaf("Sparxie"), "the built-in list needs no record")
check(False, never_voiced("Sparxie"),
      "and a run of mis-hears must never arm the firm gate against her")
check(False, usually_voiced("Sparxie"),
      "model_deaf buys center-energy corroboration, not the soft gate")

reset(**{"Reporting Furb": "unvoiced"})
feed("Reporting Furb", "v" * PRIOR_WINDOW)
check(True, never_voiced("Reporting Furb"),
      "a declared prior outranks a full window pointing the other way")
check(False, usually_voiced("Reporting Furb"), "...in both directions")

reset(Furina="voiced")
check(True, usually_voiced("Furina"), "declared voiced from the first line")
check(False, never_voiced("Furina"), "and never firm")
feed("Furina", "s" * PRIOR_WINDOW)
check(True, usually_voiced("Furina"), "a talk-over does not erode it")

reset(Nobody="nonsense")
check(False, model_deaf("Nobody"), "an unrecognized value is not a prior")

reset(**{next(iter(live.MODEL_DEAF)): "unvoiced"})
check(True, never_voiced(next(iter(live.MODEL_DEAF))),
      "settings.gate_prior overrides the built-in list")

check(False, model_deaf(""), "no speaker, no prior")
check(False, model_deaf(None), "...and None is not a dict key lookup crash")

# --- "does this scene have voice acting in it" is scene-wide ---------------
reset()
check(False, live.scene_has_vo(), "a fresh scene has heard nothing")
feed("Anyone", "sssss")
check(False, live.scene_has_vo(), "lines we read aloud are not evidence of VO")
feed("Anyone", "v")
check(True, live.scene_has_vo(), "one voiced line anywhere is")
check(True, live.scene_has_vo(window=1e6), "and it is remembered")
check(False, live.scene_has_vo(window=0.0),
      "...but only for as long as the window")
reset()

reset()
if fails:
    print(f"FAIL ({len(fails)})")
    print("\n".join(fails))
    sys.exit(1)
print("voiced prior ok")
