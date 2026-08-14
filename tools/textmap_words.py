#!/usr/bin/env python3
"""Find the words in a TextMap dump the synthesizer is going to get wrong.

    python tools/textmap_words.py                    # every map in voices.json
    python tools/textmap_words.py MAP --top 80
    python tools/textmap_words.py MAP --class split  # the Windows-only ones

tools/pronounce_names.py fixes the names we already KNOW about — the playable
rosters, plus the terms someone noticed by ear in a session. That is the wrong
end of the problem: a name is noticed only after it has already been read
wrong, out loud, in the middle of a scene. The dumps hold the whole vocabulary
of both games, so the same fault can be found before it is ever spoken.

WHAT MAKES A WORD A CANDIDATE. Kokoro's g2p is misaki with an espeak fallback,
and a word takes one of two paths through it:

  * the LEXICON has it — 176k gold entries, 186k silver — and the reading is a
    human's, which is to say right. "Onigiri" and "Phlogiston" are both in it.
  * it isn't there, and espeak guesses from English spelling rules. Every
    entry in pronounce_names.FIXES is a word that took this path: "Xiao" is
    zˈIəˌO, "Fatui" is fˈæɾui, "Snezhnaya" is snˈɛʒnAə.

So the first class of candidate is simply the words that MISS the lexicon
(`oov`) — an invented name is exactly what letter rules mangle. The second is
subtler and would be very hard to catch by ear on one machine: a word the
lexicon HAS, whose espeak reading disagrees (`split`). macOS runs misaki and
hears it right; Windows runs kokoro-onnx, which is espeak alone, and hears
"SHAM-un" for shaman, "AR-chon" for Archon, "FLAH-jis-tun" for phlogiston.
All three are in TERMS with that history written next to them, and all three
fall out of this scan without anyone having to hear them first.

WHY IT IS A LIST AND NOT A PATCH. What comes out is ranked candidates with
both engines' readings side by side, not respellings. A respelling has to be
chosen against the traps pronounce_names.py's header documents — a chunk-final
"eh" is /eɪ/, an unreadable initial cluster gets spelled out letter by letter,
every hyphen chunk takes a stress of its own — and checked by ear. That is a
person's job; finding the word is not.

The last column is the reason to think the reading is wrong. For an `oov`
word it is read off the phonemes rather than guessed from the spelling: a
pinyin x that came out /z/, a final -e that vanished, the flat /æ/ of "fat"
where a foreign a should be open, espeak's doubled rhotic, a t flapped to
/ɾ/. For a `split` it is the disagreement itself, segment by segment. A word
with neither is still listed if it missed the lexicon — plenty of invented
names come out fine ("Klee" is klˈi) — but it sorts below the ones with
evidence against them, which is the difference between a list to read and a
list to work through.

Measured on the two dumps this install has (Genshin 585,555 entries, Star
Rail 449,617; 505,211 and 398,379 of them dialogue-shaped): 95,105 distinct
words, of which 7,553 are candidates seen five or more times — 6,104 that
miss the lexicon and 1,449 the two engines read differently. Pass
--names-only, which keeps the ones seen capitalised mid-sentence, and it is
5,748. The top of that list is Xianzhou, Fontaine, Mondstadt, Sumeru, Herta,
Akademiya, Stellaron, Amphoreus, Inazuma, Natlan — places, peoples and
factions that dialogue says constantly and no playable-character roster will
ever list.
"""
import argparse
import collections
import difflib
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import textmap                                       # noqa: E402

# Below this a word is not worth the column: "Ah", "Mm", "Ei" are read as
# interjections and handled as such in live._INTERJECTIONS.
MIN_LEN = 3
# A word this rare in a 500k-line dump is in one quest nobody is playing.
MIN_COUNT = 5
# Same tokenizing as pronounce_names.PLAIN_WORD, plus the apostrophe: a
# possessive is the same word ("Paimon's"), and splitting on it would count a
# name twice and report the stub.
WORD = re.compile(r"[A-Za-z][A-Za-z'\-]*")

