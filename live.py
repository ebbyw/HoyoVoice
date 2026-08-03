#!/usr/bin/env python3
"""HoyoVoice live loop v3 — VAD gate + web dashboard + sentiment delivery.

Run: .venv/bin/python live.py     (or ./hoyovoice.sh start)
Dashboard: http://127.0.0.1:8470
"""
import difflib
import json
import os
import re
import queue
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

# Windows redirects stdout/stderr through cp1252 by default, and our log
# lines are full of '→' — reconfigure before anything prints or the first
# spoken line kills the process with UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent
# All mutable state (frames, PCM, casting, caches, TTS output) lives under
# STATE — normally the repo root. tools/replay.py points this somewhere
# disposable so replays can't touch real casting or dedupe state.
STATE = Path(os.environ.get("HOYOVOICE_STATE_DIR", str(ROOT)))
sys.path.insert(0, str(ROOT / "tools"))
from classify import (classify, classify_chat, classify_infoscreen,  # noqa: E402
                      classify_loading, classify_lore_screen,
                      classify_narration, classify_overlay,
                      classify_quickread, has_continue_hint,
                      narration_self_certain, split_camel)
from vad import CHUNK, SileroVAD  # noqa: E402
from webui import start_webui  # noqa: E402
from hv_platform import get_backend  # noqa: E402

backend = get_backend()

FRAME = STATE / "captures" / "live_frame.jpg"
# Continuous 48k stereo s16le stream (sox/CoreAudio on macOS, in-process
# WASAPI on Windows). Never route audio through ffmpeg on macOS — its
# AVFoundation input drops ~12% of samples.
AUDIO_PCM = STATE / "captures" / "game_audio_48k.pcm"
AUDIO_BYTES_PER_SEC = 48000 * 2 * 2   # 48k, stereo, s16
GAME_SLICE = STATE / "captures" / "game_slice.pcm"
SHOTS = STATE / "captures" / "shots"
SHOTS_KEEP = 300
WAV = STATE / "tts_out" / "live.wav"
UNKNOWN_LOG = STATE / "unknown_speakers.log"
SPOKEN_CACHE = STATE / "captures" / "spoken_cache.json"
VOICES_PATH = STATE / "voices.json"
if not VOICES_PATH.exists():                      # first run: seed from example
    import shutil
    VOICES_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / "voices.example.json", VOICES_PATH)
VOICES = json.loads(VOICES_PATH.read_text())

REC_DIR = {"path": Path(VOICES.get("settings", {}).get(
    "recordings_dir", str(STATE / "recordings"))).expanduser()}
CLIPS = STATE / "captures" / "rec_clips"    # temp TTS clips, cleaned after mux

# Devices BY NAME — indices can shift (index 0 once became the Mac webcam!)
# Both selectable from the dashboard; persisted in voices.json settings.
DEVICES = {
    "video": VOICES.get("settings", {}).get("video_device", "ShadowCast 3"),
    "audio": VOICES.get("settings", {}).get("audio_device", "ShadowCast 3"),
}


list_devices = backend.list_devices
SAMPLE_FPS = 6
STABLE_READS = 2
# consecutive frames where the detector loses an on-screen line before we
# give up on the candidate (~0.5s at 6fps). OCR misses are common on bright
# backgrounds; without this, a miss discards all accumulated stability.
MISS_TOLERANCE = 3
# how long a Quick Read / chat panel must stay undetected before we treat it
# as closed (drop the queue, stop reading). Scrolling briefly hides the
# hints the detector keys on, so a short count fires on ordinary scrolling.
READER_CLOSE_AFTER = 2.0
DEDUP_WINDOW = 3              # a line repeats only if it's within the last N messages
# the persisted window only guards against a restart mid-scene; older than
# this, the same text is a new encounter (a loading screen seen every
# session was being skipped as a repeat). voiced_history is NOT aged out —
# that prior is meant to accumulate.
SPOKEN_CACHE_TTL = 600
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
# Some VO sits below every audio threshold we can safely use: measured on a
# real capture, a voiced line peaked at 0.18 with 4 blocks >= 0.12, while an
# UNVOICED line in the same scene had 5 — no global threshold separates them,
# and lowering one silences the unvoiced lines this app exists to fill in.
# For a speaker whose lines have consistently turned out voiced, use that
# prior instead: accept much weaker evidence before talking over them.
# Staying silent is the safer error for a character who has a real voice.
VAD_SOFT_THRESHOLD = 0.12
VAD_SOFT_HITS = 3
SOFT_GATE_MIN_VOICED = 3      # observations before the prior is trusted
SOFT_GATE_RATIO = 0.75
# the gate's lookback must never reach back before the line appeared on
# screen — otherwise the PREVIOUS speaker's VO tail counts as evidence that
# THIS line is voiced (false skip on fast auto-advance transitions, where
# the next subtitle lands <0.5s after the old VO ends). No backward margin:
# real VO keeps playing well past the OCR sighting, so post-appearance hits
# are always enough; only a sub-half-second grunt that ends before OCR sees
# the text would slip through, and the mid-play yield covers late starts.
VAD_LINE_MARGIN = 0.0

vad_history = deque(maxlen=400)
vad_lag = {"s": 0.0}          # how far the VAD tail-reader trails the live edge
# speaker -> [times the game voiced them, times we spoke for them]
voiced_history = {}
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
# start paused — resume from the dashboard (replays auto-resume)
observing = {"on": os.environ.get("HOYOVOICE_AUTORESUME") == "1"}
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


latest_ocr = {"blocks": None}     # raw blocks of the current frame (debug)
lost_frames = {"n": 0}            # frames the OCR daemon couldn't read at all


