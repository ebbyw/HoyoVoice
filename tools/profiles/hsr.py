#!/usr/bin/env python3
"""Honkai: Star Rail layout profile.

Every band here is calibrated against real 1080p frames; the comments say
what each number is defending against. Re-measure from a saved
`captures/shots/<id>.json` before changing one.
"""
import difflib
import re

from .base import Profile, in_region


class HSR(Profile):
    name = "hsr"
    label = "Honkai: Star Rail"
    PLAYER_NAME = "Trailblazer"
    SCREENS = frozenset({"dialogue", "narration", "lore", "loading",
                         "overlay", "quickread", "infoscreen", "chat"})

    IGNORE = frozenset({"Continue", "→"})

    # The dialogue box sits at slightly different heights in cinematic vs
    # overworld conversations, so dialogue is ANCHORED to the nameplate
    # rather than a fixed band.
    PLATE_Y = (0.18, 0.31)
    PLATE_X = (0.35, 0.65)
    PLATE_MAX_W = 0.30
    DIALOGUE_X = (0.40, 0.60)
    DIALOGUE_SPAN = 0.15
    # Overlaps PLATE_Y on purpose: a single-line dialogue/narration row sits
    # at cy~=0.189, one pixel of OCR jitter away from the plate band, and the
    # old 0.19 ceiling clipped it on the frames that jittered upward.
    DIALOGUE_FALLBACK_Y = (0.08, 0.21)

    CHOICES = {"x": (0.66, 1.00), "y": (0.22, 0.62)}
    CHOICE_LEFT_EDGE = (0.68, 0.78)
    CHOICE_MIN_HEIGHT = 0.020

    # "Quick Read" book screens: label top-left, Scroll/Back hints bottom
    QUICKREAD_BODY = {"x": (0.28, 0.76), "y": (0.08, 0.90)}

    # Floating overlay dialog (event-hub host bubble): portrait + speech box
    # in the upper-center band, with its own "Continue" hint floating
    # mid-screen
    OVERLAY_BAND = {"x": (0.33, 0.78), "y": (0.70, 0.88)}

    # Info screens (Participant Details etc.): header top-left, Back hint
    # bottom
    INFO_HEADERS = ("participant details",)

    # --- message/group-chat panel ("Answer" screens) -------------------
    # All of these are tuned to this game's phone UI at 1080p.
    #
    # The body floor sits ABOVE the Scroll/Back hint row (y~=0.13-0.16):
    # those hints include bare button glyphs ("R", "O") that no text filter
    # can catch, and one was read aloud as a message. Nothing is lost — a
    # message whose last row lands that low is still scrolling in and is
    # deferred.
    CHAT_BODY = {"x": (0.63, 0.97), "y": (0.20, 0.74)}
    # conversation title above the message list ("Ashveil" over "Answer")
    CHAT_HEADER = {"x": (0.52, 0.88), "y": (0.75, 0.92)}
    # Sender labels sit at the bubble's left edge, message text is indented —
    # but only just. Measured across real frames: labels land at x=0.659,
    # message rows at x=0.671, so the two classes are separated by 0.011 and
    # nothing else distinguishes them. This is the midpoint of that gap, a
    # calibrated value rather than a round number; re-measure from
    # shots/<id>.json before changing it.
    CHAT_SENDER_MAX_X = 0.665
    # Message rows are LEFT-ALIGNED to one column: 0.671 in the original
    # calibration frames, 0.6698-0.6703 in shot #1 (2026-08-30 13:11) — a
    # spread of ~0.001 across sessions. A row right of the sender split that
    # is NOT aligned here is a reply-option button: those are centred in the
    # panel ("That's right", left edge 0.7130 in that same shot), so their
    # left edge moves with their text length and no threshold can hold them —
    # alignment is the same trick the Messages app bands use. Tolerance
    # matches MSGAPP_ALIGN_TOL's reasoning: several times the measured
    # spread, still clear of the sender column at 0.657-0.659.
    CHAT_MSG_X = 0.6705
    CHAT_ALIGN_TOL = 0.005
    # Defer a message whose deepest row sits this low: near the panel's clip
    # edge, rows below are simply not rendered yet, and reading there
    # produced a truncated message ("…Should be") followed by the full one a
    # moment later. Kept clear of the body floor so a partly-visible message
    # is always deferred rather than half-read.
    CHAT_CLIP_Y = 0.26
    CHAT_NOTICE_RATIO = 0.65       # measured: real notices 0.82-1.00, real
                                   # messages 0.33-0.42 — a wide, safe gap
    # In-conversation system notices. These are events, not speech, so they
    # are read by the narrator rather than in the sender's voice. The small
    # grey text OCRs badly ("started shan ing (ocation", "slarted sharing
    # (ecatton"), so match tolerantly and speak a canonical wording — which
    # also collapses the variants to one entry for dedupe.
    CHAT_NOTICES = ("started sharing location",)
    CHAT_NOTICE_SENDER = ""        # falsy but not None: narrator, never inherited

    # Panel chrome that sits INSIDE the body band: the Scroll/Back hints hug
    # its lower edge, and system notices ("Conversation Over", "… started
    # sharing location") print in the message column. Left in, they attach to
    # the last message and drag its position under the clip threshold, which
    # deleted the final message of every conversation.
    CHAT_SYSTEM_ROW = re.compile(
        r"^(scroll|back|answer|conversation over)$", re.I)

    # --- phone "Messages" app (the regular character chats) -------------
    # A second, unrelated panel: full-screen, the conversation list down
    # the left, the open thread on the right, unsent reply options as
    # buttons across the bottom. Nothing detected it, so the 2026-08-28
    # 14:14 session (rec_20260828_141426, shots #2-#16 — every number
    # here) was read as dialogue instead: the thread header was SPOKEN as
    # a line ("Rin iTahsaka", 14:15:01), a conversation-list preview was
    # auto-cast as a speaker ("This is way too cute"), a delivery notice
    # was auto-cast as another ("Message" → zm_yunxi, 14:15:14), and the
    # player's own sent bubbles landed in the CHOICES band and were read
    # back to them in the Trailblazer's voice.
    _MSGAPP_MARKER = re.compile(r"^messages$", re.I)
    MSGAPP_MARKER_REGION = {"x": (0.02, 0.20), "y": (0.90, 0.99)}
    # Conversation title above the thread (cx=0.347, cy=0.863). The x
    # floor keeps out the list's own copy of the same name (cx=0.118);
    # the y floor keeps out the title's tagline row (cy=0.832), which
    # would otherwise become the sender whenever the name row is missed.
    MSGAPP_HEADER = {"x": (0.28, 0.60), "y": (0.845, 0.90)}
    # The thread pane. The ceiling sits between that tagline (cy=0.832)
    # and the highest message label measured (cy=0.795); the floor clears
    # the Scroll/Select/Back hints (cy<=0.026) while keeping a row still
    # sliding up from the pane's bottom edge (cy=0.087).
    MSGAPP_BODY = {"x": (0.30, 0.92), "y": (0.05, 0.81)}
    # Rows are sorted by what they are ALIGNED to, not by which side of a
    # threshold they fall — the pane has four alignments and a row's own
    # width is irrelevant to all of them:
    #   sender label   left-aligned  0.3662-0.3677
    #   incoming row   left-aligned  0.3779-0.3794
    #   player row     right-aligned 0.8663-0.8677
    #   player label   right-aligned 0.8808-0.8833 (to the avatar, not the
    #                                bubble)
    # A threshold was tried first and got both edges wrong: the player's
    # longest reply starts at x=0.5945, left of any sensible "player
    # column" floor, and the longest delivery notice starts at x=0.3939,
    # right of the incoming rows but inside any band wide enough to be
    # safe. Alignment separates them with nothing to tune. Re-measure
    # from shots/<id>.json before touching a number here.
    MSGAPP_SENDER_X = 0.3670
    MSGAPP_INCOMING_X = 0.3786
    MSGAPP_PLAYER_RIGHT = 0.8670
    MSGAPP_PLAYER_LABEL_RIGHT = 0.8820
    # Five times the widest spread measured on any of the four (0.0015,
    # on the player bubbles), and still narrow enough to keep the four
    # windows apart: the closest pair is the incoming label and the row
    # under it, 0.0116 apart.
    MSGAPP_ALIGN_TOL = 0.005
    # Anything aligned to none of them is not speech: the delivery
    # notices ("Message failed to send.", "The user you're trying to
    # reach is currently out of the service area.") are UI status, and
    # the reply buttons across the bottom are options the player has not
    # picked yet — each is read once it has been SENT, as their own
    # bubble, which is also why reading them here would say every chosen
    # line twice.
    #
    # The one thing this cannot see is a player bubble long enough to
    # wrap: the bubble is right-aligned but its text is not, so a second
    # row would end short of MSGAPP_PLAYER_RIGHT and be dropped. Replies
    # here are the option-button texts, whose longest measured ("It's an
    # honor to fight alongside you, Master.", 0.273 wide) is barely half
    # the pane's wrap width.
    # A bubble is faded in whole here rather than clipped by the pane
    # edge: across shots #2-#16 every thread row read identically while
    # it was still rising, so there is no half-drawn read to defer and no
    # clip threshold (the Answer panel's CHAT_CLIP_Y). One would cost the
    # last message of a quiet thread, which has nothing arriving after it
    # to push it up out of the way.

    # --- Incoming Message Notification (a message popup over the world) --
    # A fourth chat layout: the modal that opens when a message arrives
    # mid-exploration, contact list on the left under the title "Incoming
    # Message Notification", the open thread on the right, reply options
    # in a band under the thread. Nothing detected it, so the 2026-11-12
    # 13:15 session (rec_20261112_131536, Windows box) spoke one line in
    # ninety seconds of a ten-message thread: the player's first reply,
    # read as dialogue with their own label glued on ("Ebby Hi, Kafka",
    # 13:16:10), after the same reply had been logged twice as an
    # unattributed choice prompt. Every number here is measured off that
    # recording at 2 fps (152 frames OCR'd by the Vision daemon); re-
    # measure from a saved frame before changing one.
    #
    # The title is the marker: it is the same on every conversation and
    # sits where no other HSR screen draws text (cx 0.268, cy 0.776).
    # Spaces are optional because RapidOCR drops them on the Windows box;
    # "notification" is required because the Furbobocom clipping carries
    # an "Incoming Message" chip of its own.
    MSGNOTE_MARKER = re.compile(r"incoming\s*message\s*notification", re.I)
    MSGNOTE_MARKER_REGION = {"x": (0.20, 0.34), "y": (0.76, 0.80)}
    # The thread pane. Its x floor clears the contact list (right edges to
    # 0.3735) and still holds a wrapped player row (left 0.4447); its
    # ceiling sits under the conversation title (cy 0.787) and over the
    # garbled half-hidden rows (cy to 0.752), which the thread parser has
    # to SEE to know their message is clipped; its floor clears the hint
    # row (cy 0.137).
    MSGNOTE_BODY = {"x": (0.43, 0.80), "y": (0.16, 0.765)}
    # While the Select hint is up the pane shrinks to make room for the
    # reply options under it (thread rows end at cy 0.418, options start
    # at cy 0.340). The options are centred, but centred text lands on a
    # column by its width alone: "Pls don't abuse Blade's account..."
    # ended at x 0.7399 — on the player column — and a long one would
    # start on the incoming column. Options are never read here: the one
    # picked comes straight back as the player's own bubble, so reading
    # them would say every chosen line twice (the Messages app's rule).
    MSGNOTE_SELECT_BODY = {"x": (0.43, 0.80), "y": (0.36, 0.765)}
    MSGNOTE_HINT_Y = (0.12, 0.16)
    # Columns, as in the other threads:
    #   player row     left-aligned  0.4447-0.4477 (a wrapped bubble)
    #                  right-aligned 0.7398-0.7413 (a one-row bubble)
    #   sender label   left-aligned  0.4780-0.4797
    #   incoming row   left-aligned  0.4875-0.4913
    #   player label   right-aligned 0.7558-0.7579
    # The player's bubble is right-hung with its text left-aligned inside,
    # like the Furbobocom popup's, so a wrapped one aligns on the left.
    # The closest pair of windows is the label and incoming columns,
    # 0.011 apart; FURBO_ALIGN_TOL (0.005) keeps them apart.
    MSGNOTE_SENDER_X = 0.4788
    MSGNOTE_INCOMING_X = 0.4895
    MSGNOTE_PLAYER_EDGES = (("left", 0.4462), ("right", 0.7405))
    MSGNOTE_PLAYER_LABEL_RIGHT = 0.7562
    # The thread scrolls up under the title rule. Clean rows top out at
    # 0.7416 (a label); rows caught under it come back garbled at full
    # confidence ("Just warma cater ap wir you", top edge 0.7597) and
    # start at 0.7547.
    MSGNOTE_CLIP_TOP = 0.748
    # Finishing the conversation pays out: an "Items Obtained" modal
    # (title cx 0.500, cy 0.831-0.836) blanks the whole popup for 1.5 s
    # (75.5-77.0 in the recording) while the last bubbles are still
    # queued — within half a second of READER_CLOSE_AFTER at 2 fps on
    # the fast OCR path, and the frame where the popup comes back under
    # it reads its rows garbled ("Stellarejadime Ill try sending…"). So
    # the modal pauses the close timer and the popup reads nothing under
    # it.
    REWARD_TITLE = re.compile(r"^items\s*obtained$", re.I)
    REWARD_TITLE_REGION = {"x": (0.45, 0.55), "y": (0.80, 0.87)}

    # --- Furbobocom (the furbo event hub) --------------------------------
    # A third chat layout, and two more screens around it. Every number
    # here is measured off rec_20261110_213011 at 1080p (21 frames OCR'd
    # with the Vision daemon); re-measure from a saved frame before
    # changing one.
    #
    # The hub is a full-screen app whose pages carry "Furbobocom" over the
    # page name top-left ("Clue Investigation", "Press Affairs"). The grey
    # app name reads at Vision confidence 0.50, the page name at 1.00, so
    # the marker is the weaker one on purpose: it is the word that is the
    # same on every page.
    FURBO_HUB_MARKER = re.compile(r"furbob", re.I)
    FURBO_HUB_REGION = {"x": (0.02, 0.20), "y": (0.92, 0.99)}
    FURBO_LABEL_MIN_CONF = 0.5
    # Clue Investigation: a thread pane under a progress bar. Sender labels
    # sit beside the avatar, bubbles start a column to the right, and the
    # player's bubbles hang on the right edge with their label beside the
    # player's avatar — the same four alignments as the Messages app, at
    # this panel's own columns:
    #   sender label   left-aligned  0.2500-0.2515   (conf 0.50, grey)
    #   incoming row   left-aligned  0.2625-0.2645
    #   player row     right-aligned 0.7384-0.7417
    #   player label   right-aligned 0.7515-0.7527
    # As in the Messages app, a player bubble long enough to wrap is
    # right-hung but its text is not: a second row would end short of
    # the edge and be dropped. None was recorded; the popup below shows
    # what such a bubble does there.
    FURBO_CHAT_TITLE = re.compile(r"^clue investigation$", re.I)
    FURBO_CHAT_TITLE_REGION = {"x": (0.02, 0.25), "y": (0.89, 0.95)}
    # The pane: ceiling under the "Clue Source" tab and the "Furbo is
    # busy…" bubble (cy 0.845-0.858); floor above the bottom hints, with
    # the reply options (cy 0.128-0.295) inside it because they are read.
    FURBO_BODY = {"x": (0.24, 0.80), "y": (0.08, 0.78)}
    FURBO_SENDER_X = 0.2513
    FURBO_INCOMING_X = 0.2637
    FURBO_PLAYER_EDGES = (("right", 0.7400),)
    FURBO_PLAYER_LABEL_RIGHT = 0.7521
    # Reply options are drawn centred in an orange band under the thread
    # (cx 0.505-0.507, cy ≤ 0.295); nothing else in the pane is centred
    # except the caption of a status card ("Furbo is on the way back…",
    # cy 0.226), which this reads as a lone option — in the player's
    # voice, once. A rare talk-over beats dropping a real lone option.
    FURBO_OPTION_Y = 0.31
    # The thread scrolls UP under the pane's top edge (y 0.752), and a row
    # caught half under it reads as garbage ("oput mio unrer em", top edge
    # 0.7442) that would prefix the rest of its message and defeat the
    # reader's tail suppression. Anything whose top edge crosses this
    # line is the OLDEST message on screen, already read when it was
    # whole, so the message it starts is dropped. Clean rows top out at
    # 0.7366 (a label) and 0.6802 (text).
    FURBO_CLIP_TOP = 0.740
    # Every bubble in these panes carries its label, drawn this far above
    # the bubble's first row (label bottom to row top: 0.022 in the pane,
    # 0.018 in the popup, under a label 0.024 tall). A message with no
    # label whose first row starts within that reach of the clip line is
    # one whose label has scrolled under it — a message already read when
    # it was whole, now coming back as its own tail. Containment in the
    # reader catches most of those; it missed "paws?" (too short to
    # test) and 'Gemibo -2"' (the original read 'Gemibo - 2"'), both
    # spoken alone in the 2026-11-10 replay.
    FURBO_LABEL_REACH = 0.045
    # The group-chat popup ("AAA Furbobo Weekly Wholesale Requests"): a
    # centred modal over the blurred hub, title and tagline left-aligned
    # at x 0.339-0.341 (cy 0.792/0.765), everything else blurred away. The
    # player's bubbles are right-hung but their TEXT is left-aligned
    # inside the bubble, and a wrapped bubble is as wide as the column —
    # so the player rows align on the LEFT, at 0.3661-0.3676, left of the
    # sender column; the player label is right-aligned to the avatar.
    #   player row     left-aligned  0.3661-0.3676 (a wrapped bubble)
    #                  right-aligned 0.5843         (a one-row bubble)
    #   sender label   left-aligned  0.3846-0.3866   (conf 0.50, grey)
    #   incoming row   left-aligned  0.3952-0.3983
    #   player label   right-aligned 0.5965-0.5976
    # The right edge is INFERRED, not measured: no one-row player bubble
    # was recorded. The bubble hangs at x 0.5948 and the full-screen pane
    # pads its text 0.010 inside the bubble; the two wrapped rows that
    # fill the column end at 0.5828 and 0.5843. Reply options are centred
    # (left 0.4041, right 0.5959-0.5974 — 0.012 clear of that edge, and
    # the same right edge as the player label, so labels are also held to
    # LABEL_MAX_W) and show only with the Scroll/Select hints (cy 0.143).
    FURBO_POPUP_HEADER = {"x": (0.33, 0.35), "y": (0.78, 0.805)}
    FURBO_POPUP_HEADER_MIN_W = 0.15
    FURBO_POPUP_X = (0.32, 0.68)
    # floor above the Scroll/Select hint row (cy 0.143), which is centred
    # like an option and was read as one ("Scroll Select"); the lowest
    # real row is an option at cy 0.205
    FURBO_POPUP_BODY = {"x": (0.32, 0.68), "y": (0.17, 0.76)}
    FURBO_POPUP_SENDER_X = 0.3857
    FURBO_POPUP_INCOMING_X = 0.3967
    FURBO_POPUP_PLAYER_EDGES = (("left", 0.3668), ("right", 0.5843))
    FURBO_POPUP_PLAYER_LABEL_RIGHT = 0.5972
    FURBO_POPUP_OPTION_Y = 0.30
    FURBO_POPUP_HINT_Y = (0.12, 0.16)
    # clean rows top out at 0.739, clipped ones start at 0.7444
    FURBO_POPUP_CLIP_TOP = 0.740
    # Five times the widest measured spread (0.0017, the player rows in
    # the full-screen pane); the closest pair of windows is the popup's
    # sender/incoming columns, 0.011 apart.
    FURBO_ALIGN_TOL = 0.005
    # A label is short; the one thing that shares a label's alignment is a
    # popup option wide enough to fill its button (w 0.19 — a short option
    # is centred, nowhere near the label's edge). Wide enough for the
    # double-act's name ("Bruce Furlee & Tiger Furlee", ~0.13).
    FURBO_LABEL_MAX_W = 0.15
    # The furbo office scenes: ordinary boxed dialogue with the '✕
    # Continue' hint, but the nameplate is a tab on the box's LEFT corner
    # (cx 0.274, cy 0.260, left edge 0.248-0.250, conf 0.50) — outside the
    # centred plate band, so the line was surrendered to the narrator and
    # Gemibo's and Joolyon's lines read in the narrator's voice (21:31:30,
    # 21:36:03 on 2026-11-10). The rows under it are centred as usual.
    FURBO_PLATE_X = (0.22, 0.33)
    # The Clue Source article the pane opens on (a news clipping: source
    # name and an "Incoming Message" chip beside an avatar, a rule, then
    # the clipping's prose): read by the narrator through the reading
    # panel's reader, which joins rows and dedupes per row. The source
    # name sits at x 0.2602 — inside the thread's incoming-row tolerance,
    # which is why the thread parser saw it as a message and the reward
    # line under the prose ("Complete investigation to obtain ×1") and
    # the Forward button as reply options. The prose column at 0.2122-
    # 0.2151 is what tells the two apart: no thread row ever starts
    # there (the avatar misreads at 0.2122-0.2137 carry no letters).
    FURBO_ARTICLE_X = 0.2140
    FURBO_ARTICLE_TITLE_X = 0.2602
    FURBO_ARTICLE_CHIP = re.compile(r"^incoming message$", re.I)
    # Investigation Results: the pane shrinks to the left half and a
    # Progress Report column opens on the right (rows at x 0.629-0.634,
    # right edges to 0.7398 — ON the full pane's player column, so
    # "Furbobo Weekly is" and "figurines!" were read as the player's
    # bubbles). The shrunken pane keeps the thread, at its own columns —
    # one frame pair each (shots at 410 s and 414 s of the recording):
    #   sender label   left-aligned  0.1932
    #   incoming row   left-aligned  0.2048-0.2063
    #   player row     right-aligned 0.4869
    #   player label   right-aligned 0.4985
    # Its reply options and the "Investigation Concluded" notice are both
    # centred in the half-pane, so options are not read here.
    FURBO_RESULTS_MARKER = re.compile(r"^investigation results$", re.I)
    FURBO_RESULTS_MARKER_REGION = {"x": (0.60, 0.85), "y": (0.83, 0.88)}
    # The report column is the second marker, because the screen
    # animates in and the column's rows can be on screen a frame before
    # its header is readable: the replay of rec_20261110_213011 still
    # read "Furbobo Weekly is" with the header test alone. Two rows on
    # the column's left edge (0.6294-0.6337) say the column is up; one
    # could be a player bubble whose width happens to end there.
    FURBO_REPORT_X = 0.6312
    FURBO_RESULTS_BODY = {"x": (0.18, 0.56), "y": (0.08, 0.78)}
    FURBO_RESULTS_SENDER_X = 0.1932
    FURBO_RESULTS_INCOMING_X = 0.2055
    FURBO_RESULTS_PLAYER_EDGES = (("right", 0.4869),)
    FURBO_RESULTS_PLAYER_LABEL_RIGHT = 0.4985

    # ------------------------------------------------------------------
    # Chrome
    # ------------------------------------------------------------------
    def trusts_dialogue(self, blocks):
        """Dialogue and narration screens show '✕ Continue' bottom-right;
        menus, boards, and info popups show other hints (Confirm, Adjust
        Lineup…)."""
        return any(b["y"] < 0.08 and b["x"] > 0.78
                   and "continue" in b["text"].strip().lower() for b in blocks)

    def _bottom_left_strip(self, blocks):
        """Joined text of the bottom-left build/UID strip. Engines disagree
        on how they chunk it — Apple Vision returns one block, Windows OCR
        splits it and often drops the underscores — so match on the JOINED
        text.

        Filters by confidence itself so every caller sees the same strip
        whether it passes raw or pre-filtered blocks.
        """
        strip = [b for b in self.confident(blocks)
                 if b["y"] < 0.08 and b["x"] + b["w"] / 2 < 0.45]
        strip.sort(key=lambda b: b["x"])
        return " ".join(b["text"] for b in strip)

    def is_system_screen(self, blocks):
        """Bottom-left build string ('OSPRODNAPS…_D…_A…') marks system
        screens: loading screens, epilepsy warnings, etc. Matched on the
        joined strip — OCR engines chunk it differently and may drop the
        underscores."""
        strip = self._bottom_left_strip(blocks)
        return (strip.count("_") >= 2
                or (re.search(r"\d\.\d", strip) is not None and len(strip) >= 30))

    def fingerprint(self, blocks):
        if self.trusts_dialogue(blocks) or self.is_system_screen(blocks):
            return 1.0
        return 0.0

    # ------------------------------------------------------------------
    # Screens
    # ------------------------------------------------------------------
    def classify(self, blocks, _no_plate=False):
        # A Furbobocom page is a menu: the Press Affairs card wall reads
        # as a nameplate and a choice list otherwise (a card's quip was
        # spoken as a line and two more as a prompt, 21:37:15 on
        # 2026-11-10). Its one conversation screen is a chat panel, read
        # by classify_chat before this runs.
        if (self._furbo_hub(blocks)
                or self._classify_furbo_popup(blocks) is not None):
            return {"speaker": None, "dialogue": "", "choices": [],
                    "boxes": [], "conf": 1.0}
        state = super().classify(blocks, _no_plate)
        if state["dialogue"] and not state["speaker"]:
            plate = self._furbo_plate(blocks)
            if plate is not None:
                state["speaker"] = plate["text"].strip()
                state["boxes"] = [plate] + state["boxes"]
        # A choice prompt needs either a speaker beside it or the game's
        # story chrome above it. This game's menus keep landing 1-2 blocks
        # in the choice band and reading them aloud as Trailblazer: the
        # Currency Wars team-setup tooltip ("Increases DMG dealt by all
        # allies…", shot #132 2026-08-24, left edges 0.738-0.757),
        # combat-screen effect names, nav labels ("Data Bank", "Back"),
        # and the Battle Preparations enemy-team title ("Mysterious
        # Familiars", x=0.712 — frames 268-272 of rec_20260726_121902 at
        # 1 fps). Every genuine prompt in that corpus kept its plate
        # (frames 111, 482-490, 547-549: the box below the bubbles still
        # shows the speaker), so the plate alone was made the test.
        #
        # It is necessary but not sufficient. A cutscene hands the player
        # a lone option with no dialogue box under it at all, and nothing
        # to plate: "I will not back down." (shot #155, 2026-08-30 12:23,
        # x=0.710) was dropped with the menus and logged "choice prompt
        # (ignored — no speaker)". The '✕ Continue' hint bottom-right is
        # what the two cases disagree on — it marks a story screen, while
        # the menus draw Confirm / Back / Start Challenge — and across the
        # 330 saved frames on hand a plateless choice list and that hint
        # coincided on exactly one: this cutscene.
        if (state["choices"] and not state["speaker"]
                and not self.trusts_dialogue(blocks)):
            state["choices"] = []
        return state

    def classify_loading(self, blocks):
        """Detect loading screens via the long version string bottom-left
        (e.g. 'OSPRODNAPS54.4.1_D…_A…_L… UID:…')."""
        conf = self.confident(blocks)
        strip = self._bottom_left_strip(conf)
        up = strip.upper()
        # UID is what separates loading screens from other system screens;
        # the build-string evidence is tolerant because engines mangle it
        # differently (underscores dropped, split across blocks)
        marker = "UID" in up and (strip.count("_") >= 2
                                  or re.search(r"\d\.\d", strip) is not None
                                  or len(strip) >= 40)
        if not marker:
            return None
        center = [b for b in conf
                  if 0.25 <= b["x"] + b["w"] / 2 <= 0.75
                  and 0.08 <= b["y"] <= 0.30]
        if not center:
            return None
        center.sort(key=lambda b: -b["y"])
        text = " ".join(b["text"] for b in center)
        return text if len(text) >= 15 else None

    def classify_overlay(self, blocks):
        conf = self.confident(blocks)
        floating_hint = any("continue" in b["text"].strip().lower()
                            and 0.55 < b["y"] < 0.78 for b in conf)
        if not floating_hint:
            return None
        body = [b for b in conf if in_region(b, self.OVERLAY_BAND)
                and "continue" not in b["text"].strip().lower()]
        if not body:
            return None
        body.sort(key=lambda b: -b["y"])
        text = " ".join(b["text"] for b in body).lstrip(">•·| ").strip()
        return text if len(text) >= 12 else None

    def classify_quickread(self, blocks):
        conf = self.confident(blocks)
        header = any(b["text"].strip().lower() == "quick read"
                     and b["x"] < 0.25 and b["y"] > 0.85 for b in conf)
        hints = any(b["text"].strip() in ("Scroll", "Back") and b["y"] < 0.08
                    for b in conf)
        if not (header and hints):
            return self._classify_furbo_article(blocks)
        body = [b for b in conf if in_region(b, self.QUICKREAD_BODY)]
        body.sort(key=lambda b: -b["y"])
        return [b["text"] for b in body]

    def classify_infoscreen(self, blocks):
        """Detect profile/info screens and return body texts in reading order
        (rows top-to-bottom, left-to-right), excluding the left tab column."""
        conf = self.confident(blocks)
        header = any(b["text"].strip().lower() in self.INFO_HEADERS
                     and b["y"] > 0.85 and b["x"] < 0.35 for b in conf)
        back = any(b["text"].strip() == "Back" and b["y"] < 0.08 for b in conf)
        if not (header and back):
            return None
        body = [b for b in conf
                if 0.08 < b["y"] < 0.85 and (b["x"] + b["w"] / 2) > 0.22]
        if not body:
            return None
        # rows bucketed at 0.03 of screen height rather than LINE_H: the
        # bucket has to be wide enough that two blocks Vision cut from one
        # row land in it together despite their y differing by a fraction
        # of a line, and narrower than the row pitch of these screens so
        # adjacent rows never fold into one
        body.sort(key=lambda b: (round((1 - b["y"]) / 0.03), b["x"]))
        return [b["text"] for b in body]

    def _chat_notice(self, raw, header_name):
        """Canonical text for a system notice row, or None if it isn't one.

        Slides the comparison window over the tail so a leading sender name
        of unknown length can't dilute the match — that alone was the
        difference between catching one mangled read and missing the other.
        """
        n = re.sub(r"[^a-z]", "", raw.lower())
        if len(n) < 12:
            return None
        for tpl in self.CHAT_NOTICES:
            t = tpl.replace(" ", "")
            best = 0.0
            for pad in (0, 2, 4, 6, 8):
                tail = n[-(len(t) + pad):] if len(n) > len(t) + pad else n
                best = max(best, difflib.SequenceMatcher(None, tail, t).ratio())
            if best >= self.CHAT_NOTICE_RATIO:
                who = header_name or (raw.split() or [""])[0]
                return f"{who} {tpl}".strip()
        return None

    def _classify_answer_panel(self, conf):
        """Returns [(sender, message_text), …] for complete visible messages,
        dropping a bottom message still clipped by the panel edge. None if
        this isn't an Answer screen."""
        hints = {b["text"].strip() for b in conf
                 if 0.10 < b["y"] < 0.20 and b["x"] > 0.72}
        # A panel waiting on a reply option swaps Back for Select, and it
        # can show Select for the WHOLE conversation — rec_20260830_131155
        # holds Scroll/Select on every frame, so nothing in it was read.
        # Select is a much weaker signature than Back (menus everywhere use
        # it), so that variant also demands the panel header below before
        # it counts; the in-panel hint band (0.10-0.20, not the screen-edge
        # 0.08 every other hint row uses) is what keeps menus out of both.
        if not ({"Scroll", "Back"} <= hints or {"Scroll", "Select"} <= hints):
            return None
        # a finished conversation can't have anything still scrolling in, so
        # its last message is complete no matter how low it sits
        ended = any(b["text"].strip().lower() == "conversation over"
                    for b in conf)
        # The panel header names the conversation partner. Messages whose own
        # label scrolled off the top (a run from one sender labels only its
        # first) would otherwise have no sender and read in the narrator's
        # voice; the header is the right default.
        hdr = [b for b in conf if in_region(b, self.CHAT_HEADER)
               and b["text"].strip().lower() not in ("answer", "close")]
        hdr.sort(key=lambda b: -(b["y"] + b["h"] / 2))
        header_name = hdr[0]["text"].strip() if hdr else None
        if "Back" not in hints and header_name is None:
            return None
        body = [b for b in conf if in_region(b, self.CHAT_BODY)
                and not self.CHAT_SYSTEM_ROW.search(b["text"].strip())]
        body.sort(key=lambda b: -(b["y"] + b["h"] / 2))
        msgs, sender, buf, last_y = [], None, [], 1.0
        for b in body:
            # Notices are centred, so they can land either side of the
            # sender/message column split — test before that branch.
            notice = self._chat_notice(b["text"], header_name)
            if notice:
                cy = b["y"] + b["h"] / 2
                if buf:                            # close the message above it
                    msgs.append((sender or header_name, " ".join(buf), last_y))
                    buf = []
                msgs.append((self.CHAT_NOTICE_SENDER, notice, cy))
                last_y = cy
                continue
            if b["x"] < self.CHAT_SENDER_MAX_X:    # sender label row
                if buf:
                    msgs.append((sender or header_name, " ".join(buf), last_y))
                sender, buf = b["text"].strip(), []
            elif abs(b["x"] - self.CHAT_MSG_X) > self.CHAT_ALIGN_TOL:
                # Centred row, not a bubble: a reply-option button. The game
                # is putting words in the player character's mouth, same as
                # a lone dialogue choice, so it reads under their name — and
                # it sorts below the messages, so it queues after them. If
                # picking it echoes a player bubble into the panel, that may
                # read again in the wrong voice — unmeasured, and a rare
                # talk-over beats the skipped line this was.
                cy = b["y"] + b["h"] / 2
                if buf and (sender != self.PLAYER_NAME
                            or (last_y - cy) > 2.2 * b["h"]):
                    msgs.append((sender or header_name, " ".join(buf), last_y))
                    buf = []
                sender = self.PLAYER_NAME
                buf.append(b["text"])
                last_y = cy
            else:                                  # message text row
                cy = b["y"] + b["h"] / 2
                # A big vertical gap means a new bubble even though no sender
                # label was read — consecutive messages from one sender only
                # label the first, and OCR drops the small grey label often.
                # Without this, two messages fuse into one utterance.
                if buf and (last_y - cy) > 2.2 * b["h"]:
                    msgs.append((sender or header_name, " ".join(buf), last_y))
                    buf = []
                buf.append(b["text"])
                last_y = cy
        if buf:
            msgs.append((sender or header_name, " ".join(buf), last_y))
        # drop the last message if its deepest row hugs the clip edge — it's
        # still scrolling into view and will be read complete later
        if msgs and msgs[-1][2] < self.CHAT_CLIP_Y and not ended:
            msgs = msgs[:-1]
        return [(s, t) for s, t, _ in msgs]

    def _classify_messages_app(self, conf):
        """The phone Messages app: [(sender, text), …], or None if this
        isn't it. Same contract as the Answer panel — live.py owns
        settling, dedupe, scrolled-tail suppression and per-sender
        voices."""
        if not any(self._MSGAPP_MARKER.match(b["text"].strip())
                   and in_region(b, self.MSGAPP_MARKER_REGION) for b in conf):
            return None
        hdr = [b for b in conf if in_region(b, self.MSGAPP_HEADER)]
        if not hdr:
            return None            # the list is open with no thread in it
        hdr.sort(key=lambda b: -(b["y"] + b["h"] / 2))
        header_name = hdr[0]["text"].strip()
        body = [b for b in conf if in_region(b, self.MSGAPP_BODY)]
        body.sort(key=lambda b: -(b["y"] + b["h"] / 2))
        # `sender` follows the bubble being built; `npc_sender` remembers
        # the last label on the incoming side, so a message that follows a
        # player bubble without a label of its own doesn't read in the
        # player's voice.
        msgs, buf, last_y = [], [], 1.0
        sender = npc_sender = None
        zone = "npc"

        def flush():
            if buf:
                msgs.append((sender or header_name, " ".join(buf)))
                buf.clear()

        def aligned(edge, to):
            return abs(edge - to) <= self.MSGAPP_ALIGN_TOL

        for b in body:
            cy = b["y"] + b["h"] / 2
            text = b["text"].strip()
            left, right = b["x"], b["x"] + b["w"]
            if aligned(left, self.MSGAPP_SENDER_X):
                # the typing indicator ("•••") sits in the label column
                if not re.search(r"[^\W\d_]", text):
                    continue
                flush()
                sender = npc_sender = text
                zone = "npc"
            elif aligned(left, self.MSGAPP_INCOMING_X):
                if zone == "player":
                    flush()
                    sender, zone = npc_sender, "npc"
                elif buf and last_y - cy > 2.2 * b["h"]:
                    flush()
                buf.append(text)
            elif aligned(right, self.MSGAPP_PLAYER_LABEL_RIGHT):
                flush()
                sender, zone = text, "player"
            elif aligned(right, self.MSGAPP_PLAYER_RIGHT):
                if zone != "player":
                    flush()
                    sender, zone = self.PLAYER_NAME, "player"
                elif buf and last_y - cy > 2.2 * b["h"]:
                    flush()
                buf.append(text)
            else:
                continue           # centred: delivery notice or reply button
            last_y = cy
        flush()
        return msgs

    def classify_chat(self, blocks):
        """Any of this game's chat panels — the in-story Answer screens,
        the phone Messages app, the Incoming Message Notification popup,
        and the Furbobocom thread and popup. [(sender, text), …] or None.

        Tried in that order, and NOT with `or`: an Answer panel whose only
        message is still clipped returns an empty list, which means "a
        chat screen with nothing to read yet" and must not fall through to
        a detector that would answer None ("not a chat screen at all") and
        hand the frame back to the dialogue classifier."""
        conf = self.confident(blocks)
        # The notification popup goes first: its title is unambiguous,
        # and the Answer panel's looser test claims its thread — the
        # player's label landed in its message column and was spoken
        # glued to the reply ("Ebby Hi, Kafka", 13:16:10 on 2026-11-12).
        msgs = self._classify_message_notification(blocks)
        if msgs is None:
            msgs = self._classify_answer_panel(conf)
        if msgs is None:
            msgs = self._classify_messages_app(conf)
        if msgs is None:
            msgs = self._classify_furbo_chat(blocks)
        if msgs is None:
            msgs = self._classify_furbo_popup(blocks)
        return msgs

    def _classify_message_notification(self, blocks):
        """The Incoming Message Notification popup: [(sender, text), …]
        or None.

        An empty list while the contact list is up with no thread open
        ("Please select a contact"): that is still this screen, and
        handing it back to the dialogue classifier is what logged the
        reply buttons as choice prompts. Labels come in at
        FURBO_LABEL_MIN_CONF like the furbo panes'; this panel's labels
        read at 1.00 on Vision, but nothing is lost by matching the other
        threads."""
        conf = self.confident(blocks)
        if not any(in_region(b, self.MSGNOTE_MARKER_REGION)
                   and self.MSGNOTE_MARKER.search(b["text"])
                   for b in conf):
            return None
        if self.holds_reader(blocks):
            return []                  # the reward modal garbles the rows
        selecting = any(
            "select" in b["text"].lower()
            and self.MSGNOTE_HINT_Y[0] <= b["y"] + b["h"] / 2
            <= self.MSGNOTE_HINT_Y[1]
            for b in conf)
        return self._furbo_thread(
            blocks,
            self.MSGNOTE_SELECT_BODY if selecting else self.MSGNOTE_BODY,
            self.MSGNOTE_SENDER_X, self.MSGNOTE_INCOMING_X,
            self.MSGNOTE_PLAYER_EDGES, self.MSGNOTE_PLAYER_LABEL_RIGHT,
            0.0, self.MSGNOTE_CLIP_TOP, options=False)

    def holds_reader(self, blocks):
        return any(in_region(b, self.REWARD_TITLE_REGION)
                   and self.REWARD_TITLE.match(b["text"].strip())
                   for b in self.confident(blocks))

    # ------------------------------------------------------------------
    # Furbobocom
    # ------------------------------------------------------------------
    def _furbo_hub(self, blocks):
        """True when a Furbobocom page is up (the app name top-left)."""
        return any(b["confidence"] >= self.FURBO_LABEL_MIN_CONF
                   and in_region(b, self.FURBO_HUB_REGION)
                   and self.FURBO_HUB_MARKER.search(b["text"])
                   for b in blocks)

    def _furbo_plate(self, blocks):
        """The furbo office scene's left-corner nameplate, or None.

        Only under the '✕ Continue' hint, which is what says this is a
        story screen at all, and only when exactly one plate-shaped block
        sits in the plate band's left reach: the band is empty there on
        every other dialogue screen this game draws."""
        if not self.trusts_dialogue(blocks):
            return None
        plates = [b for b in blocks
                  if b["confidence"] >= self.FURBO_LABEL_MIN_CONF
                  and b["text"].strip() not in self.IGNORE
                  and re.search(r"[^\W\d_]", b["text"])
                  and self.PLATE_Y[0] <= b["y"] + b["h"] / 2 <= self.PLATE_Y[1]
                  and self.FURBO_PLATE_X[0] <= b["x"] + b["w"] / 2
                  <= self.FURBO_PLATE_X[1]
                  and b["w"] <= self.PLATE_MAX_W]
        return plates[0] if len(plates) == 1 else None

    def _furbo_thread(self, blocks, body, sender_x, incoming_x,
                      player_edges, label_right, option_y, clip_top, options):
        """[(sender, text), …] for a furbo thread pane.

        Rows are sorted by what they are ALIGNED to, as in the Messages
        app; `player_edges` lists the (side, x) a player row may be
        aligned on — the right edge in the full-screen pane, either edge
        in the popup.
        Labels are taken down to FURBO_LABEL_MIN_CONF because the grey
        label font reads at 0.50; message rows keep MIN_CONF, which is
        also what drops the avatar misreads ("0.0") and a half-clipped
        row's garbage. `options` turns the centred rows under `option_y`
        into reply options, read under the player's name like the Answer
        panel's — the Clue pane always, the popup only while its
        Scroll/Select hints are up."""
        pool = [b for b in blocks
                if b["confidence"] >= self.FURBO_LABEL_MIN_CONF
                and b["text"].strip() not in self.IGNORE
                and in_region(b, body)]
        pool.sort(key=lambda b: -(b["y"] + b["h"] / 2))
        msgs, buf = [], []
        sender = npc_sender = None
        zone, last_y, clipped, labelled = "npc", 1.0, False, False

        def starts_clipped(top):
            return (top > clip_top
                    or (not labelled and top > clip_top - self.FURBO_LABEL_REACH))

        def flush():
            if buf and not clipped:
                msgs.append((sender, " ".join(buf)))
            buf.clear()

        def aligned(edge, to):
            return abs(edge - to) <= self.FURBO_ALIGN_TOL

        for b in pool:
            text = b["text"].strip()
            if (not re.search(r"\w", text)       # typing dots, cursor glyphs
                    or self.CHAT_SYSTEM_ROW.search(text)):
                continue
            cy = b["y"] + b["h"] / 2
            top = b["y"] + b["h"]
            left, right = b["x"], b["x"] + b["w"]
            label = (b["w"] <= self.FURBO_LABEL_MAX_W
                     and re.search(r"[^\W\d_]", text))
            if label and aligned(left, sender_x):
                if top > clip_top:
                    continue               # half under the edge: unreliable
                flush()
                sender = npc_sender = text
                zone, clipped, labelled = "npc", False, True
            elif label and aligned(right, label_right):
                if top > clip_top:
                    continue
                # the player's label names the player, who is already
                # cast as PLAYER_NAME; reading it as the sender made a
                # bubble read twice — once under the label, once as
                # PLAYER_NAME after the label scrolled off (short
                # texts dedupe on sender+text)
                flush()
                sender, zone, clipped, labelled = (self.PLAYER_NAME, "player",
                                                   False, True)
            elif b["confidence"] < self.MIN_CONF:
                continue
            elif aligned(left, incoming_x):
                if zone != "npc":
                    flush()
                    sender, zone, labelled = npc_sender, "npc", False
                elif buf and last_y - cy > 2.2 * b["h"]:
                    flush()
                    labelled = False
                if not buf:
                    clipped = starts_clipped(top)
                buf.append(text)
            elif any(aligned(right if side == "right" else left, x)
                     for side, x in player_edges):
                if zone != "player":
                    flush()
                    sender, zone, labelled = self.PLAYER_NAME, "player", False
                elif buf and last_y - cy > 2.2 * b["h"]:
                    flush()
                    labelled = False
                if not buf:
                    clipped = starts_clipped(top)
                buf.append(text)
            elif options and cy < option_y:
                # centred: a reply option. Each is its own item; a wrapped
                # option's rows are closer than the option pitch.
                if zone != "option" or (buf and last_y - cy > 2.2 * b["h"]):
                    flush()
                    sender, zone, clipped = self.PLAYER_NAME, "option", False
                buf.append(text)
            else:
                continue                   # centred caption, card chrome
            last_y = cy
        flush()
        return msgs

    def _furbo_clue_page(self, blocks):
        return self._furbo_hub(blocks) and any(
            in_region(b, self.FURBO_CHAT_TITLE_REGION)
            and b["confidence"] >= self.MIN_CONF
            and self.FURBO_CHAT_TITLE.match(b["text"].strip())
            for b in blocks)

    def _classify_furbo_article(self, blocks):
        """The Clue Source clipping as reader rows, or None."""
        if not self._furbo_clue_page(blocks):
            return None
        tol = self.FURBO_ALIGN_TOL
        rows = [b for b in self.confident(blocks)
                if in_region(b, self.FURBO_BODY)
                and re.search(r"[^\W\d_]", b["text"])
                and (abs(b["x"] - self.FURBO_ARTICLE_X) <= tol
                     or abs(b["x"] - self.FURBO_ARTICLE_TITLE_X) <= tol)
                and not self.FURBO_ARTICLE_CHIP.match(b["text"].strip())]
        if not any(abs(b["x"] - self.FURBO_ARTICLE_X) <= tol for b in rows):
            return None                # a thread, not a clipping
        rows.sort(key=lambda b: -(b["y"] + b["h"] / 2))
        return [b["text"] for b in rows]

    def _classify_furbo_chat(self, blocks):
        """The Clue Investigation pane: [(sender, text), …] or None."""
        if not self._furbo_clue_page(blocks):
            return None
        conf = self.confident(blocks)
        header = any(in_region(b, self.FURBO_RESULTS_MARKER_REGION)
                     and self.FURBO_RESULTS_MARKER.match(b["text"].strip())
                     for b in conf)
        report = sum(1 for b in conf if in_region(b, self.FURBO_BODY)
                     and abs(b["x"] - self.FURBO_REPORT_X) <= self.FURBO_ALIGN_TOL
                     and re.search(r"[^\W\d_]", b["text"]))
        if header or report >= 2:
            return self._furbo_thread(
                blocks, self.FURBO_RESULTS_BODY, self.FURBO_RESULTS_SENDER_X,
                self.FURBO_RESULTS_INCOMING_X, self.FURBO_RESULTS_PLAYER_EDGES,
                self.FURBO_RESULTS_PLAYER_LABEL_RIGHT, self.FURBO_OPTION_Y,
                self.FURBO_CLIP_TOP, options=False)
        return self._furbo_thread(
            blocks, self.FURBO_BODY, self.FURBO_SENDER_X,
            self.FURBO_INCOMING_X, self.FURBO_PLAYER_EDGES,
            self.FURBO_PLAYER_LABEL_RIGHT, self.FURBO_OPTION_Y,
            self.FURBO_CLIP_TOP, options=True)

    def _classify_furbo_popup(self, blocks):
        """The group-chat popup: [(sender, text), …] or None.

        Identified by its shape, not the group's name: a wide title
        left-aligned at the popup's own left margin, every confident block
        above the UID strip inside the popup's width, and at least one
        sender or player label on one of its columns. Any left-aligned
        title at that spot with nothing labelled under it is some other
        modal."""
        conf = self.confident(blocks)
        if not any(b["w"] >= self.FURBO_POPUP_HEADER_MIN_W
                   and self.FURBO_POPUP_HEADER["x"][0] <= b["x"]
                   <= self.FURBO_POPUP_HEADER["x"][1]
                   and self.FURBO_POPUP_HEADER["y"][0]
                   <= b["y"] + b["h"] / 2 <= self.FURBO_POPUP_HEADER["y"][1]
                   for b in conf):
            return None
        for b in conf:
            if b["y"] + b["h"] / 2 < 0.06:
                continue                   # UID strip
            if not (self.FURBO_POPUP_X[0] <= b["x"]
                    and b["x"] + b["w"] <= self.FURBO_POPUP_X[1]):
                return None
        tol = self.FURBO_ALIGN_TOL
        if not any(b["confidence"] >= self.FURBO_LABEL_MIN_CONF
                   and b["w"] <= self.FURBO_LABEL_MAX_W
                   and in_region(b, self.FURBO_POPUP_BODY)
                   and (abs(b["x"] - self.FURBO_POPUP_SENDER_X) <= tol
                        or abs(b["x"] + b["w"]
                               - self.FURBO_POPUP_PLAYER_LABEL_RIGHT) <= tol)
                   for b in blocks):
            return None
        hints = {b["text"].strip() for b in conf
                 if self.FURBO_POPUP_HINT_Y[0] <= b["y"] + b["h"] / 2
                 <= self.FURBO_POPUP_HINT_Y[1]}
        return self._furbo_thread(
            blocks, self.FURBO_POPUP_BODY, self.FURBO_POPUP_SENDER_X,
            self.FURBO_POPUP_INCOMING_X, self.FURBO_POPUP_PLAYER_EDGES,
            self.FURBO_POPUP_PLAYER_LABEL_RIGHT, self.FURBO_POPUP_OPTION_Y,
            self.FURBO_POPUP_CLIP_TOP,
            options={"Scroll", "Select"} <= hints)
