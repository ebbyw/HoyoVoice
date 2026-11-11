"""Pins the Star Rail Furbobocom screens — the furbo event hub of
version 4.x — off rec_20261110_213011 (2026-11-10 21:30, Windows box).
Every frame here is that recording OCR'd by the Vision daemon, verbatim.

Before this the hub had no screen of its own. In seven minutes of the
Clue Investigation thread the session log shows every bubble "skipped
(unknown speaker, no story chrome)" with a neighbouring row as its
speaker ("N-Not me!" speaking "Gemibo", 21:30:30), the quiz answers
spoken as a line by a speaker called "March 7th" (21:33:02), the group
chat popup's rows read the same way (21:30:33-21:30:37), the furbo office
dialogue read in the narrator's voice because its nameplate is a tab on
the box's left corner (21:31:30, 21:36:03), and the Press Affairs card
wall read as a nameplate and a two-option prompt (21:37:15).

What is pinned:
  - the Clue Investigation pane: senders from the grey (confidence 0.50)
    label column, incoming and player bubbles by alignment, the player's
    label scrolled off the top still reading as the player, reply options
    under the player's name, and a row half under the pane's top edge
    dropping the message it starts rather than prefixing it with garbage
  - the group-chat popup: same, at its own columns, with the player rows
    aligned on the LEFT; reply options only while Scroll/Select is up,
    and the hint row itself never read
  - the office scene's left-corner nameplate
  - the Press Affairs page being neither dialogue nor a prompt

Run directly or under pytest:

    python tools/test_hsr_furbobocom.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profiles import get_profile                # noqa: E402

HSR = get_profile("hsr")

CLUE_156 = [
    {"text": 'Furbobocom', "confidence": 0.5000,
     "x": 0.0550, "y": 0.9401, "w": 0.0615, "h": 0.0197},
    {"text": 'Clue Investigation', "confidence": 1.0000,
     "x": 0.0538, "y": 0.9093, "w": 0.1119, "h": 0.0261},
    {"text": 'Clue Source', "confidence": 1.0000,
     "x": 0.2471, "y": 0.8320, "w": 0.0916, "h": 0.0263},
    {"text": 'Furbo is busy...', "confidence": 1.0000,
     "x": 0.4416, "y": 0.8409, "w": 0.1183, "h": 0.0329},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.2514, "y": 0.7022, "w": 0.0510, "h": 0.0245},
    {"text": 'Sent a join request using the group number in the "FurboCart"', "confidence": 1.0000,
     "x": 0.2645, "y": 0.6442, "w": 0.4652, "h": 0.0360},
    {"text": 'post...', "confidence": 1.0000,
     "x": 0.2645, "y": 0.6047, "w": 0.0465, "h": 0.0258},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.2515, "y": 0.5297, "w": 0.0509, "h": 0.0233},
    {"text": 'The group owner has set up an entry quiz: answer all questions', "confidence": 1.0000,
     "x": 0.2631, "y": 0.4729, "w": 0.4797, "h": 0.0284},
    {"text": 'right to get in!', "confidence": 1.0000,
     "x": 0.2631, "y": 0.4287, "w": 0.1090, "h": 0.0315},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.2515, "y": 0.3540, "w": 0.0509, "h": 0.0258},
    {"text": "(Don't worry if you mess up. Gemibo's got your back.)", "confidence": 1.0000,
     "x": 0.2631, "y": 0.2997, "w": 0.4026, "h": 0.0336},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.2513, "y": 0.2240, "w": 0.0511, "h": 0.0248},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0155},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.9345, "y": 0.0125, "w": 0.0307, "h": 0.0215},
]

CLUE_169 = [
    {"text": 'Furbobocom', "confidence": 0.5000,
     "x": 0.0536, "y": 0.9401, "w": 0.0629, "h": 0.0198},
    {"text": 'Clue Investigation', "confidence": 1.0000,
     "x": 0.0538, "y": 0.9093, "w": 0.1119, "h": 0.0261},
    {"text": 'Clue Source', "confidence": 1.0000,
     "x": 0.2471, "y": 0.8320, "w": 0.0916, "h": 0.0263},
    {"text": 'Furbo is busy..', "confidence": 1.0000,
     "x": 0.4416, "y": 0.8411, "w": 0.1110, "h": 0.0326},
    {"text": "That's me!", "confidence": 1.0000,
     "x": 0.6584, "y": 0.6922, "w": 0.0800, "h": 0.0290},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.2511, "y": 0.6110, "w": 0.0514, "h": 0.0263},
    {"text": 'Bingo!', "confidence": 1.0000,
     "x": 0.2644, "y": 0.5576, "w": 0.0482, "h": 0.0321},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.2515, "y": 0.4832, "w": 0.0509, "h": 0.0233},
    {"text": "Q2: When's Joolyon's birthday on the Arcadian Calendar?", "confidence": 1.0000,
     "x": 0.2625, "y": 0.4222, "w": 0.4333, "h": 0.0370},
    {"text": '→', "confidence": 1.0000,
     "x": 0.2762, "y": 0.2765, "w": 0.0189, "h": 0.0336},
    {"text": 'March 25th', "confidence": 1.0000,
     "x": 0.4637, "y": 0.2815, "w": 0.0858, "h": 0.0260},
    {"text": 'January 24th', "confidence": 1.0000,
     "x": 0.4563, "y": 0.2034, "w": 0.0991, "h": 0.0312},
    {"text": "Gemibo, I'll leave it to you.", "confidence": 1.0000,
     "x": 0.4070, "y": 0.1315, "w": 0.1991, "h": 0.0315},
    {"text": 'UID: 603150536', "confidence": 1.0000,
     "x": 0.0203, "y": 0.0155, "w": 0.0654, "h": 0.0155},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.9331, "y": 0.0151, "w": 0.0321, "h": 0.0190},
]

CLUE_181 = [
    {"text": 'Furbobocom', "confidence": 0.5000,
     "x": 0.0536, "y": 0.9401, "w": 0.0629, "h": 0.0204},
    {"text": 'Clue Investigation', "confidence": 1.0000,
     "x": 0.0538, "y": 0.9093, "w": 0.1105, "h": 0.0261},
    {"text": 'Clue Source', "confidence": 1.0000,
     "x": 0.2471, "y": 0.8320, "w": 0.0916, "h": 0.0263},
    {"text": 'Furbo is busy...', "confidence": 1.0000,
     "x": 0.4416, "y": 0.8410, "w": 0.1139, "h": 0.0327},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.2515, "y": 0.6718, "w": 0.0509, "h": 0.0233},
    {"text": 'Bingo!', "confidence": 1.0000,
     "x": 0.2645, "y": 0.6150, "w": 0.0480, "h": 0.0310},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.2514, "y": 0.5399, "w": 0.0509, "h": 0.0262},
    {"text": "Q2: When's Joolyon's birthday on the Arcadian Calendar?", "confidence": 1.0000,
     "x": 0.2625, "y": 0.4815, "w": 0.4333, "h": 0.0370},
    {"text": 'Ebby', "confidence": 1.0000,
     "x": 0.7154, "y": 0.4040, "w": 0.0373, "h": 0.0337},
    {"text": "I got nothing. Gemibo, you're up!", "confidence": 1.0000,
     "x": 0.4917, "y": 0.3481, "w": 0.2500, "h": 0.0370},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.2515, "y": 0.2791, "w": 0.0509, "h": 0.0233},
    {"text": 'March 25th.', "confidence": 1.0000,
     "x": 0.2645, "y": 0.1802, "w": 0.0917, "h": 0.0298},
    {"text": 'You have chosen "paws off the keyboard": Joolyon\'s birthday is', "confidence": 1.0000,
     "x": 0.2625, "y": 0.2148, "w": 0.4792, "h": 0.0444},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0155},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.9345, "y": 0.0125, "w": 0.0307, "h": 0.0215},
]

CLUE_248 = [
    {"text": 'Furbobocom', "confidence": 0.5000,
     "x": 0.0552, "y": 0.9432, "w": 0.0610, "h": 0.0155},
    {"text": 'Clue Investigation', "confidence": 1.0000,
     "x": 0.0538, "y": 0.9093, "w": 0.1105, "h": 0.0261},
    {"text": '0.0', "confidence": 1.0000,
     "x": 0.2137, "y": 0.6331, "w": 0.0203, "h": 0.0155},
    {"text": '0.0', "confidence": 0.5000,
     "x": 0.2122, "y": 0.3747, "w": 0.0218, "h": 0.0207},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0155},
    {"text": 'Clue Source', "confidence": 1.0000,
     "x": 0.2471, "y": 0.8320, "w": 0.0916, "h": 0.0263},
    {"text": 'Furbo is busy...', "confidence": 1.0000,
     "x": 0.4416, "y": 0.8418, "w": 0.1139, "h": 0.0333},
    {"text": 'oput mio unrer em', "confidence": 0.5000,
     "x": 0.2643, "y": 0.7203, "w": 0.1384, "h": 0.0239},
    {"text": 'Joolyon', "confidence": 0.5000,
     "x": 0.2515, "y": 0.6408, "w": 0.0523, "h": 0.0258},
    {"text": 'Joolyon', "confidence": 0.5000,
     "x": 0.2514, "y": 0.3845, "w": 0.0525, "h": 0.0295},
    {"text": 'Which street do you wanna check out, President?', "confidence": 1.0000,
     "x": 0.2645, "y": 0.3333, "w": 0.3677, "h": 0.0310},
    {"text": '"Archnemesis" Street.', "confidence": 1.0000,
     "x": 0.4212, "y": 0.1832, "w": 0.1692, "h": 0.0377},
    {"text": '"Many Furbos" Street.', "confidence": 1.0000,
     "x": 0.4215, "y": 0.1111, "w": 0.1672, "h": 0.0336},
    {"text": 'Checking Mode', "confidence": 1.0000,
     "x": 0.8183, "y": 0.0102, "w": 0.0843, "h": 0.0234},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.9345, "y": 0.0125, "w": 0.0307, "h": 0.0215},
]

CLUE_292 = [
    {"text": 'Furbobocom', "confidence": 0.5000,
     "x": 0.0536, "y": 0.9401, "w": 0.0629, "h": 0.0204},
    {"text": 'Clue Investigation', "confidence": 1.0000,
     "x": 0.0538, "y": 0.9093, "w": 0.1105, "h": 0.0261},
    {"text": '0.0', "confidence": 1.0000,
     "x": 0.2122, "y": 0.7080, "w": 0.0218, "h": 0.0129},
    {"text": '0.0', "confidence": 1.0000,
     "x": 0.2137, "y": 0.3437, "w": 0.0203, "h": 0.0155},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0155},
    {"text": 'Clue Source', "confidence": 1.0000,
     "x": 0.2471, "y": 0.8320, "w": 0.0916, "h": 0.0263},
    {"text": 'Furbo is busy..', "confidence": 1.0000,
     "x": 0.4416, "y": 0.8412, "w": 0.1110, "h": 0.0325},
    {"text": 'Jootyon', "confidence": 0.5000,
     "x": 0.2514, "y": 0.7129, "w": 0.0538, "h": 0.0237},
    {"text": 'Ebby', "confidence": 1.0000,
     "x": 0.7180, "y": 0.4832, "w": 0.0334, "h": 0.0258},
    {"text": 'Nice one, Joolyon. Still playing dumb, huh?', "confidence": 1.0000,
     "x": 0.4186, "y": 0.4287, "w": 0.3198, "h": 0.0315},
    {"text": 'Joolyon', "confidence": 0.5000,
     "x": 0.2500, "y": 0.3513, "w": 0.0538, "h": 0.0260},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.2514, "y": 0.2247, "w": 0.0509, "h": 0.0234},
    {"text": "P-President, what are you saying? I don't even know how to play!", "confidence": 1.0000,
     "x": 0.2630, "y": 0.2965, "w": 0.4957, "h": 0.0356},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.9345, "y": 0.0125, "w": 0.0307, "h": 0.0215},
]

CLUE_336 = [
    {"text": 'Furbobocom', "confidence": 0.5000,
     "x": 0.0550, "y": 0.9401, "w": 0.0615, "h": 0.0203},
    {"text": 'Clue Investigation', "confidence": 1.0000,
     "x": 0.0538, "y": 0.9093, "w": 0.1105, "h": 0.0261},
    {"text": 'Clue Source', "confidence": 1.0000,
     "x": 0.2471, "y": 0.8320, "w": 0.0916, "h": 0.0263},
    {"text": 'Furbo is busy.', "confidence": 1.0000,
     "x": 0.4417, "y": 0.8431, "w": 0.1079, "h": 0.0288},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.2515, "y": 0.7003, "w": 0.0509, "h": 0.0258},
    {"text": "That's our president, strict and fair, no exceptions! Gemibo will tell", "confidence": 1.0000,
     "x": 0.2645, "y": 0.6411, "w": 0.5001, "h": 0.0368},
    {"text": 'the others about the new rules~', "confidence": 1.0000,
     "x": 0.2631, "y": 0.6072, "w": 0.2427, "h": 0.0233},
    {"text": 'Furbo is on the way back...', "confidence": 1.0000,
     "x": 0.4026, "y": 0.2119, "w": 0.2006, "h": 0.0289},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0203, "y": 0.0155, "w": 0.0654, "h": 0.0181},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.9345, "y": 0.0125, "w": 0.0292, "h": 0.0215},
]

POPUP_19 = [
    {"text": 'AAA Furbobo Weekly Wholesale Requests', "confidence": 1.0000,
     "x": 0.3387, "y": 0.7778, "w": 0.2907, "h": 0.0287},
    {"text": 'Make Furbobo Weekly Great Again!', "confidence": 1.0000,
     "x": 0.3399, "y": 0.7475, "w": 0.1894, "h": 0.0332},
    {"text": 'Press to view the incoming', "confidence": 1.0000,
     "x": 0.3675, "y": 0.6923, "w": 0.1690, "h": 0.0298},
    {"text": 'external message', "confidence": 1.0000,
     "x": 0.3675, "y": 0.6557, "w": 0.1109, "h": 0.0261},
    {"text": 'Ebby', "confidence": 1.0000,
     "x": 0.5669, "y": 0.5917, "w": 0.0305, "h": 0.0207},
    {"text": "Who placed the order? Who's been", "confidence": 1.0000,
     "x": 0.3663, "y": 0.5452, "w": 0.2166, "h": 0.0289},
    {"text": 'quietly spoiling our little furbos?', "confidence": 1.0000,
     "x": 0.3662, "y": 0.5077, "w": 0.2037, "h": 0.0299},
    {"text": 'Furbulitzer', "confidence": 1.0000,
     "x": 0.3866, "y": 0.4496, "w": 0.0625, "h": 0.0181},
    {"text": 'Not me', "confidence": 1.0000,
     "x": 0.3982, "y": 0.4080, "w": 0.0451, "h": 0.0186},
    {"text": 'Joolyon', "confidence": 0.5000,
     "x": 0.3866, "y": 0.3383, "w": 0.0437, "h": 0.0211},
    {"text": 'N-Not me!', "confidence": 1.0000,
     "x": 0.3968, "y": 0.2972, "w": 0.0712, "h": 0.0233},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.3852, "y": 0.2300, "w": 0.0436, "h": 0.0207},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0181},
]

POPUP_22 = [
    {"text": 'AAA Furbobo Weekly Wholesale Requests', "confidence": 1.0000,
     "x": 0.3387, "y": 0.7804, "w": 0.2907, "h": 0.0284},
    {"text": 'Make Furbobo Weekly Great Again!', "confidence": 1.0000,
     "x": 0.3414, "y": 0.7527, "w": 0.1878, "h": 0.0278},
    {"text": 'vino placed the order: vino s been', "confidence": 1.0000,
     "x": 0.3663, "y": 0.7287, "w": 0.2180, "h": 0.0185},
    {"text": 'quietly spoiling our little furbos?', "confidence": 1.0000,
     "x": 0.3662, "y": 0.6886, "w": 0.2037, "h": 0.0299},
    {"text": 'Furbulitzer', "confidence": 1.0000,
     "x": 0.3866, "y": 0.6305, "w": 0.0625, "h": 0.0181},
    {"text": 'Not me', "confidence": 1.0000,
     "x": 0.3982, "y": 0.5889, "w": 0.0451, "h": 0.0186},
    {"text": '0.0', "confidence": 0.5000,
     "x": 0.3532, "y": 0.5090, "w": 0.0189, "h": 0.0181},
    {"text": 'Joolyon', "confidence": 0.5000,
     "x": 0.3862, "y": 0.5176, "w": 0.0445, "h": 0.0231},
    {"text": 'N-Not me!', "confidence": 1.0000,
     "x": 0.3967, "y": 0.4739, "w": 0.0715, "h": 0.0263},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.3852, "y": 0.4109, "w": 0.0436, "h": 0.0207},
    {"text": '(Deep search in progress... 1', "confidence": 1.0000,
     "x": 0.3953, "y": 0.3618, "w": 0.1817, "h": 0.0284},
    {"text": 'suspected related forum page', "confidence": 1.0000,
     "x": 0.3983, "y": 0.3306, "w": 0.1875, "h": 0.0234},
    {"text": 'found: "FurboCart"-)', "confidence": 1.0000,
     "x": 0.3953, "y": 0.2944, "w": 0.1337, "h": 0.0260},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.3850, "y": 0.2290, "w": 0.0439, "h": 0.0226},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0181},
]

POPUP_26 = [
    {"text": 'AAA Furbobo Weekly Wholesale Requests', "confidence": 1.0000,
     "x": 0.3387, "y": 0.7778, "w": 0.2907, "h": 0.0287},
    {"text": 'Make Furbobo Weekly Great Again!', "confidence": 1.0000,
     "x": 0.3414, "y": 0.7517, "w": 0.1878, "h": 0.0263},
    {"text": 'suspected related forum page', "confidence": 1.0000,
     "x": 0.3983, "y": 0.7028, "w": 0.1875, "h": 0.0233},
    {"text": 'found: "FurboCart"-)', "confidence": 1.0000,
     "x": 0.3953, "y": 0.6667, "w": 0.1337, "h": 0.0259},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.3866, "y": 0.6047, "w": 0.0436, "h": 0.0181},
    {"text": 'iStock as pictured! Price', "confidence": 1.0000,
     "x": 0.3952, "y": 0.5538, "w": 0.1558, "h": 0.0303},
    {"text": 'adjustments: Joolyon +5,', "confidence": 1.0000,
     "x": 0.3968, "y": 0.5167, "w": 0.1570, "h": 0.0315},
    {"text": 'Paraprince +2, Furblix +1, Furli +1,', "confidence": 1.0000,
     "x": 0.3968, "y": 0.4832, "w": 0.2195, "h": 0.0288},
    {"text": 'Furbulitzer +0, Bruce Furlee &', "confidence": 1.0000,
     "x": 0.3953, "y": 0.4470, "w": 0.1919, "h": 0.0284},
    {"text": 'Tiger Furlee -3, Furbricato -4,', "confidence": 1.0000,
     "x": 0.3953, "y": 0.4109, "w": 0.1919, "h": 0.0284},
    {"text": 'Gemibo - 2"', "confidence": 1.0000,
     "x": 0.3953, "y": 0.3792, "w": 0.0729, "h": 0.0255},
    {"text": 'What do these numbers mean?', "confidence": 1.0000,
     "x": 0.4041, "y": 0.2556, "w": 0.1933, "h": 0.0213},
    {"text": "A secret society's secret code.", "confidence": 1.0000,
     "x": 0.4041, "y": 0.1935, "w": 0.1919, "h": 0.0235},
    {"text": 'Scroll', "confidence": 1.0000,
     "x": 0.5465, "y": 0.1318, "w": 0.0349, "h": 0.0233},
    {"text": 'Select', "confidence": 1.0000,
     "x": 0.6245, "y": 0.1302, "w": 0.0388, "h": 0.0256},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0187, "y": 0.0153, "w": 0.0672, "h": 0.0209},
]

POPUP_49 = [
    {"text": 'AAA Furbobo Weekly Wholesale Requests', "confidence": 1.0000,
     "x": 0.3387, "y": 0.7778, "w": 0.2907, "h": 0.0287},
    {"text": 'Make Furbobo Weekly Great Again!', "confidence": 1.0000,
     "x": 0.3414, "y": 0.7511, "w": 0.1878, "h": 0.0295},
    {"text": 'wnat these numbers mean. Mignt', "confidence": 1.0000,
     "x": 0.3983, "y": 0.7259, "w": 0.2078, "h": 0.0185},
    {"text": 'involve specialized jargon from', "confidence": 1.0000,
     "x": 0.3952, "y": 0.6857, "w": 0.1980, "h": 0.0325},
    {"text": 'another subculture...)', "confidence": 1.0000,
     "x": 0.3968, "y": 0.6537, "w": 0.1337, "h": 0.0259},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.3849, "y": 0.5883, "w": 0.0443, "h": 0.0233},
    {"text": 'There is a high likelihood the', "confidence": 1.0000,
     "x": 0.3967, "y": 0.5410, "w": 0.1819, "h": 0.0301},
    {"text": 'numbers represent "LOVE" (1043)!', "confidence": 1.0000,
     "x": 0.3967, "y": 0.5075, "w": 0.2154, "h": 0.0310},
    {"text": 'Furli', "confidence": 1.0000,
     "x": 0.3852, "y": 0.4470, "w": 0.0291, "h": 0.0207},
    {"text": 'Well well, if you ask me, someone', "confidence": 1.0000,
     "x": 0.3966, "y": 0.3960, "w": 0.2140, "h": 0.0324},
    {"text": 'might be secretly pulling the', "confidence": 1.0000,
     "x": 0.3953, "y": 0.3618, "w": 0.1817, "h": 0.0284},
    {"text": 'strings on this whole presidential', "confidence": 1.0000,
     "x": 0.3968, "y": 0.3278, "w": 0.2093, "h": 0.0262},
    {"text": 'election~', "confidence": 1.0000,
     "x": 0.3968, "y": 0.2944, "w": 0.0582, "h": 0.0237},
    {"text": 'Ebby', "confidence": 1.0000,
     "x": 0.5677, "y": 0.2288, "w": 0.0287, "h": 0.0220},
    {"text": 'UID: 603150536', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0181, "w": 0.0669, "h": 0.0155},
]

OFFICE_79 = [
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.2500, "y": 0.2478, "w": 0.0480, "h": 0.0237},
    {"text": "Gemibo has the president's plan all figured out: Infiltrate the", "confidence": 1.0000,
     "x": 0.2907, "y": 0.1757, "w": 0.4084, "h": 0.0284},
    {"text": 'group-buy chat and trace the merch orders back to their', "confidence": 1.0000,
     "x": 0.3023, "y": 0.1444, "w": 0.3852, "h": 0.0287},
    {"text": 'source.', "confidence": 1.0000,
     "x": 0.4709, "y": 0.1134, "w": 0.0510, "h": 0.0213},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0155},
    {"text": 'Continue', "confidence": 1.0000,
     "x": 0.9273, "y": 0.0152, "w": 0.0495, "h": 0.0187},
]

OFFICE_352 = [
    {"text": 'Joolyon', "confidence": 0.5000,
     "x": 0.2482, "y": 0.2452, "w": 0.0515, "h": 0.0248},
    {"text": 'I also came clean to everyone in the Furlysiae about my', "confidence": 1.0000,
     "x": 0.3037, "y": 0.1763, "w": 0.3809, "h": 0.0306},
    {"text": "true identity... Turns out, they'd already figured it out a long", "confidence": 1.0000,
     "x": 0.2907, "y": 0.1417, "w": 0.4055, "h": 0.0315},
    {"text": 'time ago.', "confidence": 1.0000,
     "x": 0.4620, "y": 0.1117, "w": 0.0672, "h": 0.0241},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0181, "w": 0.0669, "h": 0.0155},
    {"text": 'Continue', "confidence": 1.0000,
     "x": 0.9273, "y": 0.0155, "w": 0.0494, "h": 0.0181},
]

PRESS_424 = [
    {"text": 'Furbobocom', "confidence": 0.5000,
     "x": 0.0536, "y": 0.9402, "w": 0.0629, "h": 0.0189},
    {"text": 'Press Affairs', "confidence": 1.0000,
     "x": 0.0521, "y": 0.9093, "w": 0.0862, "h": 0.0281},
    {"text": 'Complete operation to obtain', "confidence": 1.0000,
     "x": 0.0887, "y": 0.7571, "w": 0.1265, "h": 0.0155},
    {"text": '×3', "confidence": 0.5000,
     "x": 0.2326, "y": 0.7545, "w": 0.0233, "h": 0.0233},
    {"text": 'Birth of a New Furbo President', "confidence": 1.0000,
     "x": 0.0378, "y": 0.7054, "w": 0.2762, "h": 0.0418},
    {"text": 'Furbo-cession: the battle for succession has', "confidence": 1.0000,
     "x": 0.0174, "y": 0.6407, "w": 0.2762, "h": 0.0208},
    {"text": 'begun! Who will become the next successor and', "confidence": 1.0000,
     "x": 0.0174, "y": 0.6120, "w": 0.3009, "h": 0.0213},
    {"text": 'lead Furbobo Weekly into the future?', "confidence": 1.0000,
     "x": 0.0145, "y": 0.5814, "w": 0.2340, "h": 0.0260},
    {"text": 'Presidential Election Kickoff', "confidence": 1.0000,
     "x": 0.0538, "y": 0.5245, "w": 0.1759, "h": 0.0236},
    {"text": 'Push Campaign Preparations', "confidence": 1.0000,
     "x": 0.0538, "y": 0.4599, "w": 0.1802, "h": 0.0262},
    {"text": 'Push Campaign Preparations', "confidence": 1.0000,
     "x": 0.0538, "y": 0.3979, "w": 0.1817, "h": 0.0261},
    {"text": 'Presidential Election Venue', "confidence": 1.0000,
     "x": 0.0523, "y": 0.3407, "w": 0.1730, "h": 0.0236},
    {"text": 'A New Clue Incoming', "confidence": 1.0000,
     "x": 0.0900, "y": 0.1342, "w": 0.1572, "h": 0.0311},
    {"text": 'Q Investigation Review', "confidence": 1.0000,
     "x": 0.0102, "y": 0.0543, "w": 0.1497, "h": 0.0284},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0155},
    {"text": 'Furbo List', "confidence": 1.0000,
     "x": 0.4099, "y": 0.8295, "w": 0.0756, "h": 0.0233},
    {"text": 'Furbulitzer', "confidence": 1.0000,
     "x": 0.4344, "y": 0.7083, "w": 0.0731, "h": 0.0272},
    {"text": '• On Duty', "confidence": 1.0000,
     "x": 0.4374, "y": 0.6674, "w": 0.0686, "h": 0.0322},
    {"text": 'People are always', "confidence": 1.0000,
     "x": 0.3850, "y": 0.6118, "w": 0.0964, "h": 0.0242},
    {"text": "asking what's up with", "confidence": 1.0000,
     "x": 0.3852, "y": 0.5917, "w": 0.1134, "h": 0.0207},
    {"text": 'me and the president.', "confidence": 1.0000,
     "x": 0.3837, "y": 0.5685, "w": 0.1148, "h": 0.0207},
    {"text": 'My response? "Look at', "confidence": 1.0000,
     "x": 0.3823, "y": 0.5452, "w": 0.1221, "h": 0.0233},
    {"text": 'my colors. Enough', "confidence": 1.0000,
     "x": 0.3837, "y": 0.5245, "w": 0.0988, "h": 0.0236},
    {"text": 'Furblix', "confidence": 1.0000,
     "x": 0.4346, "y": 0.3747, "w": 0.0567, "h": 0.0284},
    {"text": '• On Duty', "confidence": 1.0000,
     "x": 0.4416, "y": 0.3342, "w": 0.0630, "h": 0.0245},
    {"text": 'Furblix fans have it', "confidence": 1.0000,
     "x": 0.3837, "y": 0.2765, "w": 0.1221, "h": 0.0235},
    {"text": "the best 'cos", "confidence": 1.0000,
     "x": 0.3851, "y": 0.2518, "w": 0.0816, "h": 0.0227},
    {"text": "Furblix's here all", "confidence": 1.0000,
     "x": 0.3823, "y": 0.2222, "w": 0.1090, "h": 0.0233},
    {"text": 'day-', "confidence": 1.0000,
     "x": 0.3837, "y": 0.1938, "w": 0.0291, "h": 0.0233},
    {"text": "Work needs to be more fun than this! Let's chat, President!", "confidence": 1.0000,
     "x": 0.6221, "y": 0.8656, "w": 0.2907, "h": 0.0181},
    {"text": 'Joolyon', "confidence": 0.5000,
     "x": 0.5855, "y": 0.7054, "w": 0.0601, "h": 0.0291},
    {"text": '• On Duty', "confidence": 1.0000,
     "x": 0.5893, "y": 0.6637, "w": 0.0671, "h": 0.0352},
    {"text": 'Last-minute', "confidence": 1.0000,
     "x": 0.5363, "y": 0.6150, "w": 0.0741, "h": 0.0181},
    {"text": 'requests handled', "confidence": 1.0000,
     "x": 0.5347, "y": 0.5806, "w": 0.1094, "h": 0.0274},
    {"text": 'with a sprinkle of', "confidence": 1.0000,
     "x": 0.5349, "y": 0.5556, "w": 0.1119, "h": 0.0259},
    {"text": 'mood swings.', "confidence": 1.0000,
     "x": 0.5349, "y": 0.5269, "w": 0.0872, "h": 0.0261},
    {"text": 'Paraprince', "confidence": 1.0000,
     "x": 0.7354, "y": 0.7076, "w": 0.0742, "h": 0.0292},
    {"text": '• On Duty', "confidence": 1.0000,
     "x": 0.7397, "y": 0.6678, "w": 0.0672, "h": 0.0313},
    {"text": 'Glued to my desk. A', "confidence": 1.0000,
     "x": 0.6890, "y": 0.6120, "w": 0.1163, "h": 0.0213},
    {"text": 'million times more', "confidence": 1.0000,
     "x": 0.6875, "y": 0.5889, "w": 0.1105, "h": 0.0213},
    {"text": 'committed than that', "confidence": 1.0000,
     "x": 0.6860, "y": 0.5607, "w": 0.1206, "h": 0.0235},
    {"text": 'lazy detective, boop!', "confidence": 1.0000,
     "x": 0.6846, "y": 0.5349, "w": 0.1235, "h": 0.0234},
    {"text": 'Furli', "confidence": 1.0000,
     "x": 0.8852, "y": 0.7106, "w": 0.0392, "h": 0.0258},
    {"text": '• On Duty', "confidence": 1.0000,
     "x": 0.8907, "y": 0.6677, "w": 0.0676, "h": 0.0280},
    {"text": 'I never clock out.', "confidence": 1.0000,
     "x": 0.8358, "y": 0.6072, "w": 0.1192, "h": 0.0261},
    {"text": 'The work never', "confidence": 1.0000,
     "x": 0.8372, "y": 0.5787, "w": 0.1076, "h": 0.0234},
    {"text": 'ends.', "confidence": 1.0000,
     "x": 0.8371, "y": 0.5487, "w": 0.0397, "h": 0.0255},
    {"text": 'Bruce Furlee &', "confidence": 1.0000,
     "x": 0.5858, "y": 0.3898, "w": 0.0698, "h": 0.0185},
    {"text": 'Tiger Furlee', "confidence": 1.0000,
     "x": 0.5857, "y": 0.3687, "w": 0.0583, "h": 0.0198},
    {"text": '• On Duty', "confidence": 1.0000,
     "x": 0.5899, "y": 0.3341, "w": 0.0658, "h": 0.0269},
    {"text": 'Working for Furbobo', "confidence": 1.0000,
     "x": 0.5349, "y": 0.2765, "w": 0.1090, "h": 0.0235},
    {"text": 'Weekly is my greatest', "confidence": 1.0000,
     "x": 0.5377, "y": 0.2563, "w": 0.1165, "h": 0.0229},
    {"text": 'blessing. (The furbo', "confidence": 1.0000,
     "x": 0.5349, "y": 0.2351, "w": 0.1061, "h": 0.0207},
    {"text": 'who cherishes their', "confidence": 1.0000,
     "x": 0.5349, "y": 0.2145, "w": 0.1047, "h": 0.0181},
    {"text": 'blessings is the', "confidence": 1.0000,
     "x": 0.5362, "y": 0.1897, "w": 0.0832, "h": 0.0224},
    {"text": 'Furbricato', "confidence": 1.0000,
     "x": 0.7369, "y": 0.3747, "w": 0.0727, "h": 0.0258},
    {"text": '• On Duty', "confidence": 1.0000,
     "x": 0.7406, "y": 0.3287, "w": 0.0669, "h": 0.0340},
    {"text": "&=('o* *))) Ugh,", "confidence": 0.5000,
     "x": 0.6860, "y": 0.2694, "w": 0.1049, "h": 0.0305},
    {"text": "I'm dead again~~", "confidence": 1.0000,
     "x": 0.6844, "y": 0.2389, "w": 0.1181, "h": 0.0301},
    {"text": 'Gemibo', "confidence": 0.5000,
     "x": 0.8881, "y": 0.3747, "w": 0.0581, "h": 0.0258},
    {"text": 'On Duty', "confidence": 1.0000,
     "x": 0.8997, "y": 0.3306, "w": 0.0581, "h": 0.0260},
    {"text": 'Maxed-out computing,', "confidence": 1.0000,
     "x": 0.8372, "y": 0.2787, "w": 0.1163, "h": 0.0185},
    {"text": 'razor-sharp writing.', "confidence": 1.0000,
     "x": 0.8372, "y": 0.2556, "w": 0.1076, "h": 0.0185},
    {"text": 'Name it, Ive got it.', "confidence": 1.0000,
     "x": 0.8372, "y": 0.2324, "w": 0.0988, "h": 0.0208},
    {"text": 'Except for', "confidence": 1.0000,
     "x": 0.8372, "y": 0.2117, "w": 0.0553, "h": 0.0210},
    {"text": 'resignations.', "confidence": 1.0000,
     "x": 0.8372, "y": 0.1912, "w": 0.0669, "h": 0.0155},
    {"text": 'Scroll', "confidence": 1.0000,
     "x": 0.8605, "y": 0.0129, "w": 0.0349, "h": 0.0207},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.9360, "y": 0.0151, "w": 0.0292, "h": 0.0189},
]

ARTICLE_2 = [
    {"text": 'Furbobocom', "confidence": 0.5000,
     "x": 0.0538, "y": 0.9432, "w": 0.0625, "h": 0.0155},
    {"text": 'Clue Investigation', "confidence": 1.0000,
     "x": 0.0538, "y": 0.9093, "w": 0.1105, "h": 0.0261},
    {"text": 'Clue Source', "confidence": 1.0000,
     "x": 0.2471, "y": 0.8450, "w": 0.0916, "h": 0.0258},
    {"text": 'Arcadian Morning Report', "confidence": 1.0000,
     "x": 0.2602, "y": 0.6898, "w": 0.1686, "h": 0.0259},
    {"text": 'Incoming Message', "confidence": 1.0000,
     "x": 0.2602, "y": 0.6611, "w": 0.1105, "h": 0.0241},
    {"text": '"Planarcadia Manufacturing Embraces \'Furbo Fever\'!"', "confidence": 1.0000,
     "x": 0.2122, "y": 0.5889, "w": 0.4157, "h": 0.0364},
    {"text": 'Recently, multiple manufacturing plants across Planarcadia have been', "confidence": 1.0000,
     "x": 0.2151, "y": 0.5452, "w": 0.5451, "h": 0.0310},
    {"text": 'flooded with massive orders of furbo-themed merch, spanning fan', "confidence": 1.0000,
     "x": 0.2137, "y": 0.5009, "w": 0.5145, "h": 0.0315},
    {"text": 'support items, badges, standees, plushies, and more. One factory', "confidence": 1.0000,
     "x": 0.2151, "y": 0.4574, "w": 0.5058, "h": 0.0336},
    {"text": 'manager admitted, "I had no idea furbos had this many fans." According', "confidence": 1.0000,
     "x": 0.2151, "y": 0.4134, "w": 0.5538, "h": 0.0388},
    {"text": 'to insiders, the phenomenon may be closely tied to the upcoming', "confidence": 1.0000,
     "x": 0.2136, "y": 0.3677, "w": 0.5045, "h": 0.0382},
    {"text": 'presidential election at Furbobo Weekly.', "confidence": 1.0000,
     "x": 0.2151, "y": 0.3278, "w": 0.3125, "h": 0.0315},
    {"text": 'Complete investigation to obtain € x1', "confidence": 1.0000,
     "x": 0.3749, "y": 0.1665, "w": 0.2487, "h": 0.0328},
    {"text": 'Forward to Work Chat', "confidence": 1.0000,
     "x": 0.4375, "y": 0.1137, "w": 0.1497, "h": 0.0261},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0155},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.9345, "y": 0.0151, "w": 0.0307, "h": 0.0189},
]

RESULTS_410 = [
    {"text": 'Furbobocom', "confidence": 0.5000,
     "x": 0.0538, "y": 0.9432, "w": 0.0625, "h": 0.0155},
    {"text": 'Clue Investigation', "confidence": 1.0000,
     "x": 0.0538, "y": 0.9093, "w": 0.1105, "h": 0.0261},
    {"text": 'Clue Source', "confidence": 1.0000,
     "x": 0.2471, "y": 0.8320, "w": 0.0916, "h": 0.0263},
    {"text": 'Furbo is busy...', "confidence": 1.0000,
     "x": 0.4431, "y": 0.8287, "w": 0.1153, "h": 0.0315},
    {"text": 'Joolyon', "confidence": 0.5000,
     "x": 0.1932, "y": 0.6866, "w": 0.0525, "h": 0.0272},
    {"text": "Even though Furlyon's cover was blown", "confidence": 1.0000,
     "x": 0.2063, "y": 0.6308, "w": 0.2982, "h": 0.0384},
    {"text": "and the votes don't count anymore, the", "confidence": 1.0000,
     "x": 0.2048, "y": 0.5886, "w": 0.2924, "h": 0.0359},
    {"text": 'Furlysiae will still support the furbos like', "confidence": 1.0000,
     "x": 0.2049, "y": 0.5500, "w": 0.3110, "h": 0.0288},
    {"text": 'always. Furlysiae © Group 9 is almost', "confidence": 1.0000,
     "x": 0.2049, "y": 0.5065, "w": 0.2907, "h": 0.0310},
    {"text": 'full, so join while you still can!', "confidence": 1.0000,
     "x": 0.2049, "y": 0.4625, "w": 0.2297, "h": 0.0310},
    {"text": 'Furbos are just so cute.', "confidence": 1.0000,
     "x": 0.2615, "y": 0.1819, "w": 0.1805, "h": 0.0327},
    {"text": 'Pick a different name next time', "confidence": 1.0000,
     "x": 0.2326, "y": 0.1163, "w": 0.2355, "h": 0.0258},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0155},
    {"text": 'Investigation Results', "confidence": 1.0000,
     "x": 0.6294, "y": 0.8398, "w": 0.1570, "h": 0.0310},
    {"text": 'Progress Report', "confidence": 1.0000,
     "x": 0.6337, "y": 0.6769, "w": 0.1337, "h": 0.0337},
    {"text": 'Plan Objective...', "confidence": 1.0000,
     "x": 0.6105, "y": 0.6202, "w": 0.1105, "h": 0.0284},
    {"text": '[Campaign Prep Progress: 1/2] New', "confidence": 1.0000,
     "x": 0.6308, "y": 0.5736, "w": 0.1584, "h": 0.0181},
    {"text": 'campaign rule announced! External', "confidence": 1.0000,
     "x": 0.6308, "y": 0.5556, "w": 0.1570, "h": 0.0185},
    {"text": 'popularity voting system canceled', "confidence": 1.0000,
     "x": 0.6308, "y": 0.5349, "w": 0.1512, "h": 0.0181},
    {"text": 'Bonus Reward.', "confidence": 1.0000,
     "x": 0.6119, "y": 0.4625, "w": 0.1047, "h": 0.0258},
    {"text": 'Furbobo Weekly is', "confidence": 1.0000,
     "x": 0.6308, "y": 0.4157, "w": 0.1090, "h": 0.0261},
    {"text": 'launching an official merch', "confidence": 1.0000,
     "x": 0.6294, "y": 0.3926, "w": 0.1613, "h": 0.0234},
    {"text": 'line!', "confidence": 1.0000,
     "x": 0.6294, "y": 0.3695, "w": 0.0291, "h": 0.0207},
    {"text": 'Furbobo Weekly announces', "confidence": 1.0000,
     "x": 0.6337, "y": 0.3023, "w": 0.1584, "h": 0.0208},
    {"text": 'Furbulitzer and Paraprince', "confidence": 1.0000,
     "x": 0.6307, "y": 0.2757, "w": 0.1586, "h": 0.0250},
    {"text": 'figurines!', "confidence": 1.0000,
     "x": 0.6293, "y": 0.2473, "w": 0.0598, "h": 0.0275},
    {"text": 'Gemibo now supports furbo', "confidence": 1.0000,
     "x": 0.6323, "y": 0.1704, "w": 0.1628, "h": 0.0234},
    {"text": 'fan message generation', "confidence": 1.0000,
     "x": 0.6308, "y": 0.1472, "w": 0.1410, "h": 0.0207},
    {"text": 'Confirm', "confidence": 1.0000,
     "x": 0.8575, "y": 0.0146, "w": 0.0453, "h": 0.0199},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.9360, "y": 0.0151, "w": 0.0292, "h": 0.0189},
]

RESULTS_414 = [
    {"text": 'Furbobocom', "confidence": 0.5000,
     "x": 0.0538, "y": 0.9432, "w": 0.0625, "h": 0.0155},
    {"text": 'Clue Investigation', "confidence": 1.0000,
     "x": 0.0538, "y": 0.9093, "w": 0.1105, "h": 0.0261},
    {"text": '0.0', "confidence": 1.0000,
     "x": 0.1555, "y": 0.6796, "w": 0.0203, "h": 0.0129},
    {"text": 'UID:603150536', "confidence": 1.0000,
     "x": 0.0189, "y": 0.0155, "w": 0.0669, "h": 0.0155},
    {"text": 'Clue Source', "confidence": 1.0000,
     "x": 0.2471, "y": 0.8320, "w": 0.0916, "h": 0.0263},
    {"text": 'Furbo is busy...', "confidence": 1.0000,
     "x": 0.4431, "y": 0.8287, "w": 0.1153, "h": 0.0315},
    {"text": 'Joolyon', "confidence": 0.5000,
     "x": 0.1932, "y": 0.6868, "w": 0.0525, "h": 0.0269},
    {"text": "Even though Furlyon's cover was blown", "confidence": 1.0000,
     "x": 0.2063, "y": 0.6335, "w": 0.2967, "h": 0.0355},
    {"text": "and the votes don't count anymore, the", "confidence": 1.0000,
     "x": 0.2048, "y": 0.5886, "w": 0.2924, "h": 0.0359},
    {"text": 'Furlysiae will still support the furbos like', "confidence": 1.0000,
     "x": 0.2049, "y": 0.5500, "w": 0.3110, "h": 0.0288},
    {"text": 'always. Furlysiae © Group 9 is almost', "confidence": 1.0000,
     "x": 0.2049, "y": 0.5065, "w": 0.2907, "h": 0.0310},
    {"text": 'full, so join while you still can!', "confidence": 1.0000,
     "x": 0.2049, "y": 0.4625, "w": 0.2311, "h": 0.0310},
    {"text": 'Ebby', "confidence": 1.0000,
     "x": 0.4651, "y": 0.3850, "w": 0.0334, "h": 0.0258},
    {"text": 'Liking furbos is just human nature.', "confidence": 1.0000,
     "x": 0.2224, "y": 0.3333, "w": 0.2645, "h": 0.0287},
    {"text": 'Investigation Concluded', "confidence": 1.0000,
     "x": 0.2762, "y": 0.2481, "w": 0.1395, "h": 0.0207},
    {"text": 'Investigation Results', "confidence": 1.0000,
     "x": 0.6294, "y": 0.8398, "w": 0.1570, "h": 0.0310},
    {"text": 'R1', "confidence": 0.5000,
     "x": 0.8009, "y": 0.8527, "w": 0.0116, "h": 0.0129},
    {"text": 'Progress Report', "confidence": 1.0000,
     "x": 0.6337, "y": 0.6769, "w": 0.1337, "h": 0.0337},
    {"text": 'Plan Objective...', "confidence": 1.0000,
     "x": 0.6105, "y": 0.6202, "w": 0.1090, "h": 0.0284},
    {"text": '[Campaign Prep Progress: 1/2] New', "confidence": 1.0000,
     "x": 0.6308, "y": 0.5736, "w": 0.1584, "h": 0.0181},
    {"text": 'campaign rule announced! External', "confidence": 1.0000,
     "x": 0.6308, "y": 0.5556, "w": 0.1570, "h": 0.0185},
    {"text": 'popularity voting system canceled', "confidence": 1.0000,
     "x": 0.6308, "y": 0.5349, "w": 0.1512, "h": 0.0181},
    {"text": 'Bonus Reward.', "confidence": 1.0000,
     "x": 0.6119, "y": 0.4625, "w": 0.1047, "h": 0.0258},
    {"text": 'Furbobo Weekly is', "confidence": 1.0000,
     "x": 0.6308, "y": 0.4157, "w": 0.1090, "h": 0.0261},
    {"text": 'launching an official merch', "confidence": 1.0000,
     "x": 0.6294, "y": 0.3926, "w": 0.1613, "h": 0.0234},
    {"text": 'line!', "confidence": 1.0000,
     "x": 0.6294, "y": 0.3695, "w": 0.0291, "h": 0.0207},
    {"text": 'Furbobo Weekly announces', "confidence": 1.0000,
     "x": 0.6337, "y": 0.3023, "w": 0.1584, "h": 0.0208},
    {"text": 'Furbulitzer and Paraprince', "confidence": 1.0000,
     "x": 0.6307, "y": 0.2757, "w": 0.1586, "h": 0.0250},
    {"text": 'figurines!', "confidence": 1.0000,
     "x": 0.6292, "y": 0.2466, "w": 0.0600, "h": 0.0287},
    {"text": 'Gemibo now supports furbo', "confidence": 1.0000,
     "x": 0.6323, "y": 0.1704, "w": 0.1613, "h": 0.0234},
    {"text": 'fan message generation', "confidence": 1.0000,
     "x": 0.6308, "y": 0.1472, "w": 0.1410, "h": 0.0207},
    {"text": 'Back', "confidence": 1.0000,
     "x": 0.9360, "y": 0.0151, "w": 0.0292, "h": 0.0189},
]


def test_clue_pane_reads_thread_in_sender_voices():
    msgs = HSR.classify_chat(CLUE_156)
    assert msgs == [
        ("Gemibo", 'Sent a join request using the group number in the '
                   '"FurboCart" post...'),
        ("Gemibo", "The group owner has set up an entry quiz: answer all "
                   "questions right to get in!"),
        ("Gemibo", "(Don't worry if you mess up. Gemibo's got your back.)"),
    ], msgs


def test_clue_pane_player_bubble_and_options():
    """The player's bubble whose label has scrolled off the top is a
    bubble already read — it was spoken under its label two frames
    earlier, and reading it again as the player made the replay say
    "That's me!" twice. The three quiz answers are reply options, each
    its own item under the player's name, after the thread."""
    msgs = HSR.classify_chat(CLUE_169)
    assert msgs == [
        ("Gemibo", "Bingo!"),
        ("Gemibo", "Q2: When's Joolyon's birthday on the Arcadian Calendar?"),
        (HSR.PLAYER_NAME, "March 25th"),
        (HSR.PLAYER_NAME, "January 24th"),
        (HSR.PLAYER_NAME, "Gemibo, I'll leave it to you."),
    ], msgs


