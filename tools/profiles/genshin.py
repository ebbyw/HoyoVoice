#!/usr/bin/env python3
"""Genshin Impact layout profile.

Calibrated against a 4-minute 1080p session recording (Natlan world
quest, Apple Vision OCR): 198 dialogue-box frames, 281 frames total. Every
number below is a measurement from that capture, not a guess; the source
figures are quoted in the comments so a later recording can be checked
against them.

How Genshin differs from Honkai: Star Rail, which the base layout came
from:

  * No '✕ Continue' hint on the dialogue box. Its story chrome is the
    auto-play toggle ("Auto", cx=0.844 cy=0.067) — but full-screen
    narration cards DO show 'Continue' (cx=0.909 cy=0.078), so
    `trusts_dialogue` accepts either.
  * 'Confirm' sits in the same corner during ordinary dialogue, so unlike
    Star Rail it is NOT evidence of a menu — it is ignored, not trusted.
  * The nameplate is drawn at TWO heights, in separate clusters: boxed
    NPC dialogue at cy 0.2261-0.253, and world dialogue — a companion
    talking while you walk, no box and no chrome at all — at
    cy 0.2093-0.2097. A band sized for the first misses the second by
    well under a thousandth, and the miss is not quiet: the line drops to
    the plate-less band, which reaches high enough to read the nameplate
    itself as words.
  * The nameplate is dead-centered (cx 0.493-0.504 across 210 reads) and
    can carry a second, smaller line under it: the speaker's role
    ("Pucli" / "Entertainment Supervisor"). That subtitle lands exactly
    where the first dialogue row would and was being read aloud as the
    opening words of every one of that NPC's lines.
  * Dialogue rows are centered too, but only once fully typed: the
    typewriter reveals a row left-to-right from its final left edge, so a
    half-typed row's center sits far left of the axis (measured 0.24 and
    0.38 on rows that finished at 0.50). Star Rail's centered-seed test
    drops those rows outright, so rows are accepted across the whole text
    column instead.
  * The UID sits bottom-right and is on screen in nearly every context
    (249 frames), which makes it a good game fingerprint but useless as a
    system-screen marker.
  * No phone UI: no group-chat panel. Readable articles (the
    "Investigative Report" panels) ARE a reading screen and are read
    incrementally the way Star Rail's Quick Read books are, but their
    layout is entirely their own — see READABLE_* below.
"""
import re

from .base import Profile, in_region, split_camel


