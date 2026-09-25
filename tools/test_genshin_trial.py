"""Pins Genshin's trial guide: the paged panel a character trial opens with.

A band across the screen: a looping clip on the left, a title over a prose
column on the right, the pager ('2/5') and a 'Close' button centered under
it. Every number is measured off rec_20260925_122558 at 1080p: title left
edge x=0.5245 cy=0.653, body rows sharing a left edge at x=0.525 from
cy=0.597 down at a pitch of ~0.028, pager cx=0.499 cy=0.285, Close cx=0.501
cy=0.211, UID bottom-right. The geometry is the measurement; the prose is
invented — no game text ships in this repo.

Guarded: reading the guide at all (nothing did before); reading a row the
panel draws in half under its bottom fade (Vision turns it into
"…in the nartv."); and reading anything off a screen that merely has a
Close button, or merely has an 'N/M' count. Run directly or under pytest:

    python tools/test_genshin_trial.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profiles import get_profile                # noqa: E402

GENSHIN = get_profile("genshin")
HSR = get_profile("hsr")


def blk(text, cy, x, w, h=0.023, conf=1.0):
    return {"text": text, "confidence": conf,
            "x": x, "y": cy - h / 2, "w": w, "h": h}


def row(text, cy, w=0.28, h=0.023, conf=1.0):
    return blk(text, cy, 0.525, w, h, conf)


TITLE = blk("Elemental Skill: II", 0.654, 0.5247, 0.137, h=0.026)
PAGER = blk("3/5", 0.286, 0.4869, 0.025, h=0.018)
CLOSE = blk("• Close", 0.211, 0.4751, 0.054, h=0.029)
# the shoulder-button glyphs flanking the pager, read as text
L1 = blk("L1", 0.286, 0.4448, 0.015, h=0.018, conf=0.5)
UID = blk("UID: 100000000", 0.013, 0.875, 0.094, h=0.021)
CHROME = [PAGER, CLOSE, L1, UID]

BODY = [row("When Aldric uses his Elemental Skill, he gathers a", 0.597),
        row("number of stacks of \"Echo\" and \"Refrain,\" raising", 0.570),
        row("the Anemo and Geo DMG dealt by every", 0.539, w=0.24),
        row("character in the party.", 0.511, w=0.13)]


def page(*extra, title=TITLE, body=BODY, chrome=CHROME):
    return [title] + list(body) + list(extra) + list(chrome)


# The long page: ten whole rows and an eleventh drawn half under the fade
# at the viewport's foot — measured box bottom y=0.3359, h=0.016.
LONG = [row(f"row number {i} of a long page that scrolls", 0.597 - 0.0254 * i)
        for i in range(10)]
CLIPPED = blk("character in the nartv.", 0.3439, 0.5262, 0.126, h=0.016)


def test_page_is_read_title_first():
    got = GENSHIN.classify_infoscreen(page())
    assert got == ["Elemental Skill: II."] + [b["text"] for b in BODY], got


def test_reader_page_is_the_pager():
    assert GENSHIN.reader_page(page()) == "3/5"
    assert GENSHIN.reader_page(page(chrome=[
        blk("5/5", 0.286, 0.4884, 0.022, h=0.021), CLOSE, UID])) == "5/5"


def test_pages_with_the_same_wording_have_different_keys():
    """The reason reader_page exists: live.py dedupes within a page, and
    these two titles are 0.97 alike to its fuzzy matcher."""
    p2 = page(title=blk("Elemental Skill: I", 0.654, 0.5247, 0.131, h=0.026),
              chrome=[blk("2/5", 0.286, 0.4869, 0.025, h=0.018), CLOSE, UID])
    assert GENSHIN.reader_page(p2) != GENSHIN.reader_page(page())
    assert GENSHIN.classify_infoscreen(p2)[0] == "Elemental Skill: I."


def test_row_under_the_bottom_fade_is_deferred():
    got = GENSHIN.classify_infoscreen(page(body=LONG + [CLIPPED]))
    assert got is not None and len(got) == 11, got
    assert not any("nartv" in t for t in got), got


def test_close_with_the_glyph_merged_in():
    got = GENSHIN.classify_infoscreen(page(chrome=[
        PAGER, blk("◯ Close", 0.211, 0.4740, 0.058, h=0.029), UID]))
    assert got and got[0] == "Elemental Skill: II.", got


def test_text_off_the_column_edge_is_not_read():
    """A stray glyph read off the clip, level with the first row — left of
    the band, so it can't pull that row off the column edge either."""
    stray = blk("R", 0.601, 0.2166, 0.010, conf=0.5)
    got = GENSHIN.classify_infoscreen(page(stray))
    assert got == ["Elemental Skill: II."] + [b["text"] for b in BODY], got


def test_mid_page_turn_is_not_read():
    """The frame caught mid page-turn: the new page's rows slide in with
    their left edges scattered right of the column (measured 0.591-0.650)
    and read as fragments. Nothing on the edge, nothing read."""
    sliding = [blk("her Elemen IS", 0.598, 0.650, 0.102),
               blk("P st\" state, perio", 0.567, 0.653, 0.099),
               blk("we Horn of Springs Call to atu", 0.540, 0.591, 0.167)]
    assert GENSHIN.classify_infoscreen(page(body=sliding)) is None


def test_not_without_its_chrome():
    # a Close button alone is an ordinary popup
    assert GENSHIN.classify_infoscreen(page(chrome=[CLOSE, UID])) is None
    # an N/M count alone is a stack or a progress readout
    assert GENSHIN.classify_infoscreen(page(chrome=[PAGER, UID])) is None
    # a Close that is a longer label is not the button
    assert GENSHIN.classify_infoscreen(page(chrome=[
        PAGER, blk("Close all tabs", 0.211, 0.46, 0.08), UID])) is None
    # a pager that isn't one
    assert GENSHIN.classify_infoscreen(page(chrome=[
        blk("7/5", 0.286, 0.4869, 0.025, h=0.018), CLOSE, UID])) is None
    assert GENSHIN.reader_page(page(chrome=[CLOSE, UID])) is None


def test_not_without_a_title_or_prose():
    assert GENSHIN.classify_infoscreen(page(title=blk(
        "Elemental Skill: II", 0.654, 0.30, 0.137, h=0.026))) is None
    assert GENSHIN.classify_infoscreen(page(body=[
        row("ATK 1234 / 5678", 0.597, w=0.09)])) is None


def test_star_rail_never_reads_it():
    assert HSR.classify_infoscreen(page()) is None
    assert HSR.reader_page(page()) is None


def test_dialogue_and_articles_are_page_none():
    """Screens that aren't paged all share page None, one dedupe set —
    exactly what the reader did before pages existed."""
    dialogue = [blk("Paimon", 0.235, 0.47, 0.06, h=0.03),
                blk("Let's go see what's over there!", 0.19, 0.38, 0.24),
                blk("Auto", 0.067, 0.83, 0.03), UID]
    assert GENSHIN.reader_page(dialogue) is None
    assert GENSHIN.classify_infoscreen(dialogue) is None


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok    {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL  {name}: {e}")
    sys.exit(1 if failed else 0)
