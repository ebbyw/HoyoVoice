"""macOS backend: AVFoundation video (ffmpeg), CoreAudio audio (sox),
Apple Vision OCR daemon, Kokoro via MLX, afplay playback.

This is a straight extraction of the platform code that used to live in
live.py — behavior is intentionally identical.
"""
import json
import re
import signal
import subprocess
from pathlib import Path


def list_devices():
    """Enumerate AVFoundation video + audio device names."""
    p = subprocess.run(
        ["ffmpeg", "-hide_banner", "-f", "avfoundation",
         "-list_devices", "true", "-i", ""],
        capture_output=True, text=True)
    vid, aud, section = [], [], None
    for line in p.stderr.splitlines():
        if "video devices" in line:
            section = "v"
            continue
        if "audio devices" in line:
            section = "a"
            continue
        m = re.search(r"\[\d+\] (.+)$", line)
        if m and section == "v":
            vid.append(m.group(1))
        elif m and section == "a":
            aud.append(m.group(1))
    return vid, aud


class VideoCapture:
    def __init__(self, devices, frame_path, sample_fps):
        self.devices = devices          # live dict — reread on every spawn
        self.frame = frame_path
        self.fps = sample_fps
        self.proc = None

    def restart(self, record_path=None):
        self.kill()
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
               "-f", "avfoundation", "-framerate", "30",
               "-video_size", "1920x1080",   # native mode: no 4K scaling load
               "-i", self.devices["video"],
               "-map", "0:v", "-vf", f"fps={self.fps},scale=1920:-2",
               "-update", "1", "-atomic_writing", "1", "-y", str(self.frame)]
        if record_path:
            cmd += ["-map", "0:v", "-s", "1920x1080", "-r", "30",
                    "-c:v", "h264_videotoolbox", "-b:v", "6M",
                    "-y", str(record_path)]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL)

    def finalize(self, timeout=8.0):
        """SIGINT gives ffmpeg a clean MKV finalize."""
        if self.proc is None:
            return
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)
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
    """Bit-perfect continuous audio capture via CoreAudio (sox truncates
    the PCM file on each spawn). Never route this through ffmpeg — its
    AVFoundation audio input drops ~12% of samples."""

    def __init__(self, devices, pcm_path):
        self.devices = devices
        self.pcm = pcm_path
        self.proc = None

    def restart(self):
        self.kill()
        self.proc = subprocess.Popen(
            ["sox", "-q", "--buffer", "4096",
             "-t", "coreaudio", self.devices["audio"],
             "-t", "raw", "-b", "16", "-e", "signed", "-c", "2",
             "-r", "48000", str(self.pcm)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @property
    def alive(self):
        return self.proc is not None and self.proc.poll() is None

    def kill(self):
        if self.proc is not None and self.proc.poll() is None:
            self.proc.kill()
        self.proc = None


class OcrDaemon:
    """Apple Vision daemon (tools/ocrd): image path in, JSON blocks out."""

    def __init__(self, root, custom_words):
        self.root = Path(root)
        self.custom_words = Path(custom_words)
        self.proc = None
        self._spawn()

    def _spawn(self):
        self.proc = subprocess.Popen(
            [str(self.root / "tools" / "ocrd"), str(self.custom_words)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            text=True, bufsize=1)

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
    """Kokoro-82M on the Apple Silicon GPU via mlx-audio."""

    def __init__(self):
        from mlx_audio.tts.generate import load_model
        import numpy as np
        self.np = np
        self.model = load_model("prince-canuma/Kokoro-82M")
        self.custom = {}                  # voice id → .safetensors path

    def register_voice(self, voice_id, path):
        """Installed voice packs: mlx-audio loads a voice straight from a
        path when it ends in .safetensors, so the id only has to be swapped
        for the path on the way into generate()."""
        self.custom[voice_id] = str(path)

    def forget_voice(self, voice_id):
        self.custom.pop(voice_id, None)

    def synth(self, text, voice, speed):
        voice = self.custom.get(voice, voice)
        segs = [self.np.array(r.audio) for r in
                self.model.generate(text, voice=voice, speed=speed,
                                    lang_code="a")]
        if not segs:
            return None
        return self.np.concatenate(segs)


class Player:
    """afplay subprocess playback."""

    def __init__(self):
        self.proc = None

    def play(self, wav_path, audio=None, samplerate=24000):
        self.proc = subprocess.Popen(["afplay", str(wav_path)])

    def stop(self):
        interrupted = self.proc is not None and self.proc.poll() is None
        if interrupted:
            self.proc.kill()
        self.proc = None
        return interrupted

    @property
    def playing(self):
        return self.proc is not None and self.proc.poll() is None


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
