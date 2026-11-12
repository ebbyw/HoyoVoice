"""Pins the audio-track layout of a saved recording — needs ffmpeg, no
capture hardware, ~2s.

The mix is track 1 and the only default, so a player that plays one track
plays what the session sounded like; the game audio and our own speech
follow as tracks titled "game" and "tts", and replay finds the game track
by that title. A real mux is run on synthetic inputs (a 3s test video, a
tone for the game, two short tones for the clips) and the file is probed,
because the filter graph is the part that breaks — a label typo is an
ffmpeg error, not a Python one.

    python tools/test_recording_tracks.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from live import RECORDING_TRACKS, mux_command                   # noqa: E402

FF = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
fails = []


def probe(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,duration:stream_tags=handler_name:"
         "stream_disposition=default", "-of", "json", str(path)],
        capture_output=True, text=True, check=True).stdout
    return [s for s in json.loads(out)["streams"]
            if s["codec_type"] == "audio"]


def rms(path, track, a, b):
    """RMS of one track between a and b seconds."""
    raw = subprocess.run(
        FF[:-1] + ["-ss", str(a), "-t", str(b - a), "-i", str(path),
                   "-map", f"0:a:{track}", "-ac", "1",
                   "-f", "s16le", "-"], capture_output=True, check=True).stdout
    x = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    return float(np.sqrt(np.mean(x ** 2))) if len(x) else 0.0


with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    raw = d / "raw.mkv"
    subprocess.run(FF + ["-f", "lavfi", "-i", "testsrc=size=320x180:rate=10",
                         "-t", "3", "-c:v", "libx264", str(raw)], check=True)
    game = d / "game.pcm"
    t = np.arange(3 * 48000) / 48000
    tone = (3000 * np.sin(2 * np.pi * 220 * t)).astype(np.int16)
    np.stack([tone, tone], axis=1).tofile(game)
    clips = []
    for k, start in enumerate((0.5, 1.8)):
        f = d / f"clip{k}.wav"
        subprocess.run(FF + ["-f", "lavfi", "-i",
                             "sine=frequency=880:duration=0.6",
                             "-ar", "24000", str(f)], check=True)
        clips.append({"file": str(f), "start": start, "end": start + 0.6})

    out = d / "three.mp4"
    r = subprocess.run(mux_command(raw, game, clips, out, 3.0),
                       capture_output=True, text=True)
    if r.returncode:
        fails.append(f"  3-track mux failed: {r.stderr.strip()[:300]}")
    else:
        a = probe(out)
        titles = tuple(s.get("tags", {}).get("handler_name") for s in a)
        if titles != RECORDING_TRACKS:
            fails.append(f"  track titles {titles}, want {RECORDING_TRACKS}")
        defaults = [s["disposition"]["default"] for s in a]
        if defaults != [1, 0, 0]:
            fails.append(f"  default dispositions {defaults}, want [1, 0, 0]")
        durs = [float(s.get("duration", 0)) for s in a]
        if max(durs) - min(durs) > 0.1:
            fails.append(f"  tracks don't line up end to end: {durs}")
        # before the first clip (0-0.4s): game and mix carry the game tone,
        # the tts track is silent. During it (0.6-1.0s): the tts track has
        # the clip, and the mix is louder than the game alone.
        quiet = [rms(out, k, 0.05, 0.4) for k in range(3)]
        busy = [rms(out, k, 0.6, 1.0) for k in range(3)]
        if not (quiet[1] > 500 and quiet[0] > 500 and quiet[2] < 50):
            fails.append(f"  before any clip: mix/game/tts rms {quiet}, "
                         "want game tone on mix and game, tts silent")
        if not (busy[2] > 500 and busy[0] > busy[1] > 500):
            fails.append(f"  during a clip: mix/game/tts rms {busy}, "
                         "want clip on tts and mix louder than game")

    one = d / "one.mp4"
    r = subprocess.run(mux_command(raw, game, [], one, 3.0),
                       capture_output=True, text=True)
    if r.returncode:
        fails.append(f"  no-clip mux failed: {r.stderr.strip()[:300]}")
    else:
        titles = [s.get("tags", {}).get("handler_name") for s in probe(one)]
        if titles != ["game"]:
            fails.append(f"  no-clip recording tracks {titles}, want ['game']")

if fails:
    print("FAIL test_recording_tracks")
    print("\n".join(fails))
    sys.exit(1)
print("ok test_recording_tracks")
