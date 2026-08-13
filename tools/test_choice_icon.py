"""Pins that the option's bubble icon never reaches the spoken text.

Genshin draws a chat-bubble glyph beside each choice, vertically centered
on the option — so on a WRAPPED option it sits beside the middle, and
Vision returns it either as its own box (whose row sorts between the two
rows of the option) or fused into the row it lands on. Both put a
registered sign inside a sentence (shot #211 as its own box; 108 shots on
2026-08-12 fused into the row). The geometry below is those two frames';
the prose is invented — no game text ships in this repo.

Run directly or under pytest:

    python tools/test_choice_icon.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profiles import get_profile                # noqa: E402

GEN = get_profile("genshin")


def b(text, x, y, w, h, conf=1.0):
    return {"text": text, "x": x, "y": y, "w": w, "h": h, "confidence": conf}


# shot 211's geometry — the glyph came back as its OWN box, filed
# between the two rows of a wrapped option
OWN_BOX = [
    b("®", 0.669, 0.323, 0.016, 0.028),
    b("I can't say. This sounds like it'd be", 0.686, 0.337, 0.210, 0.023),
    b("quite the tangle...", 0.688, 0.310, 0.104, 0.026),
    b("Sure, I can try that...", 0.688, 0.264, 0.132, 0.026),
    b("Paimon", 0.469, 0.212, 0.061, 0.029),
    b("C'mon, Ebby. These nets are beyond tangled! Let's help!", 0.308,
      0.167, 0.383, 0.034),
]

# shot 417's geometry — the glyph FUSED into the option's second row
FUSED = [
    b("So they'll haul it to the harbor", 0.683, 0.273, 0.182, 0.028),
    b("® master..", 0.667, 0.247, 0.070, 0.039),
    b("Alyosha", 0.469, 0.203, 0.061, 0.034),
    b("A lot of them will probably hoard the lamp oil and slowly work "
      "their way through - probably a", 0.190, 0.159, 0.618, 0.034),
]

CASES = [
    ("icon as its own box", OWN_BOX,
     ["I can't say. This sounds like it'd be quite the tangle...",
      "Sure, I can try that..."]),
    ("icon fused into the second row", FUSED,
     ["So they'll haul it to the harbor master.."]),
]


def main():
    bad = 0
    for name, blocks, want in CASES:
        got = GEN.classify(blocks)["choices"]
        if got != want:
            print(f"FAIL  {name}\n        got  {got}\n        want {want}")
            bad += 1
        else:
            print(f"ok    {name}")

    # the strip must not eat punctuation a real option opens with
    # with a nameplate: Genshin refuses a prompt that has none (the teleport
    # map lists waypoints in the same column and has no plate)
    opener = [b("...Is that so?", 0.688, 0.264, 0.090, 0.026),
              b("(Say nothing)", 0.688, 0.310, 0.090, 0.026),
              b("Paimon", 0.469, 0.212, 0.061, 0.029),
              b("C'mon, Ebby.", 0.430, 0.167, 0.140, 0.034)]
    got = GEN.classify(opener)["choices"]
    if got != ["(Say nothing)", "...Is that so?"]:
        print(f"FAIL  an option's own opening punctuation survives: {got}")
        bad += 1
    else:
        print("ok    an option's own opening punctuation survives")

    print("FAILURES:", bad) if bad else print("all good")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
