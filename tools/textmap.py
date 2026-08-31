"""Snap a read line to the game's own text, when the player supplies it.

The recognizer's errors are small and local — "Ves." for "Yes.", "I'u take
it all" for "I'll take it all", a name spelled three ways in three frames —
and each one costs twice: the synthesizer says the wrong thing, and dedupe
sees a line it has never seen and reads it again. Both go away if the read
can be matched back to the line the game actually wrote.

That needs the game's dialogue strings, which are HoYoverse's and cannot
ship here. What ships is the matcher: point `settings.textmap` at a file
you extracted yourself and it is used; leave it unset and nothing changes.

    plain text   one line per entry
    JSON array   ["line", ...]
    JSON object  {"3821...": "line", ...}   (TextMap dumps look like this)

MATCHING. A full comparison against every line is far too slow at the size
these files run to (100k+ entries), so a query is narrowed first:

  * by LENGTH — a misread is close to the same length as its line, and the
    bound below is generous enough for a read that lost a whole word;
  * by TRIGRAM overlap — the shortlist is the entries sharing the most
    3-character sequences with the query, which is cheap set arithmetic and
    survives the kind of damage OCR does (a wrong letter kills 3 trigrams,
    not the line).

Only that shortlist is scored properly, and only the RAREST two dozen
trigrams of a query are walked: " th" is in half the map and its posting
list costs more than it tells us. Measured on a 100k-line map, that is
11ms a query against 66ms for the naive version — and it runs once per
line about to be spoken, not once per frame.

ACCEPTING. Three gates, and all of them matter. The score has to clear
`min_score`; it has to beat the runner-up by `min_margin`, because a line
that half the map resembles equally is exactly the case where the top match
is arbitrary; and every real word the read contains has to SURVIVE into the
match. That last one is what tells a repair from a substitution, and the
reasoning is below.

Measured first on the recorded sessions: 377 distinct lines as the map, 164
real misreads of them as queries. At a 0.82 score, 113 were repaired to
exactly the right line, 51 were refused, and NONE was snapped to the wrong
line. The catastrophic case on file — two dialogue rows fused and
interleaved — scores 0.57 against its own line and is among the refusals.
The top match is in fact right there, and it is still refused on purpose,
because nothing about a 0.57 acceptance generalizes to a bigger map.

WHAT A REAL MAP DID TO THAT. It generalized worse than feared. Across the
seven Windows sessions that ran a real 315,327-line Star Rail dump, the log
recorded 30 snaps that changed WORDS (punctuation-only repairs are not
logged). Read back by hand against the recordings, 23 of the 30 were the
wrong line — "We're a legitimate organization." became "We are a flat
organization", "Have some dignity!" became "Save her some dignity...",
"King Heartthrob!" became "Young Heartthrob". Each one is audible twice
over: the invented line is spoken, then the real line finishes typing,
fails to look like an extension of what was just said, and is spoken again.
That is the "it reads a different sentence, then corrects itself" report.

Nothing was wrong with the matcher; the map got 800 times bigger. At 315k
entries there is a plausible near-neighbour for almost every short line, so
a 0.84 match stopped being evidence of anything. Two gates were fitted to
those 30 pairs:

  * SCORE 0.90 rather than 0.82 — of the 23 wrong lines, 19 sat under 0.90,
    and only one genuine repair did.
  * WORD SURVIVAL — a real word the read contains, gone from the match,
    means the match is a different sentence rather than a repair of this
    one. OCR damage is character-level and lands on non-words ("gol" for
    "go", "Ves" for "Yes", a welded "mercyis"); it does not turn
    "legitimate" into "flat". A capitalised word mid-line is held to the
    same rule whatever its frequency, because a dropped name ("Ebby",
    "Ikhor") is the most costly word to lose and the least likely for OCR
    to have invented.

Together they leave 5 of the 7 real repairs and 1 of the 23 wrong lines.
The two repairs given up are cheap — one mispronounced word each, against
whole invented sentences — which is the trade this module has always made:
refusing is the safe answer, and speaking a misread beats speaking fiction.

`wordfreq` is a Windows-only dependency here (plans/PRE-MERGE.md says why,
and it is where the dumps are), so on macOS the word half of that gate
cannot run and only the name half does: 6 of the 7 repairs and 3 of the 23
wrong lines, measured the same way. Worth knowing, not worth fixing by
installing wordfreq on macOS — that would switch on a run-on repair which
was measured to be a no-op on Apple Vision output with a real false-
positive rate. Requiring EVERY lost token instead was measured too, and
costs four of the seven repairs to remove two wrong lines; not worth it.
"""
import difflib
import json
import re
import zlib
from array import array
from collections import Counter
from pathlib import Path