# --- reading the phonemes -----------------------------------------------
# misaki's inventory, not IPA's: /eɪ/ is written A, /aɪ/ is I, /oʊ/ is O
# (see espeak.EspeakFallback.E2M, which is what makes the two engines'
# output comparable at all).
VOWELS = set("AIOWQiɪeɛæɑɔuʊʌəɜᵊᵻ")
# Differences that are transcription rather than pronunciation. Dialect
# first: cot and caught, trap and dress are one vowel to one engine and two
# to the other ("want" is wˈɑnt against wˈɔnt), and merging them is what
# leaves "shaman" (ʃˈɑmən against ʃˈæmən) standing as the real fault. Then
# the reductions — every schwa-ish vowel becomes one symbol, because the
# engines disagree about which to write in nearly every English word
# ("before" is bəfˈɔɹ against bᵻfˈɔɹ). Then the two that are assimilation:
# n before a velar, and a flapped t.
MERGE = {"ɔ": "ɑ", "æ": "ɛ", "ɪ": "i", "ʊ": "u",
         "ᵊ": "ə", "ᵻ": "ə", "ʌ": "ə", "ɜ": "ə",
         "ŋ": "n", "ɾ": "t",
         # misaki writes the -tion ending ʧ where espeak writes ʃ, in every
         # word that has one: "mention", "attention", "situation".
         "ʧ": "ʃ"}
# Segments whose presence, absence or exchange settles nothing: the schwa
# above, the vowels it alternates with in an unstressed syllable ("expect"
# is ɪkspˈɛkt to one engine and ɛkspˈɛkt to the other, "themselves" ðəm-
# against ðɛm-), the glides (misaki writes "situation" sˌɪʧəwˈAʃən where
# espeak writes sˌɪʧuˈAʃən — the same glide, spelled), and a stray h. A
# disagreement confined to these is not one anybody can hear.
IGNORE = set("əiuɛhwj")


# The diphthongs misaki writes as one symbol and espeak sometimes leaves as
# two — "drawing" is dɹˈYŋ against dɹˈɔɪŋ, which is one sound spelled twice.
DIPHTHONGS = [("ɔɪ", "Y"), ("aɪ", "I"), ("aʊ", "W"), ("eɪ", "A"), ("oʊ", "O")]


def sound(phones):
    """One engine's reading in a form the other's can be compared against:
    stress marks off, diphthongs written one way, dialect and reduction
    merged, espeak's doubled rhotic collapsed to the one r everybody says."""
    bare = re.sub(r"ɹɹ+", "ɹ", phones.replace("ˈ", "").replace("ˌ", ""))
    for two, one in DIPHTHONGS:
        bare = bare.replace(two, one)
    return "".join(MERGE.get(c, c) for c in bare)


def disagree(misaki, espeak_):
    """Where the two engines say a DIFFERENT word, rather than spelling the
    same one differently. Empty when they agree.

    Equality is far too strict to ask of two transcriptions. Stress alone
    reported every "who", "how" and "why" in the dump as a fault, because
    misaki gives a function word secondary stress where espeak gives it
    primary; reduction reported most of the rest. So the readings are
    aligned instead, and a run that differs only in the segments above is
    passed over. What survives is a consonant swapped for another consonant
    or a full vowel swapped for a full vowel — a /ʧ/ where Archon has a /k/,
    the /æ/ of "fat" where shaman has an open a, "phlogiston" started on /ɑ/
    where misaki starts it on /oʊ/.

    The pairs come back in the engines' own symbols, not the merged ones:
    the merge exists to decide what counts, and "ɑ→æ" is the thing a person
    then has to judge by ear.
    """
    a, b = sound(misaki), sound(espeak_)
    raw_a = misaki.replace("ˈ", "").replace("ˌ", "")
    raw_b = espeak_.replace("ˈ", "").replace("ˌ", "")
    out = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if op == "equal" or set(a[i1:i2] + b[j1:j2]) <= IGNORE:
            continue
        # sound() is one output symbol per input symbol, so the normalized
        # offsets index the raw readings too — apart from espeak's doubled
        # rhotic, which shifts them and is worth no report of its own.
        out.append(f"{raw_a[i1:i2] or '∅'}→{raw_b[j1:j2] or '∅'}"
                   if len(raw_a) == len(a) and len(raw_b) == len(b)
                   else f"{a[i1:i2] or '∅'}→{b[j1:j2] or '∅'}")
    return out


