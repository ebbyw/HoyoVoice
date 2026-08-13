"""Pins that a choice prompt is read ONCE however OCR mangles its first word.

Vision fuses Genshin's choice bullet into the option's first word, and the
prompt sits on screen for as long as the player takes to click it — so the
same static option comes back differently on almost every pass. The
MANGLING patterns below are the real ones — shots 795-804 of the
2026-08-12 15:48 session, one option read ten ways over 40 seconds — with
invented option text under them; no game text ships in this repo.
Whole-string similarity puts several of those pairs under same_line's 0.9
cutoff, which made the prompt look new and had it spoken again.

The opposite error matters just as much and is pinned too: two genuinely
different options must never collapse onto each other, or one of them is
never read. Run directly or under pytest:

    python tools/test_choice_dedupe.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live                                    # noqa: E402

# every read of the one option, in order
JITTER = ["T'ul go warn the crew.",
          "@ILL go warn the crew.",
          "• I'I go warn the crew.",
          "TIL go warn the crew.",
          "TU go warn the crew.",
          "TU go warn the crew.",
          "• rIgo warn the crew.",
          "TU go warn the crew.",
          "TU go warn the crew.",
          "TIl go warn the crew."]

# (a, b, same option?)
PAIRS = [
    # the mangling is always on the first word
    ("TU go warn the crew.", "• rIgo warn the crew.", True),
    ("T'ul go warn the crew.", "@ILL go warn the crew.", True),
    ("I'll go warn the crew.", "TIL go warn the crew.", True),
    # different options that happen to share a first word — the tail decides
    ("I'll go warn the crew.", "I'll wait here for you.", False),
    ("Let's go find the divers.", "Let's ask around the docks.", False),
    # short options differ ONLY in their first word: the tail is too thin to
    # stand in for the whole option, so they must not collapse
    ("Yes.", "No.", False),
    ("Sure thing.", "Not a chance.", False),
]


def settle_reads(reads):
    """Prompts that would be treated as NEW, mirroring the loop's own
    settle-then-fresh test: a read has to repeat before it counts, and it
    counts only if it isn't the prompt already handled."""
    fresh, prev, logged = [], "", None
    for r in reads:
        norm = live.normalize_text(r)
        settled = bool(norm) and norm == prev
        if settled and not (logged and live.same_option(r, logged)):
            fresh.append(r)
            logged = r
        prev = norm
    return fresh


def main():
    bad = 0
    fresh = settle_reads(JITTER)
    if len(fresh) != 1:
        print(f"FAIL  one option read {len(fresh)}× : {fresh}")
        bad += 1
    else:
        print(f"ok    ten mangled reads → one prompt ({fresh[0]!r})")

    for a, b, want in PAIRS:
        got = live.same_option(a, b)
        if got != want:
            print(f"FAIL  same_option({a!r}, {b!r}) = {got}, want {want}")
            bad += 1
        else:
            print(f"ok    {'same' if want else 'differ'}: {a!r} / {b!r}")
    print("FAILURES:", bad) if bad else print("all good")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
