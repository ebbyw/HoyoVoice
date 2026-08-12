"""Pins how a settled line is judged against the recent-lines window.

Three verdicts, all expensive to get wrong: a missed dup reads the same
line twice, a false dup drops a line entirely, and a false EXTENSION is
the worst of the three — it speaks only what it thinks is the remainder,
so the line is cut off at the front and the player never hears the
opening words. Run directly or under pytest:

    python tools/test_window_verdict.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live                                    # noqa: E402


def w(*pairs):
    return [{"speaker": s, "norm": live.normalize_text(t)} for s, t in pairs]


def n(t):
    return live.normalize_text(t)


# (window, speaker, line, expected verdict)
#   "new"  — spoken in full
#   "dup"  — skipped
#   text   — extension: the prefix already spoken
CASES = [
    # --- extensions: the typewriter grew a line we already spoke ---
    ("grew mid-line",
     w(("Leyla", "The stems of some vegetables grow quickly.")), "Leyla",
     "The stems of some vegetables grow quickly. They absorb nutrients.",
     n("The stems of some vegetables grow quickly.")),
    # the plate flickered out while the line was still typing: the window
    # entry has no speaker, but it is plainly the same line
    ("grew with the plate missing",
     w((None, "I truly was held back by something.")), "Leyla",
     "I truly was held back by something. Apical dominance, it turns out.",
     n("I truly was held back by something.")),

    # --- the bug: a short line from ANOTHER speaker is not a prefix ---
    # Paimon's "And then?" made Leyla's answer look like a continuation
    # of it, and Leyla lost her opening words.
    ("other speaker's line is not a prefix",
     w(("Paimon", "And then?")), "Leyla",
     "And then I blossomed into a healthy vegetable with lush foliage.",
     "new"),
    # A repeat is ONE character saying the same words twice running. Two
    # characters saying the same words is a scene — one repeating the
    # other's question back at them — and both have to be read. This used
    # to dedupe on length alone, which silently dropped the second half of
    # every such exchange.
    ("another character may echo a line word for word",
     w(("Paimon", "So the treasure was buried under the old bridge?")),
     "Leyla", "So the treasure was buried under the old bridge?", "new"),
    # ...and the same character saying it again IS a repeat
    ("the same character saying it twice running is a repeat",
     w(("Leyla", "So the treasure was buried under the old bridge?")),
     "Leyla", "So the treasure was buried under the old bridge?", "dup"),

    # --- dups ---
    ("exact repeat", w(("Leyla", "It's a botanical phenomenon.")), "Leyla",
     "It's a botanical phenomenon.", "dup"),
    ("punctuation jitter", w(("Leyla", "It's a botanical phenomenon.")),
     "Leyla", "It's a botanical phenomenon", "dup"),
    ("trivial tail is jitter, not growth",
     w(("Leyla", "That is quite enough of that")), "Leyla",
     "That is quite enough of that.", "dup"),

    # --- new ---
    ("unrelated line", w(("Paimon", "This is the spot")), "Leyla",
     "Hmm. Just as I thought.", "new"),
    ("empty window", [], "Leyla", "Master Ororon said so.", "new"),

    # --- pure insertion: an OCR ghost box splices a re-read of one row
    # into the middle of a line already spoken. Verbatim from
    # rec_20260812_083939: the splice lands mid-line, so the substring
    # rule can't see the recent line contiguously, and a 25-char splice
    # into an 83-char line scores 0.869 — under the 0.90 ratio. With a
    # 1-deep window each miss evicts the clean entry, so the clean line
    # and its ghost variant ping-ponged and the same line was spoken
    # four times in fifteen seconds.
    ("ghost splice mid-line is a dup",
     w(("Paimon", "Wow, it's so majestic! Just flying from one side to the"
        " other would probably leave Paimon out of breath…")), "Paimon",
     "Wow, it s so majestic! Just flying from one side to the other would"
     " probably leave Paimon Wow, its so majestic Just Flyin out of breath…",
     "dup"),
    ("ghost splice with different jitter is still a dup",
     w(("Paimon", "Wow, it's so majestic! Just flying from one side to the"
        " other would probably leave Paimon out of breath…")), "Paimon",
     "Wow, it's so majestic! Just flying from one side to the other would"
     " probably leave Paimon Wow, it's so majestic! just flyin out of"
     " breath…", "dup"),
    # a genuinely new line that shares phrases with the recent one is NOT
    # a splice: the recent line does not survive in order and in full
    ("shared phrasing is not a splice",
     w(("Paimon", "Wow, it's so majestic! Just flying from one side to the"
        " other would probably leave Paimon out of breath…")), "Paimon",
     "Just flying from one side of Dragonspine to the other would leave"
     " anyone out of breath, honestly.", "new"),
]


def main():
    bad = 0
    for label, window, speaker, line, want in CASES:
        dup, ext = live.window_verdict(n(line), speaker, window)
        got = "dup" if dup else (ext if ext else "new")
        if got != want:
            print(f"FAIL {label}: want {want!r}, got {got!r}")
            bad += 1
    # The load-bearing property is no longer the deque's depth but
    # remember_line's semantics: a DIALOGUE line replaces the window —
    # that is what lets a character repeat their own line once anyone
    # else has spoken in between (the second "Let's go!" of a scene was
    # swallowed by a 3-deep stacking window) — while a CHOICE read stacks
    # alongside, because after one the window must hold both the option
    # texts and the dialogue line still on screen (a one-slot window let
    # the option evict that line, and its next OCR jitter variant was
    # re-spoken: "Obviousk…", 2026-08-12).
    from collections import deque
    win = deque(maxlen=live.DEDUP_WINDOW)
    live.remember_line(win, "Paimon", n("Let's go!"))
    live.remember_line(win, "Nahida", n("After you."))
    dup, _ = live.window_verdict(n("Let's go!"), "Paimon", win)
    if dup:
        print("FAIL replace: second 'Let's go!' swallowed after another "
              "speaker — dialogue must REPLACE the window")
        bad += 1
    live.remember_line(win, "Paimon", n("Obviously, the question is: what "
                                        "is the Tsaritsa planning?"))
    for opt in ("Feeling better now?", "They're all Fatui."):
        live.remember_line(win, "Traveler", n(opt), stack=True)
    dup, _ = live.window_verdict(
        n("Obviousk the question is: what is the Tsaritsa planning?"),
        "Paimon", win)
    if not dup:
        print("FAIL stack: choice read evicted the on-screen line — its "
              "jitter variant would be re-spoken")
        bad += 1
    dup, _ = live.window_verdict(n("They're all Fatui."), "Traveler", win)
    if not dup:
        print("FAIL stack: the picked option's echo was not deduped")
        bad += 1
    total = len(CASES) + 3
    print(f"{total - bad}/{total} ok")
    return 1 if bad else 0


def test_window_verdict():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
