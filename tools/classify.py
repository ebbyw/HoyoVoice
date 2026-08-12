#!/usr/bin/env python3
"""Classify raw OCR blocks (from the OCR daemon) into structured dialogue
state.

Coordinates are Vision-normalized: origin bottom-left, 0-1.

The layout itself lives in `tools/profiles/` — one profile per game, each
owning its bands and screen detectors. This module is the game-agnostic
entry point: the helpers that don't depend on layout, plus thin wrappers
bound to the default profile so the CLI below (and anything that imported
these names before profiles existed) keeps working.

Usage: python3 classify.py <ocr.json> [game]
"""
import json
import sys

from profiles import (DEFAULT, get_profile, in_region,  # noqa: F401
                      narration_self_certain, split_camel)

_default = get_profile(DEFAULT)

classify = _default.classify
classify_chat = _default.classify_chat
classify_comms = _default.classify_comms
classify_infoscreen = _default.classify_infoscreen
classify_loading = _default.classify_loading
classify_lore_screen = _default.classify_lore_screen
classify_narration = _default.classify_narration
classify_overlay = _default.classify_overlay
classify_quickread = _default.classify_quickread
has_continue_hint = _default.trusts_dialogue


if __name__ == "__main__":
    p = get_profile(sys.argv[2]) if len(sys.argv) > 2 else _default
    blocks = json.load(open(sys.argv[1]))
    print(json.dumps(p.classify(blocks), indent=2, ensure_ascii=False))
