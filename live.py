#!/usr/bin/env python3
"""HoyoVoice live loop v3 — VAD gate + web dashboard + sentiment delivery.

Run: .venv/bin/python live.py     (or ./hoyovoice.sh start)
Dashboard: http://127.0.0.1:8470
"""
import difflib
import json
import re
import queue
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from classify import (classify, classify_infoscreen, classify_loading,  # noqa: E402
                      classify_narration, classify_overlay,
                      classify_quickread, has_continue_hint,
                      narration_self_certain)
from vad import CHUNK, SileroVAD  # noqa: E402
from webui import start_webui  # noqa: E402

FRAME = ROOT / "captures" / "live_frame.jpg"
# Continuous 48k stereo s16le stream captured by sox via CoreAudio.
# ffmpeg's AVFoundation audio input drops ~12% of samples; sox is bit-perfect.
AUDIO_PCM = ROOT / "captures" / "game_audio_48k.pcm"
AUDIO_BYTES_PER_SEC = 48000 * 2 * 2   # 48k, stereo, s16
GAME_SLICE = ROOT / "captures" / "game_slice.pcm"
SHOTS = ROOT / "captures" / "shots"
SHOTS_KEEP = 300
WAV = ROOT / "tts_out" / "live.wav"
UNKNOWN_LOG = ROOT / "unknown_speakers.log"
SPOKEN_CACHE = ROOT / "captures" / "spoken_cache.json"
VOICES_PATH = ROOT / "voices.json"
if not VOICES_PATH.exists():                      # first run: seed from example
    import shutil
    shutil.copy(ROOT / "voices.example.json", VOICES_PATH)
VOICES = json.loads(VOICES_PATH.read_text())

REC_DIR = {"path": Path(VOICES.get("settings", {}).get(
    "recordings_dir", str(ROOT / "recordings"))).expanduser()}
CLIPS = ROOT / "captures" / "rec_clips"     # temp TTS clips, cleaned after mux

# Devices BY NAME — indices can shift (index 0 once became the Mac webcam!)
# Both selectable from the dashboard; persisted in voices.json settings.
DEVICES = {
    "video": VOICES.get("settings", {}).get("video_device", "ShadowCast 3"),
    "audio": VOICES.get("settings", {}).get("audio_device", "ShadowCast 3"),
}


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
SAMPLE_FPS = 6
STABLE_READS = 2
DEDUP_WINDOW = 3              # a line repeats only if it's within the last N messages
SHORT_LINE = 15               # short lines (normalized chars) may echo across speakers

VAD_THRESHOLD = 0.5
VAD_LOOKBACK = 2.0
VAD_WAIT = 0.2                # late VO beyond this is caught by the mid-play yield
VAD_MIN_HITS = 2
VAD_PEAK = 0.85               # a single decisive spike counts (robot voices
                              # register as brief spikes over a low floor)
# short/soft VO ("Which king?") peaks ~0.3 and never crosses 0.5 —
# sustained moderate probability also counts as voiced
VAD_WEAK_THRESHOLD = 0.25
VAD_WEAK_HITS = 8             # ~256ms of moderately speech-like audio

vad_history = deque(maxlen=400)
# per-block stereo energy: (t, mid_dB, side_dB). Game VO is center-panned
# (mid), music/ambience is wide (side) — a mid-only burst at line start is
# voiceover even when the VAD can't recognize the voice as speech.
energy_history = deque(maxlen=400)
ENERGY_MID_BURST = 7.0        # dB over pre-line baseline
ENERGY_MID_OVER_SIDE = 5.0    # mid must rise this much more than side
ENERGY_SIDE_FLAT = 2.5        # AND side must stay flat — music swells raise
                              # both channels; VO raises only the center

# --- shared state for the dashboard ---
events = deque(maxlen=200)
event_seq = {"n": 0}
recording = {"on": False, "t0": None, "clips": [], "raw": None}
record_request = {"want": None}
device_request = {"want": None}
unknown_speakers = set()
if UNKNOWN_LOG.exists():
    unknown_speakers.update(
        n.strip() for n in UNKNOWN_LOG.read_text().splitlines() if n.strip())
commands = queue.Queue()
observing = {"on": False}     # start paused — resume from the dashboard
stats = {"spoken": 0, "skipped_voiced": 0, "yielded": 0, "always_voiced": 0,
         "synth_ms": deque(maxlen=100), "ocr_ms": deque(maxlen=200),
         "started": time.time()}


def frame_is_dark():
    """True black narration screens sometimes show only a ▼ glyph and no
    Continue text — accept them by checking the frame is nearly all black."""
    try:
        from PIL import Image
        img = Image.open(FRAME).convert("L")
        img.thumbnail((48, 48))
        px = list(img.getdata())
        return sum(px) / len(px) < 28
    except Exception:
        return False


