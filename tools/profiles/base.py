#!/usr/bin/env python3
"""Game layout profile: OCR blocks -> screen type + speaker/dialogue/choices.

A profile owns two things:

  * the LAYOUT — normalized bands (Vision convention: origin bottom-left,
    0-1) where this game draws nameplates, dialogue, choices, chrome;
  * the SCREEN DETECTORS — which screen types the game even has, and how
    each is recognized.

The algorithms live here and are shared; a subclass supplies numbers and
overrides a detector only where the game genuinely differs. Every band
below is calibrated against real frames at 1080p — see `SCREENS` for
which detectors a profile has opted into.

`profiles/hsr.py` is the reference implementation (Honkai: Star Rail);
`profiles/genshin.py` is Genshin Impact.
"""
import difflib
import re


def in_region(block, region):
    cx = block["x"] + block["w"] / 2
    cy = block["y"] + block["h"] / 2
    (x0, x1), (y0, y1) = region["x"], region["y"]
    return x0 <= cx <= x1 and y0 <= cy <= y1


def _bounds(blocks):
    """The box that encloses these blocks — one block's own box if that is
    all there is, so a row Vision returned whole is tested unchanged."""
    if len(blocks) == 1:
        return blocks[0]
    x0 = min(b["x"] for b in blocks)
    y0 = min(b["y"] for b in blocks)
    return {"text": " ".join(b["text"] for b in blocks),
            "confidence": min(b["confidence"] for b in blocks),
            "x": x0, "y": y0,
            "w": max(b["x"] + b["w"] for b in blocks) - x0,
            "h": max(b["y"] + b["h"] for b in blocks) - y0}


