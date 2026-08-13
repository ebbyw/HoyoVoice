"""Pins the two-rows-in-one-box detector against real frames.

Vision fuses two drawn dialogue rows into a single observation and reads
them interleaved; the resulting text is not the game's, and because it
alternates with the clean read of the same motionless screen it defeated
the dedupe window and was spoken about forty times in two minutes
(2026-08-12 17:39-17:41, shots 409-581). The GEOMETRY below is real —
box positions and heights measured off the clean and fused reads of one
frame, plus the cases that must NOT be dropped (a big centered world
hint, the tallest genuinely-single row in the corpus) — but the prose
riding on it is invented; no game text ships in this repo. The detector
keys on height, not words.

Run directly or under pytest:

    python tools/test_fused_rows.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profiles import get_profile                # noqa: E402

GEN = get_profile("genshin")


def b(text, x, y, w, h, conf=1.0):
    return {"text": text, "x": x, "y": y, "w": w, "h": h, "confidence": conf}


# shot 411's geometry — the two rows read as two boxes, the correct read
CLEAN = [
    b("So they'll haul it to the harbor", 0.686, 0.287, 0.179, 0.028),
    b("Alyosha", 0.469, 0.219, 0.061, 0.035),
    b("A lot of them will probably hoard the lamp oil and slowly work "
      "their way through - probably a", 0.190, 0.176, 0.618, 0.034),
    b("smart call, since fuel prices are only gonna keep climbing. But "
      "there will always be folk", 0.195, 0.147, 0.609, 0.034),
    b("who urgently need light.", 0.411, 0.119, 0.177, 0.031),
]

# shot 422's geometry — the same screen, the same instant, the rows fused
FUSED = [
    b("So they'll haul it to the harbor", 0.686, 0.287, 0.179, 0.028),
    b("Alyosha", 0.469, 0.219, 0.061, 0.035),
    b("A lot call, si will perl oil bly hoard tely smart a kly climbing. "
      "But there alias be folky a", 0.188, 0.148, 0.621, 0.067),
    b("who urgently need light.", 0.411, 0.119, 0.177, 0.031),
]

# shot 49's geometry — a world hint, drawn big and centered, not a row
WORLD_HINT = [
    b("There is Warm Current nearby", 0.409, 0.243, 0.274, 0.079),
    b("gojo", 0.416, 0.181, 0.048, 0.049),
]

# shot 716's geometry — the tallest box that is genuinely ONE row
TALL_SINGLE = [
    b("I still remember those evenings when I read charts in the old "
      "harbor office", 0.196, 0.157, 0.604, 0.051),
]

CASES = [("clean two-row read", CLEAN, False),
         ("fused two-row read", FUSED, True),
         ("big centered world hint", WORLD_HINT, False),
         ("tall but single row", TALL_SINGLE, False)]


def main():
    bad = 0
    for name, blocks, want in CASES:
        got = GEN.fused_rows(blocks)
        if bool(got) != want:
            print(f"FAIL  {name}: fused_rows = {got}, want {want}")
            bad += 1
        else:
            print(f"ok    {name} → {'dropped' if want else 'kept'}")

    # the frame is dropped for the fused box and says so with THAT text —
    # the event is the only evidence a dropped frame leaves
    named = [b["text"] for b in GEN.fused_rows(FUSED)]
    if named != [FUSED[2]["text"]]:
        print(f"FAIL  fused_rows named {named}, want just the fused box")
        bad += 1
    else:
        print("ok    the fused box is the one reported")

    # the clean read must still classify as the line the game wrote
    line = GEN.classify(CLEAN)["dialogue"]
    if not line.startswith("A lot of them will probably hoard"):
        print(f"FAIL  clean read no longer classifies: {line[:60]!r}")
        bad += 1
    else:
        print("ok    clean read still classifies as the whole line")

    # and a profile with no measured threshold never drops anything
    if get_profile("hsr").fused_rows(FUSED):
        print("FAIL  unmeasured profile dropped a frame")
        bad += 1
    else:
        print("ok    profile without a measured height never drops")
    print("FAILURES:", bad) if bad else print("all good")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