class Genshin(Profile):
    name = "genshin"
    label = "Genshin Impact"
    PLAYER_NAME = "Traveler"
    READER_LABEL = "readable"
    # Only screens whose geometry has been checked against real frames.
    # Choice prompts did not occur in the calibration capture; they stay off
    # rather than guessed at, because a wrong band does not fail quietly —
    # it narrates menus. See CALIBRATE below.
    SCREENS = frozenset({"dialogue", "narration", "loading", "quickread"})

    # Box chrome that is never speech. 'Confirm' and 'Auto' both sit inside
    # the dialogue band's reach; without this they can join a row.
    IGNORE = frozenset({"Auto", "Confirm", "Continue", "→"})

    # A plate here is always a plate: the band starts at 0.21 and dialogue
    # rows were never seen above 0.194, so the Star Rail re-parse (drop the
    # plate, read the frame again) has nothing to rescue — and it actively
    # hurts, because a frame whose only line is still too faint to read
    # would fall back to the plate-less band and speak the role subtitle.
    REPARSE_PLATELESS = False

    # Stylized nameplates read weakly: across 197 dialogue frames the plate
    # came back at confidence 0.5 or below on 25 of them ('"Tenoyollotzin"'
    # on 22 of those), against 1.0 for the dialogue rows themselves. At the
    # 0.8 floor those frames lost their speaker AND fell back to the
    # plate-less band, which pulls the role subtitle in as the first words
    # of the line. The plate slot is geometrically constrained enough to
    # take the weaker read.
    PLATE_MIN_CONF = 0.3

    # measured row pitch: consecutive dialogue rows land 0.027-0.030 apart
    # (0.194/0.164/0.134), while fragments of one row agree to ~0.001
    LINE_H = 0.027

    # Two rows fused into one observation (see base.fused_rows). A real
    # Genshin dialogue row measures 0.031-0.034, and the tallest single row
    # in 6673 recorded blocks was 0.051 — a slightly loose box around one
    # line, still plainly one line. Every fusion measured 0.055 or more, and
    # the two-row fusions this was written for all measured 0.067 exactly.
    # 0.054 sits in the gap with room on both sides.
    FUSED_ROW_H = 0.054

    # Nameplate. Genshin draws it at two heights, and they are separate
    # clusters rather than a spread:
    #
    #   boxed dialogue (an NPC conversation)   cy 0.2261-0.253
    #   world dialogue (a companion talking
    #     while you walk, no box, no chrome)   cy 0.2093-0.2097
    #
    # The floor used to be 0.21, sized for the boxed layout alone, and the
    # world-dialogue plate misses it by seven ten-thousandths. Every one of
    # those lines lost its speaker, fell through to DIALOGUE_FALLBACK_Y —
    # which reaches up to 0.21 and so swallowed the nameplate as WORDS
    # ("Paimon These floaty lil' guys… They won't jump us out of nowhere,
    # will they?") — and was then dropped as an unknown speaker, because
    # world dialogue carries no story chrome either.
    #
    # 0.204 sits in the 0.0103 of clear air between the world plate and the
    # highest role subtitle ever measured (0.1990 over 79 sightings), which
    # is what the old floor was really defending against.
    PLATE_Y = (0.204, 0.28)
    PLATE_X = (0.45, 0.55)
    PLATE_MAX_W = 0.25
    # A role line belongs to the BOXED layout: it is the job title under an
    # NPC's name, and the world-dialogue plate never has one. Below this,
    # the subtitle test is off. It has to be, and not by a hair: the world
    # line sits 0.037 below its plate's baseline against a SUBTITLE_MAX_DROP
    # of 0.036, so on a frame where OCR reads it a shade shorter it would be
    # eaten as a role line — and with REPARSE_PLATELESS off, an eaten line
    # leaves the plate with nothing under it and vanishes without a log.
    # Placed between the two plate clusters, not next to either.
    SUBTITLE_PLATE_MIN_CY = 0.215

    # Dialogue: rows run from just under the plate down to cy=0.134 (the
    # deepest row seen, a 3-row line). The span is measured from the plate's
    # BOTTOM EDGE (`plate["y"]`), not its center — a distinction that cost a
    # word: at 0.10 the floor landed at 0.140 on a plate whose y was 0.240,
    # and the third row of a Pucli line (cy=0.136, the word "Asha.") fell
    # 0.005 outside the band and was never spoken. Row offsets below the
    # plate edge are stable at 0.045 / 0.076 / 0.105 (pitch 0.030), so 0.125
    # clears a 3-row line with margin. A 4-row line would sit at 0.135 and
    # need 0.15 — not raised speculatively, because the floor also has to
    # stay clear of the chrome row at cy~=0.067, where the bottom-left icon
    # strip misreads as text ("134)", cx=0.183) well inside DIALOGUE_X.
    # Rows are accepted across the whole text column rather than by Star
    # Rail's centered-seed test. Genshin centers each row, but only once it
    # is fully typed: the typewriter reveals a row rightward from its final
    # left edge, so a half-typed row's center sits anywhere left of the
    # axis (measured 0.24 and 0.38 on rows that finished at 0.50). Nothing
    # else lands in the band — the Auto/Confirm chrome row is at cy~=0.067,
    # well below its floor — so the column bounds are all that is needed.
    DIALOGUE_X = (0.15, 0.85)
    DIALOGUE_SPAN = 0.125
    # …but never below this, whatever the span works out to. The world
    # plate sits 0.018 lower than the boxed one, so the same span reaches
    # 0.018 further down — far enough to take in the permanent bottom HUD,
    # and "Whoa! Paimon thinks she heard a terrifying roar..." came back
    # with "Lv. 90" (cy=0.082) welded onto the end of it. The deepest
    # dialogue row ever measured is 0.134, so this costs nothing: below it
    # are only the level readout, the HP bar ("25577/25577", which the log
    # shows arriving as its own would-be line), the Chat tab and the UID.
    DIALOGUE_MIN_Y = 0.10
    DIALOGUE_FALLBACK_Y = (0.12, 0.21)

    # The role line under a name ("Pucli" / "Entertainment Supervisor").
    # What separates it from the first dialogue row is how close it hugs the
    # plate: measured across the capture, subtitles sit 0.023-0.031 below the
    # plate's baseline and first dialogue rows 0.041-0.063 below it. Font
    # size does NOT separate them — Vision returns 0.016-0.029 for the same
    # subtitle depending on which glyphs it picks up, overlapping the
    # 0.026-0.034 of dialogue rows — so height is only a damage bound here,
    # and the axis test is the second signal (subtitles are centered on the
    # plate to within 0.008).
    # The axis test is applied to the whole ROW (see Profile.subtitle_rows),
    # because a long role reaches Vision in pieces: "Shopkeeper, Mondstadt
    # General Goods" came back split, and neither half is centered on the
    # plate even though the line is — so per-piece the test cleared nothing
    # and Blanche's whole title was read as the opening words of "Please
    # have a look around."
    SUBTITLE_MAX_H = 0.032
    SUBTITLE_MAX_DX = 0.012         # from the plate's center axis
    SUBTITLE_MAX_DROP = 0.036       # below the plate's baseline

    # Choice options float to the right of the dialogue box, above it, each
    # row left-aligned past a chat-bubble icon (the icon is not text, so the
    # left edge is where the option text starts): measured x 0.686-0.689 on
    # the two-row prompts of the calibration capture, and x=0.6875 on every
    # row of the 7-option Katheryne prompt in rec_20260809_143259 — the
    # long-list capture the old CALIBRATE note was waiting for. The stack
    # grows UPWARD from a fixed bottom (~0.277): that prompt's rows sit at
    # cy 0.277/0.323-0.346/0.393/0.441-0.464/0.508/0.565/0.622, so the old
    # 0.62 ceiling (Star Rail's, kept while unverified) clipped the top
    # option out of the prompt — the session log shows it read as a
    # six-option list missing "Claim Daily Commission Reward". 0.66 clears
    # the measured top edge (0.636) by a full half-row; an 8th option
    # would sit at ~0.68 and need another +0.06 — not taken on faith, the
    # same way 0.62 wasn't.
    CHOICES = {"x": (0.66, 1.00), "y": (0.22, 0.66)}
    CHOICE_LEFT_EDGE = (0.66, 0.75)
    # What separates two OPTIONS from the wrapped rows of one, as an
    # absolute center-to-center gap. The height-relative rule (1.5x the
    # taller row) sits on a knife edge here: measured on the 7-option
    # prompt, wrapped rows of one option are 0.023 apart and adjacent
    # options 0.044-0.057, but Vision's heights for the same visual rows
    # span 0.018-0.034, putting 1.5xH anywhere from 0.027 to 0.052 — and
    # the session log shows three options fused into one ("Check Valiant
    # Chronicles information We meet again, Katheryne…"). The 0.044 floor
    # on the option side is itself an icon artifact: the bubble glyph
    # fused into the Dispatch row inflates its box, which is also why the
    # gap is measured between centers, not bottom edges. 0.034 is the
    # midpoint of the clear air between the two pitches.
    CHOICE_GROUP_GAP = 0.034
    # A wrapped option's second row is set smaller than its first (measured
    # 0.019 against 0.024); Star Rail's 0.020 floor dropped it and the
    # option read as a sentence fragment. Party-member names are the only
    # other text out here and they start at x~=0.83, well right of
    # CHOICE_LEFT_EDGE, so the floor is not what excludes them.
    CHOICE_MIN_HEIGHT = 0.014

    # Full-screen narration cards: measured at cy=0.512, cx=0.499, h=0.045,
    # with only the Continue hint and the UID elsewhere on screen.
    NARRATION_BAND = {"x": (0.15, 0.85), "y": (0.25, 0.75)}

    # UID:123456789 bottom-right, on screen in nearly every context. Digits
    # are required — "UID" alone appears in menus.
    _UID = re.compile(r"U\W?I\W?D\s*[:：]?\s*\d{6,}", re.I)
    # Story chrome: the dialogue box's auto-play toggle, or the Continue
    # hint that full-screen narration cards carry.
    _CHROME = re.compile(r"^[•\s]*(auto|continue)\s*$", re.I)
    # Everything the dialogue box draws for itself, trusted or not. Used to
    # rule OUT a screen, so it includes Confirm, which is not evidence of
    # story on its own.
    _BOX_CHROME = re.compile(r"^[•\s]*(auto|continue|confirm)\s*$", re.I)

    # Button hints, bottom-right. Every Genshin screen draws a hint cluster
    # there and WHAT IT SAYS is what separates a menu from a story frame:
    # dialogue shows Auto/Confirm and narration cards Continue, while the
    # crafting, shop and inventory screens show their own verbs ("Convert",
    # "Leave", "Item Details"). Nothing else about those screens rules them
    # out — the Convert screen's "Conversion Material" banner sits dead in
    # the plate band (cx=0.47, cy=0.27) and the item grid below it reads as
    # dialogue rows ("Shadow of… Dragon Lo… 9/1"), so a menu is one cast
    # name away from being spoken aloud. The UID shares the strip and must
    # not count as a hint, hence the letters-only word test.
    HINT_STRIP = {"x": (0.70, 1.00), "y": (0.00, 0.10)}
    _HINT_WORD = re.compile(r"^[A-Za-z][A-Za-z' ]{2,}$")

    def is_menu(self, blocks):
        """True if the hint strip advertises a menu's own actions.

        Deliberately one-sided: a frame that shows story chrome is never a
        menu no matter what else is down there, so the cost of a stray read
        in the strip is a menu that stays readable, not a line that goes
        unread.
        """
        other = False
        for b in self.confident(blocks):
            if not in_region(b, self.HINT_STRIP):
                continue
            text = b["text"].strip(" •✕×○()[]{}")
            if self._BOX_CHROME.match(text):
                return False
            other = other or bool(self._HINT_WORD.match(text))
        return other

    # --- Readable articles ---------------------------------------------
    # The reading panel ("Investigative Report: Bakunawa"): a gold title
    # centered under an ornate rule, prose in a fixed column below it, and
    # a 'Return' hint. Measured off two 1080p captures — one opened from the
    # world, one from the inventory: title cx=0.499/0.500 cy=0.924/0.925;
    # body rows all share a left edge at x=0.264-0.267 at a pitch of 0.033;
    # 'Return' cx=0.915; UID cy=0.014. The panel is the SAME either way,
    # which is why the column, not the screen around it, is what identifies
    # it.
    #
    # Opened from the inventory the article is an OVERLAY: the bag screen
    # stays on behind it and OCRs right through — 'Quest', 'Inventory
    # capacity 1185/2300', item counts, the item's own name and description
    # panel on the right. An earlier rule here demanded nothing be on screen
    # but the panel, which is true of the world-opened article and false of
    # this one, so the inventory-opened article went unread except on the
    # occasional frame where OCR happened to miss the dimmed chrome. What
    # holds in both is the COLUMN: several rows of prose sharing one left
    # edge, under a centered title. Nothing else in Genshin's UI is shaped
    # like that.
    #
    # This is NOT Star Rail's Quick Read layout — different bands, different
    # chrome — but it is the same KIND of screen, so it hooks in through
    # classify_quickread and gets the same incremental reading, scroll
    # tolerance and panel-close handling.
    READABLE_TITLE = {"x": (0.40, 0.60), "y": (0.90, 0.96)}
    # The article SCROLLS between the two ornate rules, and the rules are
    # where it is clipped. Measured off the same frame by scanning row
    # brightness across the column: the upper rule is a single bright line
    # at cy=0.896, the lower at cy=0.052 — well BELOW the Return hint
    # (cy=0.076), which floats inside the panel out at cx=0.915. So the
    # body band is the full span between the rules; anything narrower
    # silently swallows rows once the article is scrolled, which is the one
    # failure this screen cannot afford (a dropped row is never read again,
    # unlike a deferred one).
    READABLE_BODY = {"x": (0.20, 0.80), "y": (0.052, 0.896)}
    READABLE_RULE_Y = (0.052, 0.896)
    # A row sliding under a rule is drawn in half, and half a row OCRs as
    # garbage or as a fragment that dedupe cannot match against the whole
    # row it becomes — so it would be read, then read again complete. Defer
    # any row whose box reaches within this of a rule. Unscrolled, the
    # nearest row clears the upper rule by 0.023 (0.873 against 0.896) and
    # the article's own padding is a full row pitch (0.033), so a row this
    # close to a rule is one being scrolled past, not one at rest.
    READABLE_CLIP_MARGIN = 0.004
    # The column's left edge, and the whole of what identifies this screen.
    # Measured at x=0.264-0.267 across both captures; the tolerance is for
    # OCR's own left-edge jitter, not for a different column somewhere else.
    READABLE_LEFT_EDGE = (0.24, 0.30)
    # Rows on that edge before this is an article. One or two lines sharing
    # a left margin is just a menu; several rows of prose is a page. This
    # replaces the "nothing else on screen" rule, so it carries the weight
    # that rule used to — measured against 1030 frames of both games,
    # including 546 of the inventory screen this panel overlays.
    READABLE_MIN_ROWS = 3
    # Row pitch, measured at 0.033 across both captures. Blocks whose
    # centers are within ROW_TOL of each other are fragments of one drawn
    # row: real fragments agree to ~0.001, while the nearest text that is
    # NOT part of the row (the item panel beside the column) sits 0.018
    # away. Comfortably between the two.
    READABLE_LINE_H = 0.033
    READABLE_ROW_TOL = 0.010
    # Stylized proper nouns read weakly even here: "Tenochtzitoc." came
    # back at 0.50 on both frames of the capture while every other row
    # scored 1.00, and at the 0.8 floor the word was dropped SILENTLY from
    # the middle of a sentence. The column is as tightly constrained as the
    # nameplate slot, so it takes the same floor the plate does.
    READABLE_MIN_CONF = 0.3
    _WORD = re.compile(r"[A-Za-z]+")

    # The word in the panel's exit hint. Books and inventory articles say
    # Return; the world-object newspaper (Snezhnaya Vestnik,
    # rec_20260812_201648) draws the same column, same title slot, same
    # rules — but its hint says Leave (measured x=0.903 cy=0.076, the
    # exact slot Return occupies). One word is not enough to carry
    # detection either way: the title, the ≥3 prose rows on the column
    # edge and the digit guards do that; this list only names the exits.
    READABLE_HINT_WORDS = ("return", "leave")

    def _is_return_hint(self, text):
        """True if this block is the panel's Return/Leave hint.

        The button glyph beside it is not always a separate block: on the
        inventory-opened article Vision returned 'Return e', the ◯ read as
        a letter and merged into the word. The same thing happens all over
        this pipeline ('R Scroll', 'O Back', '5 Quick Read'), so match on
        the WORDS: an exit word must be there, and anything else in the
        block has to be single-glyph noise. 'Return to Title' and the like
        are still rejected.
        """
        words = self._WORD.findall(text)
        return (any(w.lower() in self.READABLE_HINT_WORDS for w in words)
                and all(len(w) <= 1 for w in words
                        if w.lower() not in self.READABLE_HINT_WORDS))

    def _readable_unclipped(self, block):
        """True if this row is drawn WHOLE — clear of both scroll rules."""
        lo, hi = self.READABLE_RULE_Y
        m = self.READABLE_CLIP_MARGIN
        return block["y"] >= lo + m and block["y"] + block["h"] <= hi - m

    def classify_quickread(self, blocks):
        """Detect a readable article and return its title and body rows in
        reading order, or None.

        Articles scroll. Rows are returned per row rather than as one string
        so live.py can read the newly revealed ones and skip what it has
        already spoken, and a row still half-hidden behind a scroll rule is
        left out until it is drawn whole.

        The title comes back with a period appended when it has no sentence
        punctuation of its own, so it is spoken as a heading rather than
        running into the first line ("Investigative Report: Bakunawa. A
        gigantic beast that…").
        """
        if "quickread" not in self.SCREENS:
            return None
        conf = self.confident(blocks)
        if not any(self._is_return_hint(b["text"])
                   and in_region(b, self.HINT_STRIP) for b in conf):
            return None
        pool = [b for b in blocks
                if b["confidence"] >= self.READABLE_MIN_CONF
                and b["text"].strip() not in self.IGNORE]
        title = [b for b in pool if in_region(b, self.READABLE_TITLE)]
        if not title:
            return None
        # Rows of the COLUMN, and only those. Keep a row only when its
        # leftmost block starts on the column's edge — that is what leaves
        # the inventory behind the overlay out of the read: its item counts
        # sit left of the column and the item's name and description panel
        # to the right of it, so neither can start a row here.
        #
        # Rows are clustered by their own baselines rather than quantized
        # onto a grid. A grid put "ash itself." (cy=0.796) and the item
        # panel's "Quest Item" (cy=0.814) in one bucket — 0.018 apart, half
        # a row pitch, but either side of a bucket edge — and the panel text
        # rode into the read on the article row's ticket.
        band = [b for b in pool
                if in_region(b, self.READABLE_BODY)
                and self._readable_unclipped(b)]
        band.sort(key=lambda b: -(b["y"] + b["h"] / 2))
        rows, cur, top = [], [], None
        for b in band:
            cy = b["y"] + b["h"] / 2
            if top is None or top - cy > self.READABLE_ROW_TOL:
                cur = []
                rows.append(cur)
                top = cy
            cur.append(b)
        body, n_rows = [], 0
        for row in rows:
            row.sort(key=lambda b: b["x"])
            if (self.READABLE_LEFT_EDGE[0] <= row[0]["x"]
                    <= self.READABLE_LEFT_EDGE[1]):
                body.extend(row)
                n_rows += 1
        if n_rows < self.READABLE_MIN_ROWS:
            return None
        text = " ".join(b["text"] for b in body).strip()
        # prose, not a stat block: the same guards the narration cards use
        if (len(text) < self.NARRATION_MIN_CHARS
                or len(text.split()) < self.NARRATION_MIN_WORDS
                or sum(c.isdigit() for c in text)
                > self.NARRATION_MAX_DIGIT_RATIO * len(text)):
            return None
        title.sort(key=lambda b: (-(b["y"] + b["h"] / 2), b["x"]))
        head = split_camel(" ".join(b["text"] for b in title).strip())
        if head and head[-1] not in ".!?…:;,":
            head += "."
        return [head] + [b["text"] for b in body]

    def _uid_corner(self, blocks):
        return any(self._UID.search(b["text"])
                   and b["y"] < 0.10 and b["x"] + b["w"] / 2 > 0.70
                   for b in self.confident(blocks))

    def trusts_dialogue(self, blocks):
        """Genshin has no Continue hint on the dialogue box. The auto-play
        toggle is the equivalent signal — drawn as part of the box, absent
        from menus and info popups — and narration cards show Continue.
        'Confirm' is deliberately NOT accepted: unlike Star Rail, Genshin
        shows it during ordinary dialogue, so it separates nothing.
        """
        if self.is_menu(blocks):
            return False
        if any(self._CHROME.match(b["text"].strip())
               and b["y"] < 0.10 and b["x"] + b["w"] / 2 > 0.70
               for b in self.confident(blocks)):
            return True
        # A pending choice HIDES the auto-play toggle — measured across both
        # prompts in the capture, neither frame carried an Auto or a
        # Confirm. Without this, a line whose speaker isn't cast yet is
        # skipped for want of chrome at exactly the moment the game is
        # asking the player something. The nameplate is required with it:
        # the teleport map lists waypoints in the same column, and has none.
        return bool(self.choice_blocks(blocks)) and self.find_plate(blocks) is not None

    # Loading screens ("Elements", "Elemental Reaction"…): a centered
    # title with centered prose under it, low on an otherwise empty screen,
    # over the game's own art. Measured: title cy=0.185, body rows at 0.152
    # / 0.131 / 0.110, every one of them centered on cx=0.500.
    LOADING_BAND = {"x": (0.42, 0.58), "y": (0.08, 0.30)}
    # Below this is the permanent bottom strip — the UID, the element icon
    # row, button hints. It is on screen here in every context, so unlike
    # Star Rail it cannot be treated as evidence of anything.
    LOADING_STRIP_Y = 0.08

    def classify_loading(self, blocks):
        # A dialogue box has the SAME shape as a loading card once the
        # bottom strip is discounted — a short centered heading with
        # centered prose under it, in the same band — so geometry alone
        # cannot tell them apart, and a loose rule here does not merely
        # miss loading screens: it captures every line of dialogue and
        # narrates it, nameplate and all. Two independent signals separate
        # them: a dialogue box always draws its own chrome (Auto, Confirm),
        # and its nameplate sits above the plate floor, where a loading
        # title never does.
        conf = self.confident(blocks)
        if any(self._BOX_CHROME.match(b["text"].strip()) for b in conf):
            return None
        body = [b for b in conf
                if b["y"] + b["h"] / 2 >= self.LOADING_STRIP_Y]
        # a title plus at least one line of prose, and NOTHING else on
        # screen — any text outside the band means this is the world, a
        # menu, or a loading screen still fading in over one of those
        if len(body) < 2 or any(not in_region(b, self.LOADING_BAND)
                                for b in body):
            return None
        if max(b["y"] + b["h"] / 2 for b in body) >= self.PLATE_Y[0]:
            return None
        body.sort(key=lambda b: -(b["y"] + b["h"] / 2))
        title = body[0]["text"].strip()
        text = " ".join(b["text"] for b in body[1:]).strip()
        if (len(text) < self.NARRATION_MIN_CHARS
                or len(text.split()) < self.NARRATION_MIN_WORDS
                or sum(c.isdigit() for c in text)
                > self.NARRATION_MAX_DIGIT_RATIO * len(text)):
            return None
        return f"{split_camel(title)}. {text}"

    def is_system_screen(self, blocks):
        # Star Rail keys this on the build string it prints bottom-left on
        # loading and warning screens. Genshin prints no such string, and
        # its bottom-right UID is on screen everywhere, so nothing here
        # marks a screen as "system" — the loading layout is recognized on
        # its own shape instead, above.
        return False

    def classify(self, blocks, _no_plate=False):
        if self.is_menu(blocks):
            return {"speaker": None, "dialogue": "", "choices": [],
                    "boxes": [], "conf": 1.0}
        state = super().classify(blocks, _no_plate)
        # A choice prompt only exists alongside a speaker. The teleport map
        # lists its waypoints ("Sea of Bygone Eras", "Temple of Space"…) in
        # the same column at the same left edge, and reads as a three-option
        # prompt otherwise; it has no nameplate.
        if state["choices"] and not state["speaker"]:
            state["choices"] = []
        return state

    # Comms message (Snezhnaya 6.x): a line delivered over the top of open
    # gameplay — the Eye of Graeae's "You have a new message…" — with the
    # nameplate anchored to the LEFT edge of its line instead of centered.
    # Measured off shot #127 (2026-08-12): plate "Eye of Gnaeae" cy=0.213
    # cx=0.401, left edge 0.361, conf 0.5 (the stylized font reads weakly,
    # same as the quoted plates PLATE_MIN_CONF exists for); line cy=0.169
    # cx=0.500, left edge 0.337, conf 1.0. The plate's cx sits well left of
    # PLATE_X's 0.45 floor, so find_plate never takes it, the line falls to
    # the plate-less fallback band, and the no-story-chrome gate drops it.
    # The x-band's 0.45 ceiling is PLATE_X's floor, so a plate is either
    # centered or comms, never both.
    COMMS_PLATE_X = (0.30, 0.45)
    # plate left edge relative to the line's: the plate text starts 0.023
    # right of the line (the sender icon isn't OCR'd); centered plates over
    # a full-width line start far further in.
    COMMS_ALIGN = (-0.02, 0.06)

    def classify_comms(self, blocks):
        """(speaker, line) for a comms message overlay, or None.

        There is no chrome to demand — the message floats over the live HUD
        — so the geometry itself is the trust signal: exactly one short
        plate-shaped block in the plate band, anchored to the left edge of
        the dialogue rows below it, and nothing else in the band. Boards
        and shop grids fill their bands with more than one block."""
        if self.is_menu(blocks):
            return None
        pool = [b for b in blocks if b["confidence"] >= self.PLATE_MIN_CONF
                and b["text"].strip() not in self.IGNORE]
        band = [b for b in pool
                if self.PLATE_Y[0] <= b["y"] + b["h"] / 2 <= self.PLATE_Y[1]]
        plates = [b for b in band
                  if self.COMMS_PLATE_X[0] <= b["x"] + b["w"] / 2
                  < self.COMMS_PLATE_X[1] and b["w"] <= self.PLATE_MAX_W]
        # one plate, and the band holds NOTHING else: a second block in the
        # band is a board/menu label column, not a sender
        if len(plates) != 1 or len(band) != 1:
            return None
        plate = plates[0]
        dlg_top = plate["y"] - 0.004
        dlg_bot = max(plate["y"] - self.DIALOGUE_SPAN, self.DIALOGUE_MIN_Y)
        rows = [b for b in self.speakable(blocks)
                if dlg_bot <= b["y"] + b["h"] / 2 <= dlg_top
                and self.DIALOGUE_X[0] <= b["x"] + b["w"] / 2
                <= self.DIALOGUE_X[1]]
        if not rows:
            return None
        if not (self.COMMS_ALIGN[0]
                <= plate["x"] - min(b["x"] for b in rows)
                <= self.COMMS_ALIGN[1]):
            return None
        rows.sort(key=lambda b: (round((1 - (b["y"] + b["h"] / 2))
                                       / self.LINE_H), b["x"]))
        text = " ".join(b["text"] for b in rows)
        return (plate["text"], text) if len(text) >= 12 else None

    def is_plate_subtitle(self, block, plate):
        # boxed layout only — see SUBTITLE_PLATE_MIN_CY
        if plate["y"] + plate["h"] / 2 < self.SUBTITLE_PLATE_MIN_CY:
            return False
        cx = block["x"] + block["w"] / 2
        pcx = plate["x"] + plate["w"] / 2
        return (block["h"] <= self.SUBTITLE_MAX_H
                and abs(cx - pcx) <= self.SUBTITLE_MAX_DX
                and 0 < plate["y"] - block["y"] <= self.SUBTITLE_MAX_DROP)

    def fingerprint(self, blocks):
        return 1.0 if self._uid_corner(blocks) else 0.0