def save_shot(eid):
    """Downscaled screenshot of the current frame for the dashboard log."""
    try:
        from PIL import Image
        img = Image.open(FRAME)
        img.thumbnail((854, 854))       # ~480p, legible and small (~60 KB)
        SHOTS.mkdir(parents=True, exist_ok=True)
        img.save(SHOTS / f"{eid}.jpg", quality=68)
        for p in sorted(SHOTS.glob("*.jpg"),
                        key=lambda p: p.stat().st_mtime)[:-SHOTS_KEEP]:
            p.unlink()
        return True
    except Exception:
        return False


def add_event(action, cls, speaker=None, text="", voice=None, speed=None,
              can_replay=False, shot=False):
    event_seq["n"] += 1
    events.append({
        "id": event_seq["n"], "t": datetime.now().strftime("%H:%M:%S"),
        "speaker": speaker, "text": text[:160], "voice": voice,
        "speed": round(speed, 2) if speed else None,
        "action": action, "cls": cls, "can_replay": can_replay,
        "shot": shot and save_shot(event_seq["n"]),
    })
    return event_seq["n"]


def metrics():
    up = int(time.time() - stats["started"])
    synth = stats["synth_ms"]
    ocr = stats["ocr_ms"]
    mins = max(up / 60, 1e-6)
    now = time.monotonic()
    recent = [p for t, p in vad_history if t >= now - 3.0]
    return {
        "vad": (f"{len(recent)}ch max={max(recent):.2f}" if recent
                else "NO AUDIO"),
        "uptime": f"{up // 3600}h{(up % 3600) // 60:02d}m",
        "spoken": stats["spoken"],
        "skipped_voiced": stats["skipped_voiced"],
        "yielded": stats["yielded"],
        "synth_avg_ms": int(sum(synth) / len(synth)) if synth else 0,
        "ocr_avg_ms": int(sum(ocr) / len(ocr)) if ocr else 0,
        "lines_per_min": round(stats["spoken"] / mins, 1),
    }


def audio_thread():
    """Tail the 48k stereo PCM that sox appends to; downmix + decimate to
    16k mono chunks for the VAD. File writes never block on a consumer, so
    nothing here can cause capture drops. Handles truncation on respawn."""
    vad = SileroVAD(ROOT / "tools" / "silero_vad.onnx")
    import numpy as np
    BLOCK = CHUNK * 3 * 2 * 2   # 512@16k = 1536 stereo frames @48k = 6144 B
    warmup = 32
    fh, pos = None, 0
    while True:
        try:
            size = AUDIO_PCM.stat().st_size
        except FileNotFoundError:
            time.sleep(0.1)
            continue
        if fh is None:
            fh = open(AUDIO_PCM, "rb")
            pos = size          # join at the live edge
            fh.seek(pos)
            warmup = 32
        if size < pos:          # sox respawned and truncated the file
            fh.close()
            fh, pos = None, 0
            continue
        if size - pos < BLOCK:
            time.sleep(0.02)
            continue
        buf = fh.read(BLOCK)
        pos += len(buf)
        stereo = np.frombuffer(buf, dtype=np.int16).astype(np.float32)
        lr = stereo.reshape(-1, 2)
        mono48 = lr.mean(axis=1)
        mid_rms = float(np.sqrt(np.mean(mono48 ** 2))) + 1e-3
        side = (lr[:, 0] - lr[:, 1]) / 2
        side_rms = float(np.sqrt(np.mean(side ** 2))) + 1e-3
        energy_history.append((time.monotonic(),
                               20 * np.log10(mid_rms),
                               20 * np.log10(side_rms)))
        chunk = mono48.reshape(-1, 3).mean(axis=1) / 32768.0   # → 16k
        p = vad.prob(chunk.astype(np.float32))
        if warmup > 0:
            warmup -= 1
            continue
        vad_history.append((time.monotonic(), p))


def speech_hits(since, threshold=None):
    threshold = VAD_THRESHOLD if threshold is None else threshold
    return sum(1 for t, p in vad_history if t >= since and p >= threshold)


def is_voiced(since):
    strong = weak = 0
    peak = 0.0
    for t, p in vad_history:
        if t >= since:
            if p >= VAD_THRESHOLD:
                strong += 1
            if p >= VAD_WEAK_THRESHOLD:
                weak += 1
            peak = max(peak, p)
    return (strong >= VAD_MIN_HITS or peak >= VAD_PEAK
            or weak >= VAD_WEAK_HITS)


# Vision misreads capital I as lowercase l in the game font. Standalone "l"
# (and "lt"/"lts"/"lm"…) are never real words, so these repairs are safe.
_OCR_FIXES = [
    (re.compile(r"\bl\b"), "I"),          # also covers l'm / l've / l'll / l'd
    (re.compile(r"\blt\b"), "It"),
    (re.compile(r"\blts\b"), "Its"),
    (re.compile(r"\bi\b"), "I"),
]


def fix_ocr_text(s):
    for pat, rep in _OCR_FIXES:
        s = pat.sub(rep, s)
    # user lexicon for proper nouns OCR keeps mangling ("lason" → "Iason")
    for wrong, right in VOICES.get("settings", {}).get("text_fixes", {}).items():
        s = re.sub(rf"\b{re.escape(wrong)}\b", right, s, flags=re.IGNORECASE)
    return s


