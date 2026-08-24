"""Pins the Genshin 6.x chat-panel detector (the Eye of Graeae's
"Messages" device).

A phone-style messaging UI over a topic sidebar. Before this detector the
sidebar topics fused into the messages and were skipped — or spoken: the
2026-08-23 17:56 session read one such fusion aloud and auto-cast
"completely lost it." and "them to you later." as speakers. The frames
here are shots #20 and #23 of that session, verbatim.

Shot #20 pins the basics: sidebar excluded, sender labels split from
message rows by left edge, the player's right-hanging reply read as their
own bubble ("Ebby"). Shot #23 pins the hard parts: both of its sender
labels came back garbled below MIN_CONF ("Vnisnown Sendi" 0.77,
"Unl nowwnS1" 0.56) so the messages under them inherit the previous NPC
sender rather than the player; the gap rule splits the label-less
bubbles; and the top message is the scrolled TAIL of one already read —
attributed to the header, and left for live.py's containment test to
suppress. Run directly or under pytest:

    python tools/test_genshin_chat.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from profiles import get_profile                # noqa: E402

GENSHIN = get_profile("genshin")

SHOT_20 = [
    {"text": "Messages from the Eye of", "confidence": 0.9824,
     "x": 0.1630, "y": 0.9296, "w": 0.1380, "h": 0.0269},
    {"text": "Graeae", "confidence": 0.9963,
     "x": 0.1625, "y": 0.9065, "w": 0.0401, "h": 0.0269},
    {"text": "Unknown Signal", "confidence": 0.9999,
     "x": 0.5573, "y": 0.8583, "w": 0.1089, "h": 0.0333},
    {"text": "Unknown Signal", "confidence": 0.9999,
     "x": 0.1609, "y": 0.8296, "w": 0.1026, "h": 0.0333},
    {"text": "Unknown Sender", "confidence": 0.9993,
     "x": 0.4161, "y": 0.8167, "w": 0.0844, "h": 0.0241},
    {"text": "Regarding the Snegurochka", "confidence": 0.9991,
     "x": 0.1620, "y": 0.7704, "w": 0.1469, "h": 0.0306},
    {"text": " \"cough* Hello? Do you copy? You should be able to hear what I'm", "confidence": 0.9741,
     "x": 0.4302, "y": 0.7778, "w": 0.3609, "h": 0.0278},
    {"text": "and their princess...", "confidence": 0.9171,
     "x": 0.1615, "y": 0.7491, "w": 0.1104, "h": 0.0269},
    {"text": "saying, I think.", "confidence": 0.9997,
     "x": 0.4271, "y": 0.7537, "w": 0.0823, "h": 0.0269},
    {"text": "Unknown Sender", "confidence": 0.9995,
     "x": 0.4156, "y": 0.7065, "w": 0.0859, "h": 0.0269},
    {"text": "About the firearms...", "confidence": 0.9865,
     "x": 0.1620, "y": 0.6861, "w": 0.1266, "h": 0.0315},
    {"text": "*sigh* Thanks for nothing, you two. I poured so much effort into", "confidence": 0.9750,
     "x": 0.4271, "y": 0.6685, "w": 0.3521, "h": 0.0287},
    {"text": "getting \"him\" out, even if in part... Only for you to send him right", "confidence": 0.9573,
     "x": 0.4271, "y": 0.6454, "w": 0.3536, "h": 0.0278},
    {"text": "Tell me about", "confidence": 0.9991,
     "x": 0.1620, "y": 0.6278, "w": 0.0859, "h": 0.0306},
    {"text": "back, as if nothing had happened. Pavlina almost won right there", "confidence": 0.9884,
     "x": 0.4276, "y": 0.6241, "w": 0.3521, "h": 0.0241},
    {"text": "Koshchei...", "confidence": 0.8879,
     "x": 0.1615, "y": 0.6000, "w": 0.0693, "h": 0.0370},
    {"text": "and then.", "confidence": 0.9709,
     "x": 0.4266, "y": 0.6019, "w": 0.0542, "h": 0.0241},
    {"text": "Tell me about Aksinya...", "confidence": 0.9825,
     "x": 0.1630, "y": 0.5435, "w": 0.1417, "h": 0.0306},
    {"text": "Ebby", "confidence": 0.9989,
     "x": 0.7818, "y": 0.5500, "w": 0.0312, "h": 0.0324},
    {"text": "Huh? Aksinya?", "confidence": 0.9995,
     "x": 0.7151, "y": 0.5120, "w": 0.0849, "h": 0.0333},
    {"text": "Regarding the reliefs", "confidence": 0.9992,
     "x": 0.1620, "y": 0.4843, "w": 0.1260, "h": 0.0296},
    {"text": "and the offering ritual...", "confidence": 0.9693,
     "x": 0.1615, "y": 0.4602, "w": 0.1432, "h": 0.0278},
    {"text": "Regarding fluctuations when", "confidence": 0.9941,
     "x": 0.1620, "y": 0.4222, "w": 0.1427, "h": 0.0241},
    {"text": "PrimeIce Constructs are", "confidence": 0.9777,
     "x": 0.1615, "y": 0.4028, "w": 0.1271, "h": 0.0231},
    {"text": "made...", "confidence": 0.9262,
     "x": 0.1599, "y": 0.3778, "w": 0.0427, "h": 0.0287},
    {"text": "Regarding trains...", "confidence": 0.9446,
     "x": 0.1615, "y": 0.3231, "w": 0.1146, "h": 0.0343},
    {"text": "About the Eye of", "confidence": 0.9724,
     "x": 0.1625, "y": 0.2694, "w": 0.1021, "h": 0.0278},
    {"text": "Graeae's mission.", "confidence": 0.9586,
     "x": 0.1620, "y": 0.2407, "w": 0.1156, "h": 0.0296},
    {"text": "Regarding Snezhnaya's", "confidence": 0.9890,
     "x": 0.1625, "y": 0.1944, "w": 0.1375, "h": 0.0296},
    {"text": "temperature levels...", "confidence": 0.9635,
     "x": 0.1620, "y": 0.1722, "w": 0.1255, "h": 0.0241},
    {"text": "Regarding the train's", "confidence": 0.9996,
     "x": 0.1625, "y": 0.1231, "w": 0.1266, "h": 0.0278},
    {"text": "new functions...", "confidence": 0.9737,
     "x": 0.1609, "y": 0.0972, "w": 0.1016, "h": 0.0296},
    {"text": "UID: 603275577", "confidence": 0.9688,
     "x": 0.8740, "y": 0.0028, "w": 0.0979, "h": 0.0241},
]

WANT_20 = [
    ("Unknown Sender",
     " \"cough* Hello? Do you copy? You should be able to hear what I'm"
     " saying, I think."),
    ("Unknown Sender",
     "*sigh* Thanks for nothing, you two. I poured so much effort into"
     " getting \"him\" out, even if in part... Only for you to send him right"
     " back, as if nothing had happened. Pavlina almost won right there"
     " and then."),
    ("Ebby", "Huh? Aksinya?"),
]

SHOT_23 = [
    {"text": "Messages from the Eye of", "confidence": 0.9950,
     "x": 0.1630, "y": 0.9296, "w": 0.1380, "h": 0.0269},
    {"text": "Graeae", "confidence": 0.9843,
     "x": 0.1620, "y": 0.9074, "w": 0.0406, "h": 0.0259},
    {"text": "Unknown Signal", "confidence": 0.9991,
     "x": 0.5573, "y": 0.8593, "w": 0.1089, "h": 0.0324},
    {"text": "Unknown Signal", "confidence": 0.9998,
     "x": 0.1604, "y": 0.8296, "w": 0.1031, "h": 0.0333},
    {"text": "getting \"him\" out, even if in part... Only for you to send him right", "confidence": 0.9804,
     "x": 0.4281, "y": 0.8306, "w": 0.3516, "h": 0.0241},
    {"text": "back, as if nothing had happened. Pavlina almost won right there", "confidence": 0.9921,
     "x": 0.4276, "y": 0.8083, "w": 0.3516, "h": 0.0231},
    {"text": "and then.", "confidence": 0.9992,
     "x": 0.4271, "y": 0.7861, "w": 0.0536, "h": 0.0241},
    {"text": "Regarding the Snegurochka", "confidence": 0.9899,
     "x": 0.1620, "y": 0.7713, "w": 0.1469, "h": 0.0296},
    {"text": "and their princess..", "confidence": 0.9456,
     "x": 0.1615, "y": 0.7491, "w": 0.1104, "h": 0.0269},
    {"text": "Ebby", "confidence": 0.9994,
     "x": 0.7823, "y": 0.7343, "w": 0.0307, "h": 0.0324},
    {"text": "Huh? Aksinya?", "confidence": 0.9995,
     "x": 0.7167, "y": 0.6963, "w": 0.0833, "h": 0.0315},
    {"text": "About the firearms..", "confidence": 0.9645,
     "x": 0.1620, "y": 0.6861, "w": 0.1266, "h": 0.0324},
    {"text": "Unknown Sender", "confidence": 0.9826,
     "x": 0.4167, "y": 0.6546, "w": 0.0844, "h": 0.0222},
    {"text": "Tell me about", "confidence": 0.9978,
     "x": 0.1620, "y": 0.6278, "w": 0.0859, "h": 0.0306},
    {"text": "Koshchei...", "confidence": 0.9297,
     "x": 0.1615, "y": 0.6000, "w": 0.0693, "h": 0.0370},
    {"text": "Hah. I am the creator of the Eye of Graeae, after all. I can still make", "confidence": 0.9924,
     "x": 0.4271, "y": 0.6148, "w": 0.3693, "h": 0.0259},
    {"text": "use of some of its functions.", "confidence": 0.9845,
     "x": 0.4271, "y": 0.5907, "w": 0.1573, "h": 0.0259},
    {"text": "Tell me about Aksinya...", "confidence": 0.9741,
     "x": 0.1635, "y": 0.5435, "w": 0.1417, "h": 0.0306},
    {"text": "Unknown Sender", "confidence": 0.9979,
     "x": 0.4161, "y": 0.5444, "w": 0.0849, "h": 0.0241},
    {"text": "..*sigh* It's been a while since we last met, eh, dear colleague? Don't", "confidence": 0.9831,
     "x": 0.4328, "y": 0.5065, "w": 0.3677, "h": 0.0269},
    {"text": "Regarding the reliefs", "confidence": 0.9995,
     "x": 0.1620, "y": 0.4852, "w": 0.1260, "h": 0.0278},
    {"text": "you think you're getting \"a bit too passionate\" right now?", "confidence": 0.9973,
     "x": 0.4281, "y": 0.4833, "w": 0.3089, "h": 0.0241},
    {"text": "and the offering ritual...", "confidence": 0.9561,
     "x": 0.1620, "y": 0.4593, "w": 0.1432, "h": 0.0278},
    {"text": "Unknown Sender", "confidence": 0.9994,
     "x": 0.4167, "y": 0.4343, "w": 0.0844, "h": 0.0269},
    {"text": "Regarding fluctuations when", "confidence": 0.9972,
     "x": 0.1615, "y": 0.4231, "w": 0.1427, "h": 0.0241},
    {"text": "PrimeIce Constructs are", "confidence": 0.9696,
     "x": 0.1615, "y": 0.4028, "w": 0.1271, "h": 0.0231},
    {"text": "Ah, sorry, that wasn't meant for you. I'm currently busy dealing", "confidence": 0.9875,
     "x": 0.4271, "y": 0.3963, "w": 0.3474, "h": 0.0287},
    {"text": "made...", "confidence": 0.8325,
     "x": 0.1599, "y": 0.3778, "w": 0.0427, "h": 0.0287},
    {"text": "with that crazy shrew... How tragic, Pavlina of the Snegovik. You've", "confidence": 0.9795,
     "x": 0.4281, "y": 0.3750, "w": 0.3661, "h": 0.0241},
    {"text": "completely lost it.", "confidence": 0.9998,
     "x": 0.4286, "y": 0.3528, "w": 0.0995, "h": 0.0213},
    {"text": "Regarding trains...", "confidence": 0.9338,
     "x": 0.1625, "y": 0.3269, "w": 0.1130, "h": 0.0278},
    {"text": "Vnisnown Sendi", "confidence": 0.7697,
     "x": 0.4182, "y": 0.3083, "w": 0.0766, "h": 0.0176},
    {"text": "About the Eye of", "confidence": 0.9911,
     "x": 0.1630, "y": 0.2694, "w": 0.1016, "h": 0.0278},
    {"text": "Her gaze is like Prime Ice, but her mind is like a powderkeg. A single", "confidence": 0.9911,
     "x": 0.4271, "y": 0.2648, "w": 0.3688, "h": 0.0287},
    {"text": "Graeae's mission", "confidence": 0.9831,
     "x": 0.1620, "y": 0.2407, "w": 0.1151, "h": 0.0306},
    {"text": "spark could set her off and destroy all around her.", "confidence": 0.9932,
     "x": 0.4266, "y": 0.2417, "w": 0.2786, "h": 0.0278},
    {"text": "Regarding Snezhnaya's", "confidence": 0.9766,
     "x": 0.1625, "y": 0.1944, "w": 0.1370, "h": 0.0296},
    {"text": "Unl nowwnS1", "confidence": 0.5580,
     "x": 0.4198, "y": 0.2009, "w": 0.0557, "h": 0.0157},
    {"text": "temperature levels...", "confidence": 0.9769,
     "x": 0.1625, "y": 0.1722, "w": 0.1255, "h": 0.0241},
    {"text": "In any case, I know what you're here for. We have the same goal.", "confidence": 0.9958,
     "x": 0.4271, "y": 0.1574, "w": 0.3500, "h": 0.0278},
    {"text": "Regarding the train's", "confidence": 0.9995,
     "x": 0.1625, "y": 0.1231, "w": 0.1266, "h": 0.0278},
    {"text": "new functions...", "confidence": 0.9215,
     "x": 0.1615, "y": 0.0972, "w": 0.1010, "h": 0.0296},
    {"text": "UID: 603275577", "confidence": 0.9691,
     "x": 0.8740, "y": 0.0028, "w": 0.0979, "h": 0.0241},
]

WANT_23 = [
    ("Unknown Signal",     # scrolled tail; live.py suppresses by containment
     "getting \"him\" out, even if in part... Only for you to send him right"
     " back, as if nothing had happened. Pavlina almost won right there"
     " and then."),
    ("Ebby", "Huh? Aksinya?"),
    ("Unknown Sender",
     "Hah. I am the creator of the Eye of Graeae, after all. I can still make"
     " use of some of its functions."),
    ("Unknown Sender",
     "..*sigh* It's been a while since we last met, eh, dear colleague? Don't"
     " you think you're getting \"a bit too passionate\" right now?"),
    ("Unknown Sender",
     "Ah, sorry, that wasn't meant for you. I'm currently busy dealing"
     " with that crazy shrew... How tragic, Pavlina of the Snegovik. You've"
     " completely lost it."),
    ("Unknown Sender",
     "Her gaze is like Prime Ice, but her mind is like a powderkeg. A single"
     " spark could set her off and destroy all around her."),
    ("Unknown Sender",
     "In any case, I know what you're here for. We have the same goal."),
]


def clipped(frame):
    """Shot #20 with the player's reply sunk to the clip edge — the frame a
    new message is still sliding in on. The label rides with it."""
    out = []
    for b in frame:
        b = dict(b)
        if b["text"] in ("Ebby", "Huh? Aksinya?"):
            b["y"] -= 0.40
        out.append(b)
    return out


def no_marker(frame):
    """The same panel without the device header: not a chat screen."""
    return [b for b in frame if not b["text"].startswith("Messages")]


CASES = [
    ("shot 20", SHOT_20, WANT_20),
    ("shot 23 (garbled labels, scrolled tail)", SHOT_23, WANT_23),
    ("clipped bottom message deferred", clipped(SHOT_20), WANT_20[:2]),
    ("no Messages header is not chat", no_marker(SHOT_20), None),
    ("empty frame", [], None),
]


def main():
    bad = 0
    for label, frame, want in CASES:
        got = GENSHIN.classify_chat(frame)
        if got != want:
            print(f"FAIL {label}:\n  want {want!r}\n  got  {got!r}")
            bad += 1
    print(f"{len(CASES) - bad}/{len(CASES)} ok")
    return 1 if bad else 0


def test_genshin_chat():
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())
