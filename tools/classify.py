#!/usr/bin/env python3
"""Classify raw OCR blocks (from ocr.swift) into structured dialogue state.

Coordinates are Vision-normalized: origin bottom-left, 0-1.
Layout profile: Honkai Star Rail, standard dialogue screen.

Usage: python3 classify.py <ocr.json>
"""
import json
import re
import sys

# HSR dialogue layout (normalized, bottom-left origin). The box sits at
# slightly different heights in cinematic vs overworld conversations, so
# dialogue is ANCHORED to the nameplate rather than a fixed band.
PROFILE = {
    "plate_y":  (0.18, 0.31),          # nameplate can appear anywhere here
    "plate_x":  (0.35, 0.65),
    "plate_max_w": 0.30,               # names are short; dialogue lines are wide
    "dialogue_x": (0.40, 0.60),        # real lines are centered
    "dialogue_span": 0.15,             # lines live this far below the nameplate
    "dialogue_fallback_y": (0.08, 0.19),
    "choices":  {"x": (0.66, 1.00), "y": (0.22, 0.62)},
}
# Choice option text is left-aligned just right of the "→" marker
CHOICE_LEFT_EDGE = (0.68, 0.78)
CHOICE_MIN_HEIGHT = 0.020

# Full-screen narration (black background, centered text, no nameplate)
NARRATION_BAND = {"x": (0.20, 0.80), "y": (0.25, 0.75)}
NARRATION_MIN_CHARS = 40
NARRATION_MIN_WORDS = 6
NARRATION_MAX_DIGIT_RATIO = 0.15   # menus/loaders are digit-heavy; prose isn't
MIN_CONF = 0.8
IGNORE = {"Continue", "→"}


def in_region(block, region):
    cx = block["x"] + block["w"] / 2
    cy = block["y"] + block["h"] / 2
    (x0, x1), (y0, y1) = region["x"], region["y"]
    return x0 <= cx <= x1 and y0 <= cy <= y1


def classify(blocks):
    state = {"speaker": None, "dialogue": [], "choices": []}
    conf = [b for b in blocks
            if b["confidence"] >= MIN_CONF and b["text"].strip() not in IGNORE]

    # find the nameplate: a short, centered block in the plate band
    plates = [b for b in conf
              if PROFILE["plate_y"][0] <= b["y"] + b["h"] / 2 <= PROFILE["plate_y"][1]
              and PROFILE["plate_x"][0] <= b["x"] + b["w"] / 2 <= PROFILE["plate_x"][1]
              and b["w"] <= PROFILE["plate_max_w"]]
    plate = max(plates, key=lambda b: b["h"]) if plates else None
    if plate is not None:
        state["speaker"] = plate["text"]
        dlg_top = plate["y"] - 0.004            # just below the nameplate
        dlg_bot = plate["y"] - PROFILE["dialogue_span"]
    else:
        dlg_bot, dlg_top = PROFILE["dialogue_fallback_y"]

    # seed rows with centered blocks, then pull in row-mates: Vision often
    # splits one visual line into several blocks whose fragments sit
    # off-center ('Error: Term' + '"Berserker" not found…')
    band = [b for b in conf if b is not plate
            and dlg_bot <= b["y"] + b["h"] / 2 <= dlg_top
            and 0.08 <= b["x"] + b["w"] / 2 <= 0.92]
    seed_rows = {round((b["y"] + b["h"] / 2) / 0.022) for b in band
                 if PROFILE["dialogue_x"][0] <= b["x"] + b["w"] / 2
                 <= PROFILE["dialogue_x"][1]}
    for b in conf:
        if b is plate:
            continue
        cy = b["y"] + b["h"] / 2
        if b in band and round(cy / 0.022) in seed_rows:
            state["dialogue"].append(b)
        elif (in_region(b, PROFILE["choices"])
              and CHOICE_LEFT_EDGE[0] <= b["x"] <= CHOICE_LEFT_EDGE[1]
              and b["h"] >= CHOICE_MIN_HEIGHT):
            state["choices"].append(b)

    # Drop ghost duplicates: the text fade-in makes Vision sometimes return
    # BOTH a stale partial and the full line as overlapping boxes on one row —
    # keep only the widest box where horizontal spans overlap
    rows = {}
    for b in state["dialogue"]:
        rows.setdefault(round((b["y"] + b["h"] / 2) / 0.022), []).append(b)
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
        key=lambda b: (round((1 - (b["y"] + b["h"] / 2)) / 0.022), b["x"]))
    dialogue_text = " ".join(b["text"] for b in state["dialogue"])

    # Group choice lines into options: lines belong to the same option if their
    # vertical gap is small (< 1.5x line height)
    state["choices"].sort(key=lambda b: -b["y"])
    options, current = [], []
    prev = None
    for b in state["choices"]:
        if prev is not None and (prev["y"] - b["y"]) > 1.5 * max(prev["h"], b["h"]):
            options.append(" ".join(x["text"] for x in current))
            current = []
        current.append(b)
        prev = b
    if current:
        options.append(" ".join(x["text"] for x in current))

    return {"speaker": state["speaker"], "dialogue": dialogue_text, "choices": options}


