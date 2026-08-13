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

ACCEPTING. Two gates, and both matter. The score has to clear `min_score`,
and it has to beat the runner-up by `min_margin`: a line that half the map
resembles equally is exactly the case where the top match is arbitrary,
and picking one anyway would put words in a character's mouth that the
game never wrote. That failure is worse than reading the misread aloud,
which is why the defaults are conservative.

Measured on the recorded sessions: 377 distinct lines as the map, 164 real
misreads of them as queries. At the defaults, 113 were repaired to exactly
the right line, 51 were refused, and NONE was snapped to the wrong line.
The catastrophic case on file — two dialogue rows fused and interleaved —
scores 0.57 against its own line and is among the refusals. The top match
is in fact right there, and it is still refused on purpose: nothing about
a 0.57 acceptance generalizes to a map three orders of magnitude larger,
and a wrong sentence spoken confidently is worse than a garbled one.
"""
import difflib
import json
import re
from collections import Counter
from pathlib import Path

# A misread can lose or gain this share of a line's length before it stops
# being a candidate. Two dialogue rows fused into one lose about a third.
LEN_TOLERANCE = 0.35
# Entries scored properly per query. Wide enough that the right line is in
# it whenever trigram overlap ranks it anywhere near the top.
SHORTLIST = 40
MIN_SCORE = 0.82
MIN_MARGIN = 0.05
# Below this a line is too short to identify: "Yes.", "Mm-hmm.", "Oh?" are
# each a dozen other lines' equal.
MIN_CHARS = 12
# Length bucket for the index, in characters. Small enough that a bucket is
# a thin slice of the map, wide enough that the length bound spans only a
# handful of them.
BUCKET = 16
# Query trigrams actually walked, rarest first (see candidates()).
RARE_GRAMS = 24

_WORD = re.compile(r"[^a-z0-9 ]+")


def key(s):
    """Comparison form: lowercase, punctuation-free, single-spaced. OCR gets
    punctuation wrong constantly ("business!" for "business.") and that is
    not a difference worth failing a match over — the ACCEPTED text is the
    map's, punctuation included, so nothing is lost by ignoring it here."""
    return " ".join(_WORD.sub(" ", (s or "").lower()).split())


def trigrams(s):
    return {s[i:i + 3] for i in range(len(s) - 2)}


class TextMap:
    """Loaded game lines, indexed for fuzzy lookup."""

    def __init__(self, lines, min_score=MIN_SCORE, min_margin=MIN_MARGIN):
        self.min_score = min_score
        self.min_margin = min_margin
        self.entries = []          # (key, original)
        # trigram → positions, kept PER LENGTH BUCKET. One flat index makes
        # a common trigram ("the") a posting list the size of the map, and
        # walking those cost 47ms a query on a 100k-line map — a third of
        # the frame budget, for a lookup that must ride along with OCR.
        # Bucketing by length first is free (the length bound has to be
        # applied anyway) and cuts it to a few ms.
        self.buckets = {}          # bucket → {trigram: [positions]}
        seen = set()
        for line in lines:
            line = (line or "").strip()
            k = key(line)
            if len(k) < MIN_CHARS or k in seen:
                continue
            seen.add(k)
            pos = len(self.entries)
            self.entries.append((k, line))
            idx = self.buckets.setdefault(len(k) // BUCKET, {})
            for t in trigrams(k):
                idx.setdefault(t, []).append(pos)

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
                for pos in postings:
                    hits[pos] += 1
        return [pos for pos, _ in hits.most_common(SHORTLIST * 3)
                if lo <= len(self.entries[pos][0]) <= hi][:SHORTLIST]

    def snap(self, text):
        """The game's own line for this read, or None to keep the read.

        None is the safe answer and is returned for everything uncertain:
        too short to identify, no candidate, a weak best match, or a best
        match the runner-up is breathing down the neck of.
        """
        k = key(text)
        if len(k) < MIN_CHARS:
            return None
        scored = sorted(
            ((difflib.SequenceMatcher(None, k, self.entries[pos][0]).ratio(),
              pos) for pos in self.candidates(k)), reverse=True)
        if not scored:
            return None
        best, pos = scored[0]
        runner = scored[1][0] if len(scored) > 1 else 0.0
        if best < self.min_score or best - runner < self.min_margin:
            return None
        line = self.entries[pos][1]
        # Returned even when only the punctuation differs. That is not
        # cosmetic here: sentence streaming decides where a line can be
        # split on terminal punctuation, and OCR drops and invents it
        # constantly ("business!" for "business.", a missing full stop at
        # the end of a row). The caller decides what is worth LOGGING —
        # a punctuation repair is not news, a word repair is.
        return None if line == text else line