# A misread can lose or gain this share of a line's length before it stops
# being a candidate. Two dialogue rows fused into one lose about a third.
LEN_TOLERANCE = 0.35
# Entries scored properly per query. Wide enough that the right line is in
# it whenever trigram overlap ranks it anywhere near the top.
SHORTLIST = 40
# 0.82 on the 377-line calibration map; 0.90 since a real 315k-line dump
# showed what a map that size does to it (see the module docstring). 19 of
# the 23 wrong lines it snapped sat below 0.90, against one real repair.
MIN_SCORE = 0.90
MIN_MARGIN = 0.05
# A read word this common that the match does not have is a word the match
# REPLACED, not one OCR broke. Zipf 3.0 is "roughly one in a million words"
# — above it sit "shhh" (3.1) and "legitimate" (4.2), below it the damage
# OCR actually produces ("gol" 2.7, "ruti" 1.4, "jeither" 0.0).
LOST_WORD_ZIPF = 3.0
# Below this a token is punctuation debris or an apostrophe fragment ("d"
# from "Where'd"), not a word whose loss says anything.
LOST_WORD_MIN = 3
# Below this a line is too short to identify: "Yes.", "Mm-hmm.", "Oh?" are
# each a dozen other lines' equal.
MIN_CHARS = 12
# And above this it is not a dialogue line either: a real map is mostly
# item descriptions, skill tooltips and patch notes, and indexing them
# costs memory for entries no dialogue read can ever be confused with.
# The longest line either game has drawn in a recorded session is 199
# characters.
MAX_CHARS = 320
# Length bucket for the index, in characters. Small enough that a bucket is
# a thin slice of the map, wide enough that the length bound spans only a
# handful of them.
BUCKET = 16
# Query trigrams actually walked, rarest first (see candidates()).
RARE_GRAMS = 24
# Only every Nth trigram is indexed, chosen by a stable hash of the trigram
# itself so an entry and a query pick the SAME subset. A full index of the
# 397,952-line Genshin dump is 27M postings and ~870MB resident, which is
# not a reasonable price for a lookup; at 1-in-3 it is 9M and ~490MB, and
# repair quality measured identical on the 151 real misreads on file. A
# line of dialogue has ~100 trigrams, so a third of them is still 30-odd
# ways to find it.
SAMPLE = 3
# A posting list longer than this is a trigram that names nothing — every
# entry in the bucket has it — and walking it is the whole cost of a query.
MAX_POSTINGS = 3000

_WORD = re.compile(r"[^a-z0-9 ]+")
_TOKEN = re.compile(r"[A-Za-z][A-Za-z']*")

# Optional, exactly as in live.py: without it the word-survival gate cannot
# tell a real word from OCR debris, so it falls back to the one signal that
# needs no frequencies — a capitalised word mid-line is a name, and losing
# one is never a repair.
try:
    import functools

    from wordfreq import zipf_frequency
    _zipf = functools.lru_cache(maxsize=16384)(zipf_frequency)
except ImportError:                                   # pragma: no cover
    _zipf = None

# --- what a real TextMap dump contains that the screen never shows -------
# A map entry is not the line the game draws: it is the line before the
# runtime substitutes the player's name, picks a gender, and renders the
# rich text. Measured against the shipped Genshin dump (237,812 entries):
# 5,719 entries open with a '#' sentinel, 4,644 carry {NICKNAME}, 1,629 a
# {F#…}{M#…} pair, 1,210 a <color> span, 560 an escaped newline, 221 a
# {RUBY#…} annotation. Star Rail's (228,068) is the same story with more
# markup: 34,613 newlines, 14,498 <unbreak> spans, 13,467 <color>, 5,098
# <i>. Left alone, every one of those entries is unmatchable — the first
# run against the real map repaired NOTHING, because the lines it needed
# read "#The name's Pell, and this is {NICKNAME}." against a screen that
# says "The name's Pell, and this is Ebby." (shape real, prose invented)
_TAG = re.compile(r"</?[a-z][^>]*>")            # <color=…>, <i>, <unbreak>
# A ruby annotation is a GLOSS drawn above the word, not part of the line:
# "Kuu{RUBY#[S]Sea Lantern}tar" is drawn as "Kuutar". Keeping the gloss
# spliced it into the middle of the word ("KuuSea Lanterntar").
_RUBY = re.compile(r"\{RUBY[_A-Z]*#\[?[SE]?\]?[^}]*\}")
_GENDER = re.compile(r"\{([FM])#([^}]*)\}")
_LEFTOVER = re.compile(r"\{[^}]*\}")


