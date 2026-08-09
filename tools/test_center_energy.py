"""Pins the centre-energy rule — no hardware, no audio, <1s.

The numbers here are real: every case marked LIVE is a (mid, side, gate)
triple lifted from a Windows session log, with the outcome the session
actually had. The invariant that matters is directional — this layer is the
last thing standing between a processed game voice and HoyoVoice talking
over it, and it fired ZERO times across thirteen sessions before the
decisive-burst path existed.

    python tools/test_center_energy.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live import (center_energy_voiced, ENERGY_MID_BURST,        # noqa: E402
                  ENERGY_MID_OVER_SIDE, ENERGY_SIDE_FLAT,
                  ENERGY_DECISIVE_OVER_SIDE)

fails = []


def check(want, mid, side, peak, why):
    got = center_energy_voiced(mid, side, peak)
    if got != want:
        fails.append(f"  mid+{mid} side+{side} peak={peak}: "
                     f"want {want}, got {got} — {why}")


# --- LIVE: lines HoyoVoice spoke over real voiceover, from session logs ---
# The repro. Paimon's processed squeak scores 0.00 to a speech model, and
# her side channel sits at 5.2dB — over the flat cap. 12.1dB of burst.
check(True, 17.3, 5.2, 0.00, "the repro line must now read as voiced")
check(True, 13.6, -0.1, 0.00, "Paimon, 13.7dB burst, silent to the VAD")
check(True, 19.3, 9.1, 0.00, "Citlali, 10.2dB burst over a loud side channel")
check(True, 15.0, 4.5, 0.00, "Wagner, 10.5dB burst")
check(True, 27.3, 16.0, 0.52, "Freminet — 11.3dB burst, side way over the cap")

# --- LIVE: lines we spoke that were genuinely unvoiced. These must stay
# spoken, or the fix trades a talk-over for a silence, which is worse.
check(False, 1.5, 1.1, 0.00, "Freminet 'Alright, it's a deal' — no burst")
check(False, 2.2, 2.5, 0.01, "the same Paimon line as replayed — flat")
check(False, 11.8, 6.6, 0.03, "5.2dB burst: real, but under the decisive cut "
                              "and over the flat cap — stays spoken")

# --- the boundaries themselves ---
d = ENERGY_DECISIVE_OVER_SIDE
check(True, 20.0, 20.0 - d, 0.00, "exactly at the decisive cut, no speechiness")
check(False, 20.0, 20.0 - d + 0.1, 0.00, "a hair under it, and the flat cap "
                                         "and floor apply again")
# below the decisive cut the old rule survives intact
check(True, 10.0, ENERGY_SIDE_FLAT, 0.15, "old rule: flat side, floor met")
check(False, 10.0, ENERGY_SIDE_FLAT, 0.14, "old rule: floor not met")
check(False, 10.0, ENERGY_SIDE_FLAT + 0.1, 0.99, "old rule: side not flat")

# --- a burst has to be a burst, however lopsided ---
check(False, ENERGY_MID_BURST - 0.1, -50.0, 0.99,
      "mid never rose: a quiet mid over a collapsing side is not a voice")
check(False, 30.0, 30.0 - ENERGY_MID_OVER_SIDE + 0.1, 0.99,
      "loud but wide — a music swell raises both channels")

# --- the layer must not fire on silence or on nonsense ---
check(False, 0.0, 0.0, 0.0, "nothing happening")
check(False, -5.0, -20.0, 0.99, "mid fell; 15dB 'over' side means nothing")

if fails:
    print(f"FAIL ({len(fails)})")
    print("\n".join(fails))
    sys.exit(1)
print("center-energy rule ok")
