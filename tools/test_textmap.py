"""Pins what snapping a read to the game's own text will and won't do.

The lines below are real: what Vision returned on the 2026-08-12 sessions,
against the text the game actually drew. The failure that matters is not a
missed repair — the read is still spoken, exactly as it is today — but a
WRONG one, which would put a sentence in a character's mouth that the game
never wrote. Every case here is aimed at that.

Run directly or under pytest:

    python tools/test_textmap.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from textmap import TextMap                      # noqa: E402

# the game's text
MAP = [
    "Right. Choose \"mission budget\" under the expense category, but be "
    "sure to specify \"emergency rescue operation\" in the description.",
    "Yes. Well, that's one option, but there are risks to consider.",
    "A lot of them will probably stockpile it and slowly work their way "
    "through — probably a good idea, since energy prices are only gonna "
    "keep rising. But there'll always be people who urgently need Mora.",
    "The real issue here is that government relief is behind schedule.",
    "Let's book this train. Regulations say that if we need to move goods "
    "in an emergency, the Fatui can requisition a train.",
    "I didn't feel comfortable expressing my true opinions in front of "
    "everyone back there.",
    "Hello, Lady Marionette.",
    "Yes.",
    "No.",
]

# (what OCR read, what it should become — or None to keep the read)
CASES = [
    # a wrong letter welded to the next word: the everyday damage
    ("Right. Choosel\"mission budget\" under the expense category, but be "
     "sure to specify \"emergency rescue operation\" in the description.",
     MAP[0]),
    # a wrong first letter
    ("Ves. Well, that's one option, but there are risks to consider.",
     MAP[1]),
    # punctuation and spacing, which the comparison ignores and the repair
    # restores — sentence streaming reads punctuation, so this is not
    # cosmetic
    ("The real issue here is that government relief is behind schedule",
     MAP[3]),
    # TWO dialogue rows fused and interleaved. Scores 0.57 against its own
    # line: the top match is right, and it is still refused, because a 0.57
    # acceptance against a map three orders of magnitude larger would be
    # matching noise. A wrong sentence spoken confidently is worse than a
    # garbled one.
    ("A lot idea, si will pergy bly stare tely god a kly rising. But there "
     "alias be peopy a who urgently need Mora.", None),
    # a line the map has never heard of stays exactly as read
    ("The quartermaster keeps a ledger of every crate that leaves the depot "
     "at dawn.", None),
    # too short to identify: half the map is an equally good match for "Yes."
    ("Ves.", None),
    # already correct, to the character — nothing to hand back
    ("Hello, Lady Marionette.", None),
]


def main():
    bad = 0
    tm = TextMap(MAP)
    for read, want in CASES:
        got = tm.snap(read)
        if got != want:
            print(f"FAIL  {read[:56]!r}\n        got  {str(got)[:70]}\n"
                  f"        want {str(want)[:70]}")
            bad += 1
        else:
            print(f"ok    {'repaired' if want else 'kept as read'}: "
                  f"{read[:52]!r}")

    # a map that isn't there, or is nonsense, must leave the app as it was
    for path in ("/nonexistent/textmap.json", os.devnull):
        if TextMap.load(path) is not None:
            print(f"FAIL  load({path}) should be None")
            bad += 1
    print("ok    an unreadable map turns snapping off, quietly")

    # and the lookup has to be affordable: it runs on every line that is
    # about to be spoken, beside a ~144ms OCR call
    big = TextMap([f"line number {i} about the {i % 97} crates of Kristall "
                   f"bound for Snezhnograd this winter" for i in range(50000)]
                  + MAP)
    t0 = time.perf_counter()
    for read, _ in CASES:
        big.snap(read)
    per = (time.perf_counter() - t0) / len(CASES) * 1000
    if per > 40:
        print(f"FAIL  {per:.0f}ms per query on a 50k-line map")
        bad += 1
    else:
        print(f"ok    {per:.0f}ms per query on a 50k-line map")

    print("FAILURES:", bad) if bad else print("all good")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
