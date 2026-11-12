"""Pins Star Rail's Incoming Message Notification popup — the message
modal that opens over the world when a contact writes mid-exploration —
off rec_20261112_131536 (2026-11-12 13:15, Windows box). Every frame
here is that recording OCR'd by the Vision daemon at 2 fps; geometry,
confidences, names and UI chrome are verbatim, the game's prose is
replaced word-for-word by placeholder words of the same length so the
fixtures carry no game text, and the player's UID is zeroed.

Before this the popup had no detector. In ninety seconds of a
ten-message thread the session log shows one line spoken: the player's
first reply, claimed by the Answer panel's detector with the player's
own label glued on ("Ebby Hi, Kafka", 13:16:10), after the same reply
had been logged twice as an unattributed choice prompt. Every one of
the contact's messages went unread.

What is pinned:
  - senders from the label column, incoming and player bubbles by
    alignment, the player's label reading as the player and never as
    text, a wrapped player bubble aligned on the LEFT
  - the contact list (its previews, the "Please select a contact"
    placeholder) never read, and still reported as this screen
  - reply options never read, including one whose right edge lands on
    the player column — the picked one comes back as the player's bubble
  - a row half under the title rule dropping the message it starts
  - the "Items Obtained" modal holding the reader open, and nothing read
    from the popup while it is drawn over it
  - this detector winning over the Answer panel's

Run directly or under pytest:

    python tools/test_hsr_msgnotify.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profiles import get_profile                # noqa: E402

HSR = get_profile("hsr")
P = HSR.PLAYER_NAME

# t=20.0s in rec_20261112_131536 (recording starts 13:15:36)
CONTACTS_20 = [
    {"text": 'Incoming Message Notification', "confidence": 1.0000,
     "x": 0.1628, "y": 0.7620, "w": 0.2108, "h": 0.0287},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.2151, "y": 0.7052, "w": 0.0364, "h": 0.0238},
    {"text": 'To, Ebby', "confidence": 1.0000,
     "x": 0.2150, "y": 0.6735, "w": 0.0526, "h": 0.0277},
    {"text": 'Please select a contact', "confidence": 1.0000,
     "x": 0.5624, "y": 0.4420, "w": 0.1296, "h": 0.0233},
    {"text": 'Select', "confidence": 1.0000,
     "x": 0.7267, "y": 0.1266, "w": 0.0378, "h": 0.0233},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.8067, "y": 0.1266, "w": 0.0305, "h": 0.0207},
    {"text": 'UID:000000000', "confidence": 1.0000,
     "x": 0.0203, "y": 0.0155, "w": 0.0654, "h": 0.0181},
]

# t=26.0s in rec_20261112_131536 (recording starts 13:15:36)
FIRST_26 = [
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4171, "y": 0.7747, "w": 0.0423, "h": 0.0242},
    {"text": 'Incoming Message Notification', "confidence": 1.0000,
     "x": 0.1628, "y": 0.7620, "w": 0.2108, "h": 0.0287},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4782, "y": 0.7158, "w": 0.0334, "h": 0.0207},
    {"text": '* Blade', "confidence": 1.0000,
     "x": 0.2031, "y": 0.6998, "w": 0.0508, "h": 0.0389},
    {"text": 'To, Field', "confidence": 1.0000,
     "x": 0.2151, "y": 0.6740, "w": 0.0582, "h": 0.0266},
    {"text": 'To, Ebby', "confidence": 1.0000,
     "x": 0.4897, "y": 0.6604, "w": 0.0541, "h": 0.0306},
    {"text": 'Ebby', "confidence": 1.0000,
     "x": 0.7267, "y": 0.5969, "w": 0.0291, "h": 0.0258},
    {"text": 'To, Field', "confidence": 1.0000,
     "x": 0.6817, "y": 0.5426, "w": 0.0596, "h": 0.0259},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4781, "y": 0.4699, "w": 0.0336, "h": 0.0214},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.8067, "y": 0.1266, "w": 0.0291, "h": 0.0233},
    {"text": 'UID:000000000', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0181},
]

# t=40.0s in rec_20261112_131536 (recording starts 13:15:36)
OPTIONS_40 = [
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4156, "y": 0.7747, "w": 0.0438, "h": 0.0242},
    {"text": 'Incoming Message Notification', "confidence": 1.0000,
     "x": 0.1628, "y": 0.7620, "w": 0.2108, "h": 0.0287},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.2119, "y": 0.7078, "w": 0.0411, "h": 0.0195},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4797, "y": 0.7028, "w": 0.0320, "h": 0.0181},
    {"text": 'Over stone river ...', "confidence": 1.0000,
     "x": 0.2166, "y": 0.6796, "w": 0.1235, "h": 0.0207},
    {"text": 'Garden a kitchen', "confidence": 1.0000,
     "x": 0.4898, "y": 0.6481, "w": 0.1076, "h": 0.0263},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4782, "y": 0.5840, "w": 0.0334, "h": 0.0233},
    {"text": "Of A mountain Window'a", "confidence": 1.0000,
     "x": 0.4898, "y": 0.5349, "w": 0.1424, "h": 0.0262},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4782, "y": 0.4677, "w": 0.0334, "h": 0.0233},
    {"text": 'Over stone river in barn the', "confidence": 1.0000,
     "x": 0.4911, "y": 0.4179, "w": 0.1864, "h": 0.0315},
    {"text": 'Can the kept?', "confidence": 1.0000,
     "x": 0.5770, "y": 0.3101, "w": 0.0988, "h": 0.0288},
    {"text": 'it on morning?', "confidence": 1.0000,
     "x": 0.5783, "y": 0.2461, "w": 0.0978, "h": 0.0332},
    {"text": "Planet lamp on'a plant kept", "confidence": 1.0000,
     "x": 0.5304, "y": 0.1904, "w": 0.1878, "h": 0.0312},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.8067, "y": 0.1266, "w": 0.0291, "h": 0.0207},
    {"text": 'Select', "confidence": 1.0000,
     "x": 0.7267, "y": 0.1266, "w": 0.0378, "h": 0.0207},
    {"text": '(R) Scroll', "confidence": 1.0000,
     "x": 0.6250, "y": 0.1111, "w": 0.0625, "h": 0.0444},
    {"text": 'UID:000000000', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0181},
]

# t=53.0s in rec_20261112_131536 (recording starts 13:15:36)
CLIPPED_53 = [
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4171, "y": 0.7747, "w": 0.0423, "h": 0.0242},
    {"text": 'Incoming Message Notification', "confidence": 1.0000,
     "x": 0.1628, "y": 0.7620, "w": 0.2108, "h": 0.0287},
    {"text": 'Over light chair we far the', "confidence": 1.0000,
     "x": 0.4927, "y": 0.7442, "w": 0.1831, "h": 0.0155},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.2150, "y": 0.7050, "w": 0.0379, "h": 0.0216},
    {"text": 'Window red a little ...', "confidence": 1.0000,
     "x": 0.2166, "y": 0.6769, "w": 0.1265, "h": 0.0234},
    {"text": 'Ebby', "confidence": 1.0000,
     "x": 0.7282, "y": 0.6744, "w": 0.0276, "h": 0.0233},
    {"text": 'Can the kept?', "confidence": 1.0000,
     "x": 0.6483, "y": 0.6176, "w": 0.0930, "h": 0.0259},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4780, "y": 0.5469, "w": 0.0338, "h": 0.0226},
    {"text": "A'a fish, A over goes'a near Window an road", "confidence": 1.0000,
     "x": 0.4897, "y": 0.4941, "w": 0.2444, "h": 0.0310},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4782, "y": 0.4315, "w": 0.0334, "h": 0.0233},
    {"text": 'A about on field over barn road up harbour', "confidence": 1.0000,
     "x": 0.4913, "y": 0.3824, "w": 0.2703, "h": 0.0233},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4781, "y": 0.3171, "w": 0.0337, "h": 0.0220},
    {"text": "Window red a little stone kept A goes'a see now", "confidence": 1.0000,
     "x": 0.4912, "y": 0.2614, "w": 0.2720, "h": 0.0319},
    {"text": 'river', "confidence": 1.0000,
     "x": 0.4898, "y": 0.2274, "w": 0.0320, "h": 0.0284},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.8081, "y": 0.1292, "w": 0.0291, "h": 0.0181},
    {"text": 'Scroll', "confidence": 1.0000,
     "x": 0.7281, "y": 0.1263, "w": 0.0350, "h": 0.0212},
    {"text": 'UID:000000000', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0181},
]

# t=59.0s in rec_20261112_131536 (recording starts 13:15:36)
WIDE_OPTION_59 = [
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4171, "y": 0.7747, "w": 0.0423, "h": 0.0242},
    {"text": 'Incoming Message Notification', "confidence": 1.0000,
     "x": 0.1628, "y": 0.7620, "w": 0.2108, "h": 0.0287},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.2118, "y": 0.7074, "w": 0.0413, "h": 0.0203},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4795, "y": 0.7074, "w": 0.0322, "h": 0.0194},
    {"text": 'On lamp, "Simple а…..', "confidence": 1.0000,
     "x": 0.2163, "y": 0.6726, "w": 0.1240, "h": 0.0328},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4781, "y": 0.5035, "w": 0.0336, "h": 0.0215},
    {"text": 'On lamp, "Simple can afternoon, to plant it', "confidence": 1.0000,
     "x": 0.4898, "y": 0.4519, "w": 0.2776, "h": 0.0288},
    {"text": 'picture!"', "confidence": 1.0000,
     "x": 0.4908, "y": 0.4189, "w": 0.0578, "h": 0.0287},
    {"text": "Way old'a light Blade'a ancient...", "confidence": 1.0000,
     "x": 0.5130, "y": 0.3099, "w": 0.2269, "h": 0.0304},
    {"text": 'Chair', "confidence": 0.5000,
     "x": 0.6017, "y": 0.2528, "w": 0.0466, "h": 0.0241},
    {"text": 'Yourself fish?', "confidence": 1.0000,
     "x": 0.5741, "y": 0.1886, "w": 0.1017, "h": 0.0284},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.8081, "y": 0.1292, "w": 0.0291, "h": 0.0181},
    {"text": 'Select', "confidence": 1.0000,
     "x": 0.7267, "y": 0.1266, "w": 0.0378, "h": 0.0207},
    {"text": 'Scroll', "confidence": 1.0000,
     "x": 0.6483, "y": 0.1266, "w": 0.0349, "h": 0.0207},
    {"text": 'UID:000000000', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0181},
]

# t=65.0s in rec_20261112_131536 (recording starts 13:15:36)
WRAPPED_65 = [
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4171, "y": 0.7747, "w": 0.0423, "h": 0.0242},
    {"text": 'Incoming Message Notification', "confidence": 1.0000,
     "x": 0.1628, "y": 0.7620, "w": 0.2108, "h": 0.0287},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4795, "y": 0.7074, "w": 0.0322, "h": 0.0194},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.2151, "y": 0.7076, "w": 0.0379, "h": 0.0190},
    {"text": "Orange old'a sun ...", "confidence": 1.0000,
     "x": 0.2178, "y": 0.6757, "w": 0.1167, "h": 0.0248},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4781, "y": 0.5035, "w": 0.0336, "h": 0.0215},
    {"text": 'On lamp, "Simple can afternoon, to plant it', "confidence": 1.0000,
     "x": 0.4898, "y": 0.4519, "w": 0.2776, "h": 0.0288},
    {"text": 'picture!"', "confidence": 1.0000,
     "x": 0.4908, "y": 0.4189, "w": 0.0578, "h": 0.0287},
    {"text": 'Ebby', "confidence": 1.0000,
     "x": 0.7282, "y": 0.3488, "w": 0.0276, "h": 0.0258},
    {"text": "Orange old'a sun Blade'a ancient up goes about", "confidence": 1.0000,
     "x": 0.4477, "y": 0.2972, "w": 0.2907, "h": 0.0233},
    {"text": 'field of blackboard. Garden field near in the', "confidence": 1.0000,
     "x": 0.4462, "y": 0.2556, "w": 0.2805, "h": 0.0287},
    {"text": 'stone can', "confidence": 1.0000,
     "x": 0.4461, "y": 0.2189, "w": 0.0714, "h": 0.0247},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.8081, "y": 0.1291, "w": 0.0291, "h": 0.0182},
    {"text": 'Scroll', "confidence": 1.0000,
     "x": 0.7281, "y": 0.1262, "w": 0.0350, "h": 0.0215},
    {"text": 'UID:000000000', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0181},
]

# t=74.5s in rec_20261112_131536 (recording starts 13:15:36)
END_74 = [
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4171, "y": 0.7747, "w": 0.0423, "h": 0.0242},
    {"text": 'Incoming Message Notification', "confidence": 1.0000,
     "x": 0.1628, "y": 0.7620, "w": 0.2108, "h": 0.0287},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.2150, "y": 0.7050, "w": 0.0379, "h": 0.0216},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4781, "y": 0.6867, "w": 0.0337, "h": 0.0220},
    {"text": 'Far', "confidence": 1.0000,
     "x": 0.2166, "y": 0.6744, "w": 0.0247, "h": 0.0258},
    {"text": 'It, river', "confidence": 1.0000,
     "x": 0.4927, "y": 0.6357, "w": 0.0581, "h": 0.0236},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4782, "y": 0.5711, "w": 0.0334, "h": 0.0207},
    {"text": 'To plant it light', "confidence": 1.0000,
     "x": 0.4898, "y": 0.5194, "w": 0.1105, "h": 0.0260},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4781, "y": 0.4545, "w": 0.0335, "h": 0.0212},
    {"text": 'Road road Red see kitchen the painting barn', "confidence": 1.0000,
     "x": 0.4898, "y": 0.4028, "w": 0.2791, "h": 0.0262},
    {"text": "Window Over'a plant", "confidence": 1.0000,
     "x": 0.4896, "y": 0.3658, "w": 0.1225, "h": 0.0298},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4781, "y": 0.3016, "w": 0.0337, "h": 0.0246},
    {"text": 'Far', "confidence": 1.0000,
     "x": 0.4898, "y": 0.2506, "w": 0.0262, "h": 0.0258},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.8067, "y": 0.1266, "w": 0.0305, "h": 0.0207},
    {"text": 'Scroll', "confidence": 1.0000,
     "x": 0.7281, "y": 0.1263, "w": 0.0350, "h": 0.0212},
    {"text": 'UID:000000000', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0181},
]

# t=76.0s in rec_20261112_131536 (recording starts 13:15:36)
REWARD_76 = [
    {"text": 'Items Obtained', "confidence": 1.0000,
     "x": 0.4520, "y": 0.8191, "w": 0.0959, "h": 0.0235},
    {"text": 'Stellar Jade', "confidence": 1.0000,
     "x": 0.4709, "y": 0.4129, "w": 0.0597, "h": 0.0191},
    {"text": 'L3 View Item Details', "confidence": 1.0000,
     "x": 0.3997, "y": 0.2528, "w": 0.1308, "h": 0.0241},
    {"text": ') Chair', "confidence": 1.0000,
     "x": 0.5590, "y": 0.2505, "w": 0.0447, "h": 0.0279},
    {"text": 'UID: 000000000', "confidence": 1.0000,
     "x": 0.0187, "y": 0.0153, "w": 0.0672, "h": 0.0209},
]

# t=77.0s in rec_20261112_131536 (recording starts 13:15:36)
REWARD_77 = [
    {"text": 'Items Obtained', "confidence": 1.0000,
     "x": 0.4520, "y": 0.8241, "w": 0.0959, "h": 0.0235},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4171, "y": 0.7750, "w": 0.0408, "h": 0.0236},
    {"text": 'Incoming Message Notification', "confidence": 1.0000,
     "x": 0.1628, "y": 0.7620, "w": 0.2108, "h": 0.0287},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.2151, "y": 0.7051, "w": 0.0379, "h": 0.0213},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4781, "y": 0.6922, "w": 0.0336, "h": 0.0213},
    {"text": 'Far', "confidence": 1.0000,
     "x": 0.2166, "y": 0.6744, "w": 0.0233, "h": 0.0258},
    {"text": 'It, river', "confidence": 1.0000,
     "x": 0.4913, "y": 0.6380, "w": 0.0581, "h": 0.0287},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4782, "y": 0.5762, "w": 0.0334, "h": 0.0207},
    {"text": 'plant it light', "confidence": 1.0000,
     "x": 0.5131, "y": 0.5296, "w": 0.0887, "h": 0.0208},
    {"text": '5', "confidence": 0.5000,
     "x": 0.4942, "y": 0.4444, "w": 0.0102, "h": 0.0155},
    {"text": 'Xxxxxxxxxxxxxx Red see kitchen the painting barn', "confidence": 1.0000,
     "x": 0.4680, "y": 0.4083, "w": 0.2994, "h": 0.0260},
    {"text": "Window Over'a plant", "confidence": 1.0000,
     "x": 0.4898, "y": 0.3747, "w": 0.1235, "h": 0.0262},
    {"text": 'Blade', "confidence": 1.0000,
     "x": 0.4780, "y": 0.3093, "w": 0.0337, "h": 0.0223},
    {"text": 'L3 View Item Details', "confidence": 1.0000,
     "x": 0.4012, "y": 0.2528, "w": 0.1294, "h": 0.0289},
    {"text": 'O Close', "confidence": 1.0000,
     "x": 0.5464, "y": 0.2527, "w": 0.0568, "h": 0.0270},
    {"text": 'UID:000000000', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0181},
]


def test_contact_list_is_this_screen_with_nothing_to_read():
    # [] and not None: None hands the frame to the dialogue classifier,
    # which logged the reply buttons as choice prompts
    assert HSR.classify_chat(CONTACTS_20) == []


def test_player_label_is_the_player_and_never_text():
    msgs = HSR.classify_chat(FIRST_26)
    assert msgs == [("Blade", "To, Ebby"), (P, "To, Field")], msgs
    assert not any("Ebby" == t or t.startswith("Ebby ") for _, t in msgs)


def test_contact_list_preview_is_not_read():
    # the list repeats the latest message under the contact's name
    texts = [t for _, t in HSR.classify_chat(FIRST_26)]
    assert texts.count("To, Field") == 1, texts


def test_reply_options_are_never_read():
    msgs = HSR.classify_chat(OPTIONS_40)
    assert msgs == [("Blade", "Garden a kitchen"),
                    ("Blade", "Of A mountain Window'a"),
                    ("Blade", "Over stone river in barn the")], msgs


def test_option_on_the_player_column_is_not_a_player_bubble():
    # a 34-character option ended at x 0.7399, on the player column;
    # only the Select hint tells it apart
    msgs = HSR.classify_chat(WIDE_OPTION_59)
    assert msgs == [("Blade",
                     'On lamp, "Simple can afternoon, to plant it picture!"')
                    ], msgs


def test_wrapped_player_bubble_aligns_left_and_joins():
    msgs = HSR.classify_chat(WRAPPED_65)
    assert msgs[-1] == (P, "Orange old'a sun Blade'a ancient up goes about "
                           "field of blackboard. Garden field near in the "
                           "stone can"), msgs
    assert len(msgs) == 2, msgs


def test_row_under_the_title_rule_drops_its_message():
    msgs = HSR.classify_chat(CLIPPED_53)
    assert msgs[0] == (P, "Can the kept?"), msgs
    assert not any("Over light" in t or "cater" in t for _, t in msgs), msgs


def test_incoming_bubble_rows_join():
    msgs = HSR.classify_chat(END_74)
    assert ("Blade", "Road road Red see kitchen the painting barn "
                     "Window Over'a plant") in msgs, msgs
    assert msgs[-1] == ("Blade", "Far"), msgs


def test_reward_modal_holds_the_reader_and_reads_nothing():
    assert HSR.holds_reader(REWARD_76)
    assert HSR.holds_reader(REWARD_77)
    assert HSR.classify_chat(REWARD_76) is None
    # the popup comes back under the modal with its rows garbled
    assert HSR.classify_chat(REWARD_77) == []
    for frame in (CONTACTS_20, FIRST_26, OPTIONS_40, END_74):
        assert not HSR.holds_reader(frame)


def test_wins_over_the_answer_panel():
    # the Answer panel's own test claims these frames and reads the
    # player's label as a message
    assert HSR._classify_answer_panel(HSR.confident(CLIPPED_53)) is not None
    assert not any(t == "Ebby" for _, t in HSR.classify_chat(CLIPPED_53))
    assert not any(t == "Ebby" for _, t in HSR.classify_chat(WRAPPED_65))


def test_marker_needs_the_whole_title():
    # Furbobocom's clipping carries an "Incoming Message" chip
    chip = [dict(b, text="Incoming Message")
            if b["text"] == "Incoming Message Notification" else b
            for b in FIRST_26]
    assert HSR._classify_message_notification(chip) is None
    spaceless = [dict(b, text="IncomingMessageNotification")
                 if b["text"] == "Incoming Message Notification" else b
                 for b in FIRST_26]
    assert HSR._classify_message_notification(spaceless) == \
        HSR.classify_chat(FIRST_26)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