def variants(text, nickname):
    """The forms of one map entry that could actually appear on screen.

    Usually one. A {F#…}{M#…} entry yields TWO — the game picks by the
    player's gender, and guessing wrong would leave that line unmatchable,
    where carrying both costs one more index entry. An entry still holding
    a placeholder after all this can never match anything drawn, so it is
    dropped rather than indexed as noise.
    """
    s = text.strip()
    if s.startswith("#"):
        s = s[1:]
    s = s.replace("\\n", " ").replace("\n", " ")
    s = _TAG.sub("", s)
    s = _RUBY.sub("", s)
    if nickname:
        s = s.replace("{NICKNAME}", nickname)
    out = [s]
    if _GENDER.search(s):
        out = [_GENDER.sub(lambda m: m.group(2) if m.group(1) == g else "", s)
               for g in "FM"]
    return [" ".join(v.split()) for v in out if not _LEFTOVER.search(v)]


def key(s):
    """Comparison form: lowercase, punctuation-free, single-spaced. OCR gets
    punctuation wrong constantly ("business!" for "business.") and that is
    not a difference worth failing a match over — the ACCEPTED text is the
    map's, punctuation included, so nothing is lost by ignoring it here."""
    return " ".join(_WORD.sub(" ", (s or "").lower()).split())


def trigrams(s):
    """The indexed trigrams of a string — a stable 1-in-SAMPLE subset.

    crc32 rather than hash(): Python randomizes string hashing per process,
    which would index one subset and look up another after a restart.
    """
    return {t for t in (s[i:i + 3] for i in range(len(s) - 2))
            if zlib.crc32(t.encode()) % SAMPLE == 0}


def _sentence_start(text, i):
    """Is the token at `i` opening a sentence? Then its capital is grammar.

    Quotes and brackets are skipped over, not treated as the sentence: the
    games open a great many lines with one.
    """
    j = i - 1
    while j >= 0 and text[j] in " \t\"'“”‘’([{<*—-":
        j -= 1
    return j < 0 or text[j] in ".!?…:;"


def lost_word(read, line):
    """A word the read has and the match dropped, or None if none did.

    The difference between repairing a line and replacing it. OCR breaks
    words into things that are not words — "gol", "Ves", "mercyis" — so a
    match that drops one of those is repairing damage. A match that drops
    "legitimate", "brought" or "Ebby" is a different sentence wearing the
    same opening, and speaking it puts words in a character's mouth that
    the game never wrote.

    Only losses count. A match that ADDS a word is the ordinary case of OCR
    having missed one ("knew you'd come" → "I knew you'd come."), which is
    exactly what snapping is for.
    """
    have = set(key(line).split())
    for m in _TOKEN.finditer(read):
        raw = m.group(0)
        k = key(raw)
        if len(k) < LOST_WORD_MIN or any(p in have for p in k.split()):
            continue
        # A capitalised word MID-SENTENCE is a name, and is held to the rule
        # whatever its frequency: the games' names are rare or invented, so
        # frequency says nothing about them, and a dropped name is the loss
        # a listener notices first. Sentence-initial capitals are grammar,
        # not names — "Right. Choosel'harbor repairs'" capitalises a welded
        # misread of "Choose", and reading that as a name would refuse the
        # commonest repair there is.
        if raw[:1].isupper() and not _sentence_start(read, m.start()):
            return raw
        if _zipf is not None and _zipf(k.split()[0], "en") >= LOST_WORD_ZIPF:
            return raw
    return None