def save_shot(eid):
    """Downscaled screenshot of the current frame for the dashboard log,
    plus the raw OCR blocks (shots/<id>.json) for layout debugging —
    open /shots/<id>.json in the browser to see what the engine saw."""
    try:
        from PIL import Image
        img = Image.open(FRAME)
        img.thumbnail((854, 854))       # ~480p, legible and small (~60 KB)
        SHOTS.mkdir(parents=True, exist_ok=True)
        img.save(SHOTS / f"{eid}.jpg", quality=68)
        if latest_ocr["blocks"] is not None:
            (SHOTS / f"{eid}.json").write_text(json.dumps(
                latest_ocr["blocks"], indent=1), encoding="utf-8")
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
    # signal level (mid-channel dB) separates "no speech" from true
    # silence: ~-60dB = digital silence (wrong input?), higher = audio
    recent_db = [m for t, m, s in energy_history if t >= now - 3.0]
    lvl = f" {max(recent_db):.0f}dB" if recent_db else ""
    lag = f" LAG {vad_lag['s']:.1f}s" if vad_lag["s"] > 0.5 else ""
    return {
        "vad": (f"{len(recent)}ch max={max(recent):.2f}{lvl}{lag}" if recent
                else "NO AUDIO"),
        "uptime": f"{up // 3600}h{(up % 3600) // 60:02d}m",
        "spoken": stats["spoken"],
        "skipped_voiced": stats["skipped_voiced"],
        "yielded": stats["yielded"],
        "synth_avg_ms": int(sum(synth) / len(synth)) if synth else 0,
        "ocr_avg_ms": int(sum(ocr) / len(ocr)) if ocr else 0,
        "lost_frames": lost_frames["n"],
        "lines_per_min": round(stats["spoken"] / mins, 1),
    }


def audio_thread():
    """Tail the 48k stereo PCM the audio backend appends to; downmix +
    decimate to 16k mono chunks for the VAD. File writes never block on a
    consumer, so nothing here can cause capture drops. Handles truncation
    on respawn."""
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
            vad.reset()         # fresh stream: no usable prior context
            warmup = 32
        if size < pos:          # capture respawned and truncated the file
            fh.close()
            fh, pos = None, 0
            continue
        backlog = size - pos
        vad_lag["s"] = backlog / AUDIO_BYTES_PER_SEC
        if backlog > AUDIO_BYTES_PER_SEC:      # reader fell >1s behind
            # stale audio with fresh timestamps poisons the gate: it judges
            # "now" using minutes-old sound. Drop the backlog, rejoin near
            # the live edge, re-prime the VAD.
            print(f"[vad: reader lagged {vad_lag['s']:.1f}s — "
                  "skipping to live]", flush=True)
            pos = size - AUDIO_BYTES_PER_SEC // 2
            pos -= pos % 4                     # stereo s16 frame alignment
            fh.seek(pos)
            vad.reset()        # discarded audio is not adjacent to what's next
            warmup = 8
            continue
        if backlog < BLOCK:
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


def usually_voiced(speaker):
    """True once a speaker has a consistent record of the game voicing them."""
    v, s = voiced_history.get(speaker, (0, 0))
    return v >= SOFT_GATE_MIN_VOICED and v >= SOFT_GATE_RATIO * (v + s)


def is_voiced(since, soft=False):
    """soft: this speaker is usually voiced, so accept weaker evidence."""
    weak_threshold = VAD_SOFT_THRESHOLD if soft else VAD_WEAK_THRESHOLD
    weak_hits = VAD_SOFT_HITS if soft else VAD_WEAK_HITS
    strong = weak = 0
    peak = 0.0
    for t, p in vad_history:
        if t >= since:
            if p >= VAD_THRESHOLD:
                strong += 1
            if p >= weak_threshold:
                weak += 1
            peak = max(peak, p)
    return (strong >= VAD_MIN_HITS or peak >= VAD_PEAK
            or weak >= weak_hits)


# HSR renders capital I without serifs, so Vision reads it as l/L constantly.
# Standalone l/L (incl. l've, L-L'm stutters) and lt/lts are never real words.
_OCR_FIXES = [
    (re.compile(r"\b[lL]\b"), "I"),   # I / I've / I'm / I-I'm stutters
    (re.compile(r"\b[lL]t\b"), "It"),
    (re.compile(r"\b[lL]ts\b"), "Its"),
    (re.compile(r"\bi\b"), "I"),
]
# decorative glyphs TTS would read aloud ("tilde") or spell out
_STRIP_GLYPHS = re.compile(r"[~*＊♪♡♥★☆]+")
# Vision drops apostrophes in this font ("youre" → Kokoro says "yo-ray").
# Restore only bare forms that aren't real English words — can't misfire.
_CONTRACTIONS = {
    "youre": "you're", "youll": "you'll", "youve": "you've", "youd": "you'd",
    "theyre": "they're", "theyve": "they've", "theyll": "they'll",
    "werent": "weren't", "wasnt": "wasn't", "isnt": "isn't",
    "arent": "aren't", "dont": "don't", "doesnt": "doesn't",
    "didnt": "didn't", "wont": "won't", "cant": "can't",
    "couldnt": "couldn't", "wouldnt": "wouldn't", "shouldnt": "shouldn't",
    "mustnt": "mustn't", "havent": "haven't", "hasnt": "hasn't",
    "hadnt": "hadn't", "im": "I'm", "ive": "I've", "hes": "he's",
    "shes": "she's", "whats": "what's", "thats": "that's",
    "theres": "there's", "heres": "here's", "whos": "who's",
    "wheres": "where's", "hows": "how's", "aint": "ain't",
}
_CONTRACTION_RE = re.compile(
    r"\b(" + "|".join(_CONTRACTIONS) + r")\b", re.IGNORECASE)