def test_clue_pane_player_bubble_reads_as_the_player():
    """Under PLAYER_NAME, not the label's text: the label is the
    player's own name, already cast, and a bubble that read as "Ebby"
    while labelled and as the player once the label scrolled off was
    spoken twice (short texts dedupe on sender+text)."""
    msgs = HSR.classify_chat(CLUE_181)
    assert (HSR.PLAYER_NAME, "I got nothing. Gemibo, you're up!") in msgs, msgs
    assert msgs[-1] == (
        "Gemibo", 'You have chosen "paws off the keyboard": Joolyon\'s '
                  'birthday is March 25th.'), msgs


def test_clue_pane_clipped_top_row_drops_its_message():
    """The row half under the pane's top edge reads as garbage ('oput mio
    unrer em') — it must not become a message, nor a prefix of one. The
    avatar misreads ('0.0') sit left of the pane and are never rows."""
    msgs = HSR.classify_chat(CLUE_248)
    assert msgs == [
        ("Joolyon", "Which street do you wanna check out, President?"),
        (HSR.PLAYER_NAME, '"Archnemesis" Street.'),
        (HSR.PLAYER_NAME, '"Many Furbos" Street.'),
    ], msgs


def test_clue_pane_sender_switches_back_after_player():
    msgs = HSR.classify_chat(CLUE_292)
    assert msgs == [
        (HSR.PLAYER_NAME, "Nice one, Joolyon. Still playing dumb, huh?"),
        ("Joolyon", "P-President, what are you saying? I don't even know "
                    "how to play!"),
    ], msgs


