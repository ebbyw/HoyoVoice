"""Windows backend: DirectShow video (ffmpeg), WASAPI audio (sounddevice,
in-process), Windows OCR daemon (tools/ocrd_win.py), Kokoro via ONNX
Runtime (CPU), sounddevice playback.

Honors the same data contracts as the macOS backend (see base.py):
frame JPEG, 48 kHz stereo s16le PCM append-file, Vision-style normalized
bottom-left OCR coordinates, 24 kHz float32 TTS audio.

UNTESTED ON REAL HARDWARE YET — see plans/WINDOWS-TESTING.md.
"""
import json
import re
import subprocess
import sys
import threading
from pathlib import Path

SAMPLE_RATE = 48000
CHANNELS = 2
# hide child console windows (ffmpeg, OCR daemon) — without this, every
# subprocess of a windowless parent pops its own console
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _sd():
    import sounddevice
    return sounddevice


def _list_dshow_video():
    """Parse `ffmpeg -f dshow -list_devices` for video device names."""
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-f", "dshow",
         "-list_devices", "true", "-i", "dummy"],
        capture_output=True, text=True, creationflags=NO_WINDOW)
    vid = []
    section = None
    for line in p.stderr.splitlines():
        low = line.lower()
        if "directshow video devices" in low:
            section = "v"
            continue
        if "directshow audio devices" in low:
            section = "a"
            continue
        # newer ffmpeg tags each line instead of using section headers
        m = re.search(r'"([^"]+)"', line)
        if not m or "Alternative name" in line:
            continue
        if "(video)" in line or section == "v":
            vid.append(m.group(1))
    return vid


def _list_wasapi_inputs():
    """Audio inputs come from sounddevice (that's what AudioCapture opens),
    preferring the WASAPI host API's view of each device."""
    sd = _sd()
    names, seen = [], set()
    try:
        hostapis = list(sd.query_hostapis())
        wasapi = next((i for i, h in enumerate(hostapis)
                       if "wasapi" in h["name"].lower()), None)
    except Exception:
        wasapi = None
    for idx, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] < 1:
            continue
        if wasapi is not None and dev["hostapi"] != wasapi:
            continue
        if dev["name"] not in seen:
            seen.add(dev["name"])
            names.append(dev["name"])
    if not names:                       # fall back to every host API
        for dev in sd.query_devices():
            if dev["max_input_channels"] >= 1 and dev["name"] not in seen:
                seen.add(dev["name"])
                names.append(dev["name"])
    return names


def list_devices():
    return _list_dshow_video(), _list_wasapi_inputs()


