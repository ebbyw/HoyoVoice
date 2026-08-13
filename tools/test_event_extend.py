"""Pins when a log event GROWS instead of adding a row.

A line is handled twice by design — the first finished sentence, then the
typewriter's remainder — and for a line that is skipped rather than spoken
those two passes are the same fact written twice. Over the 2026-08-12
18:10-18:21 session, 44 of 77 events were a skip and its own growth, or the
"repeat (deduped)" row that followed a skip. Growing the row it grew from
keeps one row per line, carrying the fullest text.

The opposite error is the expensive one: two DIFFERENT lines collapsing
into one row would hide a line from the log entirely. Run directly or under
pytest:

    python tools/test_event_extend.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live                                    # noqa: E402

SKIP = "skipped (voiced)"


def rows(*calls):
    """Feed calls through add_event and return the resulting log rows."""
    live.events.clear()
    for action, speaker, text, extend in calls:
        live.add_event(action, "skip", speaker, text, shot=False,
                       extend=extend)
    return [(e["action"], e["speaker"], e["text"]) for e in live.events]


def check(name, got, want):
    if got != want:
        print(f"FAIL  {name}\n        got  {got}\n        want {want}")
        return 1
    print(f"ok    {name}")
    return 0


def main():
    bad = 0

    # the typewriter's remainder rewrites the row it grew from
    bad += check(
        "a skip that grew keeps one row, with the whole line",
        rows((SKIP, "Odette", "Funny - I had the same idea.", True),
             (SKIP, "Odette", "Funny - I had the same idea. In that case, "
              "let me pay.", True)),
        [(SKIP, "Odette", "Funny - I had the same idea. In that case, "
          "let me pay.")])

    # OCR jitter inside the part already logged is not a growth
    bad += check(
        "a re-read that is not a prefix adds its own row",
        rows((SKIP, "Odette", "Yes. Well, that's one option.", True),
             (SKIP, "Odette", "Ves. Well, that's one option, but.", True)),
        [(SKIP, "Odette", "Yes. Well, that's one option."),
         (SKIP, "Odette", "Ves. Well, that's one option, but.")])

    # a different speaker is a different fact even if the text continues
    bad += check(
        "a different speaker never grows the previous row",
        rows((SKIP, "Odette", "Let's book this train.", True),
             (SKIP, "Alyosha", "Let's book this train. Regulations say.",
              True)),
        [(SKIP, "Odette", "Let's book this train."),
         (SKIP, "Alyosha", "Let's book this train. Regulations say.")])

    # and so is a different action — a skip must not swallow a spoken row
    bad += check(
        "a different action never grows the previous row",
        rows((SKIP, "Odette", "That should do it.", True),
             ("spoken", "Odette", "That should do it. The train will go.",
              True)),
        [(SKIP, "Odette", "That should do it."),
         ("spoken", "Odette", "That should do it. The train will go.")])

    # without the flag nothing is ever rewritten (spoken lines are two real
    # events — two pieces of audio were played)
    bad += check(
        "extend is opt-in",
        rows((SKIP, "Odette", "You flatter me.", False),
             (SKIP, "Odette", "You flatter me. It's only because.", False)),
        [(SKIP, "Odette", "You flatter me."),
         (SKIP, "Odette", "You flatter me. It's only because.")])

    # an empty previous row has no prefix to match, and must not be grown
    bad += check(
        "an empty row is not a prefix of everything",
        rows((SKIP, None, "", True), (SKIP, None, "A line.", True)),
        [(SKIP, None, ""), (SKIP, None, "A line.")])

    print("FAILURES:", bad) if bad else print("all good")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