def test_clue_pane_status_caption_reads_as_lone_option():
    """Documented trade: the status card's caption is centred like an
    option and reads as one. A rare talk-over beats a dropped lone
    option."""
    msgs = HSR.classify_chat(CLUE_336)
    assert msgs[-1] == (HSR.PLAYER_NAME, "Furbo is on the way back..."), msgs


def test_clue_pane_is_never_dialogue():
    for frame in (CLUE_156, CLUE_169, CLUE_248, CLUE_336):
        state = HSR.classify(frame)
        assert state["speaker"] is None and not state["dialogue"] \
            and not state["choices"], state


def test_popup_reads_thread_with_left_aligned_player_rows():
    msgs = HSR.classify_chat(POPUP_19)
    # the top bubble's label is under the title rule: a message that
    # scrolled up there was read when it was whole
    assert msgs == [
        (HSR.PLAYER_NAME, "Who placed the order? Who's been quietly spoiling "
                          "our little furbos?"),
        ("Furbulitzer", "Not me"),
        ("Joolyon", "N-Not me!"),
    ], msgs


def test_popup_clipped_top_row_drops_its_message():
    """'vino placed the order: vino s been' is the first row of a message
    sliding under the title rule: dropped whole, not read as garbage."""
    msgs = HSR.classify_chat(POPUP_22)
    assert msgs[0] == ("Furbulitzer", "Not me"), msgs
    assert not any("vino" in t for _, t in msgs), msgs


