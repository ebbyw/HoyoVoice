"""Pins the spoken-form substitution — what the TTS hears vs. what we log.

Names, interjections and stammers all go through this one path, because all
three are about what a line SOUNDS like rather than what it says: the log,
dedupe and casting keep "Shh" and "W-what" as the game wrote them.

Two rules bite silently. Name matching is loose so OCR case jitter can't miss
one, which means a name that is also an ordinary word would be respelled in
ordinary prose. And a stammer repair keys on the initial matching the word
after it, or it eats "X-ray" and "T-shirt". Run directly or under pytest:

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
    # Invented terms both engines read with the flat a of "fat"
    ("The Fatui hold the Northland Bank.",
     "The Fah-too-ee hold the Northland Bank."),
    ("A Fatuus stood guard.", "A Fah-too-oose stood guard."),
    # pronunciations_exact: the character, not the pastime
    ("Gaming brought the soup.", "Gah-ming brought the soup."),
    ("I spent all night gaming.", "I spent all night gaming."),

    # Interjections: the phonemizer spells these letter-by-letter, or picks
    # the wrong vowel. Same path as a respelling, for the same reason.
    ("Shh! Someone's coming.", "Shush! Someone's coming."),
    ("Tsk. Typical.", "Tisk. Typical."),
    # "Tch" is "T-C-H" on Windows, a bare ʧ on macOS — the same tut as Tsk
    ("Tch. Whatever.", "Tisk. Whatever."),
    ("Tchh, fine.", "Tisk, fine."),
    ("Uhm, I'm not sure.", "Um, I'm not sure."),
    ("Uhmm... maybe.", "Um... maybe."),
    ("Ugh, this is heavy.", "Ug, this is heavy."),
    # "Urgh" is ˈɜɹɡ — "erg", a word, not a groan
    ("Urgh… It all happened so fast.", "Ug… It all happened so fast."),
    ("Urrgh, my head.", "Ug, my head."),
    ("Aaah, that feels better.", "Ah, that feels better."),
    # "Pfft" is ˈft on its own, which is roughly the right noise. The "pfff"
    # respelling this list used to carry came out as "P-E-F-E-F".
    ("Pfft. As if.", "Pfft. As if."),

    # Stammers: a lone initial is read as the LETTER'S NAME —
    # "DOUBLE-YOU-what", "EN-no", "AY-ah" — unless it is spelled as a
    # syllable.
    ("W-what are you doing?", "Wuh-what are you doing?"),
    ("N-no, I won't.", "Nuh-no, I won't."),
    ("A-aah! Get away!", "Ah-ah! Get away!"),
    ("b-but why", "buh-but why"),
    # Genshin writes the stammer with an em dash. Same stammer, and the
    # respelling normalizes the dash to a plain hyphen.
    ("A—Ahh! Yes, uhm… Of course!", "Ah-Ah! Yes, um… Of course!"),
    ("W—what are you doing?", "Wuh-what are you doing?"),
    # the punctuation kind of dash is spaced, and never a stammer
    ("The vegetable — it is the eyes of the earth.",
     "The vegetable — it is the eyes of the earth."),
    # E/I/O already read as sounds, and every respelling tried was worse —
    # but the dash is still normalized, or espeak reads the em dash as
    # punctuation and the stammer becomes two words ("Aye. It's…")
    ("I-I don't know.", "I-I don't know."),
    ("O-okay then.", "O-okay then."),
    ("I—It's him!?", "I-It's him!?"),
    ("O—Okay then.", "O-Okay then."),
    # a whole onset stammers too, and is spelled out letter by letter
    # ("Wh-What's" → dˌʌbᵊljˌuˈAʧ—wˌʌts)
    ("Wh-What's going on?", "Whuh-What's going on?"),
    ("Sh-She's here.", "Shuh-She's here."),
    ("Th—That's it.", "Thuh-That's it."),
    ("Str-Strange…", "Struh-Strange…"),
    # an all-caps onset is read as letters again ("WHuh" → dˈʌbᵊljuhˌʌ)
    ("WH-WHAT!", "Whuh-WHAT!"),
    # a multi-letter onset carrying a vowel is a prefix, not a stammer
    ("Re-read the sign.", "Re-read the sign."),
    ("He is a co-conspirator.", "He is a co-conspirator."),
    ("The de-dented armor.", "The de-dented armor."),
    # not stammers: the letter doesn't match the word it precedes
    ("He bought a T-shirt.", "He bought a T-shirt."),
    ("The X-ray came back clear.", "The X-ray came back clear."),
    # (no name here on purpose: asserting a NEW table entry would fail every
    # install that hasn't re-run pronounce_names.py --write, and voices.json
    # is the user's file — a pull never updates it)
    ("Send an e-mail before we go.", "Send an e-mail before we go."),
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
