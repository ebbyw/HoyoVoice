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

import live                                                      # noqa: E402
from live import (center_burst_corroborated,                     # noqa: E402
                  center_energy_voiced, ENERGY_MID_BURST,
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
check(False, 1.5, 1.1, 0.00, "an unvoiced Freminet line — no burst")
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

# --- who the burst is allowed to speak for --------------------------------
# Passing the shape test above is half the decision; the other half is
# whether anything corroborates it. Energy alone never does — that is what
# kept the Snezhnaya train from silencing the scene — so a character the
# model cannot hear has to be named, because they can never earn a record.
live.voiced_history.clear()
live.voiced_recent.clear()
live.VOICES.setdefault("settings", {})["gate_prior"] = {}


def corroborated(want, speaker, peak, why):
    got = center_burst_corroborated(speaker, peak)
    if got != want:
        fails.append(f"  {speaker or 'unknown'} peak={peak}: "
                     f"want {want}, got {got} — {why}")


corroborated(False, "Wagner", 0.00, "a stranger and a silent burst: spoken")
corroborated(True, "Wagner", 0.15, "faint speechiness is corroboration")
corroborated(True, "Paimon", 0.00, "the built-in model-deaf list stands in "
                                   "for the record she cannot earn")
corroborated(True, "Sparxie", 0.00, "...and so does Sparxie's")

live.VOICES["settings"]["gate_prior"] = {"Wagner": "model_deaf",
                                         "Paimon": ""}
corroborated(True, "Wagner", 0.00, "settings.gate_prior adds a name")
corroborated(False, "Paimon", 0.00, "...and takes one off the built-in list")

# --- the relaxed cut, and the scene guard on it ----------------------------
# LIVE, rec_20260812_083939: the same sentence read four times over the
# game's own delivery of it. The app skipped the 9.8dB read as voiced and
# talked over the other three, which is what says 8.0 is inside this
# character's population rather than beside it.
live.VOICES["settings"]["gate_prior"] = {}
MAJESTIC = [(15.0, 7.9), (16.4, 10.0), (16.5, 9.8), (14.8, 5.0)]


def cut_check(want, speaker, why):
    got = live.decisive_cut(speaker)
    if got != want:
        fails.append(f"  decisive_cut({speaker!r}): want {want}, got {got}"
                     f" — {why}")


live.scene_vo.clear()
cut_check(ENERGY_DECISIVE_OVER_SIDE, "Paimon",
          "a scene with no voice acting heard in it keeps the strict cut")
for mid, side in MAJESTIC[:3]:
    check(False, mid, side, 0.00, f"...so mid+{mid} side+{side} stays spoken")

live.note_scene_vo()                    # somebody in this scene has a voice
cut_check(live.MODEL_DEAF_OVER_SIDE, "Paimon", "...and then it relaxes")
cut_check(ENERGY_DECISIVE_OVER_SIDE, "Wagner",
          "for the named speakers only, never scene-wide")
for mid, side in MAJESTIC:
    got = center_energy_voiced(mid, side, 0.00, live.decisive_cut("Paimon"))
    if not got:
        fails.append(f"  mid+{mid} side+{side}: the relaxed cut must take "
                     f"every read of the majestic line ({mid-side:.1f}dB)")
# and the strict cut still takes only the one the app itself took
for mid, side in MAJESTIC:
    want = mid - side >= ENERGY_DECISIVE_OVER_SIDE
    check(want, mid, side, 0.00,
          f"strict cut on {mid-side:.1f}dB — what the session actually did")

live.scene_vo.clear()
live.scene_vo.append(live.time.monotonic() - live.SCENE_VO_WINDOW - 1)
cut_check(ENERGY_DECISIVE_OVER_SIDE, "Paimon",
          "voice acting heard longer ago than the window does not license it")
live.scene_vo.clear()

if fails:
    print(f"FAIL ({len(fails)})")
    print("\n".join(fails))
    sys.exit(1)
print("center-energy rule ok")