# interjections that get spelled letter-by-letter → nearest real word
_INTERJECTIONS = [
    (re.compile(r"\bshh+\b", re.IGNORECASE), "shush"),
    (re.compile(r"\bhmph+\b", re.IGNORECASE), "humph"),
    (re.compile(r"\btsk\b", re.IGNORECASE), "tisk"),
    (re.compile(r"\bpff+t?\b", re.IGNORECASE), "pfff"),
]


# RapidOCR's default recognition model is Chinese-trained, and Chinese
# doesn't use spaces — so it drops the space after punctuation
# ("Patience,Sparxie,patience.Once"). Vision spaces correctly, so these
# are no-ops there. Guards keep numbers ("1,000", "2.5") and initials
# ("U.S.A") intact.
_ELLIPSIS_RUN = re.compile(r"\.{2,}")
_SPACE_AFTER_PUNCT = re.compile(r"(?<=[a-zA-Z])([,;:!?…])(?=[A-Za-z])")
_SPACE_AFTER_DOT = re.compile(r"(?<=[a-z])\.(?=[A-Za-z])")
# a lone period between two lowercase words is a misread comma — real
# sentences start with a capital. Wrong pauses hurt TTS delivery most.
_COMMA_MISREAD = re.compile(r"(?<=[a-z])\.(?=\s+[a-z])")


# Run-on repair. The Windows recognition model is Chinese-trained and
# Chinese has no spaces, so it fuses word pairs ("mercyis", "thingandbring")
# that no punctuation rule can catch. wordfreq scores candidate splits;
# optional import so the macOS/Vision path (which spaces correctly) and
# installs without it simply skip this.
try:
    from wordfreq import zipf_frequency as _zipf
except ImportError:                                   # pragma: no cover
    _zipf = None
_RUNON_MIN_PART = 3.2     # both halves must be this common (zipf)
# A token this common is left alone. Measured over the repo's own prose:
# at 2.0 the splitter mangled real words with common affixes — "tolerantly"
# (zipf 1.32) → "tolerant ly", "misreads" (1.68) → "mis reads". Genuine OCR
# fusions ("mercyis", "thingandbring", "shaning") all score 0.00, so
# dropping the bar to 1.0 keeps every true split and drops the damage.
_RUNON_IS_WORD = 1.0


def _split_runon(tok):
    """['mercyis'] → ['mercy', 'is']; unsplittable tokens come back as-is."""
    if (_zipf is None or len(tok) < 4 or not tok.isalpha()
            or _zipf(tok.lower(), "en") >= _RUNON_IS_WORD):
        return [tok]
    best = None
    for i in range(1, len(tok)):
        a, b = tok[:i], tok[i:]
        if len(a) == 1 and a.lower() not in "ai":
            continue
        if len(b) == 1 and b.lower() not in "ai":
            continue
        fa, fb = _zipf(a.lower(), "en"), _zipf(b.lower(), "en")
        if fa >= _RUNON_MIN_PART and fb >= _RUNON_MIN_PART:
            if best is None or min(fa, fb) > best[0]:
                best = (min(fa, fb), a, b)
    return [best[1], best[2]] if best else [tok]


def repair_runons(s):
    out = []
    for tok in re.split(r"(\W+)", s):
        # Capitalised tokens are game proper nouns ("Wishpower", "Cindearth")
        # — splitting those is worse than leaving a fused pair.
        if tok[:1].isupper() or not tok.isalpha():
            out.append(tok)
        else:
            out.append(" ".join(_split_runon(tok)))
    return "".join(out)


def text_quality(s):
    """Fraction of tokens that are real words — used to pick the best of
    several OCR reads of the SAME line. A read with 'mercy is' scores above
    one with 'mercyis' even when the fused version is far more common."""
    if _zipf is None:
        return 0.0
    toks = re.findall(r"[A-Za-z']+", s)
    if not toks:
        return 0.0
    good = sum(1 for w in toks
               if w[:1].isupper() or _zipf(w.lower(), "en") >= _RUNON_IS_WORD)
    return good / len(toks)


def repair_punctuation(s):
    s = _ELLIPSIS_RUN.sub("…", s)          # ".." / "..." → one ellipsis glyph
    s = _SPACE_AFTER_PUNCT.sub(r"\1 ", s)
    s = _SPACE_AFTER_DOT.sub(". ", s)
    return _COMMA_MISREAD.sub(",", s)


def _keep_case(rep):
    return lambda m: rep.capitalize() if m.group(0)[0].isupper() else rep


def fix_ocr_text(s):
    s = re.sub(r"[’‘`´ʼ]", "'", s)      # normalize apostrophe glyph variants
    s = repair_punctuation(s)           # before word fixes: \b needs spaces
    s = repair_runons(s)                # 'mercyis' → 'mercy is'
    for pat, rep in _OCR_FIXES:
        s = pat.sub(rep, s)
    s = _STRIP_GLYPHS.sub("", s)
    s = _CONTRACTION_RE.sub(
        lambda m: (_CONTRACTIONS[m.group(0).lower()].capitalize()
                   if m.group(0)[0].isupper()
                   else _CONTRACTIONS[m.group(0).lower()]), s)
    for pat, rep in _INTERJECTIONS:
        s = pat.sub(_keep_case(rep), s)
    # user lexicon for proper nouns OCR keeps mangling ("lason" → "Iason")
    for wrong, right in VOICES.get("settings", {}).get("text_fixes", {}).items():
        s = re.sub(rf"\b{re.escape(wrong)}\b", right, s, flags=re.IGNORECASE)
    return re.sub(r"  +", " ", s).strip()


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


