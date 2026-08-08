"""Pins the spoken-form substitution — what the TTS hears vs. what we log.

The case rule is the part that can bite silently: matching is loose so OCR
case jitter can't miss a name, which means a name that is also an ordinary
word would be respelled in ordinary prose. Run directly or under pytest:

    python tools/test_pronunciations.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live                                    # noqa: E402

CASES = [
    # (line, what the synthesizer should hear)
    ("Xiao and Qiqi found Zhongli.", "Shyow and Chee-chee found Jong-lee."),
    # OCR case jitter must not lose a name
    ("xiao and QIQI arrived", "Shyow and Chee-chee arrived"),
    # word-bounded: possessives carry, substrings don't
    ("Qiqi's herbs", "Chee-chee's herbs"),
    ("Xiaolong is not a character", "Xiaolong is not a character"),
    # pronunciations_exact: the character, not the pastime
    ("Gaming brought the soup.", "Gah-ming brought the soup."),
    ("I spent all night gaming.", "I spent all night gaming."),
]


def main():
    bad = 0
    pron = live.VOICES.get("settings", {}).get("pronunciations", {})
    if not pron:
        print("FAIL no pronunciations configured — run tools/pronounce_names.py --write")
        return 1
    for line, want in CASES:
        got = live.spoken_form(line)
        if got != want:
            print(f"FAIL {line!r}\n  want {want!r}\n  got  {got!r}")
            bad += 1
    exact = live.VOICES["settings"].get("pronunciations_exact", [])
    for name in exact:
        if name not in pron:
            print(f"FAIL {name!r} is in pronunciations_exact with no spoken form")
            bad += 1
    print(f"{len(CASES) + len(exact) - bad}/{len(CASES) + len(exact)} ok")
    return 1 if bad else 0


def test_pronunciations():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
