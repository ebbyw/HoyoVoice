#!/usr/bin/env python3
"""Pin the junk-casting filter (tools/casting_filter.py).

The junk side is the literal strings that reached the speaker slot in
real Windows session logs; the name side is every shape of real
nameplate both games have actually drawn. A rule change that fails
either side is rediscovering a mistake that was already paid for.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from casting_filter import canonical_quotes, junk_speaker  # noqa: E402

# From hoyovoice-20260807-223738.log and the 20260809 session: HUD
# readouts, item counters, and half-drawn readable rows that reached the
# speaker slot.
JUNK = [
    "iii", "dii", "???", "L1", "255771/25577", "85877",
    "Lv. 90", "Liv, 9.", "1v.90 2557", "06 25577-1/25577",
    "LV. -255771/25577", "fum", "hum",
]

# Real nameplates, chosen for being the closest calls each rule has:
# March 7th carries a digit, "Tenoyollotzin" is quoted, Mr. IX repeats a
# letter inside a longer name, Dan Heng • Imbibitor Lunae carries chrome
# punctuation, ??? is deliberately ON the junk side (it reads as the
# narrator — the right voice for a character the game isn't naming yet).
NAMES = [
    "Paimon", "March 7th", '"Tenoyollotzin"', "Mysterious Goldy",
    "Strange Guard", "Mr. IX", "Dan Heng • Imbibitor Lunae",
    "Katheryne", "Yae Miko", "Enjou", "Bibi",
]


def test_junk_is_junk():
    for s in JUNK:
        assert junk_speaker(s), f"should be junk: {s!r}"


def test_names_are_names():
    for s in NAMES:
        assert not junk_speaker(s), f"should be castable: {s!r}"


def test_quote_canonicalization():
    # the real pair from the 20260809 casting table: OCR read the opening
    # double quote as a single, and the plate cast as a second character
    assert canonical_quotes("'Tenoyollotzin\"") == '"Tenoyollotzin"'
    assert canonical_quotes('"Tenoyollotzin"') == '"Tenoyollotzin"'
    assert canonical_quotes("“Tenoyollotzin”") == '"Tenoyollotzin"'
    # one-ended quotes are apostrophes or clipped reads — untouched
    assert canonical_quotes("N'oubliez") == "N'oubliez"
    assert canonical_quotes("Paimon") == "Paimon"
    assert canonical_quotes("") == ""


if __name__ == "__main__":
    test_junk_is_junk()
    test_names_are_names()
    test_quote_canonicalization()
    print("all casting-filter tests passed")