def similar_speaker(a, b):
    """True if two nameplate reads are plausibly the same character.
    OCR drops leading words on stylized plates ('MysteriousGoldy' →
    'Goldy'), so containment counts, not just fuzzy equality."""
    if a == b:
        return True
    na, nb = normalize_text(a or ""), normalize_text(b or "")
    if not na or not nb:
        return not na and not nb
    return na in nb or nb in na or difflib.SequenceMatcher(
        None, na, nb).ratio() >= 0.8


def same_line(a, b, cutoff=0.9):
    """Fuzzy equality for normalized lines — used to collapse repeated log
    entries when OCR jitter makes the same on-screen line read slightly
    differently on each pass."""
    if not a or not b:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= cutoff


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
    if m:
        return m[0]
    # OCR drops leading words on stylized plates ("Mysterious Goldy" reads
    # as "Goldy"), which fuzzy matching misses — without this the partial
    # read auto-casts as a SEPARATE character with a different voice
    n_spk = normalize_text(speaker)
    if len(n_spk) >= 4:
        hits = [k for k in known
                if n_spk in normalize_text(k) or normalize_text(k) in n_spk]
        if hits:
            return max(hits, key=len)
    return speaker


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
    """Owns the TTS engine, sentiment analyzer, and playback."""

    def __init__(self):
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        import numpy as np
        import soundfile as sf
        self.np, self.sf = np, sf
        self.tts = backend.create_tts()
        self.player = backend.create_player()
        self.sia = SentimentIntensityAnalyzer()
        self.t_play = None
        self._qr = False

    @property
    def playing(self):
        return self.player.playing

    @property
    def qr_playing(self):
        """True only while a reader-queue item is ACTUALLY sounding. The
        raw flag survives natural end-of-playback, which made 'is a read in
        flight?' checks lie."""
        return self._qr and self.player.playing

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
        interrupted = self.player.stop()
        self._qr = False
        # if a recorded clip was cut short (yield/interrupt), trim it in the mix
        if interrupted and recording["on"] and recording["clips"]:
            last = recording["clips"][-1]
            if last.get("end") is None:
                last["end"] = time.monotonic() - recording["t0"]
        self.t_play = None

    def synth(self, text, voice, base_speed=1.0):
        # spoken-form substitutions (settings.pronunciations) — logs and
        # dedupe keep the real spelling; only the TTS hears these
        for word, spoken in VOICES.get("settings", {}).get(
                "pronunciations", {}).items():
            text = re.sub(rf"\b{re.escape(word)}\b", spoken, text,
                          flags=re.IGNORECASE)
        speed = round(base_speed * self.sentiment_speed(text), 3)
        t0 = time.time()
        audio = self.tts.synth(text, voice, speed)
        synth_ms = int((time.time() - t0) * 1000)
        if audio is not None:
            stats["synth_ms"].append(synth_ms)
        return audio, speed, synth_ms

    def play(self, audio, qr=False):
        if audio is None or not len(audio):
            return
        self.stop()
        self._qr = qr
        # trim Kokoro's silence padding: snappier starts, tight handoffs
        loud = self.np.where(self.np.abs(audio) > 0.012)[0]
        if len(loud):
            audio = audio[max(loud[0] - 800, 0):loud[-1] + 1600]
        self.sf.write(WAV, audio, 24000)
        self.player.play(WAV, audio, 24000)
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
        audio, speed, synth_ms = self.synth(text, voice, base_speed)
        self.play(audio)
        return synth_ms, speed