class TextMap:
    """Loaded game lines, indexed for fuzzy lookup."""

    def __init__(self, lines, min_score=MIN_SCORE, min_margin=MIN_MARGIN,
                 nickname=None):
        self.min_score = min_score
        self.min_margin = min_margin
        # (text, group): the two halves of a {F#…}{M#…} entry are the SAME
        # line as far as the margin gate is concerned — see snap().
        lines = [(v, g) for g, line in enumerate(lines)
                 for v in variants(line, nickname)]
        self.entries = []          # (key, original, group)
        # trigram → positions, kept PER LENGTH BUCKET. One flat index makes
        # a common trigram ("the") a posting list the size of the map, and
        # walking those cost 47ms a query on a 100k-line map — a third of
        # the frame budget, for a lookup that must ride along with OCR.
        # Bucketing by length first is free (the length bound has to be
        # applied anyway) and cuts it to a few ms.
        self.buckets = {}          # bucket → {trigram: [positions]}
        seen = set()
        for line, group in lines:
            line = (line or "").strip()
            k = key(line)
            if not MIN_CHARS <= len(k) <= MAX_CHARS or k in seen:
                continue
            seen.add(k)
            pos = len(self.entries)
            self.entries.append((k, line, group))
            idx = self.buckets.setdefault(len(k) // BUCKET, {})
            for t in trigrams(k):
                # machine ints, appended straight in: a Python list of the
                # 10M positions a real dump produces is ~80MB of pointers
                # on top of the numbers, and this index is the whole memory
                # cost of loading one.
                idx.setdefault(t, array("i")).append(pos)

    def __len__(self):
        return len(self.entries)

    @classmethod
    def load(cls, path, **kw):
        """Read a map file. Returns None if the path is unusable — a
        missing or malformed map must leave the app reading exactly as it
        does without one, never crash it at startup."""
        p = Path(path).expanduser()
        try:
            raw = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        lines = None
        if raw.lstrip()[:1] in "[{":
            try:
                data = json.loads(raw)
                lines = (list(data.values()) if isinstance(data, dict)
                         else list(data))
            except (ValueError, AttributeError):
                lines = None
        if lines is None:
            lines = raw.splitlines()
        lines = [x for x in lines if isinstance(x, str)]
        if not lines:
            return None
        return cls(lines, **kw)

    def candidates(self, k):
        """Entry positions worth scoring, best trigram overlap first."""
        lo, hi = len(k) * (1 - LEN_TOLERANCE), len(k) * (1 + LEN_TOLERANCE)
        grams = trigrams(k)
        hits = Counter()
        for bucket in range(int(lo) // BUCKET, int(hi) // BUCKET + 1):
            idx = self.buckets.get(bucket)
            if not idx:
                continue
            # RAREST trigrams first, and only a few of them. " th" is in
            # half the map and its posting list costs more than it tells us;
            # "zhn" names the line. Scanning every trigram's postings cost
            # 66ms a query on a 100k-line map, against 5ms for the rarest
            # 24 — with no measured loss of recall, because a line that
            # shares a rare sequence with the query is exactly the line
            # worth scoring.
            posts = sorted((idx[t] for t in grams if t in idx), key=len)
            for postings in posts[:RARE_GRAMS]:
                if len(postings) > MAX_POSTINGS:
                    break                      # sorted: the rest are worse
                # Counter.update counts the array in C — the Python-level
                # `hits[pos] += 1` loop was half of candidates()' cost
                # (measured 2.9 → 1.4 ms/query, identical output)
                hits.update(postings)
        return [pos for pos, _ in hits.most_common(SHORTLIST * 3)
                if lo <= len(self.entries[pos][0]) <= hi][:SHORTLIST]

    def snap(self, text):
        """The game's own line for this read, or None to keep the read.

        None is the safe answer and is returned for everything uncertain:
        too short to identify, no candidate, a weak best match, a best
        match the runner-up is breathing down the neck of, or a match that
        drops a word the read was sure of.
        """
        k = key(text)
        if len(k) < MIN_CHARS:
            return None
        # quick_ratio()/real_quick_ratio() are documented upper bounds on
        # ratio(), so a candidate whose bound sits under
        # min_score − min_margin can neither be an accepted best (needs
        # ≥ min_score) nor a margin-blocking runner-up (blocks only above
        # best − min_margin, and an accepted best is ≥ min_score) — the
        # verdict is provably unchanged, and the full quadratic pass runs
        # on a handful of the 40-candidate shortlist instead of all of it
        # (measured 6.9 → 2.8 ms/query on a 100k-line map).
        floor = self.min_score - self.min_margin
        scored = []
        for pos in self.candidates(k):
            sm = difflib.SequenceMatcher(None, k, self.entries[pos][0])
            if sm.real_quick_ratio() < floor or sm.quick_ratio() < floor:
                continue
            scored.append((sm.ratio(), pos))
        scored.sort(reverse=True)
        if not scored:
            return None
        best, pos = scored[0]
        # The runner-up has to be a DIFFERENT line. A {F#…}{M#…} entry is
        # indexed twice, and its two halves differ by a pronoun — they were
        # each other's runner-up at 0.98 and the margin gate refused every
        # gendered line in the map.
        group = self.entries[pos][2]
        runner = next((s for s, p in scored[1:]
                       if self.entries[p][2] != group), 0.0)
        if best < self.min_score or best - runner < self.min_margin:
            return None
        line = self.entries[pos][1]
        # Last gate, and the one the score cannot express: a top match can
        # be both strong and margin-clear and still be a DIFFERENT line
        # ("Allow me to introduce myself." → "...allow me to reintroduce
        # myself...", 0.966 and unrivalled). What separates them is whether
        # the read's own words survived.
        if lost_word(text, line):
            return None
        # Returned even when only the punctuation differs. That is not
        # cosmetic here: sentence streaming decides where a line can be
        # split on terminal punctuation, and OCR drops and invents it
        # constantly ("business!" for "business.", a missing full stop at
        # the end of a row). The caller decides what is worth LOGGING —
        # a punctuation repair is not news, a word repair is.
        return None if line == text else line


def best_score(tm, text):
    """Top score for a read, whether or not it clears the gates — the
    number `--check` reports, and the only way to tell "the map does not
    have this line" from "the match was refused"."""
    k = key(text)
    scored = [difflib.SequenceMatcher(None, k, tm.entries[pos][0]).ratio()
              for pos in tm.candidates(k)]
    return max(scored) if scored else 0.0


def _seen_lines(shots, game):
    """Every dialogue line recorded in captures/shots, most-seen first.

    These are what the app really read, on the content this player is
    really playing — the only honest yardstick for whether a dump is
    current enough to be worth loading.
    """
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent))
    from profiles import get_profile
    profile = get_profile(game)
    seen = {}
    for f in sorted(Path(shots).glob("*.json")):
        try:
            blocks = json.loads(f.read_text())
        except (OSError, ValueError):
            continue
        if not isinstance(blocks, list):
            continue
        line = (profile.classify(blocks).get("dialogue") or "").strip()
        if len(line) >= MIN_CHARS:
            seen[line] = seen.get(line, 0) + 1
    return sorted(seen, key=lambda t: -seen[t])


