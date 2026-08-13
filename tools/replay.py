#!/usr/bin/env python3
"""Replay a session recording through the REAL HoyoVoice pipeline.

    python tools/replay.py recording.mp4 [--start 60] [--duration 90]
                           [--voices path/to/voices.json] [--keep]

Extracts frames (at the live SAMPLE_FPS) and the audio bed, then runs
live.py with the replay backend: real OCR daemon, real classification,
stabilization, dedupe, VAD gate and yield — only capture, TTS synthesis,
and playback are simulated. Output is live.py's normal log, plus a
DECISIONS summary parsed from the state dir afterwards.

State is hermetic: a throwaway state dir (casting seeded from
voices.example.json, or --voices for a copy of a real one) so replays
never touch real casting or dedupe state. Wall-clock paced: a 90s clip
takes 90s.

This is the debugging workhorse: any session recording becomes a
reproducible test case. Caveat: the recording's audio bed includes any
TTS the ORIGINAL session spoke (+8dB), so gate decisions immediately
after an originally-spoken line hear that TTS as if it were game audio.
"""
import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# keep in sync with SAMPLE_FPS in live.py — importing live here would run
# its module-level setup, so the literal is duplicated on purpose; a bump
# there without one here silently desyncs replay timing
SAMPLE_FPS = 6


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("recording")
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--duration", type=float, default=None)
    ap.add_argument("--voices", default=None,
                    help="seed casting from this voices.json (copied)")
    ap.add_argument("--game", default=None,
                    help="pin the layout profile (auto|hsr|genshin) instead "
                         "of letting the recording's chrome pick it")
    ap.add_argument("--keep", action="store_true",
                    help="keep the work/state dirs for inspection")
    ap.add_argument("--synth-ms", type=int, default=900)
    args = ap.parse_args()

    work = Path(tempfile.mkdtemp(prefix="hv_replay_"))
    state = work / "state"
    frames = work / "frames"
    frames.mkdir(parents=True)
    (state / "captures").mkdir(parents=True)

    if args.voices:
        shutil.copy(args.voices, state / "voices.json")
    if args.game:
        # live.py seeds voices.json from the example on first run, but the
        # game has to be set BEFORE it starts — write the file here instead
        src = Path(args.voices) if args.voices else ROOT / "voices.example.json"
        cfg = json.loads(src.read_text())
        cfg.setdefault("settings", {})["game"] = args.game
        (state / "voices.json").write_text(json.dumps(cfg, indent=2,
                                                      ensure_ascii=False))

    cut = ["-ss", str(args.start)]
    if args.duration:
        cut += ["-t", str(args.duration)]

    print(f"[replay] extracting {args.recording} -> {work}", flush=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", *cut,
                    "-i", args.recording,
                    "-vf", f"fps={SAMPLE_FPS},scale=1920:-2",
                    "-q:v", "3", str(frames / "f_%06d.jpg"), "-y"],
                   check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", *cut,
                    "-i", args.recording, "-vn",
                    "-ac", "2", "-ar", "48000",
                    "-f", "s16le", str(work / "audio.pcm"), "-y"],
                   check=True)
    n = len(list(frames.glob("*.jpg")))
    print(f"[replay] {n} frames ({n / SAMPLE_FPS:.0f}s) — replaying in real "
          "time", flush=True)

    env = dict(
        os.environ,
        HOYOVOICE_BACKEND="replay",
        HOYOVOICE_REPLAY_DIR=str(work),
        HOYOVOICE_STATE_DIR=str(state),
        HOYOVOICE_AUTORESUME="1",
        HOYOVOICE_SYNTH_MS=str(args.synth_ms),
        HOYOVOICE_PORT="18470",
        PYTHONUNBUFFERED="1",
    )
    proc = subprocess.Popen([sys.executable, str(ROOT / "live.py")],
                            env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    try:
        for line in proc.stdout:
            print("  |", line, end="", flush=True)
    except KeyboardInterrupt:
        proc.send_signal(signal.SIGTERM)
    proc.wait()

    cache = state / "captures" / "spoken_cache.json"
    if cache.exists():
        obj = json.loads(cache.read_text())
        print("\n[replay] voiced history:",
              json.dumps(obj.get("voiced_history", {})), flush=True)
    if args.keep:
        print(f"[replay] state kept at {work}")
    else:
        shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    main()