def tells(word, phones):
    """Why this reading looks wrong. Each entry is evidence in the PHONEMES,
    not a guess from the spelling — the same faults pronounce_names.py's
    entries were written against, in the order that file records them."""
    w, out = word.lower(), []
    bare = phones.replace("ˈ", "").replace("ˌ", "")
    if not (set(w) & set("aeiouy")):
        # espeak spells a vowelless word out: "Hmph" is ˌAʧˌɛmpˌiˈAʧ.
        return ["spelled out"]
    # pinyin x, not the English one: the x of "exactly" and "explain" is a
    # perfectly ordinary /ks/ and every one of them reported as a fault. What
    # is not ordinary is an initial x, or an x before i or u that isn't the
    # "ex-" prefix.
    if re.search(r"^x|[^e]x[iu]", w) and ("z" in bare or "ks" in bare):
        out.append("x → z/ks")                       # Xiao, Xiangling, Feixiao
    # likewise q: English q is always "qu" mid-word ("unique", "require"),
    # and an initial one is the invented kind ("Qiqi", "Qucusaur").
    if re.match(r"q", w) and "k" in bare:
        out.append("q → k" + ("w" if "kw" in bare else ""))
    if "zh" in w and "ʒ" in bare:
        out.append("zh → ʒ")                         # Zhongli
    if w.endswith("e") and not w.endswith(("ee", "ie", "oe", "ue")) \
            and bare and bare[-1] not in VOWELS:
        out.append("final e dropped")                # Shenhe, Seele
    if "æ" in bare and "a" in w:
        out.append("flat a")                         # Fatui, Nahida, Natlan
    if "ɾ" in bare and ("t" in w or "d" in w):
        out.append("t flapped")                      # Fatui
    if "ɹɹ" in bare:
        out.append("doubled r")                      # Narukami, Sumeru
    if "A" in bare and re.search(r"ai|ae|ei|ey|eigh", w):
        out.append("ai → /eɪ/")                      # Tumaini, Reignbow, Yae
    return out


class Reader:
    """The exact g2p Kokoro runs, plus the espeak half of it on its own.

    Both are needed: misaki's answer is what macOS says, the fallback's is
    what Windows says, and the gap between them is a whole class of fault
    that cannot be heard on one machine.
    """

    def __init__(self):
        from misaki import en, espeak
        self.espeak = espeak.EspeakFallback(british=False)
        self.g2p = en.G2P(trf=False, british=False, fallback=self.espeak)
        self.lex = self.g2p.lexicon

    def gold(self, word):
        """(the lexicon's own reading, is it tag-dependent) — (None, False)
        for a word the lexicon does not have.

        A tag-keyed entry is a word with two readings by part of speech
        ("use" is jˈus as a noun and jˈuz as a verb, "record" ɹˈɛkəɹd against
        ɹəkˈɔɹd). Which one is right depends on the sentence, so a
        single-word comparison against espeak can only report the coin flip;
        the caller drops them. No name in either game is one.
        """
        for form in (word, word.lower(), word.capitalize()):
            for table in (self.lex.golds, self.lex.silvers):
                got = table.get(form)
                if isinstance(got, dict):
                    return got.get("DEFAULT"), True
                if got:
                    return got, False
        return None, False

    def guess(self, word):
        """espeak's letter-rules reading — the Windows one."""
        return (self.espeak(SimpleNamespace(text=word))[0] or "")

    def read(self, word):
        """(misaki, espeak, kind) for one word — kind is "oov", "known" or
        "tagged" (see gold()).

        The lexicon is consulted directly where it can be, and the full g2p
        run only where it can't: an inflection reaches the lexicon through
        stemming ("monsters" is not an entry, "monster" is), and without that
        second pass every regular plural in the dump reports as invented.
        """
        gold, tagged = self.gold(word)
        if gold is None:
            phones, tokens = self.g2p(word)
            rating = tokens[0].rating if tokens else 0
            # rating 2 is the fallback's own — see EspeakFallback.__call__.
            if rating is None or rating <= 2:
                return phones, phones, "oov"
            gold = phones
        return gold, self.guess(word), "tagged" if tagged else "known"


