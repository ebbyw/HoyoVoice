"""Pins Genshin's readable articles: what gets read, and what must not.

The panel is a gold title over a prose column, clipped top and bottom by
two ornate rules, with 'Return' alone in the hint strip. Every number here
is measured off rec_20260808_190712 at 1080p: the rules sit at cy=0.896
and cy=0.052, the title at cy=0.924, and the body rows share a left edge
at x=0.266 running from cy=0.859 down at a pitch of 0.033. The geometry
is the measurement; the prose riding on it is invented — no game text
ships in this repo.

Two failures are guarded. Reading a MENU aloud — 'Return' is an ordinary
hint, and a menu's heading over its first column has the same shape as a
title over a body — which is why nothing may be on screen but the panel and
its own bottom strip. And, once the article is SCROLLED, reading a row that
is still drawn in half: half a row OCRs as garbage or as a fragment dedupe
cannot match against the whole row it becomes, so it would be read and then
read again complete. Run directly or under pytest:

    python tools/test_genshin_readable.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profiles import get_profile                # noqa: E402

GENSHIN = get_profile("genshin")


def row(text, cy, x=0.266, w=0.43, h=0.028, conf=1.0):
    """A body row by its LEFT edge, the way the column is measured."""
    return {"text": text, "confidence": conf,
            "x": x, "y": cy - h / 2, "w": w, "h": h}


def centered(text, cy, w=0.275, h=0.034, conf=1.0):
    return row(text, cy, x=0.5 - w / 2, w=w, h=h, conf=conf)


TITLE = centered("Field Report: The Harbor Colossus", 0.924)
RETURN = row("Return", 0.076, x=0.897, w=0.036, h=0.018)
# The same hint with its ◯ button glyph merged into the word, exactly as
# Vision returned it on the inventory-opened article.
RETURN_GLYPH = row("Return e", 0.076, x=0.895, w=0.048, h=0.018)
UID = row("UID: 100000000", 0.014, x=0.875, w=0.094, h=0.023)
CHROME = [RETURN, UID]

# the article as first opened: rows from cy=0.859 down at the measured
# pitch, and the one stylized proper noun Vision only half believes
BODY = [row("A gigantic beast that surfaced on the western side of the harbor", 0.859),
        row("five hundred years ago, trailed by other deepwater creatures. Its", 0.825),
        row("body was like that of a mountain, and it swallowed the boats of", 0.795),
        row("Brinegarth.", 0.762, w=0.092, h=0.026, conf=0.50),
        row("An out-of-control engine said to be one of the old foundry's that", 0.733),
        row("once dragged down part of the pier. Lacking any pilot, its", 0.698)]


def article(*extra):
    return [TITLE] + BODY + list(extra) + CHROME


# (name, frame, expected read — None means "not a readable")
FRAMES = [
    ("the article as opened", article(),
     "Field Report: The Harbor Colossus. "
     + " ".join(b["text"] for b in BODY)),

    # The weak row is the point of the lower confidence floor: at the 0.8
    # default "Brinegarth." vanished from the middle of a sentence.
    ("a weak proper noun is still read", article(),
     lambda got: "Brinegarth." in got),

    # --- scrolling ---------------------------------------------------
    # A row sliding under the upper rule (cy=0.896): its visible box reaches
    # the rule, so it is deferred until it is drawn whole again.
    ("a row clipped by the upper rule is not read",
     article(row("half of me is behind the rule up here", 0.888, h=0.020)),
     lambda got: "behind the rule" not in got),
    # ...and the same row once scrolling has carried it clear
    ("the same row is read once it is drawn whole",
     article(row("half of me is behind the rule up here", 0.870)),
     lambda got: "behind the rule" in got),
    # The bottom is where NEW rows enter, and the band runs all the way to
    # the lower rule (cy=0.052) — well below the Return hint at 0.076. A
    # band that stopped at the hint would swallow the end of every scrolled
    # article, and a swallowed row is never read again.
    ("a row scrolled down near the lower rule is still read",
     article(row("the last line of the article", 0.075, w=0.20)),
     lambda got: "the last line of the article" in got),
    ("...but not while the lower rule still cuts it",
     article(row("the last line of the article", 0.058, h=0.020, w=0.20)),
     lambda got: "the last line of the article" not in got),
    # The visible half of a row mid-slide sits just under the upper rule,
    # at a center of ~0.897 — between the body ceiling (0.896) and the
    # title floor (0.90). It must be DEFERRED, not treated as text off the
    # panel: a veto there killed detection outright for as long as the row
    # was sliding, so a scrolling article fell silent.
    ("a row in the sliver between the bands doesn't kill detection",
     article(row("half a row caught mid-slide", 0.897, h=0.014)),
     lambda got: "mid-slide" not in got and "gigantic beast" in got),

    # --- opened from the inventory, not the world --------------------
    # The article is an OVERLAY there: the bag screen stays on behind it
    # and OCRs right through. Measured off rec_20260809_080614 at 1080p —
    # this frame is why the "nothing else on screen" rule had to go, and
    # the read must still contain none of the bag's own text.
    ("the article opened from the inventory",
     [centered("Field Report: The Glass Shallows", 0.925, w=0.282),
      row("Quest", 0.932, x=0.099, w=0.029, h=0.018),
      row("Inventory capacity 1185/2300", 0.930, x=0.799, w=0.144, h=0.021),
      row("No extant records suggest how the glass shallows could have", 0.857),
      row("It seems that every chart of the channel was lost alongside", 0.828),
      row("Quest Item", 0.814, x=0.715, w=0.054, h=0.016),
      row("ash itself.", 0.796, w=0.067),
      row("The only speculation that remains to be made comes from an", 0.762),
      row("1880", 0.712, x=0.099, w=0.020, h=0.013),
      row("A field report that", 0.613, x=0.717, w=0.148, h=0.021),
      row("someone left behind in a hurry.", 0.589, x=0.715, w=0.170, h=0.021),
      RETURN_GLYPH,
      row("Destroy", 0.075, x=0.761, w=0.043, h=0.022),
      row("406180", 0.076, x=0.161, w=0.044, h=0.018),
      UID],
     lambda got: ("No extant records" in got and "ash itself." in got
                  and "Inventory capacity" not in got
                  and "Quest Item" not in got and "1880" not in got
                  and "left behind in a hurry" not in got)),

    # --- the world-object newspaper ----------------------------------
    # The world newspaper, opened at the paper on a bench rather than from
    # the inventory: same column (left edge 0.266), same title slot, same
    # rules — but the exit hint says 'Leave', not 'Return'. Measured off
    # rec_20260812_201648 at 1080p; a session sat on this page for 20
    # seconds and read nothing before 'leave' joined the hint words.
    ("the newspaper article with a Leave hint",
     [centered("The Northerly Courier", 0.924, w=0.163),
      row("As everyone knows, a lantern keeper trims the wick within a glass",
          0.843, h=0.031),
      row("hood and coaxes out a steady flame; the spark of a flint lies in the",
          0.810),
      row("striker's pouch, eventually catching cloth to become a bright, roaring",
          0.778, h=0.031),
      row("stove. Old dockside sayings even held that when a lamp guttered, was",
          0.747, h=0.031),
      row("trimmed, and relit, its smoke would settle into fog.", 0.713, h=0.031,
          w=0.311),
      row("1/3", 0.066, x=0.488, w=0.022, h=0.023),
      row("Leave", 0.076, x=0.903, w=0.032, h=0.018),
      UID],
     lambda got: ("The Northerly Courier." in got and "lantern keeper" in got
                  and "into fog." in got and "1/3" not in got)),

    # --- things that are not articles --------------------------------
    # A menu: same title-over-column shape, same Return hint, but two rows
    # sharing a margin is a list, not a page.
    ("a menu with a Return hint",
     [centered("Character Archive", 0.924),
      row("Marisel", 0.859, w=0.10),
      row("A young lighthouse keeper of the outer shoals who", 0.825),
      row("Obtained", 0.700, x=0.86, w=0.06),          # off in a side column
      ] + CHROME,
     None),
    ("no Return hint at all", [TITLE] + BODY + [UID], None),
    # centered prose with no column edge: a card, not an article
    ("centered card with no left-aligned column",
     [TITLE, centered("A gigantic beast surfaced on the western side.", 0.859,
                      w=0.30),
      centered("It swallowed the boats of Brinegarth.", 0.825, w=0.30)]
     + CHROME,
     None),
    ("a digit-heavy stat panel",
     [centered("Adventure Handbook", 0.924),
      row("Level 45 60/100 Exp 2450 3/5 Rewards 12", 0.859),
      row("Level 46 70/100 Exp 2650 4/5 Rewards 14", 0.825),
      row("Level 47 80/100 Exp 2850 5/5 Rewards 16", 0.795),
      row("Level 48 90/100 Exp 3050 6/5 Rewards 18", 0.762)] + CHROME,
     None),
    # 'Return to Title' is not the panel's Return hint — only single-glyph
    # noise may ride along with the word.
    ("a hint that merely starts with Return",
     [TITLE] + BODY + [row("Return to Title", 0.076, x=0.880, w=0.070,
                           h=0.018), UID],
     None),
    ("a title with no body", [TITLE] + CHROME, None),
]


def main():
    bad = 0
    for name, blocks, want in FRAMES:
        qr = GENSHIN.classify_quickread(blocks)
        got = None if qr is None else " ".join(qr)
        if want is None:
            ok = qr is None
        elif callable(want):
            ok = got is not None and want(got)
        else:
            ok = got == want
        if not ok:
            print(f"FAIL {name}: got {got!r}")
            bad += 1
    # The dialogue path must stay inert on a readable: its hint strip says
    # 'Return', which is a menu's own verb, so classify() sees a menu and
    # says nothing — and classify_quickread runs first anyway.
    state = GENSHIN.classify(article())
    if state["dialogue"] or state["speaker"]:
        print(f"FAIL dialogue path speaks on a readable: {state}")
        bad += 1
    total = len(FRAMES) + 1
    print(f"{total - bad}/{total} ok")
    return 1 if bad else 0


def test_genshin_readable():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
