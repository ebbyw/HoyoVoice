#!/usr/bin/env python3
"""Classify raw OCR blocks (from ocr.swift) into structured dialogue state.

Coordinates are Vision-normalized: origin bottom-left, 0-1.
Layout profile: Honkai Star Rail, standard dialogue screen.

Usage: python3 classify.py <ocr.json>
"""
import json
import sys

# HSR standard dialogue layout (normalized, bottom-left origin)
PROFILE = {
    "speaker":  {"x": (0.30, 0.70), "y": (0.19, 0.26)},
    "dialogue": {"x": (0.40, 0.60), "y": (0.08, 0.19)},  # real lines are centered
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
    for b in blocks:
        if b["confidence"] < MIN_CONF or b["text"].strip() in IGNORE:
            continue
        if in_region(b, PROFILE["speaker"]):
            state["speaker"] = b["text"]
        elif in_region(b, PROFILE["dialogue"]):
            state["dialogue"].append(b)
        elif (in_region(b, PROFILE["choices"])
              and CHOICE_LEFT_EDGE[0] <= b["x"] <= CHOICE_LEFT_EDGE[1]
              and b["h"] >= CHOICE_MIN_HEIGHT):
            state["choices"].append(b)

    # Merge multi-line blocks: sort top-to-bottom (Vision y is bottom-left, so descending)
    state["dialogue"].sort(key=lambda b: -b["y"])
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


def classify_loading(blocks):
    """Detect loading screens via the long version string bottom-left
    (e.g. 'OSPRODNAPS54.4.1_D…_A…_L… UID:…'). Their title + lore text sit in
    the dialogue bands and would otherwise misparse as a speaker + line.
    Returns the lore text or None."""
    conf = [b for b in blocks if b["confidence"] >= MIN_CONF]
    marker = any(b["y"] < 0.06 and b["x"] < 0.35
                 and "UID:" in b["text"] and b["text"].count("_") >= 2
                 for b in conf)
    if not marker:
        return None
    center = [b for b in conf
              if 0.25 <= b["x"] + b["w"] / 2 <= 0.75 and 0.08 <= b["y"] <= 0.30]
    if not center:
        return None
    center.sort(key=lambda b: -b["y"])
    text = " ".join(b["text"] for b in center)
    return text if len(text) >= 15 else None


def has_continue_hint(blocks):
    """Dialogue and narration screens show '✕ Continue' bottom-right; menus,
    boards, and info popups show other hints (Confirm, Adjust Lineup…)."""
    return any(b["y"] < 0.08 and b["x"] > 0.78
               and "continue" in b["text"].strip().lower() for b in blocks)


def _version_marker(blocks):
    """Bottom-left build string ('OSPRODNAPS…_D…_A…') marks system screens:
    loading screens, epilepsy warnings, etc."""
    return any(b["y"] < 0.06 and b["x"] < 0.35 and b["text"].count("_") >= 2
               for b in blocks)


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