# HSR "Quick Read" book screens: label top-left, Scroll/Back hints bottom
QUICKREAD_BODY = {"x": (0.28, 0.76), "y": (0.08, 0.90)}


def classify_quickread(blocks):
    """Detect the Quick Read layout. Returns ordered body-line texts or None."""
    conf = [b for b in blocks if b["confidence"] >= MIN_CONF]
    header = any(b["text"].strip().lower() == "quick read"
                 and b["x"] < 0.25 and b["y"] > 0.85 for b in conf)
    hints = any(b["text"].strip() in ("Scroll", "Back") and b["y"] < 0.08
                for b in conf)
    if not (header and hints):
        return None
    body = [b for b in conf if in_region(b, QUICKREAD_BODY)]
    body.sort(key=lambda b: -b["y"])
    return [b["text"] for b in body]


def _bottom_left_strip(blocks):
    """Joined text of the bottom-left build/UID strip. Engines disagree on
    how they chunk it — Apple Vision returns one block, Windows OCR splits
    it and often drops the underscores — so match on the JOINED text."""
    strip = [b for b in blocks
             if b["y"] < 0.08 and b["x"] + b["w"] / 2 < 0.45]
    strip.sort(key=lambda b: b["x"])
    return " ".join(b["text"] for b in strip)


def classify_loading(blocks):
    """Detect loading screens via the long version string bottom-left
    (e.g. 'OSPRODNAPS54.4.1_D…_A…_L… UID:…'). Their title + lore text sit in
    the dialogue bands and would otherwise misparse as a speaker + line.
    Returns the lore text or None."""
    conf = [b for b in blocks if b["confidence"] >= MIN_CONF]
    strip = _bottom_left_strip(conf)
    up = strip.upper()
    # UID is what separates loading screens from other system screens; the
    # build-string evidence is tolerant because engines mangle it
    # differently (underscores dropped, split across blocks)
    marker = "UID" in up and (strip.count("_") >= 2
                              or re.search(r"\d\.\d", strip) is not None
                              or len(strip) >= 40)
    if not marker:
        return None
    center = [b for b in conf
              if 0.25 <= b["x"] + b["w"] / 2 <= 0.75 and 0.08 <= b["y"] <= 0.30]
    if not center:
        return None
    center.sort(key=lambda b: -b["y"])
    text = " ".join(b["text"] for b in center)
    return text if len(text) >= 15 else None


def classify_lore_screen(blocks):
    """Full-screen lore/loading cards that carry NO chrome: a centered
    title in the nameplate band with centered prose below it, and no
    Continue hint, no bottom strip (UID/build), no HUD. Those cards look
    exactly like a dialogue screen to classify() — title reads as a
    nameplate — so they'd otherwise be skipped as an unknown speaker.

    Returns (title, text) or None. Gameplay dialogue always carries some
    chrome (at minimum the Continue hint), which disqualifies it here.
    """
    conf = [b for b in blocks if b["confidence"] >= MIN_CONF]
    if not conf or has_continue_hint(blocks):
        return None
    for b in conf:                      # any chrome at all disqualifies
        cy = b["y"] + b["h"] / 2
        if cy < 0.08 or cy > 0.90:      # UID/build strip, HUD rails
            return None
    body = [b for b in conf if 0.15 <= b["x"] + b["w"] / 2 <= 0.85]
    if len(body) != len(conf) or len(body) < 2:
        return None                     # off-center text ⇒ not a lore card
    body.sort(key=lambda b: -b["y"])
    title = body[0]["text"].strip()
    text = " ".join(b["text"] for b in body[1:]).strip()
    if len(text) < NARRATION_MIN_CHARS or len(text.split()) < NARRATION_MIN_WORDS:
        return None
    if sum(c.isdigit() for c in text) > NARRATION_MAX_DIGIT_RATIO * len(text):
        return None                     # menus/stat panels are digit-heavy
    return title, text