def center_burst(t_line):
    """(mid_delta_dB, side_delta_dB): energy rise after the line appeared vs
    the pre-line baseline. VO shows as mid rising with side staying flat."""
    base_m = [m for t, m, s in energy_history if t_line - 9 <= t < t_line - 1.5]
    base_s = [s for t, m, s in energy_history if t_line - 9 <= t < t_line - 1.5]
    cur = [(m, s) for t, m, s in energy_history if t >= t_line - 1.2]
    if len(base_m) < 30 or len(cur) < 8:
        return 0.0, 0.0
    base_m.sort()
    base_s.sort()
    bm, bs = base_m[len(base_m) // 2], base_s[len(base_s) // 2]
    mids = [m for m, s in cur]
    sides = [s for m, s in cur]

    def smooth_max(xs):
        return max(sum(xs[i:i + 5]) / 5 for i in range(max(1, len(xs) - 4)))

    return smooth_max(mids) - bm, smooth_max(sides) - bs


def normalize_text(s):
    return "".join(c for c in s.lower() if c.isalnum())


def normalize_speaker(speaker):
    """Normalize quote glyphs but KEEP quotes: a character literally named
    '"Narrator"' is distinct from true narration. Fuzzy-match only within the
    same quoting class so the two can't merge."""
    if not speaker:
        return None
    speaker = speaker.strip()
    for a, b in (("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'")):
        speaker = speaker.replace(a, b)
    quoted = len(speaker) >= 2 and speaker[0] == '"' and speaker[-1] == '"'
    known = [k for k in (list(VOICES["characters"].keys()) + ["Narrator"]
                         + VOICES.get("always_voiced", []))
             if (k.startswith('"') and k.endswith('"')) == quoted]
    m = difflib.get_close_matches(speaker, known, n=1, cutoff=0.8)
    return m[0] if m else speaker


# Auto-casting pools: each newly met character claims the next voice not
# already in use, so scenes with several new speakers stay distinguishable.
VOICE_POOLS = {
    "female": ["af_nova", "af_bella", "af_sarah", "af_sky", "bf_emma",
               "af_jessica", "af_kore", "af_aoede", "bf_alice", "bf_lily",
               "af_alloy"],
    "male": ["am_michael", "am_liam", "am_eric", "am_onyx", "am_puck",
             "bm_daniel", "bm_fable", "bm_lewis", "am_fenrir", "am_santa",
             "am_adam"],
}


def auto_cast(speaker, gender):
    used = {c["voice"] for c in VOICES["characters"].values()}
    used.update(VOICES["defaults"].values())
    pool = VOICE_POOLS[gender]
    voice = next((v for v in pool if v not in used), None)
    if voice is None:   # pool exhausted: reuse the least-assigned voice
        counts = {v: sum(1 for c in VOICES["characters"].values()
                         if c["voice"] == v) for v in pool}
        voice = min(pool, key=counts.get)
    VOICES["characters"][speaker] = {"voice": voice, "speed": 1.0, "auto": True}
    VOICES_PATH.write_text(json.dumps(VOICES, indent=2, ensure_ascii=False))
    print(f"[auto-cast] {speaker} → {voice} ({gender} guess)", flush=True)
    return voice


def pick_voice(speaker):
    # No nameplate, the game's own unquoted narrator label, or an
    # organization/location "speaker" ("The Xianzhou Alliance") → narrator.
    # Sentence fragments (misparsed screens) also go to narrator and are
    # never registered as characters.
    if (not speaker or speaker.lower() == "narrator"
            or speaker.startswith("The ")
            or len(speaker) > 30 or len(speaker.split()) > 4):
        return VOICES["defaults"]["narrator"], 1.0
    c = VOICES["characters"].get(speaker)
    if c:
        return c["voice"], c.get("speed", 1.0)
    with open(UNKNOWN_LOG, "a") as f:
        f.write(speaker + "\n")
    # best-effort gender guess from name shape, then claim a distinct voice;
    # shows as "(auto)" in Casting — override anytime
    n = speaker.rstrip('"”').strip().lower()
    fem = n.endswith(("a", "ia", "ie", "elle", "ette", "ina", "yn", "i"))
    return auto_cast(speaker, "female" if fem else "male"), 1.0


class Speech:
    """Owns the TTS model, sentiment analyzer, and playback process."""

    def __init__(self):
        from mlx_audio.tts.generate import load_model
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        import numpy as np
        import soundfile as sf
        self.np, self.sf = np, sf
        self.model = load_model("prince-canuma/Kokoro-82M")
        self.sia = SentimentIntensityAnalyzer()
        self.player = None
        self.t_play = None
        self.qr_playing = False

    def sentiment_speed(self, text):
        """Map sentiment to delivery pace: excited slightly faster, somber slower."""
        comp = self.sia.polarity_scores(text)["compound"]
        mult = 1.0 + 0.06 * comp
        if text.count("!") >= 1 and comp >= 0:
            mult += 0.03
        if "…" in text or "..." in text:
            mult -= 0.03
        return max(0.9, min(1.12, mult))

    def stop(self):
        interrupted = self.player and self.player.poll() is None
        if interrupted:
            self.player.kill()
        self.qr_playing = False
        # if a recorded clip was cut short (yield/interrupt), trim it in the mix
        if interrupted and recording["on"] and recording["clips"]:
            last = recording["clips"][-1]
            if last.get("end") is None:
                last["end"] = time.monotonic() - recording["t0"]
        self.t_play = None

    def synth(self, text, voice, base_speed=1.0):
        speed = round(base_speed * self.sentiment_speed(text), 3)
        t0 = time.time()
        segs = [self.np.array(r.audio) for r in
                self.model.generate(text, voice=voice, speed=speed,
                                    lang_code="a")]
        synth_ms = int((time.time() - t0) * 1000)
        if segs:
            stats["synth_ms"].append(synth_ms)
        return segs, speed, synth_ms

    def play(self, segs, qr=False):
        if not segs:
            return
        self.stop()
        self.qr_playing = qr
        audio = self.np.concatenate(segs)
        # trim Kokoro's silence padding: snappier starts, tight handoffs
        loud = self.np.where(self.np.abs(audio) > 0.012)[0]
        if len(loud):
            audio = audio[max(loud[0] - 800, 0):loud[-1] + 1600]
        self.sf.write(WAV, audio, 24000)
        self.player = subprocess.Popen(["afplay", str(WAV)])
        self.t_play = time.monotonic()
        if recording["on"]:
            CLIPS.mkdir(parents=True, exist_ok=True)
            offset = self.t_play - recording["t0"]
            clip = CLIPS / f"{len(recording['clips']):04d}.wav"
            import shutil
            shutil.copy(WAV, clip)
            recording["clips"].append(
                {"file": str(clip), "start": offset, "end": None})

    def say(self, text, voice, base_speed=1.0):
        segs, speed, synth_ms = self.synth(text, voice, base_speed)
        self.play(segs)
        return synth_ms, speed


def mux_recording(raw, clips, out, s0, s1):
    """Combine: video (ffmpeg mkv) + game audio (exact byte-slice of the sox
    stream between recording start/stop) + TTS clips at wall offsets."""
    # extract the game-audio slice
    n = 0
    with open(AUDIO_PCM, "rb") as src, open(GAME_SLICE, "wb") as dst:
        src.seek(s0)
        remaining = max(s1 - s0, 0)
        while remaining > 0:
            b = src.read(min(1 << 20, remaining))
            if not b:
                break
            dst.write(b)
            n += len(b)
            remaining -= len(b)
    print(f"[recording] game audio slice: {n / AUDIO_BYTES_PER_SEC:.1f}s; "
          f"muxing {len(clips)} TTS clips into {out}", flush=True)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
           "-i", str(raw),
           "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", str(GAME_SLICE)]
    for c in clips:
        cmd += ["-i", c["file"]]
    parts, labels = [], []
    for i, c in enumerate(clips, 2):        # clip inputs start at index 2
        trim = (f"atrim=0:{max(c['end'] - c['start'], 0.05):.3f},"
                if c.get("end") is not None else "")
        ms = int(c["start"] * 1000)
        parts.append(f"[{i}:a]{trim}aresample=48000,"
                     f"aformat=channel_layouts=stereo,"
                     f"volume=2.5,alimiter=limit=0.95,"   # Kokoro is quiet
                     f"adelay={ms}|{ms}[a{i}]")
        labels.append(f"[a{i}]")
    if clips:
        fc = (";".join(parts) + ";[1:a]" + "".join(labels)
              + f"amix=inputs={len(clips) + 1}:normalize=0[out]")
        cmd += ["-filter_complex", fc, "-map", "0:v", "-map", "[out]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "copy", "-c:a", "aac", "-y", str(out)]
    ok = subprocess.run(cmd, capture_output=True).returncode == 0
    if ok:
        Path(raw).unlink(missing_ok=True)
        GAME_SLICE.unlink(missing_ok=True)
        for c in clips:
            Path(c["file"]).unlink(missing_ok=True)
        add_event("recording saved", "spoken", None, Path(out).name)
    else:
        add_event("recording mux FAILED (raw kept)", "yield", None, Path(raw).name)
    print(f"[recording] mux {'ok' if ok else 'FAILED'}: {out}", flush=True)


def handle_commands(speech):
    """Dashboard actions: assign voice (+re-read), replay event, test speech."""
    while not commands.empty():
        cmd = commands.get_nowait()
        if cmd[0] == "assign":
            _, char, voice = cmd
            VOICES["characters"].setdefault(char, {})["voice"] = voice
            VOICES["characters"][char].setdefault("speed", 1.0)
            VOICES["characters"][char].pop("auto", None)   # now user-chosen
            VOICES_PATH.write_text(json.dumps(VOICES, indent=2, ensure_ascii=False))
            print(f"[cast] {char} → {voice}", flush=True)
            for e in reversed(events):
                if e["speaker"] == char and e["can_replay"]:
                    speech.say(e["text"], voice,
                               VOICES["characters"][char].get("speed", 1.0))
                    add_event("re-read", "spoken", char, e["text"], voice)
                    break
        elif cmd[0] == "replay":
            e = next((x for x in events if x["id"] == cmd[1]), None)
            if e and e["can_replay"]:
                voice, base = pick_voice(e["speaker"])
                speech.say(e["text"], voice, base)
                add_event("re-read", "spoken", e["speaker"], e["text"], voice)
        elif cmd[0] == "say":
            _, text, voice = cmd
            speech.say(text, voice)
            add_event("test", "spoken", None, text, voice)
        elif cmd[0] == "mute":
            _, char, muted = cmd
            av = VOICES.setdefault("always_voiced", [])
            if muted and char not in av:
                av.append(char)
            if not muted and char in av:
                av.remove(char)
            VOICES_PATH.write_text(json.dumps(VOICES, indent=2, ensure_ascii=False))
            print(f"[mute] {char} = {muted}", flush=True)
        elif cmd[0] == "record":
            record_request["want"] = cmd[1]
        elif cmd[0] == "setdevice":
            device_request["want"] = cmd[1]   # {"video": …, "audio": …}
        elif cmd[0] == "recdir":
            try:
                p = Path(cmd[1]).expanduser()
                p.mkdir(parents=True, exist_ok=True)
                REC_DIR["path"] = p
                VOICES.setdefault("settings", {})["recordings_dir"] = cmd[1]
                VOICES_PATH.write_text(
                    json.dumps(VOICES, indent=2, ensure_ascii=False))
                print(f"[recordings dir] {p}", flush=True)
            except OSError as e:
                add_event(f"bad recordings dir: {e}", "yield", None, cmd[1])
        elif cmd[0] == "delete":
            char = cmd[1]
            VOICES["characters"].pop(char, None)
            if char in VOICES.get("always_voiced", []):
                VOICES["always_voiced"].remove(char)
            unknown_speakers.discard(char)
            VOICES_PATH.write_text(json.dumps(VOICES, indent=2, ensure_ascii=False))
            if UNKNOWN_LOG.exists():
                UNKNOWN_LOG.write_text("\n".join(
                    n for n in UNKNOWN_LOG.read_text().splitlines()
                    if n.strip() and n.strip() != char) + "\n")
            print(f"[deleted] {char}", flush=True)
        elif cmd[0] == "clearlog":
            events.clear()
            print("[log cleared]", flush=True)
        elif cmd[0] == "observe":
            observing["on"] = cmd[1]
            if not cmd[1]:
                speech.stop()
            print(f"[observation {'resumed' if cmd[1] else 'paused'}]", flush=True)


def main():
    import signal
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    print("loading Kokoro…", flush=True)
    speech = Speech()
    print("model ready", flush=True)

    FRAME.parent.mkdir(exist_ok=True)
    WAV.parent.mkdir(exist_ok=True)

    recent_lines = deque(maxlen=DEDUP_WINDOW)
    if SPOKEN_CACHE.exists():
        try:
            obj = json.loads(SPOKEN_CACHE.read_text())
            for spk, norm in obj.get("window", []):
                recent_lines.append({"speaker": spk, "norm": norm})
            print(f"restored dedupe window of {len(recent_lines)}", flush=True)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    port = start_webui({"events": events, "voices": VOICES,
                        "unknown": unknown_speakers, "metrics_fn": metrics,
                        "commands": commands, "observing": observing,
                        "shots_dir": str(SHOTS), "frame_dir": str(FRAME.parent),
                        "rec_dir": REC_DIR,
                        "recording": recording,
                        "devices": DEVICES, "list_devices_fn": list_devices})
    print(f"dashboard: http://127.0.0.1:{port}", flush=True)

    def spawn_capture(record_path=None):
        """Start ffmpeg VIDEO capture (audio is sox's job); re-negotiates
        device resolution each spawn. With record_path, adds a 1080p30
        hardware-encoded video-only mkv output."""
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
               "-f", "avfoundation", "-framerate", "30",
               "-video_size", "1920x1080",   # native mode: no 4K scaling load
               "-i", DEVICES["video"],
               "-map", "0:v", "-vf", f"fps={SAMPLE_FPS},scale=1920:-2",
               "-update", "1", "-atomic_writing", "1", "-y", str(FRAME)]
        if record_path:
            cmd += ["-map", "0:v", "-s", "1920x1080", "-r", "30",
                    "-c:v", "h264_videotoolbox", "-b:v", "6M",
                    "-y", str(record_path)]
        return subprocess.Popen(cmd, stdout=subprocess.DEVNULL)

    def spawn_sox():
        """Bit-perfect continuous audio capture via CoreAudio (truncates)."""
        return subprocess.Popen(
            ["sox", "-q", "--buffer", "4096",
             "-t", "coreaudio", DEVICES["audio"],
             "-t", "raw", "-b", "16", "-e", "signed", "-c", "2",
             "-r", "48000", str(AUDIO_PCM)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    threading.Thread(target=audio_thread, daemon=True).start()
    ffmpeg = spawn_capture()
    sox = spawn_sox()

    def spawn_ocrd():
        return subprocess.Popen(
            [str(ROOT / "tools" / "ocrd")],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    ocrd = spawn_ocrd()

    candidate, candidate_count = None, 0
    candidate_growing = False
    last_mtime = 0.0
    last_frame_change = time.monotonic()
    yield_event_id = None
    qr_seen, qr_absent = set(), 99      # Quick Read incremental-reading state
    read_queue = deque()
    print("live — watching feed + listening for VO", flush=True)

    try:
        while True:
            time.sleep(0.03)
            handle_commands(speech)
            now = time.monotonic()

            if device_request["want"] is not None and not recording["on"]:
                want, device_request["want"] = device_request["want"], None
                DEVICES.update({k: v for k, v in want.items() if v})
                VOICES.setdefault("settings", {}).update(
                    video_device=DEVICES["video"],
                    audio_device=DEVICES["audio"])
                VOICES_PATH.write_text(
                    json.dumps(VOICES, indent=2, ensure_ascii=False))
                print(f"[devices] video={DEVICES['video']} "
                      f"audio={DEVICES['audio']}", flush=True)
                for p in (ffmpeg, sox):
                    if p.poll() is None:
                        p.kill()
                ffmpeg = spawn_capture()
                sox = spawn_sox()
                last_frame_change = time.monotonic()

            if record_request["want"] is not None:
                want, record_request["want"] = record_request["want"], None
                if want and not recording["on"]:
                    REC_DIR["path"].mkdir(parents=True, exist_ok=True)
                    CLIPS.mkdir(parents=True, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    raw = REC_DIR["path"] / f"rec_{ts}_raw.mkv"  # mkv: crash-safe
                    if ffmpeg.poll() is None:
                        ffmpeg.kill()
                    ffmpeg = spawn_capture(raw)
                    for _ in range(40):          # align t0 with the video start
                        if raw.exists():
                            break
                        time.sleep(0.1)
                    s0 = AUDIO_PCM.stat().st_size if AUDIO_PCM.exists() else 0
                    recording.update(on=True, t0=time.monotonic(), clips=[],
                                     raw=str(raw), s0=s0)
                    last_frame_change = time.monotonic()
                    print("[recording started]", flush=True)
                elif not want and recording["on"]:
                    recording["on"] = False
                    s1 = AUDIO_PCM.stat().st_size if AUDIO_PCM.exists() else 0
                    raw, clips = recording["raw"], recording["clips"]
                    s0 = recording.get("s0", 0)
                    ffmpeg.send_signal(signal.SIGINT)   # clean mkv finalize
                    try:
                        ffmpeg.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        ffmpeg.kill()
                    ffmpeg = spawn_capture()
                    last_frame_change = time.monotonic()
                    out = raw.replace("_raw.mkv", ".mp4")
                    threading.Thread(target=mux_recording,
                                     args=(raw, clips, out, s0, s1),
                                     daemon=True).start()
                    print("[recording stopped — muxing]", flush=True)

            if (speech.player and speech.player.poll() is None and speech.t_play
                    and not speech.qr_playing
                    and is_voiced(speech.t_play + 0.2)):
                speech.stop()
                stats["yielded"] += 1
                if yield_event_id:
                    for e in events:
                        if e["id"] == yield_event_id:
                            e["action"], e["cls"] = "yielded to VO", "yield"
                print("[yielded to late VO]", flush=True)

            if not observing["on"]:
                candidate, candidate_count = None, 0
                continue

            # Watchdog: ffmpeg keeps writing frames even on static screens, so
            # a stalled frame file means capture broke (e.g. the device
            # changed resolution mid-stream). Respawn to re-negotiate.
            # sox watchdog: respawn if it died, or truncate the ever-growing
            # stream (~690 MB/hour) when safely between recordings
            if sox.poll() is not None and not recording["on"]:
                print("[sox died — respawning]", flush=True)
                sox = spawn_sox()
            elif (AUDIO_PCM.exists()
                    and AUDIO_PCM.stat().st_size > 1_500_000_000
                    and not recording["on"]):
                print("[truncating audio stream]", flush=True)
                sox.kill()
                sox = spawn_sox()

            if now - last_frame_change > 10:
                print("[capture stalled — respawning ffmpeg]", flush=True)
                if ffmpeg.poll() is None:
                    ffmpeg.kill()
                ffmpeg = spawn_capture()
                last_frame_change = time.monotonic()
                continue

            try:
                mtime = FRAME.stat().st_mtime
            except FileNotFoundError:
                continue
            if mtime == last_mtime:
                continue
            last_mtime = mtime
            last_frame_change = now

            t0 = time.time()
            try:
                ocrd.stdin.write(str(FRAME) + "\n")
                raw = ocrd.stdout.readline()
            except (BrokenPipeError, OSError):
                raw = ""
            if not raw:
                print("OCR daemon died — respawning", flush=True)
                if ocrd.poll() is None:
                    ocrd.kill()
                ocrd = spawn_ocrd()
                continue
            stats["ocr_ms"].append(int((time.time() - t0) * 1000))
            blocks = json.loads(raw)

            # --- Reading-mode screens (Quick Read books, info/profile
            # screens): incremental narrator reading ---
            qr = classify_quickread(blocks)
            if qr is None:
                qr = classify_infoscreen(blocks)
            if qr is not None:
                qr_absent = 0
                new = []
                for t in qr:
                    n = normalize_text(t)
                    if len(n) > 2 and n not in qr_seen:
                        qr_seen.add(n)
                        new.append(t)
                if new:
                    read_queue.append(fix_ocr_text(" ".join(new)))
                candidate, candidate_count = None, 0
            else:
                if qr_absent < 99:
                    qr_absent += 1
                if qr_absent == 3:              # user closed the book screen
                    read_queue.clear()
                    if speech.qr_playing:
                        speech.stop()
                if qr_absent == 40:             # gone a while: forget progress
                    qr_seen.clear()

            # pump the reading queue when the voice is idle
            if (read_queue
                    and (speech.player is None
                         or speech.player.poll() is not None)):
                text = read_queue.popleft()
                voice = VOICES["defaults"]["narrator"]
                segs, speed, _ = speech.synth(text, voice, 1.0)
                speech.play(segs, qr=True)
                stats["spoken"] += 1
                add_event("quick read", "spoken", None, text, voice, speed,
                          can_replay=True, shot=True)
                print(f"[quick read → {voice}] {text[:70]}", flush=True)
            if qr is not None:
                continue

            state = classify(blocks)
            loading = classify_loading(blocks)
            if loading:
                # loading-screen lore: read as narration, never as dialogue
                state = {"speaker": None, "dialogue": loading, "choices": []}
            elif not state["dialogue"]:
                overlay = classify_overlay(blocks)
                narration = classify_narration(blocks)
                if overlay:
                    # floating host bubble — voice set by settings.overlay_speaker
                    state = {"speaker": VOICES.get("settings", {}).get(
                                 "overlay_speaker"),
                             "dialogue": overlay, "choices": []}
                elif narration and (has_continue_hint(blocks)
                                    or frame_is_dark()
                                    or narration_self_certain(narration)):
                    # narration requires the Continue hint — menu banners
                    # and event-hub screens must not be narrated
                    state = {"speaker": None, "dialogue": narration, "choices": []}
                else:
                    candidate, candidate_count = None, 0
                    continue
            else:
                # dialogue from an UNKNOWN speaker needs the Continue hint;
                # boards/menus fake the layout but show Confirm/other hints
                spk = normalize_speaker(state["speaker"])
                known = (spk in VOICES["characters"]
                         or (spk or "").lower() == "narrator"
                         or spk in VOICES.get("always_voiced", []))
                if not known and not has_continue_hint(blocks):
                    candidate, candidate_count = None, 0
                    continue

            state["speaker"] = normalize_speaker(state["speaker"])
            state["dialogue"] = fix_ocr_text(state["dialogue"])
            key = (state["speaker"], normalize_text(state["dialogue"]))
            if key == candidate:
                candidate_count += 1
            else:
                # if the text GREW from the previous candidate, the typewriter
                # is mid-render (it pauses at sentence ends!) — stay patient
                candidate_growing = (candidate is not None
                                     and candidate[0] == key[0]
                                     and key[1].startswith(candidate[1]))
                candidate, candidate_count = key, 1
            # a line ending mid-sentence is probably still typing its next
            # visual row — hold a few extra reads so we speak it whole
            complete = state["dialogue"].rstrip().endswith(
                (".", "!", "?", "…", '"', "”", "’", ")"))
            required = (STABLE_READS if complete and not candidate_growing
                        else STABLE_READS + 4)
            if candidate_count != required:
                continue
            candidate_growing = False

            new_norm = key[1]

            # Compare against the recent window. Three outcomes:
            #   dup       — jitter variant / repeat → skip
            #   extension — line grew after we spoke a stable prefix
            #               (typewriter race) → speak only the remainder
            #   new       — speak in full
            dup, ext_base = False, None
            for e in recent_lines:
                o = e["norm"]
                same_spk = e["speaker"] == state["speaker"]
                if not (same_spk or len(new_norm) >= SHORT_LINE):
                    continue
                if (difflib.SequenceMatcher(None, new_norm, o).ratio() >= 0.90
                        or o.startswith(new_norm)):
                    dup = True
                    break
                if new_norm.startswith(o):
                    if len(new_norm) - len(o) < 8:   # trivial tail = jitter
                        dup = True
                        break
                    if ext_base is None or len(o) > len(ext_base):
                        ext_base = o
            if dup:
                continue

            speak_text = state["dialogue"]
            if ext_base:
                # map the normalized prefix length back to a raw split point
                cnt, idx = 0, len(speak_text)
                for i, ch in enumerate(speak_text):
                    if ch.isalnum():
                        cnt += 1
                    if cnt == len(ext_base):
                        idx = i + 1
                        break
                speak_text = speak_text[idx:].lstrip(" .,!?…—-")
                if len(normalize_text(speak_text)) < 3:
                    continue
                print(f"[extension — speaking remainder] {speak_text[:60]}",
                      flush=True)
            if ext_base:
                # update the window entry in place so later growth diffs
                # against the LONGEST text we've handled, never re-reads
                for e in recent_lines:
                    if e["norm"] == ext_base:
                        e["norm"] = new_norm
                        break
            else:
                recent_lines.append(
                    {"speaker": state["speaker"], "norm": new_norm})
            SPOKEN_CACHE.write_text(json.dumps(
                {"window": [[e["speaker"], e["norm"]] for e in recent_lines]}))

            if state["speaker"] in VOICES.get("always_voiced", []):
                stats["always_voiced"] += 1
                add_event("muted char", "always", state["speaker"],
                          state["dialogue"], shot=True)
                continue

            # Speculative synthesis: render audio while the VAD gate listens;
            # discarded if the line turns out to be voiced.
            voice, base_speed = pick_voice(state["speaker"])
            spec = {}
            synth_thread = threading.Thread(
                target=lambda: spec.update(zip(
                    ("segs", "speed", "ms"),
                    speech.synth(speak_text, voice, base_speed))))
            synth_thread.start()

            # --- VAD gate ---
            while (not vad_history
                   or time.monotonic() - vad_history[0][0] < VAD_LOOKBACK):
                time.sleep(0.1)
            t_stable = time.monotonic()
            voiced = is_voiced(t_stable - VAD_LOOKBACK)
            deadline = t_stable + VAD_WAIT
            while not voiced and time.monotonic() < deadline:
                time.sleep(0.05)
                voiced = is_voiced(t_stable - VAD_LOOKBACK)
            if not voiced:
                quiet_deadline = time.monotonic() + 2.5
                while time.monotonic() < quiet_deadline:
                    if speech_hits(time.monotonic() - 0.4, threshold=0.25) == 0:
                        break
                    if is_voiced(t_stable - VAD_LOOKBACK):
                        voiced = True
                        break
                    time.sleep(0.1)
            # center-energy layer: catches VO the VAD can't recognize as
            # speech (vocoder/robot voices) — mid-channel burst, flat side
            mid_up, side_up = center_burst(t_stable)
            # center SFX (explosions, magic flashes) are mid-panned like VO —
            # demand at least faint speechiness so booms don't count
            vad_peak = max((p for t, p in vad_history if t >= t_stable - 1.2),
                           default=0.0)
            if (not voiced and mid_up >= ENERGY_MID_BURST
                    and side_up <= ENERGY_SIDE_FLAT
                    and mid_up - side_up >= ENERGY_MID_OVER_SIDE
                    and vad_peak >= 0.15):
                voiced = True
                print(f"[voiced — center energy] mid+{mid_up:.1f}dB "
                      f"side+{side_up:.1f}dB peak={vad_peak:.2f}", flush=True)
            synth_thread.join()
            if ext_base and not voiced:
                # the remainder continues a line we're still speaking —
                # let the prefix finish instead of cutting it off
                wait_until = time.monotonic() + 15
                while (speech.player and speech.player.poll() is None
                       and time.monotonic() < wait_until):
                    time.sleep(0.05)
            if voiced:
                stats["skipped_voiced"] += 1
                add_event("skipped (voiced)", "skip", state["speaker"],
                          state["dialogue"], shot=True)
                print(f"[voiced — skipping mid+{mid_up:.1f} side+{side_up:.1f}] "
                      f"{state['dialogue'][:60]}", flush=True)
                continue

            speech.play(spec.get("segs"))
            speed = spec.get("speed")
            stats["spoken"] += 1
            yield_event_id = add_event(
                "spoken", "spoken", state["speaker"], speak_text,
                voice, speed, can_replay=True, shot=True)
            gate_max = max((p for t, p in vad_history
                            if t >= t_stable - VAD_LOOKBACK), default=-1.0)
            print(f"[{state['speaker'] or 'Narrator'} → {voice} ×{speed} "
                  f"gate={gate_max:.2f} mid+{mid_up:.1f} side+{side_up:.1f}] "
                  f"{speak_text}", flush=True)
    finally:
        speech.stop()
        for p in (ffmpeg, sox, ocrd):
            if p and p.poll() is None:
                p.kill()


if __name__ == "__main__":
    main()
