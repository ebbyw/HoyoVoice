"""Replay backend: feeds a pre-extracted session recording through the REAL
orchestrator — actual stabilization, dedupe, VAD gate, yield, and OCR daemon
— with only capture, TTS, and playback simulated. Selected via
HOYOVOICE_BACKEND=replay; driven by tools/replay.py.

Env contract (set by the driver):
    HOYOVOICE_REPLAY_DIR   dir containing frames/f_%06d.jpg (at SAMPLE_FPS)
                           and audio.pcm (48k stereo s16le)
    HOYOVOICE_STATE_DIR    disposable state dir (live.py honors this)
    HOYOVOICE_SYNTH_MS     simulated TTS latency (default 900)

Timing is wall-clock (a 2-minute clip replays in 2 minutes) so every
production code path behaves exactly as it does live. When both streams are
exhausted the process prints '[replay complete]' and exits.

Caveat: recordings mux OUR TTS into the audio bed (+8dB), so the gate
"hears" any TTS the original session spoke. Interpret gate decisions in
windows right after an original spoken line accordingly.
"""
import os
import threading
import time
from pathlib import Path

from hv_platform.win32 import OcrDaemon      # same daemon, runs anywhere

REPLAY_DIR = Path(os.environ.get("HOYOVOICE_REPLAY_DIR", "/tmp/hv_replay"))
SYNTH_MS = int(os.environ.get("HOYOVOICE_SYNTH_MS", "900"))
SAMPLE_RATE = 48000
BYTES_PER_SEC = SAMPLE_RATE * 2 * 2

_done = {"video": False, "audio": False, "armed": False}


def _maybe_finish():
    if _done["video"] and _done["audio"] and not _done["armed"]:
        _done["armed"] = True

        def bye():
            time.sleep(12)               # let in-flight lines settle
            print("[replay complete]", flush=True)
            os._exit(0)
        threading.Thread(target=bye, daemon=True).start()


def list_devices():
    return ["replay"], ["replay"]


class VideoCapture:
    """Paces extracted frames into frame_path at sample_fps, atomically."""

    def __init__(self, devices, frame_path, sample_fps):
        self.frame = Path(frame_path)
        self.fps = sample_fps
        self.thread = None
        self.stop_flag = threading.Event()

    def restart(self, record_path=None):
        if self.thread and self.thread.is_alive():
            return                       # never restart a replay mid-flight
        if _done["video"]:
            # The clip is finished. live.py's stall watchdog fires ~10s
            # after the last frame; without this it replayed the whole clip
            # again, appending phantom reads to the transcript.
            return
        self.stop_flag.clear()
        self.frame.parent.mkdir(parents=True, exist_ok=True)
        frames = sorted((REPLAY_DIR / "frames").glob("*.jpg"))

        def run():
            t0 = time.monotonic()
            for i, f in enumerate(frames):
                target = t0 + i / self.fps
                delay = target - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                if self.stop_flag.is_set():
                    return
                tmp = self.frame.with_suffix(".tmp")
                tmp.write_bytes(f.read_bytes())
                os.replace(tmp, self.frame)
            _done["video"] = True
            _maybe_finish()
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    def finalize(self, timeout=8.0):
        pass

    @property
    def alive(self):
        return bool(self.thread and self.thread.is_alive()) or _done["video"]

    def kill(self):
        self.stop_flag.set()


class AudioCapture:
    """Streams audio.pcm into pcm_path in real time (contract: truncate on
    restart, append s16le 48k stereo)."""

    def __init__(self, devices, pcm_path):
        self.pcm = Path(pcm_path)
        self.thread = None
        self.stop_flag = threading.Event()

    def restart(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_flag.clear()
        self.pcm.parent.mkdir(parents=True, exist_ok=True)
        src = REPLAY_DIR / "audio.pcm"

        def run():
            data = src.read_bytes() if src.exists() else b""
            out = open(self.pcm, "wb", buffering=0)
            chunk = BYTES_PER_SEC // 20            # 50ms
            t0 = time.monotonic()
            pos = 0
            while pos < len(data) and not self.stop_flag.is_set():
                target = t0 + pos / BYTES_PER_SEC
                delay = target - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                out.write(data[pos:pos + chunk])
                pos += chunk
            out.close()
            _done["audio"] = True
            _maybe_finish()
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    @property
    def alive(self):
        return bool(self.thread and self.thread.is_alive()) or _done["audio"]

    def kill(self):
        self.stop_flag.set()


class Tts:
    """Deterministic fake: sleeps a realistic synth latency, returns silence
    sized like real speech (~15 chars/sec)."""

    def synth(self, text, voice, speed):
        import numpy as np
        time.sleep(SYNTH_MS / 1000)
        dur = max(0.6, len(text) / (15.0 * speed))
        return np.zeros(int(dur * 24000), dtype=np.float32)


class Player:
    """Tracks a playback deadline instead of making sound."""

    def __init__(self):
        self.deadline = 0.0

    def play(self, wav_path, audio=None, samplerate=24000):
        n = len(audio) if audio is not None else 0
        self.deadline = time.monotonic() + n / samplerate

    def stop(self):
        interrupted = self.playing
        self.deadline = 0.0
        return interrupted

    @property
    def playing(self):
        return time.monotonic() < self.deadline


def create_video_capture(devices, frame_path, sample_fps):
    return VideoCapture(devices, frame_path, sample_fps)


def create_audio_capture(devices, pcm_path):
    return AudioCapture(devices, pcm_path)


def create_ocr(root, custom_words):
    return OcrDaemon(root, custom_words)


def create_tts():
    return Tts()


def create_player():
    return Player()
