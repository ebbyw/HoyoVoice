"""Pins BoundedVAD's one promise — no model, no audio, <1s.

Every probability it returns comes from a model that has heard between
PERIOD/2 and PERIOD chunks since its last reset: never minutes of history
(which deafened Silero to the Furbo voices in rec_20261112_145744) and,
after the first half-period, never a cold start. The Silero models are
replaced with stubs that answer with their own age in chunks, so the
invariant is checked directly rather than through audio.

    python tools/test_bounded_vad.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import vad                                                       # noqa: E402


class AgeStub:
    """Answers each chunk with how many chunks it has seen since reset."""

    def __init__(self, *a, **kw):
        self.age = 0

    def reset(self):
        self.age = 0

    def prob(self, chunk):
        self.age += 1
        return self.age


vad.SileroVAD = AgeStub
fails = []

for period in (250, 10, 7):
    half = period // 2
    v = vad.BoundedVAD("unused", period=period)
    ages = [v.prob(None) for _ in range(period * 20)]
    # the first half-period is the cold start the caller's warmup covers
    steady = ages[half:]
    lo, hi = min(steady), max(steady)
    if lo < half or hi > period:
        fails.append(f"  period={period}: answering model's history ran "
                     f"{lo}..{hi} chunks, want {half}..{period}")
    if ages[:half] != list(range(1, half + 1)):
        fails.append(f"  period={period}: cold start not counted from 1")

    v.reset()
    after = [v.prob(None) for _ in range(period * 3)]
    if after[:half] != list(range(1, half + 1)):
        fails.append(f"  period={period}: reset() left history behind")
    if min(after[half:]) < half or max(after[half:]) > period:
        fails.append(f"  period={period}: bound broken after reset()")

if fails:
    print("FAIL test_bounded_vad")
    print("\n".join(fails))
    sys.exit(1)
print("ok test_bounded_vad")