def test_popup_options_only_with_hints_and_hints_never_read():
    msgs = HSR.classify_chat(POPUP_26)
    assert msgs[-2:] == [
        (HSR.PLAYER_NAME, "What do these numbers mean?"),
        (HSR.PLAYER_NAME, "A secret society's secret code."),
    ], msgs
    assert not any("Scroll" in t or "Select" in t for _, t in msgs), msgs
    # same rows with the hints gone: a message still typing, no options
    quiet = [b for b in POPUP_26 if b["text"] not in ("Scroll", "Select")]
    assert not any(s == HSR.PLAYER_NAME for s, _ in HSR.classify_chat(quiet))


def test_popup_player_label_is_not_an_option():
    """'Ebby' shares the options' right edge; its width is what keeps it
    a label, and a label with nothing under it reads nothing. The
    unlabelled rows at the top are the tail of a message whose label has
    scrolled under the rule — read before, dropped now."""
    msgs = HSR.classify_chat(POPUP_49)
    assert msgs == [
        ("Gemibo", 'There is a high likelihood the numbers represent '
                   '"LOVE" (1043)!'),
        ("Furli", "Well well, if you ask me, someone might be secretly "
                  "pulling the strings on this whole presidential election~"),
    ], msgs


def test_popup_is_never_dialogue():
    for frame in (POPUP_19, POPUP_26, POPUP_49):
        state = HSR.classify(frame)
        assert state["speaker"] is None and not state["dialogue"], state