def dialogue(path, nickname, everything=False):
    """The map's entries as they could appear on screen.

    textmap.variants() is what does the work — a raw entry is markup, gender
    branches and placeholders, and counting words in it would report {NICKNAME}
    and <color> as vocabulary. The length window is textmap's too: below it a
    line is "Yes.", above it the entry is an item description or a patch note,
    and neither is a line anybody's voice has to say.
    """
    raw = json.loads(Path(path).expanduser().read_text(encoding="utf-8",
                                                       errors="replace"))
    values = raw.values() if isinstance(raw, dict) else raw
    for v in values:
        if not isinstance(v, str):
            continue
        for s in textmap.variants(v, nickname):
            if everything or (textmap.MIN_CHARS <= len(textmap.key(s))
                              <= textmap.MAX_CHARS):
                yield s


def scan(paths, nickname, everything=False):
    """word → (times seen, times capitalised mid-sentence).

    The second number is what separates a name from a word that merely starts
    sentences: "But" is written with a capital 8,482 times in the Genshin
    dump and is never once a name. It is counted off the line rather than off
    the token list, because a sentence can end in the middle of one — after a
    "?" the next capital proves nothing.
    """
    seen = collections.Counter()
    mid = collections.Counter()
    for path in paths:
        for line in dialogue(path, nickname, everything):
            for m in WORD.finditer(line):
                w = m.group(0)
                seen[w] += 1
                before = line[:m.start()].rstrip(" \"'“”‘’(")
                # a dash counts as a break like a full stop: the games write
                # "Wait—Hmm" and an interrupted line starts a new sentence
                if w[:1].isupper() and before and before[-1] not in ".!?…—–-":
                    mid[w] += 1
    return seen, mid


def cleared():
    """Words a person has already ruled on and left without an entry.

    The scan is a list to work through, and a candidate that has been
    judged once should not come back the next time it is run — otherwise
    the floor never falls and every pass re-reads the same eighty words.
    pronounce_names.CLEARED is where that judgement lives, next to the
    entries and the reasons.
    """
    try:
        import pronounce_names
    except Exception:                                # noqa: BLE001
        return frozenset()
    return frozenset(getattr(pronounce_names, "CLEARED", ()))


def covered(word, spoken_form):
    """Already fixed — the word goes through the app's own substitution and
    comes out different. That covers the pronunciations map, the interjections
    ("Hmph" is respelled to "Humph" before it ever reaches the g2p) and the
    multi-word keys a plain `in` test would miss."""
    return spoken_form(word) != word


def load_spoken_form(voices):
    """live.spoken_form, pointed at the voices.json being audited.

    Imported rather than mirrored, unlike pronounce_names.check(): that one
    has to work on a machine where the app is the broken thing, this one
    already needs misaki loaded and has no such excuse to drift.
    """
    try:
        import live
    except Exception as e:                           # noqa: BLE001
        print(f"[no live.py: {e}] — nothing will be filtered as already fixed",
              file=sys.stderr)
        return lambda s: s
    path = Path(voices).expanduser()
    if path.exists():
        try:
            live.VOICES = json.loads(path.read_text())
        except ValueError:
            pass
    return live.spoken_form


