"""Pins what snapping a read to the game's own text will and won't do.

The corruption SHAPES below are real — the weld, the wrong first letter,
the dropped full stop and the two-row fusion are exactly what Vision
returned on the 2026-08-12 sessions — but the prose is invented; no game
text ships in this repo. The failure that matters is not a missed repair —
the read is still spoken, exactly as it is today — but a WRONG one, which
would put a sentence in a character's mouth that was never written. Every
case here is aimed at that.

Run directly or under pytest:

    python tools/test_textmap.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from textmap import TextMap, variants            # noqa: E402

# the map's text (invented, in the games' dialogue register)
MAP = [
    "Right. Choose \"harbor repairs\" under the expense category, but be "
    "sure to specify \"emergency dredging works\" in the description.",
    "Yes. Well, that's one route, but there are tolls to consider.",
    "A lot of them will probably hoard the lamp oil and slowly work their "
    "way through — probably a smart call, since fuel prices are only gonna "
    "keep climbing. But there will always be folk who urgently need light.",
    "The real issue here is that the relief convoy is behind schedule.",
    "Let's charter this barge. Regulations say that if we need to move "
    "goods in an emergency, the guild can requisition a vessel.",
    "I didn't feel comfortable expressing my true opinions in front of "
    "everyone back there.",
    "Hello, Lady Halvette.",
    "Yes.",
    "No.",
]

# (what OCR read, what it should become — or None to keep the read)
CASES = [
    # a wrong letter welded to the next word: the everyday damage
    ("Right. Choosel\"harbor repairs\" under the expense category, but be "
     "sure to specify \"emergency dredging works\" in the description.",
     MAP[0]),
    # a wrong first letter
    ("Ves. Well, that's one route, but there are tolls to consider.",
     MAP[1]),
    # punctuation and spacing, which the comparison ignores and the repair
    # restores — sentence streaming reads punctuation, so this is not
    # cosmetic
    ("The real issue here is that the relief convoy is behind schedule",
     MAP[3]),
    # TWO dialogue rows fused and interleaved. Scores barely over half
    # against its own line: the top match is right, and it is still
    # refused, because an acceptance that low against a map three orders
    # of magnitude larger would be matching noise. A wrong sentence spoken
    # confidently is worse than a garbled one.
    ("A lot call, si will perl oil bly hoard tely smart a kly climbing. "
     "But there alias be folky a who urgently need light.", None),
    # a line the map has never heard of stays exactly as read
    ("The quartermaster keeps a ledger of every crate that leaves the depot "
     "at dawn.", None),
    # too short to identify: half the map is an equally good match for "Yes."
    ("Ves.", None),
    # already correct, to the character — nothing to hand back
    ("Hello, Lady Halvette.", None),
]


# A real dump is not the text on screen: the MARKUP forms here ({NICKNAME},
# gender switches, ruby glosses, rich text) are the entry shapes the games'
# TextMapEN.json files actually use; the sentence bodies are invented.
RAW = [
    # the '#' sentinel, and the player's name substituted at runtime
    ("#The name's Pell, and this is {NICKNAME}.",
     ["The name's Pell, and this is Ebby."]),
    # gender: the game picks one, so BOTH are indexed
    ("#Huh? {M#He}{F#She} has to cross the rope bridge at the end?",
     ["Huh? She has to cross the rope bridge at the end?",
      "Huh? He has to cross the rope bridge at the end?"]),
    # a ruby annotation is a gloss drawn ABOVE the word, not part of the
    # line — keeping it spliced "Moon Maiden" into the middle of "Kuutar"
    ("The Kuu{RUBY#[S]Moon Maiden}tar shines over the northern ice.",
     ["The Kuutar shines over the northern ice."]),
    # rich text renders as its content
    ("Old <color=#00E1FFFF>cliff wardens</color> who lost their footing.",
     ["Old cliff wardens who lost their footing."]),
    ("Your mailbox holds <unbreak>1000</unbreak> messages.",
     ["Your mailbox holds 1000 messages."]),
    # escaped newlines are line breaks in one drawn line
    ("First part\\nsecond part of the same line.",
     ["First part second part of the same line."]),
    # unresolvable at load: whatever the runtime would put there, this
    # entry can never match what is drawn, so it is not indexed at all
    ("In the end you reach the final count: 1{TEXTJOIN#44} coins.", []),
]


def main():
    bad = 0
    for raw, want in RAW:
        got = variants(raw, "Ebby")
        if got != want:
            print(f"FAIL  cleaning {raw[:48]!r}\n        got  {got}\n"
                  f"        want {want}")
            bad += 1
        else:
            print(f"ok    cleaned: {raw[:52]!r}")

    # the two halves of a gendered entry must not veto each other: they are
    # each other's runner-up at 0.98, and the margin gate refused every
    # gendered line in the map until it learned they are one entry
    gendered = TextMap(["Huh? {M#He}{F#She} has to cross the rope bridge at "
                        "the end? That's really dangerous.",
                        "Hello, Lady Halvette."], nickname="Ebby")
    got = gendered.snap("Huh? She has to cross the rope bridge at the end? "
                        "That's realIy dangerous.")
    if got != ("Huh? She has to cross the rope bridge at the end? That's "
               "really dangerous."):
        print(f"FAIL  a gendered entry's own twin vetoed it: {got}")
        bad += 1
    else:
        print("ok    a gendered entry is not its own runner-up")

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
    big = TextMap([f"line number {i} about the {i % 97} crates of glasswork "
                   f"bound for Port Halven this winter" for i in range(50000)]
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
