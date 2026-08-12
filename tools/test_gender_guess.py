"""Pins the auto-cast gender guess — documented gender beats name shape.

Session hoyovoice-20260812-084224 auto-cast Paimon as am_liam ("[auto-cast]
Paimon → am_liam (male guess)"): the guess was a name-shape suffix
heuristic and nothing else, so neither the roster's documented genders nor
an NPC table ever got a vote — "-on" is not a feminine suffix, and Genshin's
most common speaker read in a male voice until recast by hand. This file
keeps the lookup order fixed: settings.genders, then the shipped NPC table,
then — only for genuinely unknown names — the suffix guess.

    python tools/test_gender_guess.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live                                    # noqa: E402

fails = []


def check(want, got, why):
    if want != got:
        fails.append(f"  want {want}, got {got} — {why}")


# --- the reported failure ---------------------------------------------------
check("female", live.guess_gender("Paimon"),
      "Paimon is female; the -on suffix guess must not win")
# OCR case jitter must not lose the entry
check("female", live.guess_gender("PAIMON"), "case jitter keeps the entry")
# a nameplate's trailing quote glyph strips before the lookup
check("female", live.guess_gender('Paimon"'), "trailing quote stripped")

# --- documented beats heuristic in the other direction too ------------------
live.VOICES.setdefault("settings", {}).setdefault(
    "genders", {})["Venti"] = "male"
check("male", live.guess_gender("Venti"),
      "roster says male; the -i suffix heuristic says female and must lose")
live.VOICES["settings"]["genders"].pop("Venti")

# --- the shipped NPC table beyond Paimon ------------------------------------
check("male", live.guess_gender("Enjou"), "NPC table: Enjou")
check("female", live.guess_gender("Katheryne"),
      "Katheryne ends -yne, which the suffix list would call male")

# --- unknown names still get the name-shape guess ---------------------------
check("female", live.guess_gender("Stella"), "unknown -a name guesses female")
check("male", live.guess_gender("Bartholomew"), "unknown name guesses male")

if fails:
    print(f"FAIL ({len(fails)})")
    print("\n".join(fails))
    sys.exit(1)
print("gender guess ok")
