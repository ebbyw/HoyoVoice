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
  * No phone UI: no group-chat panel, no Quick Read book screen.
"""
import re

from .base import Profile, in_region, split_camel


class Genshin(Profile):
    name = "genshin"
    label = "Genshin Impact"
    # Only screens whose geometry has been checked against real frames.
    # Choice prompts did not occur in the calibration capture; they stay off
    # rather than guessed at, because a wrong band does not fail quietly —
    # it narrates menus. See CALIBRATE below.
    SCREENS = frozenset({"dialogue", "narration", "loading"})

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

    # Nameplate: cy 0.222-0.253, cx 0.493-0.504, w 0.034-0.058. The floor is
    # 0.21 rather than 0.18 deliberately — the role subtitle sits at
    # cy~=0.198 and must not be able to win the speaker slot.
    PLATE_Y = (0.21, 0.28)
    PLATE_X = (0.45, 0.55)
    PLATE_MAX_W = 0.25

    # Dialogue: rows run from just under the plate down to cy=0.134 (the
    # deepest row seen, a 3-row line). The span stops at 0.10 so the
    # Auto/Confirm chrome row at cy~=0.067 stays out of the band entirely.
    # Rows are accepted across the whole text column rather than by Star
    # Rail's centered-seed test. Genshin centers each row, but only once it
    # is fully typed: the typewriter reveals a row rightward from its final
    # left edge, so a half-typed row's center sits anywhere left of the
    # axis (measured 0.24 and 0.38 on rows that finished at 0.50). Nothing
    # else lands in the band — the Auto/Confirm chrome row is at cy~=0.067,
    # well below its floor — so the column bounds are all that is needed.
    DIALOGUE_X = (0.15, 0.85)
    DIALOGUE_SPAN = 0.10
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
    SUBTITLE_MAX_H = 0.032
    SUBTITLE_MAX_DX = 0.012         # from the plate's center axis
    SUBTITLE_MAX_DROP = 0.036       # below the plate's baseline

    # Choice options float to the right of the dialogue box, above it, each
    # row left-aligned past a chat-bubble icon (the icon is not text, so the
    # left edge is where the option text starts): measured x 0.686-0.689,
    # rows at cy 0.291 and 0.267 across two prompts.
    # CALIBRATE: both prompts in the capture were a SINGLE two-row option,
    # so how far a longer list stacks upward is unverified — the ceiling
    # here is Star Rail's and may be short.
    CHOICES = {"x": (0.66, 1.00), "y": (0.22, 0.62)}
    CHOICE_LEFT_EDGE = (0.66, 0.75)
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
        state = super().classify(blocks, _no_plate)
        # A choice prompt only exists alongside a speaker. The teleport map
        # lists its waypoints ("Sea of Bygone Eras", "Temple of Space"…) in
        # the same column at the same left edge, and reads as a three-option
        # prompt otherwise; it has no nameplate.
        if state["choices"] and not state["speaker"]:
            state["choices"] = []
        return state

    def is_plate_subtitle(self, block, plate):
        cx = block["x"] + block["w"] / 2
        pcx = plate["x"] + plate["w"] / 2
        return (block["h"] <= self.SUBTITLE_MAX_H
                and abs(cx - pcx) <= self.SUBTITLE_MAX_DX
                and 0 < plate["y"] - block["y"] <= self.SUBTITLE_MAX_DROP)

    def fingerprint(self, blocks):
        return 1.0 if self._uid_corner(blocks) else 0.0
