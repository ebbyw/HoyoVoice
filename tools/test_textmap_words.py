"""Pins the word scan — what counts as a word the synthesizer gets wrong.

The scan is only worth running if it is quiet about ordinary English, so the
cases below are half true positives and half silence. The true positives are
not invented: every one is an entry pronounce_names.py already ships, with
the reading that was measured when it was written. If the scan cannot find
the faults somebody already found by ear, it will not find the ones nobody
has heard yet.

The silences matter as much. Two transcriptions of the same word disagree
constantly about stress, reduction and dialect — the first cut of this
reported 8,349 English words as faults — and each entry here is one of the
shapes that noise takes.

Needs misaki (the g2p Kokoro runs); no dump and no network. Run directly or
under pytest:

    python tools/test_textmap_words.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import textmap_words as tw                          # noqa: E402

# Words the two engines really do read differently — wrong on Windows, right
# on macOS. All four are TERMS entries, put there after someone heard them.
SPLIT = [
    ("shaman", "ʃˈɑmən", "ʃˈæmən"),                 # the salmon vowel
    ("Archon", "ˈɑɹkɑn", "ˈɑɹʧˌɔn"),                # the ch of church
    ("phlogiston", "flOʤˈɪstən", "flˈɑʤɪstən"),
    ("Gilgamesh", "ɡˈɪlɡəmˌɛʃ", "ɡˈɪlɡAməʃ"),
]

# Every one of these is two spellings of the same reading. Left in, they bury
# the list: "who", "how" and "why" are among the twenty most common words in
# either dump.
QUIET = [
    ("the", "ði", "ðə"),                            # reduction
    ("not", "nˌɑt", "nˈɑt"),                        # stress mark only
    ("want", "wˈɑnt", "wˈɔnt"),                     # cot/caught
    ("character", "kˈɛɹəktəɹ", "kˈæɹɪktəɹ"),        # trap/dress
    ("expect", "ɪkspˈɛkt", "ɛkspˈɛkt"),             # unstressed prefix
    ("mention", "mˈɛnʧᵊn", "mˈɛnʃən"),              # misaki's -tion
    ("around", "əɹˈWnd", "əɹɹˈWnd"),                # espeak's doubled r
    ("situation", "sˌɪʧəwˈAʃən", "sˌɪʧuˈAʃən"),     # a glide, spelled
    ("increased", "ɪnkɹˈist", "ɪŋkɹˈist"),          # n before a velar
    ("drawing", "dɹˈYŋ", "dɹˈɔɪŋ"),                 # one diphthong, two ways
    ("opportunity", "ˌɑpəɹtˈunəɾi", "ɑpəɹtˈunᵻɾi"),
]

# (word, espeak reading, a tell it must produce)
TELLS = [
    ("Xiao", "zˈIəˌO", "x → z/ks"),
    ("Feixiao", "fAksˈɪW", "x → z/ks"),
    ("Qiqi", "kˈɪki", "q → k"),
    ("Zhongli", "ʒˈɑŋɡli", "zh → ʒ"),
    ("Shenhe", "ʃˈɛnh", "final e dropped"),
    ("Fatui", "fˈæɾui", "flat a"),
    ("Fatui", "fˈæɾui", "t flapped"),
    ("Narukami", "nˌɑɹɹukˈɑmi", "doubled r"),
    ("Tumaini", "tˈumAni", "ai → /eɪ/"),
    ("Hmph", "ˌAʧˌɛmpˌiˈAʧ", "spelled out"),
]

# An English x or q is not a pinyin one. The /ks/ of "exactly" and the /kw/
# of "request" are exactly right, and reporting them put every "expect",
# "explain" and "unique" in the dump on the list.
# (word, espeak reading, a tell it must NOT produce)
NO_TELL = [
    ("exactly", "ɪɡzˈæktli", "x → z/ks"),
    ("explain", "ɪksplˈAn", "x → z/ks"),
    ("example", "ɪɡzˈæmpəl", "x → z/ks"),
    ("unique", "junˈik", "q → k"),
    ("request", "ɹᵻkwˈɛst", "q → kw"),
]


def check():
    bad = 0
    for word, misaki, espeak in SPLIT:
        if not tw.disagree(misaki, espeak):
            print(f"MISSED  {word}: {misaki} vs {espeak} read as one word")
            bad += 1
    for word, misaki, espeak in QUIET:
        why = tw.disagree(misaki, espeak)
        if why:
            print(f"NOISE   {word}: {misaki} vs {espeak} reported {why}")
            bad += 1
    for word, phones, tell in TELLS:
        got = tw.tells(word, phones)
        if tell not in got:
            print(f"NO TELL {word}: {phones} gave {got}, wanted {tell!r}")
            bad += 1
    for word, phones, tell in NO_TELL:
        got = tw.tells(word, phones)
        if tell in got:
            print(f"NOISE   {word}: {phones} reported {tell!r}")
            bad += 1
    return bad


def test_word_scan():
    assert check() == 0


if __name__ == "__main__":
    n = check()
    total = len(SPLIT) + len(QUIET) + len(TELLS) + len(NO_TELL)
    print(f"{total - n}/{total} ok")
    sys.exit(1 if n else 0)
