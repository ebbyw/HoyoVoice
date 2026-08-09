#!/usr/bin/env python3
"""Keep OCR garbage out of the casting table.

Casting is append-only in practice: an auto-cast row lives in voices.json
until someone deletes it by hand, so a speaker slot that once read `iii`
or `LV. -255771/25577` (both from real Windows session logs) leaves a
row that can never match a real nameplate again — and claims a voice
from the auto-cast pool while doing it.

The filter runs at AUTO-CAST time, not in the plate slot, and that
placement is the decision this module exists to record:

  * Genshin uses `???` as the literal nameplate of a not-yet-named
    character, and Star Rail has `March 7th`. Geometry-band filtering of
    "implausible" plates would eat real speakers, and a rejected plate
    can silence a line — the one error this project treats as worse than
    any talk-over.
  * A junk name refused here still SPEAKS, in the narrator's voice; all
    it is refused is a permanent casting row and a pooled voice. If the
    filter is ever wrong about a real character, the line is still read
    and casting them by hand overrides the filter entirely — live.py
    consults the cast table before this ever runs.

Rules are the classes actually seen in session logs, nothing broader.
Every rule is pinned with the real strings in tools/test_casting_filter.py.
"""
_QUOTES = "\"'“”‘’"


def canonical_quotes(name):
    """OCR reads the opening quote of a quoted nameplate with the wrong
    glyph often enough that `'Tenoyollotzin"` auto-cast as a separate
    character from `"Tenoyollotzin"` (real log, two rows, two voices).
    If BOTH ends are quote glyphs — any quote glyphs — the plate was a
    quoted name: canonicalize both to double quotes so the quoting class
    is stable however OCR drew them. A quote on only one end is left
    alone; that's a real apostrophe or a genuinely clipped read."""
    if len(name) >= 2 and name[0] in _QUOTES and name[-1] in _QUOTES:
        return '"' + name[1:-1] + '"'
    return name


def junk_speaker(name):
    """True if this speaker must never earn a casting row.

    The caller speaks the line as the narrator instead. Kept deliberately
    narrow: `Crafting Bench` is lexically indistinguishable from the real
    NPC `Strange Guard`, so menu banners are NOT this module's problem —
    the profiles' menu detection is what keeps those screens from being
    read at all."""
    core = name.strip().strip(_QUOTES).strip()
    letters = [c for c in core if c.isalpha()]
    digits = sum(c.isdigit() for c in core)
    # `???`, `85877`, `L1`, `255771/25577`: a name needs at least two
    # letters. (`???` is a real Genshin plate — its lines still read, in
    # the narrator's voice, which is the right voice for an unnamed one.)
    if len(letters) < 2:
        return True
    # `Lv. 90`, `1v.90 2557`, `06 25577-1/25577`: HUD readouts are digit-
    # heavy where names are letter-heavy. >= not >, so a 50/50 string is
    # junk; `March 7th` (1 digit, 7 letters) clears it with room.
    if digits >= len(letters):
        return True
    # `Liv, 9.` and `255771/25577`: nameplates never carry commas or
    # slashes — those come from the HP readout and item counters.
    if "," in core or "/" in core:
        return True
    # `iii`: one letter of the alphabet, repeated. No plate looks like
    # that; a half-drawn row caught mid-scroll does.
    if len(set(c.lower() for c in letters)) == 1:
        return True
    # `dii`, `fum`, `hum`: both games draw every nameplate with a capital
    # first letter; an all-lowercase read is a fragment of a word, not a
    # name. If a future game ever lowercases a real plate ("il Dottore"
    # style), the line still reads — narrator-voiced — and a manual cast
    # row ends the argument.
    first_alpha = next((c for c in core if c.isalpha()), "")
    if first_alpha.islower():
        return True
    return False