class VideoCapture:
    def __init__(self, devices, frame_path, sample_fps):
        self.devices = devices          # live dict — reread on every spawn
        self.frame = frame_path
        self.fps = sample_fps
        self.proc = None

    def restart(self, record_path=None):
        self.kill()
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
               "-f", "dshow", "-rtbufsize", "256M",
               "-framerate", "30", "-video_size", "1920x1080",
               "-i", f"video={self.devices['video']}",
               "-map", "0:v", "-vf", f"fps={self.fps},scale=1920:-2",
               "-update", "1", "-atomic_writing", "1", "-y", str(self.frame)]
        if record_path:
            cmd += ["-map", "0:v", "-s", "1920x1080", "-r", "30",
                    "-c:v", "libx264", "-preset", "veryfast", "-b:v", "6M",
                    "-y", str(record_path)]
        # stdin pipe: 'q' is the only clean-shutdown channel on Windows
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
            creationflags=NO_WINDOW)

    def finalize(self, timeout=8.0):
        """No SIGINT on Windows — 'q' on stdin asks ffmpeg to finalize."""
        if self.proc is None:
            return
        if self.proc.poll() is None:
            try:
                self.proc.stdin.write(b"q\n")
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass
            try:
                self.proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None

    @property
    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def kill(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None


class AudioCapture:
    """In-process WASAPI capture appending s16le 48k stereo to pcm_path.

    Replaces sox: a sounddevice.InputStream callback writes straight to the
    file, so the byte-offset math used by the VAD tail-reader and the
    recording mux is preserved exactly. restart() truncates, like sox did.
    WASAPI auto_convert handles devices whose native rate isn't 48 kHz.
    """

    def __init__(self, devices, pcm_path):
        self.devices = devices
        self.pcm = pcm_path
        self.stream = None
        self.fh = None
        self.lock = threading.Lock()
        self._dead = False

    def _find_device(self):
        sd = _sd()
        want = (self.devices["audio"] or "").lower()
        best = None
        for idx, dev in enumerate(sd.query_devices()):
            if dev["max_input_channels"] < 1:
                continue
            if dev["name"].lower() == want:
                return idx, dev
            if best is None and want and want in dev["name"].lower():
                best = (idx, dev)
        if best:
            return best
        return None, None

    def restart(self):
        self.kill()
        sd = _sd()
        idx, dev = self._find_device()
        if idx is None:
            print(f"[audio] input device not found: "
                  f"{self.devices['audio']!r}", flush=True)
            self._dead = True
            return
        in_ch = min(CHANNELS, dev["max_input_channels"])
        self.fh = open(self.pcm, "wb", buffering=0)   # truncate, unbuffered
        self._dead = False

        def callback(indata, frames, t, status):
            # indata: int16 (frames, in_ch). Upmix mono; never block long.
            buf = indata
            if in_ch == 1:
                buf = indata.repeat(2, axis=1)
            with self.lock:
                if self.fh is not None:
                    try:
                        self.fh.write(buf.tobytes())
                    except OSError:
                        self._dead = True

        extra = None
        try:
            extra = sd.WasapiSettings(auto_convert=True)
        except (AttributeError, TypeError):
            pass                          # older sounddevice: try without
        try:
            self.stream = sd.InputStream(
                device=idx, samplerate=SAMPLE_RATE, channels=in_ch,
                dtype="int16", blocksize=1024, callback=callback,
                extra_settings=extra)
            self.stream.start()
        except Exception as e:
            print(f"[audio] failed to open {dev['name']!r}: {e}", flush=True)
            self._close_fh()
            self.stream = None
            self._dead = True

    def _close_fh(self):
        with self.lock:
            if self.fh is not None:
                try:
                    self.fh.close()
                except OSError:
                    pass
                self.fh = None

    @property
    def alive(self):
        return (self.stream is not None and self.stream.active
                and not self._dead)

    def kill(self):
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
        self._close_fh()


class OcrDaemon:
    """tools/ocrd_win.py subprocess — same line protocol as the mac daemon."""

    def __init__(self, root, custom_words):
        self.root = Path(root)
        self.custom_words = Path(custom_words)
        self.proc = None
        self._spawn()

    def _spawn(self):
        self.proc = subprocess.Popen(
            [sys.executable, str(self.root / "tools" / "ocrd_win.py"),
             str(self.custom_words)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1, creationflags=NO_WINDOW)

    def recognize(self, image_path):
        try:
            self.proc.stdin.write(str(image_path) + "\n")
            raw = self.proc.stdout.readline()
        except (BrokenPipeError, OSError):
            raw = ""
        if not raw:
            print("OCR daemon died — respawning", flush=True)
            self.kill()
            self._spawn()
            return None
        return json.loads(raw)

    def kill(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None


class Tts:
    """Kokoro-82M via kokoro-onnx on CPU (onnxruntime). Same voice IDs as
    the MLX runtime, so voices.json carries over unchanged. Model files are
    fetched by setup.ps1 into models/."""

    MODEL = "kokoro-v1.0.onnx"
    VOICES = "voices-v1.0.bin"

    def __init__(self):
        from kokoro_onnx import Kokoro
        import numpy as np
        self.np = np
        models = Path(__file__).resolve().parent.parent / "models"
        self.kokoro = Kokoro(str(models / self.MODEL),
                             str(models / self.VOICES))

    def synth(self, text, voice, speed):
        samples, sr = self.kokoro.create(text, voice=voice, speed=speed,
                                         lang="en-us")
        if samples is None or len(samples) == 0:
            return None
        audio = self.np.asarray(samples, dtype=self.np.float32)
        if sr != 24000:                  # contract: 24 kHz out
            n = int(len(audio) * 24000 / sr)
            audio = self.np.interp(
                self.np.linspace(0, len(audio) - 1, n),
                self.np.arange(len(audio)), audio).astype(self.np.float32)
        return audio


class Player:
    """sounddevice playback on the default output. sd.play/sd.stop keep a
    module-level stream; all calls happen on the orchestrator thread."""

    def __init__(self):
        self.sd = _sd()
        self._started = False

    def play(self, wav_path, audio=None, samplerate=24000):
        if audio is None:
            import soundfile as sf
            audio, samplerate = sf.read(str(wav_path), dtype="float32")
        self.sd.play(audio, samplerate)
        self._started = True

    def stop(self):
        interrupted = self.playing
        if self._started:
            self.sd.stop()
        self._started = False
        return interrupted

    @property
    def playing(self):
        if not self._started:
            return False
        try:
            stream = self.sd.get_stream()
            return stream.active
        except Exception:
            return False


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