def _check(args):
    """Score a dump against the lines this install has actually read."""
    tm = TextMap.load(args.map, nickname=args.nickname)
    if tm is None:
        raise SystemExit(f"{args.map}: unreadable or empty")
    print(f"{len(tm)} usable lines "
          f"(entries outside {MIN_CHARS}-{MAX_CHARS} characters, and any "
          f"still holding a placeholder, are not indexed)")
    lines = _seen_lines(args.shots, args.game)[:args.limit]
    if not lines:
        raise SystemExit(f"no recorded lines in {args.shots} — play a little "
                         f"with the app running first")
    bands = {"0.95+": 0, "0.82-0.95": 0, "0.60-0.82": 0, "under 0.60": 0}
    misses = []
    for line in lines:
        s = best_score(tm, line)
        bands["0.95+" if s >= 0.95 else "0.82-0.95" if s >= MIN_SCORE
              else "0.60-0.82" if s >= 0.60 else "under 0.60"] += 1
        if s < 0.60:
            misses.append((s, line))
    print(f"\n{len(lines)} lines this install has read, best match in the map:")
    for band, n in bands.items():
        print(f"   {band:12} {n:4}  ({100 * n / len(lines):.0f}%)")
    hit = bands["0.95+"] + bands["0.82-0.95"]
    print(f"\n{hit} of {len(lines)} would be snapped. A dump for the patch "
          f"you are playing scores most lines 0.95+; a stale one leaves them "
          f"under 0.60 — those lines are simply not in it.")
    for s, line in misses[:args.show]:
        print(f"   {s:.2f}  {line[:88]}")


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="Check a TextMap dump against the lines this install "
                    "has actually read.")
    ap.add_argument("map")
    ap.add_argument("--game", default="genshin")
    ap.add_argument("--nickname", default="",
                    help="the player character's in-game name, for "
                         "{NICKNAME} entries")
    ap.add_argument("--shots", default=str(
        Path(__file__).resolve().parent.parent / "captures" / "shots"))
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--show", type=int, default=5)
    _check(ap.parse_args())
