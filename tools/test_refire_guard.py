"""Pins that a line left on screen is not re-fired when its nameplate
read flickers, and that two characters saying one line are both read.

The flicker is real: Vision read the plate "Ebby" as Cyrillic "ЕЬЬу" two
seconds after the latin read, the line under it unchanged (2026-08-12
17:26). With the speaker part of the re-fire guard and window_verdict
same-character only, every flip between the two reads sent the static line
through the gate again — and the game's voiceover long over, the gate
spoke it, over and over, for as long as the player idled on it.

Run directly or under pytest:

    python tools/test_refire_guard.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live                                    # noqa: E402

LINE = live.normalize_text("Placeholder line the player idles on.")
OTHER = live.normalize_text("A different placeholder line.")


def test_static_line_flicker_is_blocked():
    fired = ("Ebby", LINE)
    # the plate read flips while the text never leaves the screen
    for spk in ("ЕЬЬу", "Ebby", "ЕЬЬу", "", "Ebby"):
        assert live.refire_blocked((spk, LINE), fired, text_left=False), spk


def test_second_character_same_line_is_read():
    # re-typed for the second speaker: the text left the screen first
    assert not live.refire_blocked(("Paimon", LINE), ("Ebby", LINE),
                                   text_left=True)


def test_same_character_same_line_still_blocked_after_gap():
    for spk in ("Ebby", "", "Ebb"):
        assert live.refire_blocked((spk, LINE), ("Ebby", LINE),
                                   text_left=True), spk


def test_different_text_never_blocked():
    for left in (False, True):
        assert not live.refire_blocked(("Ebby", OTHER), ("Ebby", LINE),
                                       text_left=left)
    assert not live.refire_blocked(("Ebby", LINE), None, text_left=False)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
