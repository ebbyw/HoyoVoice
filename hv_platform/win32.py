"""Windows backend: DirectShow video (ffmpeg), WASAPI audio (sounddevice,
in-process), Windows OCR daemon (tools/ocrd_win.py), Kokoro via ONNX
Runtime, sounddevice playback.

Honors the same data contracts as the macOS backend (see base.py):
frame JPEG, 48 kHz stereo s16le PCM append-file, Vision-style normalized
bottom-left OCR coordinates, 24 kHz float32 TTS audio.

Verified end to end on real hardware; see plans/WINDOWS-TESTING.md for
the checklist and the platform quirks this backend works around.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from glob import glob
from pathlib import Path

SAMPLE_RATE = 48000
CHANNELS = 2
# hide child console windows (ffmpeg, OCR daemon) — without this, every
# subprocess of a windowless parent pops its own console
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _dedupe_path(value):
    """Preserve order, drop repeats (case-insensitive, trailing-slash
    agnostic) — PATH is rebuilt more than once per process."""
    out, seen = [], set()
    for part in value.split(os.pathsep):
        p = part.strip()
        if not p:
            continue
        canon = p.rstrip("\\/").lower()
        if canon not in seen:
            seen.add(canon)
            out.append(p)
    return os.pathsep.join(out)


def _refresh_path_from_registry():
    """Rebuild PATH the way a fresh shell would (machine + user registry
    values). The launching shell often predates installer PATH edits —
    e.g. winget's ffmpeg — and stale PATHs otherwise follow us into every
    subprocess (WinError 2)."""
    import winreg
    parts = [os.environ.get("PATH", "")]
    for hive, key in (
            (winreg.HKEY_LOCAL_MACHINE,
             r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
            (winreg.HKEY_CURRENT_USER, r"Environment")):
        try:
            with winreg.OpenKey(hive, key) as k:
                val, _ = winreg.QueryValueEx(k, "Path")
                parts.append(os.path.expandvars(val))
        except OSError:
            pass
    os.environ["PATH"] = _dedupe_path(os.pathsep.join(p for p in parts if p))


_ffmpeg_path = {"p": None}


def ensure_ffmpeg():
    """Resolve 'ffmpeg' for this process; returns its path.

    Called lazily (not at import) so a missing ffmpeg surfaces as a clear
    message from the capture backend rather than an import-time traceback.
    The result is cached: capture restarts run on the watchdog path, and
    shutil.which() stats every PATH entry.
    """
    if _ffmpeg_path["p"]:
        return _ffmpeg_path["p"]
    ff = shutil.which("ffmpeg")
    if not ff:
        _refresh_path_from_registry()
        ff = shutil.which("ffmpeg")
    if not ff:
        local = os.environ.get("LOCALAPPDATA", "")
        for pat in (rf"{local}\Microsoft\WinGet\Links\ffmpeg.exe",
                    rf"{local}\Microsoft\WinGet\Packages"
                    rf"\Gyan.FFmpeg*\**\bin\ffmpeg.exe"):
            hits = glob(pat, recursive=True)
            if hits:
                os.environ["PATH"] = _dedupe_path(
                    os.path.dirname(hits[0]) + os.pathsep
                    + os.environ.get("PATH", ""))
                ff = hits[0]
                break
    if not ff:
        raise RuntimeError(
            "ffmpeg not found — run setup.ps1, or open a new terminal so "
            "PATH updates take effect")
    _ffmpeg_path["p"] = ff
    return ff


def _sd():
    import sounddevice
    return sounddevice


def _list_dshow_video():
    """Parse `ffmpeg -f dshow -list_devices` for video device names."""
    ensure_ffmpeg()
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


def _wasapi_hostapi(sd):
    try:
        return next((i for i, h in enumerate(sd.query_hostapis())
                     if "wasapi" in h["name"].lower()), None)
    except Exception:
        return None


def _ranked_devices(output=False):
    """Every input (or output) device, WASAPI entries first: sounddevice
    lists each physical device once per host API, and MME truncates names to
    ~31 chars ('Digital Audio Interface (Shado…'), which breaks matching."""
    sd = _sd()
    key = "max_output_channels" if output else "max_input_channels"
    wasapi = _wasapi_hostapi(sd)
    devs = [(i, d) for i, d in enumerate(sd.query_devices()) if d[key] >= 1]
    return ([(i, d) for i, d in devs if d["hostapi"] == wasapi]
            + [(i, d) for i, d in devs if d["hostapi"] != wasapi])


def _match_device(want, output=False):
    """Resolve a saved device NAME to a (index, info) pair — exact match
    first, then substring. (None, None) when nothing matches."""
    want = (want or "").strip().lower()
    if not want:
        return None, None
    ranked = _ranked_devices(output)
    for idx, dev in ranked:
        if dev["name"].strip().lower() == want:
            return idx, dev
    for idx, dev in ranked:
        if want in dev["name"].strip().lower():
            return idx, dev
    return None, None


def _list_names(output=False):
    """Device names for the dashboard pickers: WASAPI's view of each device
    only, so one physical device isn't listed once per host API. These are
    the names _match_device() has to accept back."""
    sd = _sd()
    wasapi = _wasapi_hostapi(sd)
    ranked = _ranked_devices(output)
    names, seen = [], set()
    for _, dev in ranked:
        if wasapi is not None and dev["hostapi"] != wasapi:
            continue
        if dev["name"] not in seen:
            seen.add(dev["name"])
            names.append(dev["name"])
    if not names:                       # fall back to every host API
        for _, dev in ranked:
            if dev["name"] not in seen:
                seen.add(dev["name"])
                names.append(dev["name"])
    return names


def list_devices():
    return _list_dshow_video(), _list_names(), _list_names(output=True)


class VideoCapture:
    def __init__(self, devices, frame_path, sample_fps):
        self.devices = devices          # live dict — reread on every spawn
        self.frame = frame_path
        self.fps = sample_fps
        self.proc = None

    def restart(self, record_path=None):
        self.kill()
        ensure_ffmpeg()
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

    RETRY_COOLDOWN = 5.0        # the watchdog polls every 30 ms — don't spam

    def __init__(self, devices, pcm_path):
        self.devices = devices
        self.pcm = pcm_path
        self.stream = None
        self.fh = None
        self.lock = threading.Lock()
        self._dead = False
        self._next_retry = 0.0
        self._last_want = None

    def _find_device(self):
        idx, dev = _match_device(self.devices["audio"])
        if idx is not None:
            return idx, dev
        print(f"[audio] no input matches {self.devices['audio']!r}. "
              "Available inputs:", flush=True)
        for _, d in _ranked_devices():
            print(f"[audio]   {d['name']!r}", flush=True)
        return None, None

    def restart(self):
        want = self.devices["audio"]
        if want != self._last_want:      # dashboard hot-swap: never defer
            self._next_retry = 0.0
        self._last_want = want
        if time.time() < self._next_retry:
            return
        self.kill()
        sd = _sd()
        idx, dev = self._find_device()
        if idx is None:
            self._dead = True
            self._next_retry = time.time() + self.RETRY_COOLDOWN
            return
        in_ch = min(CHANNELS, dev["max_input_channels"])
        self.fh = open(self.pcm, "wb", buffering=0)   # truncate, unbuffered
        self._dead = False
        self._rs_next = 0.0               # resampler phase (fallback mode)
        self._rs_tail = None              # last frame of the previous block

        def make_callback(sr_in):
            import numpy as np
            step = sr_in / SAMPLE_RATE    # input samples per output sample

            def callback(indata, frames, t, status):
                # indata: int16 (frames, in_ch). Upmix mono, resample if the
                # device couldn't open at 48k; never block long.
                buf = indata
                if in_ch == 1:
                    buf = buf.repeat(2, axis=1)
                if sr_in != SAMPLE_RATE:
                    # Prepend the previous block's last frame so interpolation
                    # is continuous across block boundaries — without it every
                    # boundary gets a small step discontinuity (audible as a
                    # faint tick, and the VAD sees it as broadband noise).
                    tail = self._rs_tail
                    if tail is None:
                        tail = buf[:1]
                    work = np.concatenate([tail, buf])
                    self._rs_tail = buf[-1:].copy()
                    n = len(work)
                    # Phase is measured from the start of `buf`, i.e. index 1
                    # of `work`. Stop at n-1: np.interp CLAMPS beyond the last
                    # sample, which flattens the tail and leaves a step at the
                    # next block's join. Positions past it belong to the next
                    # block, which prepends this block's final frame.
                    pos = np.arange(1.0 + self._rs_next, n - 1, step)
                    if not len(pos):
                        self._rs_next -= len(buf)
                        return
                    src = np.arange(n)
                    buf = np.stack(
                        [np.interp(pos, src, work[:, c]) for c in (0, 1)],
                        axis=1).astype(np.int16)
                    self._rs_next = pos[-1] + step - n
                with self.lock:
                    if self.fh is not None:
                        try:
                            self.fh.write(np.ascontiguousarray(buf).tobytes())
                        except OSError:
                            self._dead = True   # bool write: benign race
            return callback

        # WASAPI extra settings are REJECTED by other host APIs (-9984), so
        # only attach them when this device entry actually belongs to WASAPI.
        # Ladder: 48k (+wasapi auto-convert if applicable) → 48k plain →
        # device-native rate with software resampling to keep the 48k
        # stereo s16 PCM contract intact.
        is_wasapi = False
        try:
            hostapi = sd.query_hostapis(dev["hostapi"])
            is_wasapi = "wasapi" in hostapi["name"].lower()
        except Exception:
            pass
        extra = None
        if is_wasapi:
            try:
                extra = sd.WasapiSettings(auto_convert=True)
            except (AttributeError, TypeError):
                pass
        native = int(dev.get("default_samplerate") or SAMPLE_RATE)
        attempts = [(SAMPLE_RATE, extra)] if extra is not None else []
        attempts += [(SAMPLE_RATE, None)]
        if native != SAMPLE_RATE:
            attempts += [(native, None)]
        err = None
        for sr_in, ex in attempts:
            try:
                self.stream = sd.InputStream(
                    device=idx, samplerate=sr_in, channels=in_ch,
                    dtype="int16", blocksize=1024,
                    callback=make_callback(sr_in), extra_settings=ex)
                self.stream.start()
                self._next_retry = 0.0
                mode = ("wasapi-convert" if ex is not None else
                        "native" if sr_in == SAMPLE_RATE else
                        f"resampled from {sr_in}")
                print(f"[audio] capturing from {dev['name']!r} "
                      f"({in_ch}ch @ {SAMPLE_RATE}, {mode})", flush=True)
                return
            except Exception as e:
                err = e
                self.stream = None
        print(f"[audio] failed to open {dev['name']!r} "
              f"(tried {[a[0] for a in attempts]}): {err}", flush=True)
        self._close_fh()
        self._dead = True
        self._next_retry = time.time() + self.RETRY_COOLDOWN

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
        self.custom = {}                  # voice id → style array

    def register_voice(self, voice_id, path):
        """Installed voice packs: the packaged voices live inside
        voices-v1.0.bin (a read-only npz), so a new one can't be added to
        them — but kokoro-onnx's create() takes a style array as readily as
        a name, so the array is kept here and passed through instead."""
        try:
            import voicepack
        except ImportError:      # imported outside live.py, which adds tools/
            sys.path.insert(
                0, str(Path(__file__).resolve().parent.parent / "tools"))
            import voicepack
        self.custom[voice_id] = voicepack.normalize(voicepack.read(path))

    def forget_voice(self, voice_id):
        self.custom.pop(voice_id, None)

    def synth(self, text, voice, speed):
        voice = self.custom.get(voice, voice)
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
    """sounddevice playback on devices["output"] ("" = system default).
    sd.play/sd.stop keep a module-level stream; all calls happen on the
    orchestrator thread."""

    def __init__(self, devices=None):
        self.sd = _sd()
        self.devices = devices if devices is not None else {}
        self._started = False
        self._deadline = 0.0
        self._last_want = None           # name we last resolved
        self._index = None               # its device index (None = default)
        self._ok = True                  # last resolve found the device
        self._next_retry = 0.0

    # After a miss, keep speaking through the system default and re-check
    # only this often: query_devices() costs real time, and re-resolving on
    # every line would print the same complaint under every spoken line.
    RETRY_COOLDOWN = 10.0

    def _output_index(self):
        """Resolve the dashboard's output NAME to an index. Cached, because
        query_devices() is slow and indices shift when devices come and go —
        a dashboard change re-resolves at once, a failure after a cooldown."""
        want = (self.devices.get("output") or "").strip()
        if want == self._last_want:
            if self._ok:
                return self._index
            if time.monotonic() < self._next_retry:
                return None              # system default until the cooldown
        self._last_want = want
        self._index = None
        self._ok = True
        if want:
            idx, dev = _match_device(want, output=True)
            if idx is None:
                self._ok = False
                self._next_retry = time.monotonic() + self.RETRY_COOLDOWN
                print(f"[audio] no output matches {want!r} — using the "
                      "system default. Available outputs:", flush=True)
                for _, d in _ranked_devices(output=True):
                    print(f"[audio]   {d['name']!r}", flush=True)
            else:
                self._index = idx
                print(f"[audio] output → {dev['name']!r}", flush=True)
        else:
            print("[audio] output → system default", flush=True)
        return self._index

    def play(self, wav_path, audio=None, samplerate=24000):
        if audio is None:
            import soundfile as sf
            audio, samplerate = sf.read(str(wav_path), dtype="float32")
        idx = self._output_index()
        try:
            self.sd.play(audio, samplerate, device=idx)
        except Exception as exc:
            # device unplugged / exclusive-mode grab: fall back to the system
            # default rather than losing the line entirely
            print(f"[audio] output {self._last_want!r} failed ({exc}) — "
                  "falling back to the system default", flush=True)
            self._index = None
            self._ok = False
            self._next_retry = time.monotonic() + self.RETRY_COOLDOWN
            self.sd.play(audio, samplerate)
        self._started = True
        # We know exactly how long this audio runs. PortAudio reports a
        # stream INACTIVE as soon as the callback has handed over the last
        # frames, which on WASAPI happens well before the sound has finished
        # coming out — the caller then thought playback was idle, started the
        # next line, and cut this one off mid-sentence (chat reads were
        # audibly truncated). Sample count is the authority.
        self._deadline = time.monotonic() + len(audio) / float(samplerate)

    def stop(self):
        interrupted = self.playing
        if self._started:
            self.sd.stop()
        self._started = False
        self._deadline = 0.0
        return interrupted

    @property
    def playing(self):
        if not self._started:
            return False
        if time.monotonic() < self._deadline:
            return True
        # past the expected end: trust the device (it may still be draining)
        try:
            return bool(self.sd.get_stream().active)
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


def create_player(devices=None):
    return Player(devices)
