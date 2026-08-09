"""Pins Genshin's readable articles: what gets read, and what must not.

The panel is a gold title over a prose column, clipped top and bottom by
two ornate rules, with 'Return' alone in the hint strip. Every number here
is measured off rec_20260808_190712 ("Investigative Report: Bakunawa") at
1080p: the rules sit at cy=0.896 and cy=0.052, the title at cy=0.924, and
the body rows share a left edge at x=0.266 running from cy=0.859 down at a
pitch of 0.033.

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


TITLE = centered("Investigative Report: Bakunawa", 0.924)
RETURN = row("Return", 0.076, x=0.897, w=0.036, h=0.018)
UID = row("UID: 603275577", 0.014, x=0.875, w=0.094, h=0.023)
CHROME = [RETURN, UID]

# the article as first opened: 11 rows from cy=0.859 down, and the one
# stylized proper noun Vision only half believes
BODY = [row("A gigantic beast that appeared on the Western side of Natlan five", 0.859),
        row("hundred years ago, accompanied by other Abyssal monsters. Its body", 0.825),
        row("was like that of a mountain, and it devoured the tribespeople of", 0.795),
        row("Tenochtzitoc.", 0.762, w=0.092, h=0.026, conf=0.50),
        row("An out-of-control creation identified as one of \"Gold\"'s that once", 0.733),
        row("attacked and swallowed part of her body. Lacking in intelligence, its", 0.698)]


def article(*extra):
    return [TITLE] + BODY + list(extra) + CHROME


# (name, frame, expected read — None means "not a readable")
FRAMES = [
    ("the article as opened", article(),
     "Investigative Report: Bakunawa. "
     + " ".join(b["text"] for b in BODY)),

    # The weak row is the point of the lower confidence floor: at the 0.8
    # default "Tenochtzitoc." vanished from the middle of a sentence.
    ("a weak proper noun is still read", article(),
     lambda got: "Tenochtzitoc." in got),

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

    # --- things that are not articles --------------------------------
    # A menu: same title-over-column shape, same Return hint, but it has
    # text elsewhere — tabs down the left, a counter up top — and an
    # article never does.
    ("a menu with a Return hint",
     [centered("Character Archive", 0.924),
      row("Kachina", 0.859, w=0.10),
      row("A young Natlan girl of the Children of Echoes tribe who", 0.825),
      row("Obtained", 0.700, x=0.86, w=0.06),          # off in a side column
      ] + CHROME,
     None),
    ("no Return hint at all", [TITLE] + BODY + [UID], None),
    # centered prose with no column edge: a card, not an article
    ("centered card with no left-aligned column",
     [TITLE, centered("A gigantic beast appeared on the Western side.", 0.859,
                      w=0.30),
      centered("It devoured the tribespeople of Tenochtzitoc.", 0.825, w=0.30)]
     + CHROME,
     None),
    ("a digit-heavy stat panel",
     [centered("Adventure Handbook", 0.924),
      row("Level 45 60/100 Exp 2450 3/5 Rewards 12", 0.859),
      row("Level 46 70/100 Exp 2650 4/5 Rewards 14", 0.825)] + CHROME,
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
