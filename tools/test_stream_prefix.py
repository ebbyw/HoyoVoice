"""Pins mid-line streaming — the rule that decides how early a line is read.

Both failure directions are expensive: clip too eagerly and one spoken
thought is chopped in half (or a decimal is read as a sentence end); clip
too rarely and the read lags a second behind the typewriter. Run directly
or under pytest:

    python tools/test_stream_prefix.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live                                    # noqa: E402

STREAMS = [
    # (line still being typed, prefix we should speak now)
    ("Hello there, traveler. How ar", "Hello there, traveler."),
    ("We should go now. But first, we ne", "We should go now."),
    ("Wait!! Look over there. It is mov", "Wait!! Look over there."),
    ('"Not this time," she said. Then she', '"Not this time," she said.'),
    # two sentences already closed: speak the longest complete prefix
    ("One thing happened. Then another. And th",
     "One thing happened. Then another."),
]

HOLDS = [
    "Hello there, traveler. H",     # tail too short to prove it's still typing
    "Hi. Wh",                       # head too short to be worth its own read
    "Mr. Ito said so, and then some",   # abbreviation, not a sentence end
    "Hmm… I really do not know about that but",  # "…" is a pause, not an end
    "That is quite enough of that.",             # nothing typed past the end
    "It costs 3.50 mora and then some more",     # decimal
]


def main():
    bad = 0
    for line, want in STREAMS:
        got = live.stream_prefix(line)
        if got != want:
            print(f"FAIL stream {line!r}: want {want!r}, got {got!r}")
            bad += 1
    for line in HOLDS:
        got = live.stream_prefix(line)
        if got is not None:
            print(f"FAIL hold {line!r}: clipped to {got!r}")
            bad += 1
    print(f"{len(STREAMS) + len(HOLDS) - bad}/"
          f"{len(STREAMS) + len(HOLDS)} ok")
    return 1 if bad else 0


def test_stream_prefix():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
