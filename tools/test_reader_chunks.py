"""Pins how a readable page is cut for the reading pump.

The contract the pump depends on: the FIRST chunk is a single sentence
(the first sound costs one sentence's synth, not a page's), later chunks
pack whole sentences to ~240 chars, no text is lost or reordered, and
every boundary is a sentence end — a chunk handoff must land where a
pause belongs. Run directly or under pytest:

    python tools/test_reader_chunks.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live                                    # noqa: E402

PAGE = ("Along with Divinity: Prologue. "
        "When our perceptions are unfettered by archons and churches, we "
        "shall learn that the people of Mondstadt preserved their culture. "
        "The surplus grain produced became their source of brews, and the "
        "brews further nourished their easygoing temperament. "
        "But I do not intend to make my readers think that we could do "
        "without archons. "
        "The answer would be no. "
        "Mondstadt is an inland city and would have struggled to provide "
        "for itself if not for the grace of Barbatos. "
        "It was the power of Barbatos that changed everything.")


def main():
    bad = 0

    def check(name, ok):
        nonlocal bad
        if not ok:
            print(f"FAIL {name}")
            bad += 1

    chunks = live.reader_chunks(PAGE)
    # the title row gets its period appended upstream, so the first
    # sentence — and with it the first synth — is the short title alone
    check("first chunk is the first sentence alone",
          chunks[0] == "Along with Divinity: Prologue.")
    check("nothing lost or reordered", " ".join(chunks) == PAGE)
    check("later chunks pack several sentences", len(chunks) < 7)
    check("every chunk ends on a sentence boundary",
          all(c[-1] in ".!?…\"'" for c in chunks))
    # an unfinished sentence at the clip edge still comes through — it is
    # the page's tail today exactly as it was as one utterance
    tail = live.reader_chunks("A short page. And then the scroll cut this")
    check("a clipped tail is kept",
          " ".join(tail).endswith("the scroll cut this"))
    check("a one-sentence page is one chunk",
          live.reader_chunks("Just this.") == ["Just this."])

    total = 6
    print(f"{total - bad}/{total} ok")
    return 1 if bad else 0


def test_reader_chunks():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