def candidates(counts, mids, reader, spoken_form, min_count, min_len):
    """The words worth a person's attention, worst first."""
    out, done = [], cleared()
    for word, n in counts.most_common():
        if n < min_count:
            break
        if len(word) < min_len or word in done or covered(word, spoken_form):
            continue
        misaki, espeak_, kind = reader.read(word)
        if kind == "tagged":
            continue                                 # two readings by tag
        if word.isupper() and kind == "oov":
            # An all-caps word is normally read out as its letters, which is
            # right ("DMG" is dˌiˌɛmʤˈi, "ATK" ˌAtˌikˈA), and reporting every
            # one of them was noise. This used to skip them ALL — and hid the
            # case where an engine tries to SAY the acronym instead: espeak
            # reads "IPC" as ˈɪpk, three letters mashed into one syllable,
            # 3,004 times in the Star Rail dump, where misaki spells it out.
            # That is a `split` and is now reported; only the ones both
            # engines agree on are skipped.
            continue
        if kind == "oov":
            # both engines read it the same way and both are guessing; the
            # spelling is the only evidence there is.
            why = tells(word, espeak_)
        else:
            why = disagree(misaki, espeak_)
            if not why:
                continue                             # a word, read as one
        out.append(SimpleNamespace(
            word=word, count=n, mid=mids[word],
            cls="oov" if kind == "oov" else "split",
            misaki=misaki, espeak=espeak_, why=why))
    # evidence first: a word with a tell against it outranks a commoner one
    # the engines merely failed to find, and a `split` is wrong on a whole
    # platform by definition.
    out.sort(key=lambda c: (bool(c.why), c.count), reverse=True)
    return out


def report(rows, top):
    print(f"{'word':22} {'seen':>7} {'macOS (misaki)':24} "
          f"{'Windows (espeak)':24} why")
    for c in rows[:top]:
        print(f"{c.word:22} {c.count:>7} {c.misaki:24} {c.espeak:24}"
              f"{', '.join(c.why)}")
    n_split = sum(1 for c in rows if c.cls == "split")
    print(f"\n{len(rows)} candidates: {n_split} in the lexicon but read "
          f"differently by espeak (wrong on Windows only), "
          f"{len(rows) - n_split} not in it at all.")
    print("Respellings go in tools/pronounce_names.py — read its header "
          "first, then `python tools/pronounce_names.py` to check by ear.")


def main():
    ap = argparse.ArgumentParser(
        description="Find TextMap words the synthesizer will mispronounce.")
    ap.add_argument("maps", nargs="*",
                    help="dump files (default: settings.textmap in voices.json)")
    ap.add_argument("--voices", default=str(ROOT / "voices.json"))
    ap.add_argument("--nickname", default=None,
                    help="the player's in-game name (default: "
                         "settings.player_name)")
    ap.add_argument("--min-count", type=int, default=MIN_COUNT)
    ap.add_argument("--min-len", type=int, default=MIN_LEN)
    ap.add_argument("--top", type=int, default=60)
    ap.add_argument("--names-only", action="store_true",
                    help="only words seen capitalised mid-sentence")
    ap.add_argument("--class", dest="cls", choices=("oov", "split"),
                    help="one class of fault only")
    ap.add_argument("--all-entries", action="store_true",
                    help="count item descriptions and tooltips too, not just "
                         "dialogue-shaped entries")
    ap.add_argument("--json", action="store_true", help="machine-readable")
    args = ap.parse_args()

    settings = {}
    vpath = Path(args.voices).expanduser()
    if vpath.exists():
        settings = json.loads(vpath.read_text()).get("settings", {})
    maps = args.maps or list((settings.get("textmap") or {}).values())
    if not maps:
        raise SystemExit("no maps: pass one, or set settings.textmap in "
                         f"{vpath}")
    missing = [m for m in maps if not Path(m).expanduser().exists()]
    if missing:
        raise SystemExit(f"not found: {', '.join(missing)}")
    nickname = args.nickname
    if nickname is None:
        nickname = settings.get("player_name") or ""

    counts, mids = scan(maps, nickname, args.all_entries)
    # the player's own name is in every second line after substitution and is
    # not a word either game wrote
    for n in nickname.split():
        counts.pop(n, None)
    print(f"{len(counts)} distinct words in {len(maps)} map(s)",
          file=sys.stderr)
    reader = Reader()
    rows = candidates(counts, mids, reader, load_spoken_form(args.voices),
                      args.min_count, args.min_len)
    if args.names_only:
        rows = [c for c in rows if c.mid]
    if args.cls:
        rows = [c for c in rows if c.cls == args.cls]
    if args.json:
        print(json.dumps([vars(c) for c in rows[:args.top]], indent=2,
                         ensure_ascii=False))
        return 0
    report(rows, args.top)
    return 0


if __name__ == "__main__":
    sys.exit(main())
