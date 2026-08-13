"""Pins the startup health warning being skipped, and only it.

Both games open on an unskippable ~150-word epilepsy notice that renders as a
chrome-free title + prose card — structurally identical to a real lore card,
so it can only be told apart by what it says. Both failure directions are
expensive: miss it and the first thing HoyoVoice ever does is read a wall of
legal text aloud; match too eagerly and it silently eats real dialogue.

Every marker is medical, and the title is deliberately not one of them — the
card is only ever assembled as title + body, so the body always carries the
match, and a title-only marker ("before playing") also swallows ordinary
lines. KEEP is where that trade-off is pinned. Run directly or under pytest:

    python tools/test_boot_notice.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live                                    # noqa: E402

# A paraphrase in the notice's register, carrying every marker the matcher
# looks for — the real notice's wording stays out of the repo, and the
# matcher never needed it: it matches markers, not the wall of text.
TITLE = "WARNING: READ BEFORE PLAYING"
BODY = (
    "For a small number of players, exposure to flashing imagery or certain "
    "light patterns on a screen can bring on epileptic seizures, and can do "
    "so even in players with no prior history of epilepsy or any epileptic "
    "symptoms. If you, or anyone in your family, has ever experienced a "
    "seizure, consult your physician before you play."
)
BODY2 = (
    "Beyond the above, should you notice a headache, dizziness, nausea, any "
    "feeling like motion sickness, or a discomfort or pain anywhere in your "
    "body while playing, IMMEDIATELY stop playing. If the condition "
    "persists, seek medical attention."
)

SKIP = [
    f"{TITLE}. {BODY}",                  # as the lore card assembles it
    BODY,
    BODY2,                               # second paragraph on its own
    # the font's l/I confusion inside a word, which fix_ocr_text only repairs
    # for standalone letters — a single marker must not be load-bearing
    "WARNlNG: READ BEFORE PLAYlNG. For a small number of players, flashing "
    "imagery can bring on epileptic seizures.",
    "WARNING: READ BEFORE PLAYING. For a small number of pIayers, flashlng "
    "lmagery can brlng on epileptlc selzures.",
]

KEEP = [
    "Hello, you two. Is the ferry running late?",
    "The Warning Bell tolled at dawn. Read the notice before playing.",
    "I have a headache. Stop playing that lyre, would you?",
    "Consult the almanac before you set out.",
    "Seek the physician in Liyue Harbor.",
    "",
]


def main():
    bad = 0
    for s in SKIP:
        if not live.boot_notice(live.fix_ocr_text(s)):
            print(f"FAIL missed notice: {s[:60]!r}")
            bad += 1
    for s in KEEP:
        if live.boot_notice(live.fix_ocr_text(s)):
            print(f"FAIL ate dialogue: {s[:60]!r}")
            bad += 1
    total = len(SKIP) + len(KEEP)
    print(f"{total - bad}/{total} ok")
    return 1 if bad else 0


def test_boot_notice():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