def test_popup_needs_a_label_on_a_column():
    """A left-aligned title at the popup's spot with no sender or player
    label under it is some other modal, not a chat."""
    no_labels = [b for b in POPUP_49
                 if b["text"] not in ("Gemibo", "Furli", "Ebby")]
    assert HSR.classify_chat(no_labels) is None


def test_office_scene_left_corner_plate():
    for frame, who in ((OFFICE_79, "Gemibo"), (OFFICE_352, "Joolyon")):
        state = HSR.classify(frame)
        assert state["speaker"] == who, state
        assert state["dialogue"].startswith(
            {"Gemibo": "Gemibo has the president's plan",
             "Joolyon": "I also came clean"}[who]), state
        assert state["boxes"][0]["text"] == who


def test_office_plate_needs_story_chrome():
    """Without the ✕ Continue hint the left reach of the plate band is
    just any text: the line falls to the narrator as before."""
    no_hint = [b for b in OFFICE_79 if b["text"] != "Continue"]
    assert HSR.classify(no_hint)["speaker"] is None


def test_clue_source_article_is_read_by_the_reader():
    """The clipping goes through the reading-panel path, title first,
    without its "Incoming Message" chip, the reward line or the Forward
    button — and is not a chat screen."""
    rows = HSR.classify_quickread(ARTICLE_2)
    assert rows[:2] == ["Arcadian Morning Report",
                        '"Planarcadia Manufacturing Embraces \'Furbo Fever\'!"'], rows
    assert rows[-1] == "presidential election at Furbobo Weekly.", rows
    assert not any("Forward" in r or "obtain" in r or "Incoming" in r
                   for r in rows), rows
    assert HSR.classify_quickread(CLUE_156) is None