def split_camel(s):
    """'CindearthAge' → 'Cindearth Age'. OCR drops the space in these
    stylized titles, and TTS then reads them as one mangled word."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)


def has_continue_hint(blocks):
    """Dialogue and narration screens show '✕ Continue' bottom-right; menus,
    boards, and info popups show other hints (Confirm, Adjust Lineup…)."""
    return any(b["y"] < 0.08 and b["x"] > 0.78
               and "continue" in b["text"].strip().lower() for b in blocks)


def _version_marker(blocks):
    """Bottom-left build string ('OSPRODNAPS…_D…_A…') marks system screens:
    loading screens, epilepsy warnings, etc. Matched on the joined strip —
    OCR engines chunk it differently and may drop the underscores."""
    strip = _bottom_left_strip(blocks)
    return (strip.count("_") >= 2
            or (re.search(r"\d\.\d", strip) is not None and len(strip) >= 30))


# Floating overlay dialog (event-hub host bubble): portrait + speech box in
# the upper-center band, with its own "Continue" hint floating mid-screen
OVERLAY_BAND = {"x": (0.33, 0.78), "y": (0.70, 0.88)}


def classify_overlay(blocks):
    conf = [b for b in blocks if b["confidence"] >= MIN_CONF]
    floating_hint = any("continue" in b["text"].strip().lower()
                        and 0.55 < b["y"] < 0.78 for b in conf)
    if not floating_hint:
        return None
    body = [b for b in conf if in_region(b, OVERLAY_BAND)
            and "continue" not in b["text"].strip().lower()]
    if not body:
        return None
    body.sort(key=lambda b: -b["y"])
    text = " ".join(b["text"] for b in body).lstrip(">•·| ").strip()
    return text if len(text) >= 12 else None


# HSR message/group-chat panel ("Answer" screens): sender labels at the
# bubble's left edge (x<0.666), message text indented (x>=0.666), panel
# header above y=0.74, R-Scroll/O-Back hints floating at y~0.135
CHAT_BODY = {"x": (0.63, 0.97), "y": (0.14, 0.74)}


def classify_chat(blocks):
    """Returns [(sender, message_text), …] for complete visible messages,
    dropping a bottom message still clipped by the panel edge. None if this
    isn't a chat screen."""
    conf = [b for b in blocks if b["confidence"] >= MIN_CONF]
    hints = {b["text"].strip() for b in conf
             if 0.10 < b["y"] < 0.20 and b["x"] > 0.72}
    if not {"Scroll", "Back"} <= hints:
        return None
    body = [b for b in conf if in_region(b, CHAT_BODY)]
    body.sort(key=lambda b: -(b["y"] + b["h"] / 2))
    msgs, sender, buf, last_y = [], None, [], 1.0
    for b in body:
        if b["x"] < 0.666:                     # sender label row
            if sender and buf:
                msgs.append((sender, " ".join(buf), last_y))
            sender, buf = b["text"].strip(), []
        else:                                  # message text row
            buf.append(b["text"])
            last_y = b["y"] + b["h"] / 2
    if sender and buf:
        msgs.append((sender, " ".join(buf), last_y))
    # drop the last message if its deepest row hugs the clip edge — it's
    # still scrolling into view and will be read complete later
    if msgs and msgs[-1][2] < 0.21:
        msgs = msgs[:-1]
    return [(s, t) for s, t, _ in msgs]


# Info screens (Participant Details etc.): header top-left, Back hint bottom
INFO_HEADERS = ("participant details",)


def classify_infoscreen(blocks):
    """Detect profile/info screens and return body texts in reading order
    (rows top-to-bottom, left-to-right), excluding the left tab column."""
    conf = [b for b in blocks if b["confidence"] >= MIN_CONF]
    header = any(b["text"].strip().lower() in INFO_HEADERS
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


def narration_self_certain(text):
    """Bright cutscene narration (no black bg, no Continue hint) can still
    self-certify: a real prose sentence, no menu-banner symbols."""
    return (len(text.split()) >= 8
            and text.rstrip().endswith((".", "!", "?", "…"))
            and not any(c in text for c in "©•®™|"))


def classify_narration(blocks):
    """Detect the full-screen narration layout: confident text only in the
    center band of an otherwise empty (black) screen. Returns joined text
    or None."""
    # system screens (epilepsy warning etc.) look like narration — never read
    # them. Loading screens are handled separately before this runs.
    if _version_marker(blocks):
        return None
    confident = [b for b in blocks
                 if b["confidence"] >= MIN_CONF
                 and b["text"].strip() not in IGNORE
                 and b["y"] > 0.06]           # ignore bottom strip (UID, hints)
    if not confident:
        return None
    center = [b for b in confident if in_region(b, {"x": NARRATION_BAND["x"],
                                                    "y": NARRATION_BAND["y"]})]
    # every confident block must be in the band — HUD text anywhere else
    # means this is gameplay, not a narration screen
    if not center or len(center) != len(confident):
        return None
    center.sort(key=lambda b: -b["y"])
    text = " ".join(b["text"] for b in center)
    if (len(text) < NARRATION_MIN_CHARS
            or len(text.split()) < NARRATION_MIN_WORDS
            or text.lstrip().startswith("Warning")
            or "%" in text
            or sum(c.isdigit() for c in text) > NARRATION_MAX_DIGIT_RATIO * len(text)):
        return None
    return text


if __name__ == "__main__":
    blocks = json.load(open(sys.argv[1]))
    print(json.dumps(classify(blocks), indent=2, ensure_ascii=False))
