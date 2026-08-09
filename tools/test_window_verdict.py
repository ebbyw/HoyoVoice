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
]


def main():
    bad = 0
    for label, window, speaker, line, want in CASES:
        dup, ext = live.window_verdict(n(line), speaker, window)
        got = "dup" if dup else (ext if ext else "new")
        if got != want:
            print(f"FAIL {label}: want {want!r}, got {got!r}")
            bad += 1
    # The window is ONE line deep, and that is load-bearing rather than a
    # tuning knob: it is what lets a character repeat their own line once
    # anyone else has spoken in between. Deeper, and the second "Let's go!"
    # of a scene is swallowed; the only job the window has is catching the
    # line still on screen re-stabilizing after we spoke it.
    if live.DEDUP_WINDOW != 1:
        print(f"FAIL window depth: want 1, got {live.DEDUP_WINDOW}")
        bad += 1
    print(f"{len(CASES) + 1 - bad}/{len(CASES) + 1} ok")
    return 1 if bad else 0


def test_window_verdict():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