def test_results_screen_reads_the_half_pane_only():
    """The Progress Report column on the right ends on the full pane's
    player column and was read as the player ("Furbobo Weekly is"); the
    shrunken thread on the left reads at its own columns, options and
    the "Investigation Concluded" notice left out."""
    msgs = HSR.classify_chat(RESULTS_410)
    assert msgs == [
        ("Joolyon", "Even though Furlyon's cover was blown and the votes "
                    "don't count anymore, the Furlysiae will still support "
                    "the furbos like always. Furlysiae © Group 9 is almost "
                    "full, so join while you still can!"),
    ], msgs
    msgs = HSR.classify_chat(RESULTS_414)
    assert msgs[-1] == (HSR.PLAYER_NAME,
                        "Liking furbos is just human nature."), msgs
    assert not any("Weekly" in t or "Concluded" in t for _, t in msgs), msgs
    # the screen animates in: the report column can be readable a frame
    # before its header is, and that frame read the column as the player
    no_header = [b for b in RESULTS_410
                 if b["text"] != "Investigation Results"]
    msgs = HSR.classify_chat(no_header)
    assert msgs and not any("Weekly" in t for _, t in msgs), msgs


def test_press_affairs_is_a_menu():
    state = HSR.classify(PRESS_424)
    assert state == {"speaker": None, "dialogue": "", "choices": [],
                     "boxes": [], "conf": 1.0}, state
    assert HSR.classify_chat(PRESS_424) is None


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
