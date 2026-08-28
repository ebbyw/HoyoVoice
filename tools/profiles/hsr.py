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
        state = super().classify(blocks, _no_plate)
        # A choice prompt only exists alongside a speaker — same rule as
        # Genshin, arrived at from the other direction. This game's menus
        # keep landing 1-2 blocks in the choice band and reading them
        # aloud as Trailblazer: the Currency Wars team-setup tooltip
        # ("Increases DMG dealt by all allies…", shot #132 2026-08-24,
        # left edges 0.738-0.757), combat-screen effect names, nav labels
        # ("Data Bank", "Back"), and the Battle Preparations enemy-team
        # title ("Mysterious Familiars", x=0.712 — frames 268-272 of
        # rec_20260726_121902 at 1 fps). Against the same corpus every
        # genuine prompt kept its plate (frames 111, 482-490, 547-549:
        # the box below the bubbles still shows the speaker), so the
        # plate is the discriminator, and a prompt this drops leaves a
        # "choice prompt (ignored — no speaker)" row in the log.
        if state["choices"] and not state["speaker"]:
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
            return None
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
        if not {"Scroll", "Back"} <= hints:
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
        """Either of this game's two chat panels — the in-story Answer
        screens or the phone Messages app. [(sender, text), …] or None.

        Tried in that order, and NOT with `or`: an Answer panel whose only
        message is still clipped returns an empty list, which means "a
        chat screen with nothing to read yet" and must not fall through to
        a detector that would answer None ("not a chat screen at all") and
        hand the frame back to the dialogue classifier."""
        conf = self.confident(blocks)
        msgs = self._classify_answer_panel(conf)
        if msgs is None:
            msgs = self._classify_messages_app(conf)
        return msgs
