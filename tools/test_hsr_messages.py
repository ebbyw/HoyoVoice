"""Pins Star Rail's phone Messages app — the regular character chats,
as opposed to the in-story "Answer" panel the CHAT_* constants describe.

Before this detector the app had no screen of its own and fell through to
the dialogue classifier. In the 2026-08-28 14:14 session that produced,
in one minute: the thread header spoken as a line ("Rin iTahsaka", read
in the player's voice at 14:15:01), a conversation-list preview auto-cast
as a speaker ("This is way too cute"), a delivery notice auto-cast as
another ("Message" -> zm_yunxi, which then said Rin's line at 14:15:14),
and the player's own sent bubbles read back to them as Trailblazer choice
prompts because they land in the CHOICES band.

The frames here are four of rec_20260828_141426's, verbatim. The first
pins the basics: list column excluded, header used as the sender, the
player's right-hanging bubble read as their own. The second pins the
delivery notices and a typing indicator's bare label, all dropped, and an
incoming run that follows a player bubble keeping the incoming sender.
The third pins the reply buttons — unsent options, dropped so the chosen
one is only ever read once, as a sent bubble. The last pins the two rows
that broke a left/right threshold and forced the alignment test that
replaced it.

Run directly or under pytest:

    python tools/test_hsr_messages.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profiles import get_profile                # noqa: E402

HSR = get_profile("hsr")

SHOT_2 = [
    {"text": 'Change Chat Boxes', "confidence": 1.0000,
     "x": 0.8067, "y": 0.9432, "w": 0.1206, "h": 0.0263},
    {"text": 'Messages', "confidence": 1.0000,
     "x": 0.0552, "y": 0.9428, "w": 0.0611, "h": 0.0239},
    {"text": 'Rin Tohsaka', "confidence": 1.0000,
     "x": 0.3009, "y": 0.8500, "w": 0.0916, "h": 0.0260},
    {"text": 'Rin Tohsaka', "confidence": 1.0000,
     "x": 0.0799, "y": 0.8370, "w": 0.0770, "h": 0.0234},
    {"text": 'Gem recycling! Hit me up anytime!', "confidence": 1.0000,
     "x": 0.3009, "y": 0.8213, "w": 0.1846, "h": 0.0213},
    {"text": 'Rin Tohsaka', "confidence": 1.0000,
     "x": 0.3663, "y": 0.7674, "w": 0.0683, "h": 0.0181},
    {"text": 'Sure, give me a sec.', "confidence": 1.0000,
     "x": 0.0640, "y": 0.7442, "w": 0.1308, "h": 0.0262},
    {"text": 'Ebby, can you help me snap a photo of the conductor?', "confidence": 1.0000,
     "x": 0.3794, "y": 0.7130, "w": 0.3372, "h": 0.0261},
    {"text": '× A surprise awaits', "confidence": 1.0000,
     "x": 0.0465, "y": 0.6769, "w": 0.1294, "h": 0.0260},
    {"text": 'Ebby', "confidence": 1.0000,
     "x": 0.8520, "y": 0.6444, "w": 0.0313, "h": 0.0289},
    {"text": 'Sure, give me a sec.', "confidence": 1.0000,
     "x": 0.7369, "y": 0.5889, "w": 0.1294, "h": 0.0261},
    {"text": 'March 7th', "confidence": 1.0000,
     "x": 0.0799, "y": 0.5890, "w": 0.0640, "h": 0.0236},
    {"text": '???', "confidence": 1.0000,
     "x": 0.0799, "y": 0.4832, "w": 0.0203, "h": 0.0233},
    {"text": 'Sparxie', "confidence": 1.0000,
     "x": 0.0799, "y": 0.3743, "w": 0.0481, "h": 0.0266},
    {"text": 'Argenti', "confidence": 1.0000,
     "x": 0.0799, "y": 0.2661, "w": 0.0465, "h": 0.0284},
    {"text": 'Gilgamesh', "confidence": 1.0000,
     "x": 0.0799, "y": 0.1596, "w": 0.0670, "h": 0.0270},
    {"text": 'Filter', "confidence": 1.0000,
     "x": 0.0610, "y": 0.0698, "w": 0.0334, "h": 0.0233},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0203, "y": 0.0181, "w": 0.0654, "h": 0.0155},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.9346, "y": 0.0155, "w": 0.0291, "h": 0.0181},
]

SHOT_13 = [
    {"text": 'Change Chat Boxes', "confidence": 1.0000,
     "x": 0.8067, "y": 0.9432, "w": 0.1206, "h": 0.0263},
    {"text": 'Messages', "confidence": 1.0000,
     "x": 0.0552, "y": 0.9429, "w": 0.0611, "h": 0.0238},
    {"text": 'Rin Tohsaka', "confidence": 1.0000,
     "x": 0.3009, "y": 0.8500, "w": 0.0901, "h": 0.0260},
    {"text": 'Rin Tohsaka', "confidence": 1.0000,
     "x": 0.0799, "y": 0.8370, "w": 0.0770, "h": 0.0234},
    {"text": 'Gem recycling! Hit me up anytime!', "confidence": 1.0000,
     "x": 0.3023, "y": 0.8213, "w": 0.1831, "h": 0.0213},
    {"text": 'Rin Tohsaka', "confidence": 1.0000,
     "x": 0.3662, "y": 0.7587, "w": 0.0685, "h": 0.0226},
    {"text": 'Message failed to send.', "confidence": 1.0000,
     "x": 0.0640, "y": 0.7468, "w": 0.1497, "h": 0.0236},
    {"text": 'Thank you, Ebby! My life is complete!', "confidence": 1.0000,
     "x": 0.3779, "y": 0.7054, "w": 0.2340, "h": 0.0288},
    {"text": '› A surprise awaits', "confidence": 1.0000,
     "x": 0.0465, "y": 0.6769, "w": 0.1294, "h": 0.0260},
    {"text": 'Rin Tohsaka', "confidence": 1.0000,
     "x": 0.3663, "y": 0.6460, "w": 0.0683, "h": 0.0181},
    {"text": "I was planning to visit the Express, but it's a shame I won't have the time...", "confidence": 1.0000,
     "x": 0.3779, "y": 0.5917, "w": 0.4666, "h": 0.0259},
    {"text": 'March 7th', "confidence": 1.0000,
     "x": 0.0799, "y": 0.5889, "w": 0.0640, "h": 0.0237},
    {"text": 'Rin Tohsaka', "confidence": 1.0000,
     "x": 0.3663, "y": 0.5296, "w": 0.0683, "h": 0.0185},
    {"text": '???', "confidence": 1.0000,
     "x": 0.0799, "y": 0.4858, "w": 0.0203, "h": 0.0207},
    {"text": 'You absolutely gotta introduce me to the conductor when the time comes! I just', "confidence": 1.0000,
     "x": 0.3794, "y": 0.4778, "w": 0.4942, "h": 0.0235},
    {"text": 'wanna pet them kgfpoirfqialkfjwe', "confidence": 0.5000,
     "x": 0.3779, "y": 0.4389, "w": 0.2108, "h": 0.0262},
    {"text": 'Sparxie', "confidence": 1.0000,
     "x": 0.0799, "y": 0.3747, "w": 0.0480, "h": 0.0258},
    {"text": 'A Message failed to receive.', "confidence": 1.0000,
     "x": 0.5509, "y": 0.3667, "w": 0.1497, "h": 0.0235},
    {"text": 'Ebby', "confidence": 1.0000,
     "x": 0.8532, "y": 0.3049, "w": 0.0291, "h": 0.0233},
    {"text": 'Argenti', "confidence": 1.0000,
     "x": 0.0799, "y": 0.2660, "w": 0.0466, "h": 0.0288},
    {"text": 'Rin, you headed off already?', "confidence": 1.0000,
     "x": 0.6875, "y": 0.2454, "w": 0.1788, "h": 0.0287},
    {"text": 'A Message failed to send.', "confidence": 1.0000,
     "x": 0.5567, "y": 0.1704, "w": 0.1381, "h": 0.0234},
    {"text": 'Gilgamesh', "confidence": 1.0000,
     "x": 0.0798, "y": 0.1590, "w": 0.0671, "h": 0.0282},
    {"text": 'Rin Tohsaka', "confidence": 1.0000,
     "x": 0.3677, "y": 0.1111, "w": 0.0669, "h": 0.0185},
    {"text": 'Filter', "confidence": 1.0000,
     "x": 0.0610, "y": 0.0698, "w": 0.0334, "h": 0.0233},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0203, "y": 0.0181, "w": 0.0654, "h": 0.0155},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.9360, "y": 0.0155, "w": 0.0276, "h": 0.0181},
    {"text": 'Scroll', "confidence": 1.0000,
     "x": 0.8604, "y": 0.0152, "w": 0.0350, "h": 0.0186},
]

SHOT_16 = [
    {"text": 'Change Chat Boxes', "confidence": 1.0000,
     "x": 0.8067, "y": 0.9406, "w": 0.1206, "h": 0.0289},
    {"text": 'Messages', "confidence": 1.0000,
     "x": 0.0552, "y": 0.9431, "w": 0.0611, "h": 0.0235},
    {"text": 'Rin Tohsaka', "confidence": 1.0000,
     "x": 0.3009, "y": 0.8500, "w": 0.0916, "h": 0.0260},
    {"text": 'Rin Tohsaka', "confidence": 1.0000,
     "x": 0.0799, "y": 0.8370, "w": 0.0770, "h": 0.0234},
    {"text": 'Gem recycling! Hit me up anytime!', "confidence": 1.0000,
     "x": 0.3023, "y": 0.8213, "w": 0.1831, "h": 0.0213},
    {"text": 'Rin Tohsaka', "confidence": 1.0000,
     "x": 0.3663, "y": 0.7722, "w": 0.0683, "h": 0.0185},
    {"text": "Because I'm just really gla...", "confidence": 1.0000,
     "x": 0.0640, "y": 0.7468, "w": 0.1773, "h": 0.0236},
    {"text": 'You absolutely gotta introduce me to the conductor when the time comes! I just', "confidence": 1.0000,
     "x": 0.3779, "y": 0.7209, "w": 0.4956, "h": 0.0235},
    {"text": 'wanna pet them kgfpoirfqialkfjwe', "confidence": 0.5000,
     "x": 0.3779, "y": 0.6822, "w": 0.2108, "h": 0.0284},
    {"text": '~ A surprise awaits', "confidence": 1.0000,
     "x": 0.0465, "y": 0.6769, "w": 0.1294, "h": 0.0260},
    {"text": 'A Message failed to receive.', "confidence": 1.0000,
     "x": 0.5509, "y": 0.6098, "w": 0.1497, "h": 0.0235},
    {"text": 'March 7th', "confidence": 1.0000,
     "x": 0.0799, "y": 0.5889, "w": 0.0640, "h": 0.0237},
    {"text": 'Ebby', "confidence": 1.0000,
     "x": 0.8532, "y": 0.5478, "w": 0.0276, "h": 0.0233},
    {"text": 'Rin, you headed off already?', "confidence": 1.0000,
     "x": 0.6875, "y": 0.4880, "w": 0.1788, "h": 0.0288},
    {"text": '???', "confidence": 1.0000,
     "x": 0.0799, "y": 0.4832, "w": 0.0203, "h": 0.0233},
    {"text": 'A Message failed to send.', "confidence": 1.0000,
     "x": 0.5567, "y": 0.4134, "w": 0.1381, "h": 0.0236},
    {"text": 'Sparxie', "confidence": 1.0000,
     "x": 0.0799, "y": 0.3747, "w": 0.0480, "h": 0.0258},
    {"text": 'Rin Tohsaka', "confidence": 1.0000,
     "x": 0.3663, "y": 0.3565, "w": 0.0683, "h": 0.0185},
    {"text": "Because I'm just really glad 1 met you guys, Ebby.", "confidence": 1.0000,
     "x": 0.3779, "y": 0.2997, "w": 0.3110, "h": 0.0284},
    {"text": 'Argenti', "confidence": 1.0000,
     "x": 0.0799, "y": 0.2660, "w": 0.0466, "h": 0.0288},
    {"text": 'Same here, Rin.', "confidence": 1.0000,
     "x": 0.5770, "y": 0.1912, "w": 0.1090, "h": 0.0310},
    {"text": 'Gilgamesh', "confidence": 1.0000,
     "x": 0.0799, "y": 0.1597, "w": 0.0670, "h": 0.0269},
    {"text": 'Me too, Master.', "confidence": 1.0000,
     "x": 0.5785, "y": 0.1343, "w": 0.1061, "h": 0.0287},
    {"text": 'Filter', "confidence": 1.0000,
     "x": 0.0610, "y": 0.0698, "w": 0.0334, "h": 0.0233},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0203, "y": 0.0181, "w": 0.0654, "h": 0.0155},
    {"text": 'Scroll', "confidence": 1.0000,
     "x": 0.7863, "y": 0.0155, "w": 0.0349, "h": 0.0207},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.9360, "y": 0.0155, "w": 0.0276, "h": 0.0181},
    {"text": 'Select', "confidence": 1.0000,
     "x": 0.8605, "y": 0.0155, "w": 0.0378, "h": 0.0181},
]

SHOT_END = [
    {"text": 'Change Chat Boxes', "confidence": 1.0000,
     "x": 0.8067, "y": 0.9406, "w": 0.1206, "h": 0.0289},
    {"text": 'Messages', "confidence": 1.0000,
     "x": 0.0552, "y": 0.9431, "w": 0.0611, "h": 0.0235},
    {"text": 'Rin Tohsaka', "confidence": 1.0000,
     "x": 0.3009, "y": 0.8500, "w": 0.0916, "h": 0.0260},
    {"text": 'Rin Tohsaka', "confidence": 1.0000,
     "x": 0.0799, "y": 0.8370, "w": 0.0770, "h": 0.0234},
    {"text": 'Gem recycling! Hit me up anytime!', "confidence": 1.0000,
     "x": 0.3009, "y": 0.8213, "w": 0.1846, "h": 0.0213},
    {"text": "› The user you're trying to r...", "confidence": 1.0000,
     "x": 0.0465, "y": 0.7442, "w": 0.1948, "h": 0.0262},
    {"text": 'A Message failed to receive.', "confidence": 1.0000,
     "x": 0.5509, "y": 0.7183, "w": 0.1497, "h": 0.0233},
    {"text": '/ A surprise awaits', "confidence": 1.0000,
     "x": 0.0465, "y": 0.6769, "w": 0.1294, "h": 0.0260},
    {"text": 'Ebby', "confidence": 1.0000,
     "x": 0.8532, "y": 0.6537, "w": 0.0276, "h": 0.0258},
    {"text": 'Rin, you headed off already?', "confidence": 1.0000,
     "x": 0.6875, "y": 0.5969, "w": 0.1788, "h": 0.0262},
    {"text": 'March 7th', "confidence": 1.0000,
     "x": 0.0799, "y": 0.5889, "w": 0.0640, "h": 0.0235},
    {"text": 'A Message failed to send.', "confidence": 1.0000,
     "x": 0.5567, "y": 0.5220, "w": 0.1381, "h": 0.0207},
    {"text": '???', "confidence": 1.0000,
     "x": 0.0799, "y": 0.4832, "w": 0.0203, "h": 0.0233},
    {"text": 'Rin Tohsaka', "confidence": 1.0000,
     "x": 0.3663, "y": 0.4625, "w": 0.0683, "h": 0.0181},
    {"text": "Because I'm just really glad I met you guys, Ebby.", "confidence": 1.0000,
     "x": 0.3779, "y": 0.4056, "w": 0.3125, "h": 0.0287},
    {"text": 'Sparxie', "confidence": 1.0000,
     "x": 0.0799, "y": 0.3747, "w": 0.0480, "h": 0.0258},
    {"text": 'Ebby', "confidence": 1.0000,
     "x": 0.8532, "y": 0.3411, "w": 0.0276, "h": 0.0233},
    {"text": "It's an honor to fight alongside you, Master.", "confidence": 1.0000,
     "x": 0.5945, "y": 0.2815, "w": 0.2733, "h": 0.0287},
    {"text": 'Argenti', "confidence": 1.0000,
     "x": 0.0799, "y": 0.2661, "w": 0.0465, "h": 0.0284},
    {"text": '& Message failed to receive.', "confidence": 1.0000,
     "x": 0.5509, "y": 0.2065, "w": 0.1497, "h": 0.0235},
    {"text": 'Gilgamesh', "confidence": 1.0000,
     "x": 0.0798, "y": 0.1590, "w": 0.0671, "h": 0.0282},
    {"text": "A The user you're trying to reach is currently out of the service area. Please try again later.", "confidence": 1.0000,
     "x": 0.3953, "y": 0.1395, "w": 0.4622, "h": 0.0234},
    {"text": 'Filter', "confidence": 1.0000,
     "x": 0.0610, "y": 0.0698, "w": 0.0334, "h": 0.0233},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0203, "y": 0.0181, "w": 0.0654, "h": 0.0155},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.9360, "y": 0.0155, "w": 0.0276, "h": 0.0181},
    {"text": 'Scroll', "confidence": 1.0000,
     "x": 0.8604, "y": 0.0153, "w": 0.0349, "h": 0.0185},
]


def test_shot_2():
    msgs = HSR.classify_chat(SHOT_2)
    assert msgs == [
        ("Rin Tohsaka",
         "Ebby, can you help me snap a photo of the conductor?"),
        ("Ebby", "Sure, give me a sec."),
    ], msgs


def test_shot_13():
    msgs = HSR.classify_chat(SHOT_13)
    assert msgs == [
        ("Rin Tohsaka", "Thank you, Ebby! My life is complete!"),
        ("Rin Tohsaka",
         "I was planning to visit the Express, but it's a shame I won't "
         "have the time..."),
        # the bubble's second row ("wanna pet them kgfpoirfqialkfjwe")
        # reads at confidence 0.50 and is dropped before this detector
        # ever sees it — gibberish the game itself typed
        ("Rin Tohsaka",
         "You absolutely gotta introduce me to the conductor when the "
         "time comes! I just"),
        ("Ebby", "Rin, you headed off already?"),
    ], msgs


def test_shot_16():
    msgs = HSR.classify_chat(SHOT_16)
    assert msgs == [
        ("Rin Tohsaka",
         "You absolutely gotta introduce me to the conductor when the "
         "time comes! I just"),
        ("Ebby", "Rin, you headed off already?"),
        ("Rin Tohsaka", "Because I'm just really glad 1 met you guys, Ebby."),
    ], msgs


def test_shot_end():
    """The end of the same thread, and the two edges a left/right
    THRESHOLD got wrong before alignment replaced it: the player's
    longest reply starts at x=0.5945, left of any workable player-column
    floor, and the service-area notice starts at x=0.3939, right of the
    incoming rows but inside any band wide enough to hold them safely."""
    msgs = HSR.classify_chat(SHOT_END)
    assert msgs == [
        ("Ebby", "Rin, you headed off already?"),
        ("Rin Tohsaka", "Because I'm just really glad I met you guys, Ebby."),
        ("Ebby", "It's an honor to fight alongside you, Master."),
    ], msgs


def test_notices_and_buttons_are_never_speech():
    """Nothing centred in the pane is read: the delivery notices are UI
    status, and the reply buttons are options not yet sent."""
    spoken = " ".join(t for shot in (SHOT_13, SHOT_16, SHOT_END)
                      for _, t in HSR.classify_chat(shot))
    for phrase in ("failed to send", "failed to receive", "service area",
                   "Same here, Rin.", "Me too, Master."):
        assert phrase not in spoken, phrase


def test_list_column_is_never_a_speaker():
    """The conversation list carries each thread's last message as a
    preview; one of them was auto-cast as a speaker."""
    senders = {s for shot in (SHOT_2, SHOT_13, SHOT_16, SHOT_END)
               for s, _ in HSR.classify_chat(shot)}
    assert senders == {"Rin Tohsaka", "Ebby"}, senders


def test_menu_is_not_a_chat_screen():
    """The phone's own menu has a "Messages" tile on it — mid-screen, not
    in the app's title corner."""
    menu = [{"text": "Messages", "confidence": 1.0,
             "x": 0.7020, "y": 0.3719, "w": 0.0509, "h": 0.0181},
            {"text": "Travel Log", "confidence": 1.0,
             "x": 0.7052, "y": 0.4884, "w": 0.0553, "h": 0.0235}]
    assert HSR.classify_chat(menu) is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all Star Rail Messages-app checks pass")
