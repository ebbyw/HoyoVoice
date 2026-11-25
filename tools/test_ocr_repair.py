"""Pins post-OCR run-on repair, lexicon repair, and variant voting (live.py).

These paths target Windows RapidOCR failure modes: 3-way word fusions,
sentence-initial capitalized fusions, 1-edit proper-noun slips (where the
Windows daemon ignores custom_words.txt), and 1-char jitter on the firing
frame that used to exclude clean earlier sightings from the vote.

Run directly or under pytest:

    python tools/test_ocr_repair.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("HOYOVOICE_BACKEND", "replay")

import live  # noqa: E402

# Realistic Zipf frequencies for synthetic wordfreq testing on macOS
# (where wordfreq is intentionally not installed).
FAKE_ZIPF = {
    "the": 7.7, "i": 7.3, "and": 7.5, "to": 7.4, "a": 7.3, "of": 7.4,
    "in": 7.2, "is": 7.0, "it": 6.9, "we": 6.6, "you": 6.8, "are": 6.5,
    "not": 6.6, "for": 7.0, "its": 6.1, "this": 6.7, "that": 6.9,
    "think": 6.0, "know": 6.1, "dont": 5.8, "worry": 5.2, "mercy": 4.4,
    "informant": 3.7, "thing": 5.8, "bring": 5.4, "going": 6.0, "be": 6.8,
    "wish": 5.2, "power": 5.7, "star": 5.1, "light": 5.4, "take": 6.0,
    "all": 6.5, "i'll": 6.2, "really": 6.1, "here": 6.2, "well": 6.2,
    "lane": 4.8, "hello": 5.0, "right": 6.4, "now": 6.5,
}


def fake_zipf(word, lang="en"):
    return FAKE_ZIPF.get(word.lower(), 0.0)


def _with_zipf(fn):
    def wrapper():
        saved_zipf = live._zipf
        saved_chars = dict(live.VOICES.get("characters", {}))
        saved_settings = dict(live.VOICES.get("settings", {}))
        live._zipf = fake_zipf
        live._PROPER_CACHE["key"] = None
        try:
            fn()
        finally:
            live._zipf = saved_zipf
            live.VOICES["characters"] = saved_chars
            live.VOICES["settings"] = saved_settings
            live._PROPER_CACHE["key"] = None
    wrapper.__name__ = fn.__name__
    return wrapper


@_with_zipf
def test_runon_2way_3way_and_sentence_initial():
    assert live.repair_runons("mercyis here") == "mercy is here"
    assert live.repair_runons("thingandbring it") == "thing and bring it"
    assert live.repair_runons("goingtobe fine") == "going to be fine"
    # sentence-initial function-word fusions split cleanly
    assert live.repair_runons("Theinformant is here.") == "The informant is here."
    assert live.repair_runons("Well. Ithink we know.") == "Well. I think we know."
    assert live.repair_runons("Weare here.") == "We are here."
    # mid-sentence capitals AND sentence-initial invented compounds stay intact
    assert live.repair_runons("Use Wishpower now.") == "Use Wishpower now."
    assert live.repair_runons("Wishpower is real.") == "Wishpower is real."
    assert live.repair_runons("Starlight shines.") == "Starlight shines."


@_with_zipf
def test_lexicon_repair_unique_1_edit_only():
    live.VOICES["characters"] = {
        "Sparxie": {"voice": "af_nova", "speed": 1.0},
        "Paimon": {"voice": "af_sky", "speed": 1.0},
        "Aventurine": {"voice": "am_liam", "speed": 1.0},
        # Ambiguous pair: two names 1 edit from "Kaelan"
        "Kaelen": {"voice": "am_eric", "speed": 1.0},
        "Kaelin": {"voice": "af_bella", "speed": 1.0},
    }
    live._PROPER_CACHE["key"] = None
    assert live.repair_lexicon("Hello Sparxile!") == "Hello Sparxie!"
    assert live.repair_lexicon("Paimen knows.") == "Paimon knows."
    assert live.repair_lexicon("Ask Aventurlne.") == "Ask Aventurine."
    # Real English words and ambiguous matches are never rewritten
    assert live.repair_lexicon("Hello here.") == "Hello here."
    assert live.repair_lexicon("Ask Kaelan.") == "Ask Kaelan."


@_with_zipf
def test_best_variant_recovers_clean_read_across_jitter():
    # Frame 1 clean, Frame 2 jittered and tripped stabilization
    clean = "I'll take it all here right now."
    jitter = "I'u take it all here right now."
    variants = [(clean, 0.96), (jitter, 0.87)]
    got = live.best_variant(variants, live.normalize_text(jitter))
    assert got == clean, f"expected clean frame, got {got!r}"

    # Even with equal confidence, text_quality prefers "I'll" over "I'u"
    variants_eq = [(clean, 0.90), (jitter, 0.90)]
    got_eq = live.best_variant(variants_eq, live.normalize_text(jitter))
    assert got_eq == clean, f"expected I'll, got {got_eq!r}"


def test_best_variant_uses_confidence_without_wordfreq():
    saved = live._zipf
    live._zipf = None
    try:
        clean = "I'll take it all here right now."
        jitter = "I'u take it all here right now."
        variants = [(clean, 0.99), (jitter, 0.72)]
        got = live.best_variant(variants, live.normalize_text(jitter))
        assert got == clean
    finally:
        live._zipf = saved


def main():
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    print("all ocr-repair tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
