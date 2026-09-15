#!/usr/bin/env python3
"""A piece of text with nothing to pronounce must not take the session down.

    .venv/bin/python tools/test_empty_synth.py

On Windows a chat chunk kokoro-onnx could not phonemize raised
`ValueError: need at least one array to concatenate` out of create(); the
reading pump synthesizes on the orchestrator thread, so the process died
with it (traceback relayed 2026-09-14). Three layers now stand between
that text and a dead session, and each is pinned here without a model:

  * the Windows backend answers a rejected text with None — the contract
    the macOS backend already kept for a generate() that yields no segments;
  * Speech.synth never hands the runtime a sentence with no letter or
    digit in it, on either platform;
  * the inline callers (reader pump, choice reader) go through try_synth,
    which logs a failure the way the speculative thread does and returns
    no audio instead of raising.
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np                                        # noqa: E402

import live                                               # noqa: E402
from hv_platform import win32                             # noqa: E402


class RejectingKokoro:
    """kokoro_onnx.Kokoro on text that phonemizes to nothing: current
    builds raise a ValueError of their own, older ones let np.concatenate
    raise its — both are ValueError."""

    def create(self, text, voice, speed, lang):
        raise ValueError("need at least one array to concatenate")


class RecordingTts:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def synth(self, text, voice, speed):
        self.calls.append(text)
        if self.fail:
            raise ValueError("need at least one array to concatenate")
        return np.full(2400, 0.5, dtype="float32")


def make_speech(tts):
    sp = live.Speech.__new__(live.Speech)
    sp.np = np
    sp.tts = tts
    sp.sia = types.SimpleNamespace(polarity_scores=lambda t: {"compound": 0.0})
    sp._effects = {}
    return sp


def test_win32_returns_none_for_unpronounceable():
    tts = win32.Tts.__new__(win32.Tts)
    tts.np, tts.custom, tts.kokoro = np, {}, RejectingKokoro()
    assert tts.synth("…", "am_michael", 1.0) is None


def test_speech_skips_punctuation_only_sentences():
    tts = RecordingTts()
    sp = make_speech(tts)
    audio, _, _ = sp.synth("…", "am_michael")
    assert audio is None and tts.calls == [], tts.calls
    audio, _, _ = sp.synth('"', "am_michael")
    assert audio is None and tts.calls == [], tts.calls
    audio, _, _ = sp.synth("Go now. Run!", "am_michael")
    assert audio is not None and len(audio)
    assert tts.calls == ["Go now.", "Run!"], tts.calls


def test_try_synth_logs_and_returns_no_audio():
    saved = live.save_shot
    live.save_shot = lambda eid: None
    events_before = len(live.events)
    try:
        sp = make_speech(RecordingTts(fail=True))
        audio, speed, ms = sp.try_synth("Eye of Graeae", "Check the location.",
                                        "am_michael", 1.0)
    finally:
        live.save_shot = saved
    assert audio is None and speed is None and ms == 0
    new = list(live.events)[events_before:]
    assert len(new) == 1 and new[0]["action"].startswith("synth failed"), new
    assert new[0]["cls"] == "yield" and new[0]["speaker"] == "Eye of Graeae"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all passed")
