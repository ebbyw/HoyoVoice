"""Pins what the synthesizer is handed for a line that is more sound than
sentence.

"*cough*" is a noise the character makes, not a word: read as one it lands
somewhere between flat and comic. Asterisks have to survive OCR repair for
that to be actionable, without the decorative ones surviving with them, and
the log has to keep the line as the game wrote it either way. Run directly or
under pytest:

    python tools/test_stage_directions.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import live                                    # noqa: E402

# (what the game wrote, what the log keeps) — asterisks around a short phrase
# survive OCR repair; everything else asterisks are used for does not
OCR = [
    ("*cough* Anyway, where were we?", "*cough* Anyway, where were we?"),
    ("＊cough＊ Anyway.", "*cough* Anyway."),
    ("* sigh *", "*sigh*"),
    ("Huh!? You... You're Paimon!", "Huh!? You… You're Paimon!"),
    ("2 * 3 is 6", "2 3 is 6"),               # unpaired: decoration, dropped
    ("~*Hello*~", "*Hello*"),
]

# (line, the pieces synthesis runs) — against the SOUND_EFFECTS below
SOUND_EFFECTS = {"cough": "sounds/cough.wav", "sigh": "Ahem.", "gasp": ""}
PARTS = [
    ("*cough* Anyway.", [("play", "sounds/cough.wav"), ("say", "Anyway.")]),
    ("Well. *cough* Anyway.",
     [("say", "Well."), ("play", "sounds/cough.wav"), ("say", "Anyway.")]),
    ("*sigh* Fine.", [("say", "Ahem."), ("say", "Fine.")]),
    ("*gasp* Fine.", [("say", "Fine.")]),      # mapped to nothing: silent cut
    ("*yawn* Fine.", [("say", "yawn Fine.")]),  # unmapped: spoken as the word
    ("Nothing here.", [("say", "Nothing here.")]),
]

# (line, the one-string form the logs show as "synth heard") — a line the TTS
# path doesn't touch has to come back identical, or every log grows a
# duplicate of every line
FLATTENED = [
    ("*cough* Anyway.", "[sounds/cough.wav] Anyway."),
    ("Hello, you two. Is something the matter?",
     "Hello, you two. Is something the matter?"),
    ("", ""),
]


def main():
    bad = 0
    for raw, want in OCR:
        got = live.fix_ocr_text(raw)
        if got != want:
            print(f"FAIL ocr {raw!r}: want {want!r}, got {got!r}")
            bad += 1
    saved = live.VOICES.get("settings", {}).get("sound_effects")
    live.VOICES.setdefault("settings", {})["sound_effects"] = SOUND_EFFECTS
    try:
        for line, want in PARTS:
            got = live.speech_parts(line)
            if got != want:
                print(f"FAIL parts {line!r}: want {want}, got {got}")
                bad += 1
        for line, want in FLATTENED:
            got = live.tts_text(line)
            if got != want:
                print(f"FAIL flat {line!r}: want {want!r}, got {got!r}")
                bad += 1
    finally:
        if saved is None:
            live.VOICES["settings"].pop("sound_effects", None)
        else:
            live.VOICES["settings"]["sound_effects"] = saved
    total = len(OCR) + len(PARTS) + len(FLATTENED)
    print(f"{total - bad}/{total} ok")
    return 1 if bad else 0


def test_stage_directions():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