def mux_recording(raw, clips, out, s0, s1):
    """Combine: video (ffmpeg mkv) + game audio (exact byte-slice of the
    PCM stream between recording start/stop) + TTS clips at wall offsets."""
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
            # The window exists so a restart MID-SCENE doesn't re-read the
            # line still on screen. After a real break the same text is a
            # fresh encounter — a loading screen you see every session was
            # being silently skipped as a repeat — so let it go stale.
            age = time.time() - obj.get("saved_at", 0)
            if age <= SPOKEN_CACHE_TTL:
                for spk, norm in obj.get("window", []):
                    recent_lines.append({"speaker": spk, "norm": norm})
            else:
                print(f"dedupe window discarded ({age / 60:.0f} min old)",
                      flush=True)
            for spk, counts in obj.get("voiced_history", {}).items():
                if isinstance(counts, list) and len(counts) == 2:
                    voiced_history[spk] = list(counts)
            print(f"restored dedupe window of {len(recent_lines)}"
                  f"; voiced history for {len(voiced_history)} speaker(s)",
                  flush=True)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    port = start_webui({"events": events, "voices": VOICES,
                        "unknown": unknown_speakers, "metrics_fn": metrics,
                        "commands": commands, "observing": observing,
                        "shots_dir": str(SHOTS), "frame_dir": str(FRAME.parent),
                        "rec_dir": REC_DIR,
                        # written by the launcher (repo root), not STATE
                        "log_path": str(ROOT / "live.log"),
                        "recording": recording,
                        "devices": DEVICES, "list_devices_fn": list_devices})
    print(f"dashboard: http://127.0.0.1:{port}", flush=True)

    threading.Thread(target=audio_thread, daemon=True).start()
    video = backend.create_video_capture(DEVICES, FRAME, SAMPLE_FPS)
    audio_cap = backend.create_audio_capture(DEVICES, AUDIO_PCM)
    video.restart()
    audio_cap.restart()

    def custom_words_file():
        words = set()
        for name in VOICES["characters"]:
            words.update(name.strip('"“”').split())
        words.update(VOICES.get("settings", {}).get("text_fixes", {}).values())
        words.update(VOICES.get("settings", {}).get("custom_words", []))
        cw = ROOT / "captures" / "custom_words.txt"
        cw.parent.mkdir(exist_ok=True)
        cw.write_text("\n".join(sorted(w for w in words if w)))
        return cw

    # settings.ocr_engine (Windows): auto | rapid | windows. auto measures
    # the accurate engine's speed on this machine and falls back if needed
    os.environ.setdefault("HOYOVOICE_OCR_ENGINE",
                          VOICES.get("settings", {}).get("ocr_engine", "auto"))
    ocr = backend.create_ocr(ROOT, custom_words_file())

    candidate, candidate_count = None, 0
    candidate_growing = False
    candidate_t0 = 0.0          # when the current line was FIRST seen on screen
    last_dup_logged = None
    last_unknown_logged = None
    last_spoken_norm = None     # suppresses repeat-logs for the live line
    fired_norm = None           # line already pushed through the gate once
    unstable_count = 0
    miss_streak = 0             # consecutive frames the detector lost the line
    candidate_variants = []     # every raw read of the current line
    last_mtime = 0.0
    last_frame_change = time.monotonic()
    yield_event_id = None
    qr_seen, qr_absent = set(), 99      # Quick Read incremental-reading state
    qr_gone_t0 = 0.0                    # when the reader panel first vanished
    chat_prev = set()                   # last frame's messages (settle check)
    reader_closed = True                # panel-closed handling already done
    read_queue = deque()
    chat_senders = []                   # session canon: OCR jitters the tiny
                                        # sender labels (Ashveil/Ashvell/Ashval)

    def canon_sender(name):
        """Snap a jittered sender label to this chat session's canonical
        spelling (or a cast name) so one character can't multiply."""
        known = list(VOICES["characters"].keys()) + chat_senders
        m = difflib.get_close_matches(name, known, n=1, cutoff=0.75)
        if m:
            return m[0]
        chat_senders.append(name)
        return name
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
                video.restart()
                audio_cap.restart()
                last_frame_change = time.monotonic()

            if record_request["want"] is not None:
                want, record_request["want"] = record_request["want"], None
                if want and not recording["on"]:
                    REC_DIR["path"].mkdir(parents=True, exist_ok=True)
                    CLIPS.mkdir(parents=True, exist_ok=True)
                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                    raw = REC_DIR["path"] / f"rec_{ts}_raw.mkv"  # mkv: crash-safe
                    video.restart(record_path=raw)
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
                    video.finalize(timeout=8)   # clean mkv close (platform-specific)
                    video.restart()
                    last_frame_change = time.monotonic()
                    out = raw.replace("_raw.mkv", ".mp4")
                    threading.Thread(target=mux_recording,
                                     args=(raw, clips, out, s0, s1),
                                     daemon=True).start()
                    print("[recording stopped — muxing]", flush=True)

            # Mid-play yield. Our TTS is NOT in the capture (it plays on the
            # computer's speakers; the card hears only HDMI), so while we're
            # talking, ANY speech evidence in the feed is game VO — use the
            # aggressive soft thresholds unconditionally. The worst false
            # positive merely clips our own playback.
            if (speech.playing and speech.t_play
                    and not speech.qr_playing
                    and is_voiced(speech.t_play + 0.2, soft=True)):
                speech.stop()
                stats["yielded"] += 1
                if yield_event_id:
                    for e in events:
                        if e["id"] == yield_event_id:
                            e["action"], e["cls"] = "yielded to VO", "yield"
                print("[yielded to late VO]", flush=True)

            if not observing["on"]:
                candidate, candidate_count = None, 0
                # keep the stall timer fresh while paused, or resuming
                # instantly trips the "capture stalled" watchdog
                last_frame_change = now
                continue

            # Watchdog: capture keeps writing frames even on static screens,
            # so a stalled frame file means capture broke (e.g. the device
            # changed resolution mid-stream). Respawn to re-negotiate.
            # audio watchdog: respawn if it died, or truncate the ever-growing
            # stream (~690 MB/hour) when safely between recordings
            if not audio_cap.alive and not recording["on"]:
                print("[audio capture died — respawning]", flush=True)
                audio_cap.restart()
            elif (AUDIO_PCM.exists()
                    and AUDIO_PCM.stat().st_size > 1_500_000_000
                    and not recording["on"]):
                print("[truncating audio stream]", flush=True)
                audio_cap.restart()

            if now - last_frame_change > 10:
                print("[capture stalled — respawning]", flush=True)
                video.restart()
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
            blocks = ocr.recognize(FRAME)
            if blocks is None:          # daemon died; it respawned itself
                continue
            stats["ocr_ms"].append(int((time.time() - t0) * 1000))
            latest_ocr["blocks"] = blocks
            if not blocks:
                # NO blocks at all means we failed to read the frame (a torn
                # JPEG mid-rewrite, common under recording load), not that
                # the screen is empty. Counting it as evidence made reader
                # panels look closed while they were plainly on screen —
                # which stopped the read and dropped its queue.
                lost_frames["n"] += 1
                continue

            # --- Reading-mode screens (Quick Read books, info/profile
            # screens, message/group-chat panels): incremental reading ---
            qr = classify_quickread(blocks)
            if qr is None:
                qr = classify_infoscreen(blocks)
            chat = None if qr is not None else classify_chat(blocks)
            if qr is not None or chat is not None:
                qr_absent = 0
                reader_closed = False
                items = [(None, t) for t in qr] if qr is not None else chat
                if chat is not None:
                    # A message is queued the instant it's seen, so a frame
                    # caught mid fade-in gets read verbatim — that is where
                    # "started shan ing (ocation" came from; the same text
                    # reads at 0.98+ confidence once settled. Require a
                    # message to survive one more frame before reading it.
                    cur = {normalize_text(t) for _, t in chat}
                    settled = {c for c in cur
                               if any(same_line(c, p, 0.92)
                                      for p in chat_prev)}
                    chat_prev = cur
                    items = [(s, t) for s, t in items
                             if normalize_text(t) in settled]
                new = []
                for spk, t in items:
                    if spk:
                        spk = canon_sender(spk.strip())
                    elif spk is None and chat is not None and chat_senders:
                        # label scrolled off the top (or was missed): a run of
                        # messages only labels its first, so inherit the last
                        # known sender rather than reading in the narrator's
                        # voice — which is what a None sender falls back to
                        spk = chat_senders[-1]
                    # dedupe on text alone for substantial messages — sender
                    # label jitter must not requeue the same message; keep
                    # sender in the key only for short echoes ("ok")
                    tn = normalize_text(t)
                    n = tn if len(tn) >= 12 else normalize_text((spk or "") + t)
                    # A scrolled panel clips its TOP message, so the tail of
                    # one already read comes back as its own bubble ("City
                    # right now" from "…is in Seafeld City right now"). Fuzzy
                    # ratio can't see that — a short fragment scores low
                    # against the long original — so test containment. The
                    # length floor keeps genuine short replies ("Okay").
                    fragment = len(n) >= 8 and any(n in o for o in qr_seen)
                    if (len(n) > 2 and n not in qr_seen and not fragment
                            and not any(difflib.SequenceMatcher(
                                None, n, o).ratio() >= 0.9 for o in qr_seen)):
                        qr_seen.add(n)
                        new.append((spk, t))
                if qr is not None:
                    if new:
                        read_queue.append(
                            (None, fix_ocr_text(" ".join(t for _, t in new))))
                else:
                    # chat messages queue individually — each sender reads
                    # in their own cast (or auto-cast) voice
                    for spk, t in new:
                        read_queue.append((normalize_speaker(spk),
                                           fix_ocr_text(t)))
                candidate, candidate_count = None, 0
            else:
                chat_prev = set()
                if qr_absent < 99:
                    qr_absent += 1
                if qr_absent == 1:
                    qr_gone_t0 = now
                # Treat the panel as CLOSED only after it has been missing
                # for a sustained stretch. Scrolling briefly hides the
                # Scroll/Back hints this detector keys on, and the old
                # 3-frame rule (~0.5s) fired on that: it cleared the queue
                # and cut the read in progress just as the user scrolled.
                # Wall-clock is the whole test — a frame count would only
                # restate it, and badly, since the loop rate varies with
                # OCR and synth load.
                if (not reader_closed
                        and now - qr_gone_t0 >= READER_CLOSE_AFTER):
                    reader_closed = True
                    dropped = len(read_queue)
                    read_queue.clear()
                    if speech.qr_playing:
                        print(f"[reader panel closed — stopping mid-read, "
                              f"{dropped} queued dropped]", flush=True)
                        speech.stop()
                if qr_absent == 40:             # gone a while: forget progress
                    qr_seen.clear()
                    chat_senders.clear()

            # pump the reading queue when the voice is idle
            if read_queue and not speech.playing:
                spk, text = read_queue.popleft()
                voice, base_speed = pick_voice(spk)
                audio, speed, _ = speech.synth(text, voice, base_speed)
                speech.play(audio, qr=True)
                stats["spoken"] += 1
                last_spoken_norm = normalize_text(text)   # suppress its repeats
                kind = ("chat" if spk else
                        "chat notice" if chat is not None else "quick read")
                add_event(kind, "spoken", spk, text, voice, speed,
                          can_replay=True, shot=True)
                print(f"[{kind}{' ' + spk if spk else ''} → {voice}] "
                      f"{text[:70]}", flush=True)
            if qr is not None or chat is not None:
                continue

            state = classify(blocks)
            loading = classify_loading(blocks)
            # chrome-free lore/loading cards (title + prose, no Continue
            # hint, no UID strip, no HUD) — classify() sees the title as a
            # nameplate, so without this they're skipped as unknown speakers
            lore = None if loading else classify_lore_screen(blocks)
            if lore and normalize_speaker(lore[0]) in VOICES["characters"]:
                lore = None       # a cast member really is speaking
            # what KIND of screen this line came from — surfaced in the log
            # so a loading screen, lore card, narration and ordinary dialogue
            # are told apart instead of all reading as "spoken"
            screen_kind = "spoken"
            if loading:
                # loading-screen lore: read as narration, never as dialogue
                state = {"speaker": None, "dialogue": loading, "choices": []}
                screen_kind = "loading screen"
            elif lore:
                title, body = lore
                state = {"speaker": None, "choices": [],
                         "dialogue": f"{split_camel(title)}. {body}"}
                screen_kind = "lore card"
            elif not state["dialogue"]:
                overlay = classify_overlay(blocks)
                narration = classify_narration(blocks)
                if overlay:
                    # floating host bubble — voice set by settings.overlay_speaker
                    state = {"speaker": VOICES.get("settings", {}).get(
                                 "overlay_speaker"),
                             "dialogue": overlay, "choices": []}
                    screen_kind = "overlay"
                elif narration and (has_continue_hint(blocks)
                                    or frame_is_dark()
                                    or narration_self_certain(narration)):
                    # narration requires the Continue hint — menu banners
                    # and event-hub screens must not be narrated
                    state = {"speaker": None, "dialogue": narration, "choices": []}
                    screen_kind = "narration"
                else:
                    # OCR MISS, not necessarily a screen change: the detector
                    # drops a line on some frames (bright backgrounds). A hard
                    # reset here means every miss discards accumulated
                    # stability, so a line that never gets N consecutive hits
                    # is never spoken at all. Ride out a short gap; a real
                    # screen change lands on the branches above instead.
                    miss_streak += 1
                    if miss_streak > MISS_TOLERANCE:
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
                    # visible in the log (once per line): silent drops here
                    # made missing-speaker/missing-hint issues undiagnosable.
                    # Keyed on TEXT ONLY — the speaker read jitters too
                    # ("Goldy" / "MysteriousGoldy") and would defeat this.
                    utext = normalize_text(state["dialogue"])
                    if utext and not same_line(utext, last_unknown_logged):
                        last_unknown_logged = utext
                        add_event("skipped (unknown speaker, no Continue hint)",
                                  "skip", spk, state["dialogue"], shot=True)
                    candidate, candidate_count = None, 0
                    continue

            miss_streak = 0          # a real read: the line is on screen
            state["speaker"] = normalize_speaker(state["speaker"])
            state["dialogue"] = fix_ocr_text(state["dialogue"])
            key = (state["speaker"], normalize_text(state["dialogue"]))
            same_text = candidate is not None and key[1] == candidate[1]
            # a strict prefix is the typewriter growing, not jitter
            growing = (candidate is not None and not same_text
                       and (key[1].startswith(candidate[1])
                            or candidate[1].startswith(key[1])))
            jitter = (candidate is not None and key != candidate
                      and not growing
                      and (same_text
                           or same_line(key[1], candidate[1], 0.95))
                      # the nameplate read jitters independently of the line
                      # ("Goldy" vs "MysteriousGoldy"); only treat unrelated
                      # speakers as distinct, and only for short lines that
                      # two characters could plausibly both say
                      and (similar_speaker(key[0], candidate[0])
                           or len(key[1]) >= SHORT_LINE))
            if key == candidate:
                candidate_count += 1
                candidate_variants.append(state["dialogue"])
            elif jitter:
                # Same on-screen line, slightly different read (". mongrel."
                # vs ".mongrel."). Restarting the count here made lines
                # re-stabilize forever: they'd re-enter dedupe and log a
                # skip every few seconds. Keep counting, adopt the latest.
                candidate = key
                candidate_count += 1
                candidate_variants.append(state["dialogue"])
            else:
                candidate_variants = [state["dialogue"]]
                # if the text GREW from the previous candidate, the typewriter
                # is mid-render (it pauses at sentence ends!) — stay patient
                candidate_growing = (candidate is not None
                                     and candidate[0] == key[0]
                                     and key[1].startswith(candidate[1]))
                if not candidate_growing:
                    # genuinely new line (not the typewriter extending the
                    # current one) — anchor the VAD gate window here
                    candidate_t0 = time.monotonic()
                # Reads too different for the jitter branch to absorb (>5%
                # apart) yet clearly the same line still churning. KEPT
                # deliberately: the jitter branch and MISS_TOLERANCE cover
                # everything milder, so this narrow 0.70–0.95 band is the
                # remaining way a line can fail to stabilise, and it is the
                # only warning that would say so.
                if (candidate is not None and candidate[1] and key[1]
                        and not candidate_growing
                        and 0.70 <= difflib.SequenceMatcher(
                            None, key[1], candidate[1]).ratio() < 0.95):
                    unstable_count += 1
                    if unstable_count == 6:
                        add_event("OCR unstable — text won't stabilize",
                                  "yield", state["speaker"],
                                  state["dialogue"], shot=True)
                        unstable_count = 0
                else:
                    unstable_count = 0
                candidate, candidate_count = key, 1
            # a line ending mid-sentence is probably still typing its next
            # visual row — hold a few extra reads so we speak it whole
            complete = state["dialogue"].rstrip().endswith(
                (".", "!", "?", "…", '"', "”", "’", ")"))
            if complete and not candidate_growing:
                required = STABLE_READS
            elif complete:
                # SENTENCE STREAMING: the text is still growing but pauses at
                # a sentence boundary (HSR's typewriter pauses exactly there).
                # Speak what's complete now instead of waiting the patient +4;
                # if more text follows, it arrives as growth and the extension
                # path speaks only the remainder — after the prefix finishes.
                required = STABLE_READS + 1
            else:
                required = STABLE_READS + 4
            # `>=`, not `==`: `required` can DROP mid-count (a jittered read
            # adds the closing period, so `complete` flips and the patient
            # +4 allowance disappears). With exact equality the count sails
            # past the new threshold and the line is never spoken at all.
            # fired_norm then stops a re-fire — punctuation jitter normalizes
            # to the same string, while a genuine extension differs.
            if candidate_count < required or key[1] == fired_norm:
                continue
            fired_norm = key[1]
            candidate_growing = False
            # Speak the BEST read of this line, not whichever frame happened
            # to trip the threshold. OCR emits micro-variants of the same
            # line ("mercy is" vs "mercyis"); measured on a real capture, the
            # correct one was a 2-of-29 minority, so majority voting would
            # pick the wrong text. Score by how many tokens are real words.
            same_norm = [v for v in candidate_variants
                         if normalize_text(v) == key[1]]
            if len(same_norm) > 1:
                best = max(same_norm, key=text_quality)
                if best != state["dialogue"]:
                    state["dialogue"] = best

            new_norm = key[1]

            # Compare against the recent window. Three outcomes:
            #   dup       — jitter variant / repeat → skip
            #   extension — line grew after we spoke a stable prefix
            #               (typewriter race) → speak only the remainder
            #   new       — speak in full
            dup, ext_base = False, None
            for e in recent_lines:
                o = e["norm"]
                same_spk = similar_speaker(e["speaker"], state["speaker"])
                if not (same_spk or len(new_norm) >= SHORT_LINE):
                    continue
                # extension FIRST: with sentence streaming, a grown line's
                # remainder can be short enough that the 0.90 fuzzy check
                # below would classify the whole thing as a repeat and the
                # remainder would never be spoken
                if new_norm != o and new_norm.startswith(o):
                    if len(new_norm) - len(o) < 8:   # trivial tail = jitter
                        dup = True
                        break
                    if ext_base is None or len(o) > len(ext_base):
                        ext_base = o
                    continue
                if (difflib.SequenceMatcher(None, new_norm, o).ratio() >= 0.90
                        or new_norm in o):   # substring too: VFX flicker can
                    dup = True               # drop a row, leaving just a tail
                    break
                if (len(o) >= 30 and o in new_norm
                        and len(new_norm) - len(o) <= 25):
                    dup = True   # long recent line wrapped in OCR ghost-junk
                    break
                # fuzzy tail: OCR jitter re-reads the last visual row with a
                # near-miss ("thereetoo" vs "thereatoo") that exact substring
                # checks can't catch
                if len(o) > len(new_norm) >= 12:
                    tail = o[-(len(new_norm) + 6):]
                    if difflib.SequenceMatcher(
                            None, new_norm, tail).ratio() >= 0.85:
                        dup = True
                        break
            if dup:
                # Log only genuinely INTERESTING repeats — a line we spoke
                # long ago coming round again. A re-read of the line still
                # on screen (or the one we just spoke) is noise: it answers
                # no question and buries the real log.
                # Window persists via spoken_cache.json.
                if not (same_line(new_norm, last_spoken_norm)
                        or same_line(new_norm, last_dup_logged)):
                    add_event("repeat (deduped)" if screen_kind == "spoken"
                              else f"repeat (deduped) · {screen_kind}",
                              "skip", state["speaker"], state["dialogue"])
                last_dup_logged = new_norm
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
                {"window": [[e["speaker"], e["norm"]] for e in recent_lines],
                 "saved_at": time.time(),
                 "voiced_history": voiced_history}))

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
                    ("audio", "speed", "ms"),
                    speech.synth(speak_text, voice, base_speed))))
            synth_thread.start()

            # --- VAD gate ---
            # if the audio stream is dead we can't gate — after a grace
            # period speak anyway rather than deadlocking the whole loop
            # (commands, record stop, pause all run on this thread)
            gate_deadline = time.monotonic() + 5.0
            while (not vad_history
                   or time.monotonic() - vad_history[0][0] < VAD_LOOKBACK):
                if time.monotonic() > gate_deadline:
                    print("[VAD gate: no audio stream — speaking ungated]",
                          flush=True)
                    break
                time.sleep(0.1)
            t_stable = time.monotonic()
            # never look back past the line's on-screen appearance: audio
            # before that belongs to the PREVIOUS line's VO, not this one
            gate_since = max(t_stable - VAD_LOOKBACK,
                             candidate_t0 - VAD_LINE_MARGIN)
            # this speaker's VO has consistently been detected before, so
            # weak evidence is enough to hold our tongue
            soft = usually_voiced(state["speaker"])
            voiced = is_voiced(gate_since, soft)
            deadline = t_stable + VAD_WAIT
            while not voiced and time.monotonic() < deadline:
                time.sleep(0.05)
                voiced = is_voiced(gate_since, soft)
            if not voiced:
                quiet_deadline = time.monotonic() + 2.5
                while time.monotonic() < quiet_deadline:
                    if speech_hits(time.monotonic() - 0.4, threshold=0.25) == 0:
                        break
                    if is_voiced(gate_since, soft):
                        voiced = True
                        break
                    time.sleep(0.1)
            # center-energy layer: catches VO the VAD can't recognize as
            # speech (vocoder/robot voices) — mid-channel burst, flat side
            mid_up, side_up = center_burst(t_stable)
            # center SFX (explosions, magic flashes) are mid-panned like VO —
            # demand at least faint speechiness so booms don't count
            vad_peak = max((p for t, p in vad_history
                            if t >= max(t_stable - 1.2, gate_since)),
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
                while speech.playing and time.monotonic() < wait_until:
                    time.sleep(0.05)
            rec = voiced_history.setdefault(state["speaker"], [0, 0])
            rec[0 if voiced else 1] += 1
            if voiced:
                stats["skipped_voiced"] += 1
                skip_label = ("skipped (voiced — soft gate)" if soft
                              else "skipped (voiced)")
                if screen_kind != "spoken":
                    skip_label += f" · {screen_kind}"
                add_event(skip_label, "skip", state["speaker"],
                          state["dialogue"], shot=True)
                print(f"[voiced — skipping mid+{mid_up:.1f} side+{side_up:.1f}] "
                      f"{state['dialogue'][:60]}", flush=True)
                continue

            speech.play(spec.get("audio"))
            speed = spec.get("speed")
            stats["spoken"] += 1
            last_spoken_norm = new_norm
            yield_event_id = add_event(
                screen_kind, "spoken", state["speaker"], speak_text,
                voice, speed, can_replay=True, shot=True)
            gate_max = max((p for t, p in vad_history
                            if t >= gate_since), default=-1.0)
            tag = "" if screen_kind == "spoken" else f"{screen_kind}: "
            print(f"[{tag}{state['speaker'] or 'Narrator'} → {voice} ×{speed} "
                  f"gate={gate_max:.2f} mid+{mid_up:.1f} side+{side_up:.1f}] "
                  f"{speak_text}", flush=True)
    finally:
        speech.stop()
        video.kill()
        audio_cap.kill()
        ocr.kill()


if __name__ == "__main__":
    main()