def split_camel(s):
    """'CindearthAge' -> 'Cindearth Age'. OCR drops the space in these
    stylized titles, and TTS then reads them as one mangled word."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)


def narration_self_certain(text):
    """Bright cutscene narration (no black bg, no chrome hint) can still
    self-certify: a real prose sentence, no menu-banner symbols."""
    return (len(text.split()) >= 8
            and text.rstrip().endswith((".", "!", "?", "…"))
            and not any(c in text for c in "©•®™|"))


class Profile:
    """Base layout profile. Subclass and override constants, not methods,
    wherever a game only differs in geometry."""

    name = "base"
    label = "Base"
    # What this game calls the player character. Dialogue options are the
    # player's own words but carry no nameplate, so they are cast under this
    # name — which puts a row in Casting like any other character, instead
    # of falling to the narrator with nothing to assign a voice to.
    PLAYER_NAME = "Player"

    # Screen types this game HAS. A detector whose type isn't listed
    # returns None without looking at the frame, so a game that has no
    # phone UI can't have one hallucinated out of a menu.
    SCREENS = frozenset()

    # What this game calls its reading panel, for the log and the history.
    # Star Rail's is a "Quick Read" book; Genshin's is a readable article.
    READER_LABEL = "quick read"

    MIN_CONF = 0.8
    # Confidence floor for the nameplate slot alone. That slot is heavily
    # constrained by geometry (short, inside a narrow band, above the line),
    # so it can carry weaker text evidence than a line that will be spoken
    # verbatim. None = use MIN_CONF.
    PLATE_MIN_CONF = None
    IGNORE = frozenset()
    # Re-parse a frame with the nameplate suppressed when the plate yields
    # no dialogue under it. Worth it where un-nameplated narration can pass
    # the plate filters; harmful where the plate band is tight enough that a
    # plate is always a plate, since the re-parse then reaches back up and
    # reads the plate's own rows as speech.
    REPARSE_PLATELESS = True
    # Row quantization for grouping OCR blocks into visual lines — roughly
    # one dialogue line height. Font size differs between games.
    LINE_H = 0.022

    # --- dialogue screen ---
    PLATE_Y = (0.18, 0.31)          # nameplate can appear anywhere here
    PLATE_X = (0.35, 0.65)
    PLATE_MAX_W = 0.30              # names are short; dialogue lines are wide
    DIALOGUE_X = (0.40, 0.60)       # real lines are centered
    DIALOGUE_SPAN = 0.15            # lines live this far below the nameplate
    # Hard floor for dialogue rows, whatever the span works out to. The span
    # is measured DOWN FROM the nameplate, so a game that draws the plate
    # lower reaches further into whatever sits at the bottom of the screen.
    # 0.0 = no floor (the span alone decides).
    DIALOGUE_MIN_Y = 0.0
    DIALOGUE_FALLBACK_Y = (0.08, 0.21)
    DIALOGUE_WIDE_X = (0.08, 0.92)  # row-mate fragments can sit this far out

    # --- choice list ---
    CHOICES = {"x": (0.66, 1.00), "y": (0.22, 0.62)}
    CHOICE_LEFT_EDGE = (0.68, 0.78)  # option text is left-aligned past the marker
    CHOICE_MIN_HEIGHT = 0.020
    # Vertical gap that separates two OPTIONS, as opposed to the wrapped
    # rows of one. None = 1.5x the taller row's height, which works while
    # OCR reports heights consistently; a game where measured heights
    # jitter across the option-pitch boundary pins an absolute gap
    # instead (see genshin.py for the measurement that forced it).
    CHOICE_GROUP_GAP = None

    # --- full-screen narration (centered prose, no nameplate) ---
    NARRATION_BAND = {"x": (0.20, 0.80), "y": (0.25, 0.75)}
    NARRATION_MIN_CHARS = 40
    NARRATION_MIN_WORDS = 6
    NARRATION_MAX_DIGIT_RATIO = 0.15  # menus/loaders are digit-heavy; prose isn't

    def find_plate(self, blocks):
        """The nameplate block for this frame, or None: a short block in the
        plate band. Exposed because "is there a speaker on screen" is a
        useful question outside classify() too."""
        pool = self.speakable(blocks) if self.PLATE_MIN_CONF is None else [
            b for b in blocks if b["confidence"] >= self.PLATE_MIN_CONF
            and b["text"].strip() not in self.IGNORE]
        plates = [b for b in pool
                  if self.PLATE_Y[0] <= b["y"] + b["h"] / 2 <= self.PLATE_Y[1]
                  and self.PLATE_X[0] <= b["x"] + b["w"] / 2 <= self.PLATE_X[1]
                  and b["w"] <= self.PLATE_MAX_W]
        # TOPMOST, not tallest. A SHORT dialogue line ("The beach!") is narrow
        # enough to pass PLATE_MAX_W and sits at cy~=0.189 — just inside
        # PLATE_Y — and the dialogue font is LARGER than the nameplate, so
        # picking by height handed the speaker slot to the line itself and
        # left the dialogue band (anchored below it) empty. The nameplate is
        # always the higher of the two.
        return max(plates, key=lambda b: b["y"]) if plates else None

    def choice_blocks(self, blocks):
        """Blocks that look like rows of the choice list.

        A block with no letters at all is an option's ICON, not its text:
        Vision returned Genshin's chat-bubble glyph as its own block ('®',
        x=0.6686 — inside the left-edge band) on the 7-option Katheryne
        prompt, and it would otherwise join an option as a leading word.
        Every real option row carries letters."""
        return [b for b in self.speakable(blocks)
                if in_region(b, self.CHOICES)
                and self.CHOICE_LEFT_EDGE[0] <= b["x"] <= self.CHOICE_LEFT_EDGE[1]
                and b["h"] >= self.CHOICE_MIN_HEIGHT
                and any(c.isalpha() for c in b["text"])]

    def is_plate_subtitle(self, block, plate):
        """True if this block is part of the NAMEPLATE rather than speech —
        a role/title line drawn under the name. It sits in the dialogue band
        and would otherwise be read aloud as the first words of the line.

        Called with a whole ROW's bounding box, not with a single OCR box —
        see `subtitle_rows`."""
        return False

    def subtitle_rows(self, blocks, plate):
        """Row buckets under `plate` that are the role/title line.

        The test runs on the row's bounding box because Vision splits one
        drawn line into several boxes as readily as it returns it whole:
        "Shopkeeper, Mondstadt General Goods" came back as two, and a
        fragment of a centered line is not itself centered, so a per-box
        axis test cleared neither half and the whole title was read as the
        opening words of the line. A row's union has the geometry the game
        actually drew, however Vision cut it up."""
        rows = {}
        for b in blocks:
            if b is not plate:
                rows.setdefault(self._row(b), []).append(b)
        return {row for row, members in rows.items()
                if self.is_plate_subtitle(_bounds(members), plate)}

    def is_dialogue_seed(self, block):
        """True if this block is confidently a dialogue row (as opposed to a
        fragment of one, which is pulled in afterwards as a row-mate)."""
        cx = block["x"] + block["w"] / 2
        return self.DIALOGUE_X[0] <= cx <= self.DIALOGUE_X[1]

    def confident(self, blocks):
        return [b for b in blocks if b["confidence"] >= self.MIN_CONF]

    def speakable(self, blocks):
        """Confident blocks minus chrome words that are never speech."""
        return [b for b in self.confident(blocks)
                if b["text"].strip() not in self.IGNORE]

    def _row(self, b):
        return round((b["y"] + b["h"] / 2) / self.LINE_H)

    # ------------------------------------------------------------------
    # Chrome. `trusts_dialogue` is the gate that lets an UNKNOWN speaker's
    # line be read at all: boards, menus and info popups fake the dialogue
    # layout, and only the game's own story chrome tells them apart.
    # ------------------------------------------------------------------
    def trusts_dialogue(self, blocks):
        raise NotImplementedError

    def is_system_screen(self, blocks):
        """Build/version chrome that marks a non-story system screen
        (loading, epilepsy warning). Those look exactly like narration."""
        return False

    # ------------------------------------------------------------------
    # Dialogue screen
    # ------------------------------------------------------------------
    def classify(self, blocks, _no_plate=False):
        state = {"speaker": None, "dialogue": [], "choices": []}
        conf = self.speakable(blocks)

        plate = None if _no_plate else self.find_plate(blocks)
        if plate is not None:
            state["speaker"] = plate["text"]
            dlg_top = plate["y"] - 0.004            # just below the nameplate
            dlg_bot = max(plate["y"] - self.DIALOGUE_SPAN, self.DIALOGUE_MIN_Y)
            # a role/title line under the name is part of the plate, not the
            # line — drop it before it can seed a dialogue row
            subtitle = self.subtitle_rows(conf, plate)
            conf = [b for b in conf
                    if b is plate or self._row(b) not in subtitle]
        else:
            dlg_bot, dlg_top = self.DIALOGUE_FALLBACK_Y

        # seed rows with centered blocks, then pull in row-mates: Vision often
        # splits one visual line into several blocks whose fragments sit
        # off-center ('Error: Term' + '"Berserker" not found…')
        band = [b for b in conf if b is not plate
                and dlg_bot <= b["y"] + b["h"] / 2 <= dlg_top
                and self.DIALOGUE_WIDE_X[0] <= b["x"] + b["w"] / 2
                <= self.DIALOGUE_WIDE_X[1]]
        seed_rows = {self._row(b) for b in band if self.is_dialogue_seed(b)}
        for b in conf:
            if b is plate:
                continue
            if b in band and self._row(b) in seed_rows:
                state["dialogue"].append(b)
            elif (in_region(b, self.CHOICES)
                  and self.CHOICE_LEFT_EDGE[0] <= b["x"] <= self.CHOICE_LEFT_EDGE[1]
                  and b["h"] >= self.CHOICE_MIN_HEIGHT):
                state["choices"].append(b)

        # Drop ghost duplicates: the text fade-in makes Vision sometimes
        # return BOTH a stale partial and the full line as overlapping boxes
        # on one row — keep only the widest box where horizontal spans overlap
        rows = {}
        for b in state["dialogue"]:
            rows.setdefault(self._row(b), []).append(b)
        kept = []
        for row in rows.values():
            row.sort(key=lambda b: -b["w"])
            chosen = []
            for b in row:
                x0, x1 = b["x"], b["x"] + b["w"]
                if any(max(0.0, min(x1, c["x"] + c["w"]) - max(x0, c["x"]))
                       > 0.6 * b["w"] for c in chosen):
                    continue
                chosen.append(b)
            kept.extend(chosen)
        state["dialogue"] = kept

        # Merge: rows top-to-bottom, fragments left-to-right within a row
        state["dialogue"].sort(
            key=lambda b: (round((1 - (b["y"] + b["h"] / 2)) / self.LINE_H),
                           b["x"]))
        dialogue_text = " ".join(b["text"] for b in state["dialogue"])

        # A nameplate with nothing under it is not a nameplate. Un-nameplated
        # narration ("A bicycle station.") is short and centered enough to
        # pass the plate filters, so it became a phantom speaker with empty
        # dialogue — which live.py drops SILENTLY (the skip log only fires
        # when there IS text), so whole lines vanished with no trace in the
        # log. Re-parse with the plate suppressed so the line lands in the
        # fallback band instead.
        if (plate is not None and not dialogue_text and not _no_plate
                and self.REPARSE_PLATELESS):
            return self.classify(blocks, _no_plate=True)

        # Group choice lines into options: lines belong to the same option if
        # their vertical gap is small (< 1.5x line height)
        state["choices"].sort(key=lambda b: -b["y"])
        options, current = [], []
        prev = None
        for b in state["choices"]:
            if prev is not None:
                # An absolute gap compares row CENTERS: an icon glyph fused
                # into a block inflates its height and so shrinks the
                # bottom-edge gap below the real row pitch (measured: the
                # Dispatch row at h=0.034 against its neighbors' 0.024),
                # while the centers keep the drawn pitch. The legacy rule
                # stays on bottom edges — it predates the measurement and
                # its games are calibrated to it.
                if self.CHOICE_GROUP_GAP:
                    split = ((prev["y"] + prev["h"] / 2)
                             - (b["y"] + b["h"] / 2)) > self.CHOICE_GROUP_GAP
                else:
                    split = (prev["y"] - b["y"]) > 1.5 * max(prev["h"],
                                                             b["h"])
                if split:
                    options.append(" ".join(x["text"] for x in current))
                    current = []
            current.append(b)
            prev = b
        if current:
            options.append(" ".join(x["text"] for x in current))

        return {"speaker": state["speaker"], "dialogue": dialogue_text,
                "choices": options,
                # the blocks this screen was actually read from. The change
                # gate watches these and nothing else: HUD chrome and
                # Genshin's permanent UID sit over open world, so judging
                # them would hand the verdict to whatever the scenery is
                # doing, while a dialogue panel is dark and still between
                # keystrokes. Choice blocks are in here because an option
                # bubble can arrive AFTER the line beneath it has settled —
                # left out, the gate would call that frame unchanged and the
                # prompt would go unseen until the next line.
                "boxes": ([plate] if plate is not None else [])
                + state["dialogue"] + state["choices"],
                # weakest link of the rows that made the line: a mid-fade or
                # half-rendered read scores visibly below settled text, and
                # live.py uses that to make shaky reads earn extra sightings.
                # Engines without real confidences report 1.0 → no effect.
                "conf": min((b["confidence"] for b in state["dialogue"]),
                            default=1.0)}

    # ------------------------------------------------------------------
    # Narration / lore cards
    # ------------------------------------------------------------------
    def classify_narration(self, blocks):
        """Detect the full-screen narration layout: confident text only in
        the center band of an otherwise empty (black) screen. Returns joined
        text or None."""
        if "narration" not in self.SCREENS:
            return None
        # system screens (epilepsy warning etc.) look like narration — never
        # read them. Loading screens are handled separately before this runs.
        if self.is_system_screen(blocks):
            return None
        confident = [b for b in self.speakable(blocks)
                     if b["y"] > 0.06]        # ignore bottom strip (UID, hints)
        if not confident:
            return None
        center = [b for b in confident if in_region(b, self.NARRATION_BAND)]
        # every confident block must be in the band — HUD text anywhere else
        # means this is gameplay, not a narration screen
        if not center or len(center) != len(confident):
            return None
        center.sort(key=lambda b: -b["y"])
        text = " ".join(b["text"] for b in center)
        if (len(text) < self.NARRATION_MIN_CHARS
                or len(text.split()) < self.NARRATION_MIN_WORDS
                or text.lstrip().startswith("Warning")
                or "%" in text
                or sum(c.isdigit() for c in text)
                > self.NARRATION_MAX_DIGIT_RATIO * len(text)):
            return None
        return text

    def classify_lore_screen(self, blocks):
        """Full-screen lore/loading cards that carry NO chrome: a centered
        title in the nameplate band with centered prose below it, and no
        story-chrome hint, no bottom strip (UID/build), no HUD. Those cards
        look exactly like a dialogue screen to classify() — title reads as a
        nameplate — so they'd otherwise be skipped as an unknown speaker.

        Returns (title, text) or None. Gameplay dialogue always carries some
        chrome, which disqualifies it here.
        """
        if "lore" not in self.SCREENS:
            return None
        conf = self.confident(blocks)
        if not conf or self.trusts_dialogue(blocks):
            return None
        for b in conf:                      # any chrome at all disqualifies
            cy = b["y"] + b["h"] / 2
            if cy < 0.08 or cy > 0.90:      # UID/build strip, HUD rails
                return None
        body = [b for b in conf if 0.15 <= b["x"] + b["w"] / 2 <= 0.85]
        if len(body) != len(conf) or len(body) < 2:
            return None                     # off-center text => not a lore card
        body.sort(key=lambda b: -b["y"])
        title = body[0]["text"].strip()
        text = " ".join(b["text"] for b in body[1:]).strip()
        if (len(text) < self.NARRATION_MIN_CHARS
                or len(text.split()) < self.NARRATION_MIN_WORDS):
            return None
        if sum(c.isdigit() for c in text) > self.NARRATION_MAX_DIGIT_RATIO * len(text):
            return None                     # menus/stat panels are digit-heavy
        return title, text

    def classify_loading(self, blocks):
        """Loading screens: their title + lore text sit in the dialogue bands
        and would otherwise misparse as a speaker + line. Returns the lore
        text or None."""
        return None

    # ------------------------------------------------------------------
    # Optional per-game screens. A profile opts in via SCREENS and
    # supplies the geometry; games without the screen inherit None.
    # ------------------------------------------------------------------
    def classify_overlay(self, blocks):
        """Floating overlay dialog (portrait + speech bubble mid-screen)."""
        return None

    def classify_quickread(self, blocks):
        """In-game reading panel. Returns ordered body-line texts or None."""
        return None

    def classify_infoscreen(self, blocks):
        """Profile/info screens. Returns body texts in reading order."""
        return None

    def classify_chat(self, blocks):
        """Message/group-chat panel. Returns [(sender, text), …] or None."""
        return None

    # ------------------------------------------------------------------
    # Game detection: how confident are we that this frame is THIS game?
    # ------------------------------------------------------------------
    def fingerprint(self, blocks):
        """1.0 = chrome unique to this game is on screen, 0.0 = no evidence.
        Never negative: absence of one game's chrome is not evidence for
        another's, and most frames (menus, combat) show neither."""
        return 0.0
