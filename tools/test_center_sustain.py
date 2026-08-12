"""Pins center_burst's sustain measurement: a centre-panned transient is
not voiceover, however hard it spikes.

The failing case (2026-08-12, "I was a disappointment."): a
dialogue-advance click against quiet music measured mid+13.0 side+1.8 with
VAD peak 0.00 — decisive on the numbers — and silenced a streamed first
sentence from a speaker the game had never voiced. The click is over in a
few 32ms blocks; even a one-word VO line holds its rise for half a second.
sustain_s is the discriminator, and this pins both sides of the 0.35s
threshold with the smoothing overlap included. Run directly or under
pytest:

    python tools/test_center_sustain.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live                                    # noqa: E402


T0 = 1000.0        # line appearance; history is stamped relative to this


def fill(profile):
    """Rebuild energy_history: 9s of quiet baseline, then `profile` — a list
    of (duration_s, mid_dB) segments starting at the line's appearance.
    Side stays at baseline throughout (the click and VO are both
    centre-panned; side is not under test here)."""
    live.energy_history.clear()
    t = T0 - 9.0
    while t < T0:
        live.energy_history.append((t, -40.0, -40.0))
        t += 0.032
    for dur, mid in profile:
        end = t + dur
        while t < end:
            live.energy_history.append((t, mid, -40.0))
            t += 0.032
    return t


# (name, profile after line start, want_voiced_at_gate)
# ENERGY_MID_BURST is 7dB: a +13 segment is elevated, quiet is not.
CASES = [
    # the failing frame: 0.26s click, then silence while the gate waits
    ("advance click", [(0.26, -27.0), (1.8, -40.0)], False),
    # a one-word VO line — short, but it LASTS like speech
    ("one-word VO", [(0.65, -27.0), (1.4, -40.0)], True),
    # ordinary VO
    ("full VO line", [(1.8, -27.0), (0.3, -40.0)], True),
]


def main():
    bad = 0
    for name, profile, want in CASES:
        fill(profile)
        mid_up, side_up, sustain = live.center_burst(T0)
        # every profile here is decisive on the numbers — the click too;
        # that is the point
        if not live.center_energy_voiced(mid_up, side_up, 0.0):
            print(f"FAIL {name}: profile no longer decisive "
                  f"(mid+{mid_up:.1f} side+{side_up:.1f})")
            bad += 1
            continue
        got = sustain >= live.ENERGY_SUSTAIN_S
        if got != want:
            print(f"FAIL {name}: sustain={sustain:.2f}s → voiced={got}, "
                  f"want {want}")
            bad += 1
    live.energy_history.clear()
    print(f"{len(CASES) - bad}/{len(CASES)} ok")
    return 1 if bad else 0


def test_center_sustain():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
