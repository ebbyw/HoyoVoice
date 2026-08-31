"""Pins the Star Rail in-story chat panel waiting on a reply option.

A panel with an option pending swaps its Back hint for Select — and it can
show Select for the whole conversation: every frame of rec_20260830_131155
(7s, cutscene chat with Kuchiba) reads Scroll/Select, the detector demanded
Scroll/Back, and nothing in the panel was read at all. The blocks here are
that recording's shot #1, verbatim.

Two things are pinned: the Select variant is a chat screen (with the panel
header required, since Select alone is menu furniture), and the option
button — centred in the panel, so aligned to neither the sender column nor
the message column — reads under the player's name rather than fusing into
the sender's bubble above it.

Run directly or under pytest:

    python tools/test_hsr_answer_choice.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profiles import get_profile                # noqa: E402

HSR = get_profile("hsr")

SHOT_1 = [
    {"text": 'Kuchiba', "confidence": 0.9997,
     "x": 0.5953, "y": 0.7806, "w": 0.0630, "h": 0.0333},
    {"text": 'Kuchiba', "confidence": 0.9946,
     "x": 0.6568, "y": 0.7009, "w": 0.0500, "h": 0.0315},
    {"text": "Everything's set. Ill be heading", "confidence": 0.9838,
     "x": 0.6703, "y": 0.6519, "w": 0.1969, "h": 0.0352},
    {"text": 'to the target location with the', "confidence": 0.9862,
     "x": 0.6703, "y": 0.6185, "w": 0.1880, "h": 0.0278},
    {"text": 'detective.', "confidence": 0.9805,
     "x": 0.6698, "y": 0.5824, "w": 0.0651, "h": 0.0306},
    {"text": 'Kuchiba', "confidence": 0.9993,
     "x": 0.6578, "y": 0.5157, "w": 0.0484, "h": 0.0287},
    {"text": 'You mean.. the "Life Sciences', "confidence": 0.9806,
     "x": 0.6703, "y": 0.4667, "w": 0.1901, "h": 0.0343},
    {"text": 'Institute"?', "confidence": 0.9957,
     "x": 0.6703, "y": 0.4324, "w": 0.0651, "h": 0.0306},
    {"text": "That's right", "confidence": 0.9593,
     "x": 0.7130, "y": 0.3130, "w": 0.0839, "h": 0.0426},
    {"text": 'Scroll', "confidence": 0.9777,
     "x": 0.8021, "y": 0.1306, "w": 0.0380, "h": 0.0306},
    {"text": 'Select', "confidence": 0.9980,
     "x": 0.8781, "y": 0.1296, "w": 0.0411, "h": 0.0324},
    {"text": 'X', "confidence": 0.9575,
     "x": 0.8651, "y": 0.1380, "w": 0.0073, "h": 0.0130},
    {"text": 'UID:603150536', "confidence": 0.9900,
     "x": 0.0177, "y": 0.0148, "w": 0.0677, "h": 0.0222},
]


def test_select_panel_reads_messages_and_choice():
    msgs = HSR.classify_chat(SHOT_1)
    assert msgs == [
        ("Kuchiba",
         "Everything's set. Ill be heading to the target location with "
         "the detective."),
        ("Kuchiba", 'You mean.. the "Life Sciences Institute"?'),
        (HSR.PLAYER_NAME, "That's right"),
    ], msgs


def test_select_without_header_is_not_a_chat_screen():
    """Scroll/Select with no panel header is any menu at all — the header
    is what buys the weaker hint pair its trust."""
    no_header = [b for b in SHOT_1 if b["y"] < 0.75]
    assert HSR.classify_chat(no_header) is None


def test_back_panel_needs_no_header():
    """The Back variant keeps its original contract: header optional."""
    back = [dict(b, text="Back") if b["text"] == "Select" else b
            for b in SHOT_1 if b["y"] < 0.75]
    msgs = HSR.classify_chat(back)
    assert msgs is not None
    assert (HSR.PLAYER_NAME, "That's right") in msgs, msgs


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all Star Rail answer-choice checks pass")
