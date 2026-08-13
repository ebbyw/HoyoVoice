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
from profiles import (ProfileSelector, narration_self_certain,  # noqa: E402
                      split_camel)
from change_gate import ChangeGate  # noqa: E402
from anchors import (AnchorPack, crop_frame, decode_half,  # noqa: E402
                     remap_box)
from casting_filter import canonical_quotes, junk_speaker  # noqa: E402
from pronounce_names import NPC_GENDERS  # noqa: E402
from textmap import TextMap  # noqa: E402
from vad import CHUNK, SileroVAD  # noqa: E402
import voicepack  # noqa: E402
from webui import VOICE_CATALOG, start_webui  # noqa: E402
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

# Installed voice packs (dashboard "Add voice file"). The canonical copy of
# every one lives here, so casting survives the original download being
# deleted, and a replay's throwaway STATE dir starts with none of them.
CUSTOM_VOICES = STATE / "voices_custom"
UPLOADS = STATE / "captures" / "uploads"

REC_DIR = {"path": Path(VOICES.get("settings", {}).get(
    "recordings_dir", str(STATE / "recordings"))).expanduser()}
CLIPS = STATE / "captures" / "rec_clips"    # temp TTS clips, cleaned after mux

# Devices BY NAME — indices can shift (index 0 once became the Mac webcam!)
# All three selectable from the dashboard; persisted in voices.json settings.
# "output" is where OUR speech goes: "" means whatever the OS default is, so
# a second set of speakers can take the reads without moving the whole system.
DEVICES = {
    "video": VOICES.get("settings", {}).get("video_device", "ShadowCast 3"),
    "audio": VOICES.get("settings", {}).get("audio_device", "ShadowCast 3"),
    "output": VOICES.get("settings", {}).get("output_device", ""),
}


list_devices = backend.list_devices


def _game_switched(p):
    print(f"[game] layout profile → {p.label}", flush=True)
    add_event(f"game detected: {p.label}", "always")


# Which game's screen layout to read. settings.game: "auto" (default),
# "hsr", "genshin" — see tools/profiles/. Auto starts on the default
# profile and switches only on chrome unique to another game.
game = ProfileSelector(VOICES.get("settings", {}).get("game", "auto"),
                       on_switch=_game_switched)

SAMPLE_FPS = 6
STABLE_READS = 2
# OCR confidence thresholds for stabilization (classify() reports the
# weakest block that made the line; an engine without confidences reports
# a flat 0.90 — inside the neutral band below, where no rule fires).
# Measured on real captures: a
# settled line reads at 0.98+, a mid-fade / half-rendered one visibly lower.
CONF_TRUSTED = 0.97           # skip the sentence-streaming cushion read
CONF_SHAKY = 0.85             # earn one extra sighting before speaking
# Punctuation that ends a rendered line — used both to decide the typewriter
# has stopped and to find a streamable sentence boundary inside a line.
LINE_END = (".", "!", "?", "…", '"', "”", "’", ")")
# MID-LINE STREAMING: when the typewriter is still typing past a finished
# sentence, speak that sentence NOW instead of waiting out the whole line —
# the remainder arrives later as an extension. Guards: the head must be worth
# a separate utterance, and enough must be typed past the boundary to prove
# the line really is still growing (not just OCR dropping a final period).
STREAM_HEAD_MIN = 12          # normalized chars in the speakable prefix
STREAM_TAIL_MIN = 3           # chars visible past the sentence end
# consecutive frames where the detector loses an on-screen line before we
# give up on the candidate (~0.5s at 6fps). OCR misses are common on bright
# backgrounds; without this, a miss discards all accumulated stability.
MISS_TOLERANCE = 3
# how long a Quick Read / chat panel must stay undetected before we treat it
# as closed (drop the queue, stop reading). Scrolling briefly hides the
# hints the detector keys on, so a short count fires on ordinary scrolling.
READER_CLOSE_AFTER = 2.0
# A line is a repeat only against the line spoken IMMEDIATELY before it,
# and only when the same character said both. Anyone else speaking in
# between makes it a fresh line: characters really do say the same words
# again a moment later, and a 3-deep window swallowed those — the second
# "Let's go!" of a scene never got read. What the window is actually for is
# the line still on screen re-stabilizing after we spoke it, and one
# dialogue entry covers that completely — so a DIALOGUE line still clears
# the window before entering it (the maxlen-1 eviction it used to get for
# free). The extra room exists for choice reads, which append WITHOUT
# clearing: after one, the window must hold both the option texts (the
# game echoes the picked one as the next line) and the dialogue line still
# on screen. With one slot the option evicted that line, and its next OCR
# jitter variant ("Obviousk…", a mid-render "help us, bui") sailed past
# the exact-match fired_norm and an empty window and was spoken again —
# twice in the 2026-08-12 Snezhnaya sessions, right after choice reads.
DEDUP_WINDOW = 4
# the persisted window only guards against a restart mid-scene; older than
# this, the same text is a new encounter (a loading screen seen every
# session was being skipped as a repeat). voiced_history is NOT aged out —
# that prior is meant to accumulate.
SPOKEN_CACHE_TTL = 600
SHORT_LINE = 15               # short lines (normalized chars) may echo across speakers
SILENCE = 0.012               # below this amplitude is padding, not speech
# Silence spliced between sentences. The trim keeps ~33ms of Kokoro's own
# padding either side, so the audible pause is roughly this plus 66ms.
SENTENCE_GAP = 0.08

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
# ...over the last this-many observations of that speaker, not their whole
# recorded life. A lifetime ratio cannot describe a character whose voicing
# CHANGES, and in these games it changes per quest: Paimon is unvoiced for
# hundreds of lines and then fully voiced for a scene. Her lifetime tally
# makes 0.75 unreachable no matter how thoroughly the current scene voices
# her, so she was judged at full-strength thresholds through a quest that
# voiced every one of her lines. Eight, because the ratio needs enough slots
# to express 0.75 (6 of 8) while still turning over inside a single
# conversation; measured across thirteen sessions and 944 spoken lines,
# windowing changes the gate on exactly four of them — the three Paimon
# talk-overs and one Sigewinne line — and nothing else moves.
PRIOR_WINDOW = 8
# The same prior, pointed the other way, and only ever used to decide
# whether to CUT our own playback. A speaker the game has never once been
# heard to voice — across sessions, the history outlives a restart — is a
# speaker whose lines the player is relying on us for, and a scene with the
# voice acting off has nothing but music and effects to offer the VAD.
# Measured on rec_20260808_161001: 400s, 47 lines, and every speech-like
# stretch in the capture was our own playback — yet one line was cut 0.8s in
# on three 32ms chunks peaking at 0.66. Sustained speech (or a decisive
# spike) may still take the line; a blip may not.
# Three, the same count the soft prior asks for in the other direction: a
# scene with the voice acting off declares itself in its first few lines,
# and waiting longer leaves the opening of every session on the old bar.
FIRM_GATE_MIN_SPOKEN = 3      # lines seen unvoiced before the prior is trusted
VAD_FIRM_HITS = 6             # ~192ms of confident speech
# settings.late_yield: false stops HoyoVoice cutting its own playback when
# it thinks the game has started talking over it. Worth having as a switch
# rather than only a threshold: in a scene with no voice acting at all,
# every yield is a false one, and this is the one-line way to prove it.
LATE_YIELD = True
# the gate's lookback must never reach back before the line appeared on
# screen — otherwise the PREVIOUS speaker's VO tail counts as evidence that
# THIS line is voiced (false skip on fast auto-advance transitions, where
# the next subtitle lands <0.5s after the old VO ends). No backward margin:
# real VO keeps playing well past the OCR sighting, so post-appearance hits
# are always enough; only a sub-half-second grunt that ends before OCR sees
# the text would slip through, and the mid-play yield covers late starts.
VAD_LINE_MARGIN = 0.0
# How far back to listen for game VO before reading a choice option. The
# option shares the screen with a line the game may be voicing — including
# a line we deliberately stayed quiet for — so the read waits out the VO
# instead of landing on top of it.
CHOICE_VO_LOOKBACK = 1.0
# Give up on a held option after this long. Normally it is released the
# moment the line under it clears the gate, or dropped when the next line
# fires; this only catches the case where that line never gets there.
CHOICE_PENDING_TTL = 20.0
# Once the line under it has cleared the gate AND the option has left the
# screen, it waits this long for a gap in the talking before being dropped
# — past that, the read would arrive as an interruption several beats
# late. While the prompt is still visible the clock refreshes every frame:
# the game is paused waiting for the player, so no wait is "late", and
# counting from arming raced the under-line's own voiceover (armed at
# gate-fire ≈ VO start, so every option under a >8s voiced line lost).
CHOICE_STALE_AFTER = 8.0
# How long to keep looking for a line under the option before giving up and
# reading it anyway. There may be nothing to wait for: a wordless "..." (or
# a beat with the box empty) normalizes to nothing, and the "has the line
# below fired yet" test can never match an empty line — which held the
# option forever and it went unread. Long enough for a typing line to show
# up and be adopted instead.
CHOICE_EMPTY_GRACE = 2.0
# Beat of silence between the line above and the option, once our own voice
# has stopped. The option is the player answering, and answering the instant
# the other character's last syllable ends reads as one breathless run —
# both halves are ours, in different voices, with nothing between them. Long
# enough to hear as a turn taken, short enough that the player has usually
# not clicked through yet.
CHOICE_LEAD_IN = 0.5

vad_history = deque(maxlen=400)
vad_lag = {"s": 0.0}          # how far the VAD tail-reader trails the live edge
# speaker -> [times the game voiced them, times we spoke for them], over
# that speaker's last PRIOR_WINDOW observations. Derived from voiced_recent
# and kept in this shape because it is what the gates, the log line and the
# persisted state all read.
voiced_history = {}
# speaker -> the outcomes themselves, oldest first ("v" voiced, "s" spoken).
# The window is the source of truth; the counts above are a view of it.
voiced_recent = {}


def record_voiced(speaker, was_voiced):
    """Add one observation and roll the window forward."""
    w = voiced_recent.setdefault(speaker, deque(maxlen=PRIOR_WINDOW))
    w.append("v" if was_voiced else "s")
    voiced_history[speaker] = [sum(1 for c in w if c == "v"),
                               sum(1 for c in w if c == "s")]


def seed_window(speaker, v, s):
    """Rebuild a window from legacy lifetime counts, preserving the ratio.

    State written before the window existed is a pair of lifetime tallies
    with no order in it, so the honest reconstruction is the ratio it
    implies. A character with a long unvoiced history seeds to an all-spoken
    window, which is what their record actually says — and it re-arms the
    firm gate for them, which is the protection that record earns.
    """
    n = v + s
    nv = min(PRIOR_WINDOW, round(PRIOR_WINDOW * v / n)) if n else 0
    w = deque("v" * nv + "s" * (PRIOR_WINDOW - nv) if n else "",
              maxlen=PRIOR_WINDOW)
    voiced_recent[speaker] = w
    voiced_history[speaker] = [sum(1 for c in w if c == "v"),
                               sum(1 for c in w if c == "s")]
# per-block stereo energy: (t, mid_dB, side_dB). Game VO is center-panned
# (mid), music/ambience is wide (side) — a mid-only burst at line start is
# voiceover even when the VAD can't recognize the voice as speech.
energy_history = deque(maxlen=400)
ENERGY_MID_BURST = 7.0        # dB over pre-line baseline
ENERGY_MID_OVER_SIDE = 5.0    # mid must rise this much more than side
ENERGY_SIDE_FLAT = 2.5        # AND side must stay flat — music swells raise
                              # both channels; VO raises only the center
# Above this much mid-over-side, the burst is decisive on its own and neither
# the side-flat cap nor the speechiness floor applies. Both guards exist to
# keep center-panned SFX out; a burst this lopsided is not an explosion,
# which is broadband. Measured over 1107 spoken and 46 known-voiced lines
# from thirteen sessions: mid-over-side runs p50 0.5 / p90 4.2 on lines we
# read aloud and p50 8.8 / p90 11.4 on lines the VAD independently called
# voiced, so 8 sits between the populations rather than inside either. At
# this cut 18 of 1107 spoken lines (1.6%) become voiced, and 27 of the 46
# known-voiced ones are reachable without the VAD agreeing at all.
ENERGY_DECISIVE_OVER_SIDE = 8.0
# A decisive burst with NO speechiness at all must also hold its rise this
# long. The dialogue-advance click is mid-panned against quiet music and
# scored mid+13.0 side+1.8 — decisive on the numbers — but was over in
# ~0.2s of elevated windows; a one-word VO line holds ~0.5s. 0.35 sits
# between them with the overlap-inflation (~0.13s) already spent. Only
# applied when the VAD saw nothing (peak < 0.15) and the speaker has no
# usually-voiced record: with either corroboration the burst is believed
# as before, so the measured vocoder-VO cases keep their skips.
ENERGY_SUSTAIN_S = 0.35

# --- shared state for the dashboard ---
events = deque(maxlen=200)
event_seq = {"n": 0}
# `parts` are the recording's video segments — a capture respawn has to open
# a new one (see respawn_capture) — each stamped with the wall-clock offset
# it started at, which is what lets the mux measure the gaps between them.
recording = {"on": False, "t0": None, "clips": [], "raw": None,
             "parts": []}
record_request = {"want": None}
device_request = {"want": None}
# set by casting edits (assign/delete): the OCR lexicon file is stale.
# Only DASHBOARD edits raise it — auto-cast also adds characters, but
# restarting the daemon every time a new NPC speaks would be churn for a
# name the recognizer already managed to read once.
lexicon_stale = {"flag": False}
unknown_speakers = set()
if UNKNOWN_LOG.exists():
    unknown_speakers.update(
        n.strip() for n in UNKNOWN_LOG.read_text().splitlines() if n.strip())
commands = queue.Queue()
# last "Add voice file" outcome, polled by the dashboard: verification runs
# on the orchestrator thread (it needs the TTS engine), so the upload
# request can only answer "accepted", not "worked"
voice_import = {"state": "", "voice": None, "msg": ""}
# start paused — resume from the dashboard (replays auto-resume)
observing = {"on": os.environ.get("HOYOVOICE_AUTORESUME") == "1"}
stats = {"spoken": 0, "skipped_voiced": 0, "yielded": 0, "always_voiced": 0,
         "fused_reads": 0, "snapped": 0,
         "synth_ms": deque(maxlen=100), "ocr_ms": deque(maxlen=200),
         "anchor_ms": deque(maxlen=200), "started": time.time()}

# UI anchors — pixel evidence of game chrome, matched before/without OCR.
# Phase (a) of plans/ANCHORS.md made matches log-only; phase (b) — behind
# settings.anchor_roi, off by default — lets a matched anchor's ROI crop
# the frame before OCR, because detector cost scales with area. The rules
# that must hold (paid for once already, by the change gate): absence of
# an anchor is weak evidence, so no match → full frame, today's behavior;
# and a bounded crop run, because a wrong "crop here" latches exactly like
# a wrong "unchanged" — text appearing outside the crop is invisible, and
# nothing inside the crop will ever disagree. Packs are cached per game; a
# game without anchor data gets an empty pack and zero behavior change.
anchor_packs = {}
anchor_state = {"enabled": True, "roi": False, "matched": (),
                "crop_run": 0, "crops": 0}
# Consecutive cropped reads before one full-frame read re-arms the set
# (~2s at 6fps) — the same medicine, and the same number, as the change
# gate's MAX_SKIP_RUN, and for the same reason.
ANCHOR_MAX_CROP_RUN = 12
CROP = FRAME.parent / "live_crop.png"


def match_anchors(profile_name):
    """Match the current frame against the active game's anchor pack, log
    when the SET of matched anchors changes, and return the ROI the
    matched set implies (Vision-normalized union, or None). Called only on
    frames about to pay for a fresh OCR — a gate-unchanged frame provably
    didn't change where text was, and chrome moves even less than text."""
    pack = anchor_packs.get(profile_name)
    if pack is None:
        pack = anchor_packs[profile_name] = AnchorPack(profile_name)
    if not pack.anchors:
        return None
    t0 = time.perf_counter()
    try:
        hits = pack.match(decode_half(FRAME))
    except Exception:
        return None                 # a torn frame is OCR's problem, not ours
    stats["anchor_ms"].append(int((time.perf_counter() - t0) * 1000))
    matched = tuple(sorted(hits))
    if matched != anchor_state["matched"]:
        anchor_state["matched"] = matched
        shown = "  ".join(f"{n}={hits[n]:.2f}" for n in matched) or "none"
        print(f"[anchors] {profile_name}: {shown}", flush=True)
    return pack.roi_for(matched)


def frame_is_dark():
    """True black narration screens sometimes show only a ▼ glyph and no
    Continue text — accept them by checking the frame is nearly all black."""
    try:
        from PIL import Image
        img = Image.open(FRAME).convert("L")
        img.thumbnail((48, 48))
        # getdata() is deprecated and goes away in Pillow 14; its replacement
        # only exists from Pillow 11.3, so keep the old call as the fallback
        # rather than pinning a floor the rest of the app doesn't need.
        data = getattr(img, "get_flattened_data", None) or img.getdata
        px = list(data())
        return sum(px) / len(px) < 28
    except Exception:
        return False


# raw blocks of the current frame (debug), plus the subset the last read
# built its line from — what the change gate watches
latest_ocr = {"blocks": None, "text_blocks": None}
lost_frames = {"n": 0}            # frames the OCR daemon couldn't read at all
# skips OCR while the text region is pixel-identical; see tools/change_gate.py
# for the contract (an "unchanged" verdict replays the previous blocks — it
# must never skip the iteration, or stabilization counting stalls)
gate = ChangeGate()


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
              can_replay=False, shot=False, extend=False):
    """Append a log event — or, with `extend`, GROW the one just written.

    A line is handled twice by design: the first finished sentence goes
    through, then the typewriter's remainder follows as an extension. For a
    line that gets spoken those are two real events, because two pieces of
    audio were played. For a line that gets SKIPPED they are one fact
    written twice — "we saw this and stayed quiet" — and they filled the log
    with pairs whose only difference was the tail of the sentence
    (2026-08-12 18:10-18:21: 44 of 77 events were a skip and its own
    growth). With `extend`, a skip whose text simply grew rewrites the row
    it grew from, so the log keeps one row per line carrying the FULLEST
    text. Same action and same speaker required, and the old text has to be
    a prefix of the new one — anything else is a different fact.
    """
    if extend and events:
        prev = events[-1]
        pn, nn = normalize_text(prev["text"]), normalize_text(text)
        if (prev["action"] == action and prev["speaker"] == speaker
                and pn and nn.startswith(pn)):
            prev["text"] = text[:160]
            return prev["id"]
    event_seq["n"] += 1
    said = tts_text(text)[:160]
    events.append({
        "id": event_seq["n"], "t": datetime.now().strftime("%H:%M:%S"),
        # what the synthesizer was handed, when that isn't the line as
        # written. Respellings and delivery fixes are invisible everywhere
        # else by design, which makes "is the fix even running?" unanswerable
        # from a session log — the one question a bug report has to settle.
        "speaker": speaker, "text": text[:160], "voice": voice,
        "spoken": said if said != text[:160] else None,
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
        "ocr_skipped": gate.skips,
        "anchor_avg_ms": (int(sum(stats["anchor_ms"])
                              / len(stats["anchor_ms"]))
                          if stats["anchor_ms"] else 0),
        "roi_crops": anchor_state["crops"],
        "lost_frames": lost_frames["n"],
        "fused_reads": stats["fused_reads"],
        "snapped": stats["snapped"],
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


def center_energy_voiced(mid_up, side_up, vad_peak):
    """Is this centre-channel burst voiceover rather than a sound effect?

    Game VO is mixed to the stereo centre; music and ambience are wide. The
    side-flat cap and the speechiness floor both exist to keep centre-panned
    SFX out — but a burst this lopsided is not an explosion, which is
    broadband, so above ENERGY_DECISIVE_OVER_SIDE neither applies. Kept as a
    pure function so tools/test_center_energy.py can pin it.
    """
    if mid_up < ENERGY_MID_BURST or mid_up - side_up < ENERGY_MID_OVER_SIDE:
        return False
    if mid_up - side_up >= ENERGY_DECISIVE_OVER_SIDE:
        return True
    return side_up <= ENERGY_SIDE_FLAT and vad_peak >= 0.15


def usually_voiced(speaker):
    """True once a speaker has a consistent record of the game voicing them."""
    v, s = voiced_history.get(speaker, (0, 0))
    return v >= SOFT_GATE_MIN_VOICED and v >= SOFT_GATE_RATIO * (v + s)


def never_voiced(speaker):
    """True once a speaker has a consistent record of the game NOT voicing
    them — every line so far has been ours to read."""
    v, s = voiced_history.get(speaker, (0, 0))
    return v == 0 and s >= FIRM_GATE_MIN_SPOKEN


def vad_evidence(since, soft=False):
    """(strong hits, weak hits, peak) in the VAD history since `since`.

    Split out of is_voiced so a decision can SAY what it heard: a yield
    that cuts a line off mid-sentence is indistinguishable in the log from
    one that was right to fire, and the two want opposite fixes."""
    weak_threshold = VAD_SOFT_THRESHOLD if soft else VAD_WEAK_THRESHOLD
    strong = weak = 0
    peak = 0.0
    for t, p in vad_history:
        if t >= since:
            if p >= VAD_THRESHOLD:
                strong += 1
            if p >= weak_threshold:
                weak += 1
            peak = max(peak, p)
    return strong, weak, peak


def is_voiced(since, soft=False, firm=False):
    """soft: this speaker is usually voiced, so accept weaker evidence.
    firm: the game has never been heard to voice them, and this evidence
    would cut a line we are already reading — demand sustained speech."""
    weak_hits = VAD_SOFT_HITS if soft else VAD_WEAK_HITS
    strong, weak, peak = vad_evidence(since, soft)
    if firm:
        return strong >= VAD_FIRM_HITS or peak >= VAD_PEAK
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
# decorative glyphs TTS would read aloud ("tilde") or spell out. Asterisks
# are NOT in here: *cough* is a stage direction, handled at synthesis.
_STRIP_GLYPHS = re.compile(r"[~♪♡♥★☆]+")
# *cough*, *sigh* — a sound the character makes, written out. Kept through
# OCR repair with a canonical spelling so the TTS path can act on it.
_STAGE_DIRECTION = re.compile(r"[*＊]\s*([^*＊]{1,24}?)\s*[*＊]")
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
# Interjections the phonemizer spells letter-by-letter, or reads as the wrong
# vowel → the nearest spelling it says correctly. Checked with
# tools/pronounce_names.py, which runs the same phonemizer Kokoro does:
#   Shh   ˌɛsˌAʧˈAʧ ("S-H-H")  → shush  ʃˈʊʃ
#   Hmph  ˌAʧˌɛmpˌiˈAʧ         → humph  hˈʌmf
#   Tsk   tˈəsk ("tuhsk")      → tisk   tˈɪsk
#   Tch   tˌiːsˌiːˈeɪtʃ ("T-C-H" on Windows; ʧ, a bare consonant, on macOS)
#         → tisk, the same tut "Tsk" already maps to — Kokoro can't click
#   Uhm   ˈum ("oom")          → um     ˈʌm
#   Ugh   ˈʌh on macOS, ˈʌɡ on Windows → ug ˈʌɡ on both
#   Urgh  ˈɜɹɡ ("erg", a word)         → ug ˈʌɡ on both
#   Aah   fine, but Aaah is ˈææə       → ah     ˈɑ
# "Pfft" is deliberately absent: it phonemizes to ˈft, a short puff that is
# roughly the right noise, and the "pfff" respelling this list used to carry
# came out as "P-E-F-E-F" — worse than leaving it alone.
_INTERJECTIONS = [
    (re.compile(r"\bshh+\b", re.IGNORECASE), "shush"),
    (re.compile(r"\bhmph+\b", re.IGNORECASE), "humph"),
    (re.compile(r"\btsk\b", re.IGNORECASE), "tisk"),
    (re.compile(r"\btch+\b", re.IGNORECASE), "tisk"),
    (re.compile(r"\buh+m+\b", re.IGNORECASE), "um"),
    (re.compile(r"\bugh+\b", re.IGNORECASE), "ug"),
    (re.compile(r"\bu+r+gh+\b", re.IGNORECASE), "ug"),
    (re.compile(r"\ba+h+\b", re.IGNORECASE), "ah"),
]

# A stammer is written as a repeated initial — "W-what", "N-no", "A-aah" —
# and the phonemizer reads that lone letter as its NAME: "DOUBLE-YOU-what",
# "EN-no", "AY-ah". Spelling the stammer as a syllable fixes it. Only when
# the initial matches the word it precedes, so "X-ray", "T-shirt" and "e-mail"
# are left alone.
#
# The initial can be the whole ONSET rather than one letter — "Wh-What's",
# "Sh-She's", "Th-That's", "Str-Strange" — and then it is spelled out letter
# by letter: "Wh-What's" is dˌʌbᵊljˌuˈAʧ—wˌʌts, "DOUBLE-YOU-AITCH-what's".
# Same repair, with the same "uh" ending: "Whuh-What's" (wˈʌ—wˌʌts).
# A multi-letter onset has to be ALL CONSONANTS, which is what separates a
# stammer from an ordinary prefix that happens to repeat the word's opening:
# "re-read", "co-conspirator" and "de-dent" all carry a vowel and are left
# alone. An all-caps onset is title-cased first — "WHuh" is read as letters
# again (dˈʌbᵊljuhˌʌ), "Whuh-WHAT!" is wˈʌwˈʌt.
#
# The dash can be an EM dash: Genshin writes "A—Ahh!" that way and the
# hyphen-only pattern walked straight past it, so the lone "A" was read as
# the letter. Any of the dashes count, and all of them are respelled to a
# plain hyphen — including for the letters whose reading is left alone, since
# the dash is a fault of its own (see _unstutter). A spaced dash (" — ", the
# punctuation kind) can't match: the letter and the dash have to be adjacent.
_STUTTER = re.compile(r"\b([A-Za-z]{1,3})[-‐‑–—]([A-Za-z]+)")
# E/I/O already read as sounds rather than names ("I-I'm" → ˌIˌIm), and every
# respelling tried for them was worse. A and U are not: "A-" is "AY", "U-" is
# "YOU".
_STUTTER_KEEP = "eio"
_STUTTER_TAIL = {"a": "h", "u": "h"}
_VOWELS = set("aeiou")


def _unstutter(m):
    """A letter that keeps its own reading still gets the dash normalized.

    An em dash is punctuation to the phonemizer, a hyphen is not: espeak —
    the g2p behind kokoro-onnx, so this is the Windows reading — says
    aɪ ɪts for "I—It's" (two words, a punctuation pause between them: "Aye.
    It's Enjou!?") and aɪɪts for "I-It's", the run-together the stammer
    actually is. Misaki reads both as ˌI—ˌɪts, the same break "Wuh-what"
    already gets, so macOS is unchanged either way.
    """
    onset, word = m.group(1), m.group(2)
    if onset.lower() != word[:len(onset)].lower():
        return m.group(0)
    if len(onset) == 1:
        if onset.lower() in _STUTTER_KEEP:
            return f"{onset}-{word}"
        return f"{onset}{_STUTTER_TAIL.get(onset.lower(), 'uh')}-{word}"
    if _VOWELS & set(onset.lower()):     # a prefix ("re-read"), not a stammer
        return m.group(0)
    return f"{onset.capitalize() if onset.isupper() else onset}uh-{word}"


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


def mark_stage_directions(s):
    """Normalize *cough* to one spelling and drop asterisks used as decoration.

    A paired asterisk around a short phrase is the games' notation for a
    sound the character makes rather than a word they say; an unpaired one
    is emphasis or ornament, and TTS reads it as "asterisk"."""
    s = _STAGE_DIRECTION.sub(lambda m: f"\0{m.group(1)}\0", s)
    s = re.sub(r"[*＊]+", "", s)
    return s.replace("\0", "*")


def fix_ocr_text(s):
    s = re.sub(r"[’‘`´ʼ]", "'", s)      # normalize apostrophe glyph variants
    s = repair_punctuation(s)           # before word fixes: \b needs spaces
    s = repair_runons(s)                # 'mercyis' → 'mercy is'
    for pat, rep in _OCR_FIXES:
        s = pat.sub(rep, s)
    s = _STRIP_GLYPHS.sub("", s)
    s = mark_stage_directions(s)
    s = _CONTRACTION_RE.sub(
        lambda m: (_CONTRACTIONS[m.group(0).lower()].capitalize()
                   if m.group(0)[0].isupper()
                   else _CONTRACTIONS[m.group(0).lower()]), s)
    # user lexicon for proper nouns OCR keeps mangling ("lason" → "Iason")
    for wrong, right in VOICES.get("settings", {}).get("text_fixes", {}).items():
        s = re.sub(rf"\b{re.escape(wrong)}\b", right, s, flags=re.IGNORECASE)
    return re.sub(r"  +", " ", s).strip()


def spoken_form(text):
    """Apply settings.pronunciations — what the TTS hears, not what we log.

    Kokoro phonemizes English spelling rules, so pinyin and romaji names come
    out wrong in predictable ways ("Xiao" → "ZY-ah-oh"); the respellings live
    in voices.json, audited by tools/pronounce_names.py. Matching is
    case-insensitive so OCR case jitter can't miss a name — a name that is
    ALSO an ordinary English word ("Gaming") goes in
    settings.pronunciations_exact, or every "gaming" in prose is respelled too.

    Interjections and stammers are respelled here for the same reason and by
    the same rule: it is what the line SOUNDS like, not what it says, so the
    log, dedupe and casting all keep "Shh" and "W-what" as written. The
    "synth heard:" line in the log is where the respelling shows up.
    """
    settings = VOICES.get("settings", {})
    exact = set(settings.get("pronunciations_exact", []))
    for word, spoken in settings.get("pronunciations", {}).items():
        # a key ending in "." ("Ms.") can't take a trailing \b: between the
        # period and the following space there is no word boundary, so the
        # entry would never fire. The period is its own right edge.
        tail = r"\b" if word[-1:].isalnum() else ""
        text = re.sub(rf"\b{re.escape(word)}{tail}", spoken, text,
                      flags=0 if word in exact else re.IGNORECASE)
    for pat, rep in _INTERJECTIONS:
        text = pat.sub(_keep_case(rep), text)
    return _STUTTER.sub(_unstutter, text)


# what mark_stage_directions() leaves behind, and the extensions that make a
# settings.sound_effects value a file to play rather than words to speak
_MARKED_DIRECTION = re.compile(r"\*([^*]+)\*")
_EFFECT_SUFFIXES = (".wav", ".mp3", ".flac", ".ogg", ".oga", ".aiff", ".aif")


def speech_parts(text):
    """A line split into ("say", text) and ("play", sound file) pieces.

    `settings.sound_effects` maps the inside of a stage direction to either an
    audio file — Kokoro can't cough, so the only convincing cough is a
    recording — or to a respelling to speak in its place ("cough": "Ahem.").
    A direction with no entry keeps the old behavior and is read as the bare
    word, which for "*sigh*" is what you want anyway.
    """
    effects = {str(k).strip().lower(): v for k, v in
               VOICES.get("settings", {}).get("sound_effects", {}).items()}
    parts, at = [], 0

    def say(s):
        s = re.sub(r"\s+", " ", s.replace("*", " ")).strip()
        if s:
            parts.append(("say", s))

    for m in _MARKED_DIRECTION.finditer(text):
        repl = effects.get(m.group(1).strip().lower())
        if repl is None:
            continue                        # unmapped: stays in the spoken text
        say(text[at:m.start()])
        if str(repl).lower().endswith(_EFFECT_SUFFIXES):
            parts.append(("play", str(repl)))
        else:
            say(str(repl))
        at = m.end()
    say(text[at:])
    return parts


# The health/legal notice both games show at startup. Matched on content, not
# position: it renders as a chrome-free title + prose card, which is exactly
# what a real lore card looks like, so nothing structural tells them apart.
# Several markers rather than one, because a single OCR slip shouldn't hand
# you the whole wall of text read aloud — and it is a wall, ~150 words.
# Kept short deliberately: "epilepticseizures" loses to one l/I slip inside a
# word, which fix_ocr_text only repairs for standalone letters. "epilep" does
# not, and nothing in either game's script says it.
#
# All medical, none from the title. "beforeplaying" would catch "READ BEFORE
# PLAYING" too, but it also catches "Read the notice before playing" — and
# silently eating a real line is a worse failure than reading a four-word
# title, which is all the title alone would ever cost.
_NOTICE_MARKERS = (
    "epilep", "consultyourphysician", "seekmedicalattention",
    "immediatelystopplaying",
)


def boot_notice(text):
    """True for the epilepsy/health warning shown before the title screen."""
    n = normalize_text(text)
    return any(m in n for m in _NOTICE_MARKERS)


def sentences(text):
    """A line split at sentence ends, punctuation kept.

    Kokoro predicts prosody for a whole utterance in one pass, so a long line
    degrades its own opening: "Huh?! You… You're Paimon, travel companion of
    the great hero Ebby!" hisses through the interjection and into the word
    after it, while "Huh?!" and the rest of the line each come out clean
    synthesized alone. Measured by bisection against the failing line — it is
    not the "!?", not the ellipsis, and not the name's respelling, all of
    which A/B'd identical. Short utterances survive; long ones don't.

    "…" is deliberately not a boundary, exactly as in stream_prefix(): in
    these games it's a pause the typewriter runs straight through, and
    splitting there would chop one spoken thought in half.
    """
    out, at = [], 0
    for m in _SENT_END.finditer(text):
        head = text[at:m.end()]
        abbr = _ABBREV_RE.search(head.rstrip())
        if abbr and abbr.group(1).lower() in _ABBREV:
            continue                       # "Mr. Ito" is not two sentences
        out.append(head.strip())
        at = m.end()
    tail = text[at:].strip()
    if tail:
        out.append(tail)
    return out or [text]


def tts_text(text):
    """The whole TTS-side transform of a line, flattened back to one string
    for logs: respellings, and stage directions with a sound file shown as
    [path] where the synthesizer is handed silence and the file is spliced in
    instead."""
    return " ".join(v if kind == "say" else f"[{v}]"
                    for kind, v in speech_parts(spoken_form(text)))


def center_burst(t_line):
    """(mid_delta_dB, side_delta_dB, sustain_s): energy rise after the line
    appeared vs the pre-line baseline, and for how long the mid channel held
    that rise. VO shows as mid rising with side staying flat.

    sustain_s is what tells a centre-panned SFX transient from voiceover
    when neither carries any speechiness: the dialogue-advance click that
    skipped "I was a disappointment." (2026-08-12, mid+13.0 side+1.8,
    VAD peak 0.00) is over in a few 32ms blocks, while even a one-word VO
    line holds its rise for half a second. Counted as smoothed 160ms
    windows sitting ENERGY_MID_BURST over baseline — overlapping windows,
    so a transient's tail inflates the count by up to ~0.13s, which the
    threshold accounts for."""
    base_m = [m for t, m, s in energy_history if t_line - 9 <= t < t_line - 1.5]
    base_s = [s for t, m, s in energy_history if t_line - 9 <= t < t_line - 1.5]
    cur = [(m, s) for t, m, s in energy_history if t >= t_line - 1.2]
    if len(base_m) < 30 or len(cur) < 8:
        return 0.0, 0.0, 0.0
    base_m.sort()
    base_s.sort()
    bm, bs = base_m[len(base_m) // 2], base_s[len(base_s) // 2]
    mids = [m for m, s in cur]
    sides = [s for m, s in cur]

    def smoothed(xs):
        return [sum(xs[i:i + 5]) / 5 for i in range(max(1, len(xs) - 4))]

    sm, ss = smoothed(mids), smoothed(sides)
    sustain = sum(1 for x in sm if x - bm >= ENERGY_MID_BURST) * 0.032
    return max(sm) - bm, max(ss) - bs, sustain


def normalize_text(s):
    return "".join(c for c in s.lower() if c.isalnum())


# A sentence end is terminal punctuation (plus any closing quote/bracket)
# followed by whitespace and the start of a new sentence. "3.5" fails the
# lookahead, "Mr. Ito" is caught by _ABBREV. "…" is deliberately NOT a
# boundary: in these games it is a pause the typewriter runs straight
# through, so splitting there would chop one spoken thought in half.
_SENT_END = re.compile(r'[.!?]["”’)]?(?=\s+["“‘(]?[A-Z0-9])')
_ABBREV = {"mr", "mrs", "ms", "dr", "st", "sr", "jr", "vs", "etc", "no"}
_ABBREV_RE = re.compile(r"([A-Za-z']+)[.!?]$")


def stream_prefix(s):
    """Longest complete-sentence prefix of a line still being typed, or None.

    HSR/Genshin type a line out over a second or more; waiting for the last
    character means the read always lags the game. Once a sentence inside the
    line has closed we can speak that much immediately — the rest is spoken
    afterwards through the extension path, which diffs against what we said.
    """
    best = None
    for m in _SENT_END.finditer(s):
        head = s[:m.end()]
        if len(s[m.end():].strip()) < STREAM_TAIL_MIN:
            continue                       # nothing typed past the boundary
        abbr = _ABBREV_RE.search(head.rstrip())
        if abbr and abbr.group(1).lower() in _ABBREV:
            continue
        if len(normalize_text(head)) >= STREAM_HEAD_MIN:
            best = head.rstrip()
    return best


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


# An option's tail has to be this many characters before it may stand in for
# the whole option: "Yes." and "No." differ only in their first word, and
# collapsing two short options onto each other would silently drop one.
OPTION_TAIL_MIN = 12


def same_option(a, b):
    """same_line for choice options, and blind to the first word.

    Vision fuses Genshin's choice bullet into the first word of the option
    and returns a different blob almost every pass. One static prompt —
    "I'll go rescue them." — came back as T'ul / @ILL / I'I / TIL / TU /
    rIgo / TIl across ten reads in 40s (2026-08-12 15:48, shots 795-804),
    the screen never changing: the gate re-OCRs because the controller
    hints beside the bubble flicker, and the mangling lands on "I'll" every
    time. An option is short, so a wrong first word drags the whole-string
    ratio under same_line's 0.9 (tu… vs rI… is 0.86) — the prompt then
    reads as a NEW option, re-arms and is spoken a second and third time.
    The tail is the part OCR gets right, so it decides.
    """
    if same_line(normalize_text(a), normalize_text(b)):
        return True
    ta, tb = option_tail(a), option_tail(b)
    return (len(ta) >= OPTION_TAIL_MIN and len(tb) >= OPTION_TAIL_MIN
            and same_line(ta, tb))


def option_tail(s):
    """An option's normalized text with its first word dropped."""
    return normalize_text(" ".join(s.split()[1:]))


def remember_line(recent_lines, speaker, norm, stack=False):
    """Put a line into the dedupe window. A DIALOGUE line replaces the
    window — "immediately before" is the contract (see DEDUP_WINDOW), and
    replacing is what lets a character repeat their own line once anyone
    else has spoken in between. A choice read stacks alongside instead
    (stack=True): after one, the window must hold both the option texts
    (the game echoes the picked one as the next line) and the dialogue
    line still on screen — with a one-slot window the option evicted that
    line, and its next OCR jitter variant was spoken a second time."""
    if not stack:
        recent_lines.clear()
    recent_lines.append({"speaker": speaker, "norm": norm})


def window_verdict(new_norm, speaker, recent_lines):
    """Judge a settled line against the recent window. Returns
    (dup, ext_base):

        dup       — jitter variant / repeat → skip
        ext_base  — the prefix we already spoke: the line grew after we
                    spoke a stable prefix (typewriter race), so only the
                    remainder is new
        neither   — a new line, speak it in full
    """
    ext_base = None
    for e in recent_lines:
        o = e["norm"]
        same_spk = similar_speaker(e["speaker"], speaker)
        # SAME CHARACTER only. A repeat is one character saying the same
        # words twice running; two characters saying the same words is a
        # scene, not a duplicate, and it has to be read for both. An
        # unknown nameplate on either side still counts as the same
        # character: the plate flickers out mid-line, and the re-read that
        # follows is the same line, not a new speaker's.
        if not (same_spk or not e["speaker"] or not speaker):
            continue
        # extension FIRST: with sentence streaming, a grown line's
        # remainder can be short enough that the 0.90 fuzzy check below
        # would classify the whole thing as a repeat and the remainder
        # would never be spoken.
        #
        # The same-character gate above is what protects this: a line grows
        # by typewriter and the typewriter never changes speaker mid-line,
        # so before that gate covered extensions too, Paimon's "And then?"
        # made Leyla's "And then I blossomed into a healthy vegetable…" look
        # like a continuation of it, and Leyla was cut off at the front.
        if new_norm != o and new_norm.startswith(o):
            if len(new_norm) - len(o) < 8:   # trivial tail = jitter
                return True, None
            if ext_base is None or len(o) > len(ext_base):
                ext_base = o
            continue
        if (difflib.SequenceMatcher(None, new_norm, o).ratio() >= 0.90
                or new_norm in o):   # substring too: VFX flicker can
            return True, None        # drop a row, leaving just a tail
        if len(o) >= 30 and o in new_norm and len(new_norm) - len(o) <= 25:
            return True, None   # long recent line wrapped in OCR ghost-junk
        # pure insertion: the new line IS the recent line with junk spliced
        # into the middle — an OCR ghost box re-reading a row it already
        # read lands between the real rows and breaks the contiguity the
        # substring check above needs ("…leave Paimon [Wow, its so majestic
        # Just Flyin] out of breath"). A 25-char splice into an 83-char line
        # also scores 0.869, under the 0.90 ratio. Only equal/delete opcodes
        # means the recent line survives IN ORDER and IN FULL; ≤3 equal runs
        # keeps this to real splices — a coincidental subsequence of a
        # genuinely new line would be shredded into many fragments.
        if len(o) >= 30 and len(o) < len(new_norm) <= 2 * len(o):
            ops = difflib.SequenceMatcher(None, new_norm, o,
                                          autojunk=False).get_opcodes()
            if (all(op[0] in ("equal", "delete") for op in ops)
                    and sum(1 for op in ops if op[0] == "equal") <= 3):
                return True, None
        # fuzzy tail: OCR jitter re-reads the last visual row with a
        # near-miss ("thereetoo" vs "thereatoo") that exact substring
        # checks can't catch
        if len(o) > len(new_norm) >= 12:
            tail = o[-(len(new_norm) + 6):]
            if difflib.SequenceMatcher(None, new_norm, tail).ratio() >= 0.85:
                return True, None
    return False, ext_base


def normalize_speaker(speaker):
    """Normalize quote glyphs but KEEP quotes: a character literally named
    '"Narrator"' is distinct from true narration. Fuzzy-match only within the
    same quoting class so the two can't merge."""
    if not speaker:
        return None
    speaker = speaker.strip()
    for a, b in (("“", '"'), ("”", '"'), ("‘", "'"), ("’", "'")):
        speaker = speaker.replace(a, b)
    # OCR reads the opening quote of a quoted plate with the wrong glyph
    # often enough that `'Tenoyollotzin"` cast as a SECOND character next
    # to `"Tenoyollotzin"` — canonicalize both ends before the quoting
    # class is decided, so the fuzzy match below can see them as one
    speaker = canonical_quotes(speaker)
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


SMOKE_LINE = "Voice check, one two three."


def release_voice(voice_id):
    """Undo every reference to a voice that no longer exists.

    A dangling id is not a cosmetic problem: the character cast to it goes
    silent at the moment they speak, and a *default* pointing at one takes
    every unnamed speaker or every narration line with it. Characters go
    back to the auto-caster (which claims a packaged voice on their next
    line); defaults are put back to a packaged voice outright."""
    for char, c in list(VOICES["characters"].items()):
        if c.get("voice") == voice_id:
            VOICES["characters"].pop(char)
    fallback = {"female": VOICE_POOLS["female"][0],
                "male": VOICE_POOLS["male"][0], "narrator": "bm_george"}
    for slot, voice in VOICES.get("defaults", {}).items():
        if voice == voice_id:
            VOICES["defaults"][slot] = fallback.get(slot,
                                                    VOICE_POOLS["female"][0])


def register_custom_voices(speech):
    """Hand every installed voice pack to the TTS engine at startup.

    A pack whose file has gone missing is dropped rather than left to fail
    at the moment a character speaks: an entry that can't synthesize is
    worse than no entry, because the character it is cast to goes silent
    with the reason buried in a traceback."""
    packs = VOICES.get("custom_voices", {})
    dropped = False
    for voice_id in list(packs):
        path = (STATE / packs[voice_id]["file"]).resolve()
        try:
            speech.tts.register_voice(voice_id, path)
            print(f"[voice] {voice_id} ← {path.name}", flush=True)
        except Exception as exc:
            packs.pop(voice_id)
            release_voice(voice_id)
            dropped = True
            print(f"[voice] dropped {voice_id}: {exc}", flush=True)
    if dropped:
        VOICES_PATH.write_text(json.dumps(VOICES, indent=2, ensure_ascii=False))


def install_voice(speech, src, name=None, key=None, source=None):
    """Verify a voice-pack file, install it, and prove it makes sound.

    Two halves of verification, and the second is the one that matters: the
    file can parse to a correctly shaped tensor and still be noise, a
    zeroed pack, or a style vector from a different model — none of which
    is visible until something is synthesized with it. So the pack is only
    written into voices.json after a real line has been synthesized through
    the real engine and come back as audible audio. Anything short of that
    is rolled back, leaving no half-installed voice behind.
    """
    voice_id, dest = voicepack.install(
        src, CUSTOM_VOICES, name=name, key=key, source=source,
        taken=set(VOICE_CATALOG) | set(VOICES.get("custom_voices", {})))
    try:
        speech.tts.register_voice(voice_id, dest)
        audio = speech.tts.synth(SMOKE_LINE, voice_id, 1.0)
        if audio is None or len(audio) < 4000:          # <0.17s isn't a line
            raise voicepack.VoiceError(
                "the engine produced no audio from that voice")
        rms = float(speech.np.sqrt(speech.np.mean(
            speech.np.square(speech.np.asarray(audio, dtype="float32")))))
        if rms < 0.005:
            raise voicepack.VoiceError(
                f"that voice synthesizes near-silence (rms {rms:.4f}) — the "
                "data is shaped like a voice but isn't one")
    except Exception:
        speech.tts.forget_voice(voice_id)
        dest.unlink(missing_ok=True)
        raise
    VOICES.setdefault("custom_voices", {})[voice_id] = {
        # posix separators: voices.json is portable between the two platforms
        "file": dest.relative_to(STATE).as_posix(),
        "source": source or Path(src).name}
    VOICES_PATH.write_text(json.dumps(VOICES, indent=2, ensure_ascii=False))
    print(f"[voice] installed {voice_id} from {Path(src).name}", flush=True)
    return voice_id, audio


def guess_gender(speaker):
    """Documented gender first; name shape only as a last resort.

    settings.genders carries the playable roster's own gender record
    (bodyType, written by tools/pronounce_names.py --write) and NPC_GENDERS
    ships the named NPCs no roster lists. The suffix guess below stays for
    genuinely unknown speakers, but it must never outrank a documented
    entry: it read Paimon — "-on", so "male" — in a male voice for a whole
    session before she was recast by hand."""
    n = speaker.rstrip('"”').strip()
    table = {**NPC_GENDERS, **VOICES.get("settings", {}).get("genders", {})}
    g = {k.lower(): v for k, v in table.items()}.get(n.lower())
    if g in ("female", "male"):
        return g
    fem = n.lower().endswith(("a", "ia", "ie", "elle", "ette", "ina",
                              "yn", "i"))
    return "female" if fem else "male"


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
    # OCR garbage in the speaker slot (`iii`, `Lv. 90`, `???`) must not
    # earn a permanent casting row and a pooled voice — but the LINE is
    # still spoken, as the narrator. Checked only after the cast lookup,
    # so casting a name by hand always beats the filter. The rules and
    # the session-log strings behind them: tools/casting_filter.py.
    if junk_speaker(speaker):
        return VOICES["defaults"]["narrator"], 1.0
    with open(UNKNOWN_LOG, "a") as f:
        f.write(speaker + "\n")
    # documented gender (roster/NPC table) or name-shape guess, then claim
    # a distinct voice; shows as "(auto)" in Casting — override anytime
    return auto_cast(speaker, guess_gender(speaker)), 1.0


class Speech:
    """Owns the TTS engine, sentiment analyzer, and playback."""

    def __init__(self):
        from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
        import numpy as np
        import soundfile as sf
        self.np, self.sf = np, sf
        self.tts = backend.create_tts()
        self.player = backend.create_player(DEVICES)
        self.sia = SentimentIntensityAnalyzer()
        self.t_play = None
        self._qr = False
        self._effects = {}                # sound file → decoded 24k mono

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

    def effect(self, path):
        """A stage-direction sound, decoded once and resampled to the synth
        rate. A file that won't load isn't worth losing the line over: the
        read goes ahead without it, and the failure is logged once."""
        if path not in self._effects:
            p = Path(path).expanduser()
            try:
                audio, sr = self.sf.read(str(p if p.is_absolute() else STATE / p),
                                         dtype="float32", always_2d=True)
                audio = audio.mean(axis=1)
                if sr != 24000:             # linear is plenty for a one-shot
                    n = round(len(audio) * 24000 / sr)
                    audio = self.np.interp(
                        self.np.linspace(0, len(audio) - 1, n),
                        self.np.arange(len(audio)), audio).astype("float32")
                self._effects[path] = audio
            except Exception as e:
                print(f"sound effect {path!r}: {e}", flush=True)
                self._effects[path] = None
        return self._effects[path]

    def trim(self, audio, lead=800):
        """Kokoro's silence padding off both ends. Cheap on its own, but the
        point is control: a spliced line's pauses should be the ones we chose,
        not two clips' padding back to back."""
        if audio is None or not len(audio):
            return audio
        loud = self.np.where(self.np.abs(audio) > SILENCE)[0]
        if not len(loud):
            return audio
        return audio[max(loud[0] - lead, 0):loud[-1] + lead * 2]

    def join(self, pieces):
        """Splice synthesized pieces with a sentence-length pause between
        them. One piece is the common case and passes through untouched."""
        if not pieces:
            return None
        if len(pieces) == 1:
            return pieces[0]
        gap = self.np.zeros(int(24000 * SENTENCE_GAP), dtype="float32")
        return self.np.concatenate(
            [x for p in pieces for x in (p, gap)][:-1])

    def synth(self, text, voice, base_speed=1.0):
        # sentiment reads the line as written — spoken_form respells names
        # into nonsense words, which is not what a sentiment model should see
        speed = round(base_speed * self.sentiment_speed(text), 3)
        t0 = time.time()
        pieces = []
        for kind, val in speech_parts(spoken_form(text)):
            if kind == "play":
                pieces.append(self.effect(val))
            else:
                pieces += [self.trim(self.tts.synth(s, voice, speed))
                           for s in sentences(val)]
        pieces = [p for p in pieces if p is not None and len(p)]
        audio = self.join(pieces)
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
        audio = self.trim(audio)
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


def shift_offset(t, gaps):
    """A wall-clock offset moved onto the recorded timeline.

    The video loses every capture gap; the audio stream doesn't, and the
    mux cuts the same windows out of it. So a clip stamped in wall time
    has to come back by everything that was removed before it. A clip that
    started *inside* a gap collapses onto its leading edge."""
    shift = 0.0
    for g in gaps:
        if t >= g["t1"]:
            shift += g["t1"] - g["t0"]
        elif t > g["t0"]:
            shift += t - g["t0"]
    return max(0.0, t - shift)


def probe_duration(path):
    """Seconds of video in a file, or None if ffprobe can't say."""
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "format=duration:stream=duration",
             "-of", "default=nw=1:nk=1", str(path)],
            capture_output=True, text=True, timeout=20)
        for line in r.stdout.split():
            if line not in ("N/A", ""):
                return float(line)
    except (subprocess.SubprocessError, ValueError, OSError):
        pass
    return None


def measure_gaps(parts, s0):
    """Where the capture was down, measured rather than assumed.

    Each part records the wall-clock offset it STARTED at. How much video
    it then actually contains only ffprobe knows — the frame file can stop
    updating well before the encoder does, so the stall the watchdog timed
    is longer than the video that went missing (measured: 10.4s waited,
    6.2s of video lost, and the 4.2s difference came straight off the sync
    of everything after it). The gap before part i is therefore the wall
    time between the end of part i-1's video and the start of part i."""
    gaps, prev_end = [], None
    for p in parts:
        dur = probe_duration(p["file"])
        if prev_end is not None:
            g = max(0.0, p["t"] - prev_end)
            if g > 0.05:
                gaps.append({
                    "t0": prev_end, "t1": p["t"],
                    "a0": s0 + int(prev_end * AUDIO_BYTES_PER_SEC) // 4 * 4,
                    "a1": s0 + int(p["t"] * AUDIO_BYTES_PER_SEC) // 4 * 4})
        if dur is None:
            return gaps          # can't measure further; cut nothing more
        prev_end = p["t"] + dur
    return gaps


def audio_keep_ranges(s0, s1, gaps):
    """Byte ranges of the PCM stream that have video behind them.

    The capture can die and be respawned mid-take; the audio stream never
    stops. Pairing the whole of one with the gapped other is what made a
    28s video carry 265s of sound, so the windows where nothing was
    captured come out of the audio as well."""
    keep, cursor = [], s0
    for g in sorted(gaps, key=lambda g: g["a0"]):
        a0, a1 = min(max(g["a0"], s0), s1), min(max(g["a1"], s0), s1)
        if a0 > cursor:
            keep.append((cursor, a0))
        cursor = max(cursor, a1)
    if s1 > cursor:
        keep.append((cursor, s1))
    return keep


def concat_parts(parts):
    """One video file out of the recording's segments, or None.

    Segments come from separate ffmpeg runs with identical encoder
    settings, so they stream-copy together; if that ever fails, the caller
    keeps the longest single part rather than losing the take."""
    parts = [p for p in parts if Path(p).exists() and Path(p).stat().st_size]
    if not parts:
        return None
    if len(parts) == 1:
        return Path(parts[0])
    listing = Path(parts[0]).with_suffix(".parts.txt")
    listing.write_text("".join(
        f"file '{Path(p).as_posix()}'\n" for p in parts))
    joined = Path(str(parts[0]).replace("_raw", "_joined"))
    ok = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "concat",
         "-safe", "0", "-i", str(listing), "-c", "copy", "-y", str(joined)],
        capture_output=True).returncode == 0
    listing.unlink(missing_ok=True)
    if ok:
        return joined
    joined.unlink(missing_ok=True)
    print(f"[recording] concat of {len(parts)} segments FAILED — keeping the "
          f"longest one", flush=True)
    return Path(max(parts, key=lambda p: Path(p).stat().st_size))


def mux_recording(parts, clips, out, s0, s1):
    """Combine: video (ffmpeg mkv segments) + game audio (byte-slices of the
    PCM stream between recording start/stop, minus any capture gaps) + TTS
    clips at their offsets on that same timeline."""
    gaps = measure_gaps(parts, s0)
    raw = concat_parts([p["file"] for p in parts])
    if raw is None:
        add_event("recording FAILED (no video)", "yield", None, Path(out).name)
        print(f"[recording] no usable video segment for {out}", flush=True)
        return
    keep = audio_keep_ranges(s0, s1, gaps)
    n = 0
    with open(AUDIO_PCM, "rb") as src, open(GAME_SLICE, "wb") as dst:
        for a0, a1 in keep:
            src.seek(a0)
            remaining = max(a1 - a0, 0)
            while remaining > 0:
                b = src.read(min(1 << 20, remaining))
                if not b:
                    break
                dst.write(b)
                n += len(b)
                remaining -= len(b)
    clips = [dict(c, start=shift_offset(c["start"], gaps),
                  end=(None if c.get("end") is None
                       else shift_offset(c["start"], gaps)
                       + max(c["end"] - c["start"], 0.05)))
             for c in clips]
    dropped = (s1 - s0 - n) / AUDIO_BYTES_PER_SEC
    print(f"[recording] game audio slice: {n / AUDIO_BYTES_PER_SEC:.1f}s"
          + (f" ({dropped:.1f}s cut across {len(gaps)} capture gap(s))"
             if gaps else "")
          + f"; muxing {len(clips)} TTS clips into {out}", flush=True)
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
           "-i", str(raw),
           "-f", "s16le", "-ar", "48000", "-ac", "2", "-i", str(GAME_SLICE)]
    for c in clips:
        cmd += ["-i", c["file"]]
    filters, labels = [], []
    for i, c in enumerate(clips, 2):        # clip inputs start at index 2
        trim = (f"atrim=0:{max(c['end'] - c['start'], 0.05):.3f},"
                if c.get("end") is not None else "")
        ms = int(c["start"] * 1000)
        filters.append(f"[{i}:a]{trim}aresample=48000,"
                       f"aformat=channel_layouts=stereo,"
                       f"volume=2.5,alimiter=limit=0.95,"  # Kokoro is quiet
                       f"adelay={ms}|{ms}[a{i}]")
        labels.append(f"[a{i}]")
    if clips:
        fc = (";".join(filters) + ";[1:a]" + "".join(labels)
              + f"amix=inputs={len(clips) + 1}:normalize=0[out]")
        cmd += ["-filter_complex", fc, "-map", "0:v", "-map", "[out]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a"]
    cmd += ["-c:v", "copy", "-c:a", "aac", "-y", str(out)]
    ok = subprocess.run(cmd, capture_output=True).returncode == 0
    if ok:
        for p in {str(raw), *(p["file"] for p in parts)}:
            Path(p).unlink(missing_ok=True)
        GAME_SLICE.unlink(missing_ok=True)
        for c in clips:
            Path(c["file"]).unlink(missing_ok=True)
        add_event("recording saved", "spoken", None, Path(out).name)
    else:
        add_event("recording mux FAILED (raw kept)", "yield", None, Path(raw).name)
    print(f"[recording] mux {'ok' if ok else 'FAILED'}: {out}", flush=True)


# One owner of the capture process at a time. A single ffmpeg holds BOTH the
# capture device and the live frame file, so two of them must never overlap —
# every restart/finalize, on the loop or off it, goes through this lock.
video_lock = threading.Lock()
video_swap = {"thread": None}


def respawn_capture(video):
    """Restart the capture, keeping an in-progress recording alive.

    One ffmpeg owns both the capture device and the recording, so every
    respawn ends the MKV it was writing — and a respawn that asks for no
    recording amputates the take silently. That is what a stalled capture
    did mid-session: video stopped at the stall, `recording["on"]` stayed
    true, clips and the audio slice kept running on wall clock, and the
    mux paired a 28s video with 265s of sound. The recording continues
    into the next segment instead.

    All that is recorded here is WHEN each segment started, in wall time.
    How much video was actually lost is not knowable yet and must not be
    guessed: the first attempt inferred it from how long the watchdog had
    been waiting, which overshot by 4.2s on a real stall — the frame file
    stops updating before the encoder does — and everything after the gap
    came out that far off. mux_recording measures each segment instead.

    Caller must hold video_lock.
    """
    if not recording["on"]:
        video.restart()
        return
    part = Path(recording["raw"].replace(
        "_raw.mkv", f"_raw.p{len(recording['parts']) + 1}.mkv"))
    video.restart(record_path=part)
    recording["parts"].append(
        {"file": str(part), "t": time.monotonic() - recording["t0"]})
    print(f"[recording] capture respawned — continuing into {part.name}",
          flush=True)


def swap_video_async(video, finalize_first=False, on_finalized=None):
    """Tear down and respawn the capture WITHOUT blocking the reading loop.

    finalize() waits for ffmpeg to flush the recording MKV — seconds on a
    long take — and restart() then re-negotiates the device. Run inline on
    recording stop, they froze OCR for that whole window, so a line already
    on screen could not stabilise until capture came back; that is the tail
    of the late "The beach!" read. The two steps cannot be overlapped with
    each other, so they move to a worker together. The loop needs no other
    change — a frame file that stops changing is already a no-op — beyond
    holding off the stall watchdog while the swap is in flight.

    on_finalized runs once the MKV is closed and before the respawn. The
    mux MUST be sequenced here rather than fired from the caller: ffmpeg is
    still writing the file until finalize returns, so a mux kicked off in
    parallel would read a half-written recording.
    """
    def run():
        with video_lock:
            if finalize_first:
                video.finalize(timeout=8)
            if on_finalized is not None:
                on_finalized()
            # normally the recording is already off here (this IS the stop
            # path); respawn_capture keeps one alive if it isn't
            respawn_capture(video)

    video_swap["thread"] = threading.Thread(target=run, daemon=True)
    video_swap["thread"].start()


def video_swapping():
    t = video_swap["thread"]
    return t is not None and t.is_alive()


def handle_commands(speech, recent_lines):
    """Dashboard actions: assign voice (+re-read), replay event, test speech."""
    while not commands.empty():
        cmd = commands.get_nowait()
        if cmd[0] == "assign":
            _, char, voice = cmd
            VOICES["characters"].setdefault(char, {})["voice"] = voice
            VOICES["characters"][char].setdefault("speed", 1.0)
            VOICES["characters"][char].pop("auto", None)   # now user-chosen
            VOICES_PATH.write_text(json.dumps(VOICES, indent=2, ensure_ascii=False))
            lexicon_stale["flag"] = True
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
            lexicon_stale["flag"] = True
            print(f"[deleted] {char}", flush=True)
        elif cmd[0] == "addvoice":
            _, src, name, key = cmd
            src = Path(src)
            try:
                voice_id, audio = install_voice(speech, src, name, key)
                # audition it immediately: hearing the voice is the only
                # check that tells you whether it's the one you wanted
                speech.play(audio)
                add_event(f"added voice {voice_id}", "spoken", None,
                          SMOKE_LINE, voice_id)
                voice_import.update(state="ok", voice=voice_id,
                                    msg=f"added {voice_id} — auditioning it now")
            except voicepack.VoiceError as exc:
                voice_import.update(state="error", voice=None, msg=str(exc))
                print(f"[voice] rejected {src.name}: {exc}", flush=True)
            except Exception as exc:                  # engine/IO failure
                voice_import.update(state="error", voice=None,
                                    msg=f"{type(exc).__name__}: {exc}")
                print(f"[voice] failed on {src.name}: {exc}", flush=True)
            finally:
                if src.parent == UPLOADS:             # browser upload: temp
                    src.unlink(missing_ok=True)
        elif cmd[0] == "blendvoice":
            _, name, parts = cmd
            tmp = None
            try:
                styles = [speech.tts.voice_style(v) for v, _ in parts]
                arr, weights = voicepack.blend(styles, [w for _, w in parts])
                recipe = " + ".join(f"{w:.2f}*{v}" for (v, _), w
                                    in zip(parts, weights))
                # write the mix as an ordinary pack file so it goes through
                # the same install path as an imported one: same id rules,
                # same synthesize-and-hear-it verification, same rollback
                UPLOADS.mkdir(parents=True, exist_ok=True)
                tmp = UPLOADS / "blend.safetensors"
                voicepack.write_safetensors(tmp, arr, {"source": recipe})
                voice_id, audio = install_voice(
                    speech, tmp, name=name or "blend", source=recipe)
                speech.play(audio)
                add_event(f"blended voice {voice_id} = {recipe}", "spoken",
                          None, SMOKE_LINE, voice_id)
                voice_import.update(state="ok", voice=voice_id,
                                    msg=f"added {voice_id} ({recipe}) — "
                                        "auditioning it now")
            except voicepack.VoiceError as exc:
                voice_import.update(state="error", voice=None, msg=str(exc))
                print(f"[voice] blend rejected: {exc}", flush=True)
            except Exception as exc:                  # engine/IO failure
                voice_import.update(state="error", voice=None,
                                    msg=f"{type(exc).__name__}: {exc}")
                print(f"[voice] blend failed: {exc}", flush=True)
            finally:
                if tmp is not None:
                    tmp.unlink(missing_ok=True)
        elif cmd[0] == "delvoice":
            voice_id = cmd[1]
            pack = VOICES.get("custom_voices", {}).pop(voice_id, None)
            if pack:
                speech.tts.forget_voice(voice_id)
                (STATE / pack["file"]).unlink(missing_ok=True)
                release_voice(voice_id)
                VOICES_PATH.write_text(
                    json.dumps(VOICES, indent=2, ensure_ascii=False))
                print(f"[voice] removed {voice_id}", flush=True)
                voice_import.update(state="ok", voice=None,
                                    msg=f"removed {voice_id}")
        elif cmd[0] == "clearlog":
            # The dedupe window goes with it. It outlives a restart on
            # purpose, so a crash mid-scene doesn't re-read the line still on
            # screen — but that also means replaying a quest inside the TTL
            # is silently skipped as a repeat, and Clear is what you reach for
            # when you want the next lines read as if they were new. The line
            # ALREADY on screen is not re-read: `fired_norm` still holds it,
            # so pressing Clear can't make the app start talking at you.
            events.clear()
            n = len(recent_lines)
            recent_lines.clear()
            SPOKEN_CACHE.write_text(json.dumps(
                {"window": [], "saved_at": time.time(),
                 "voiced_history": voiced_history,
                 "voiced_recent": {k: "".join(w)
                                   for k, w in voiced_recent.items()}}))
            print(f"[log cleared — dedupe window of {n} cleared too]",
                  flush=True)
        elif cmd[0] == "game":
            p = game.set_setting(cmd[1])
            VOICES.setdefault("settings", {})["game"] = cmd[1]
            VOICES_PATH.write_text(json.dumps(VOICES, indent=2, ensure_ascii=False))
            print(f"[game] {cmd[1]} (reading as {p.label})", flush=True)
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
            recent = obj.get("voiced_recent", {})
            for spk, outcomes in recent.items():
                if isinstance(outcomes, str):
                    voiced_recent[spk] = deque(
                        [c for c in outcomes if c in "vs"][-PRIOR_WINDOW:],
                        maxlen=PRIOR_WINDOW)
                    w = voiced_recent[spk]
                    voiced_history[spk] = [sum(1 for c in w if c == "v"),
                                           sum(1 for c in w if c == "s")]
            # state written before the window existed carries lifetime
            # tallies only — seed from the ratio they imply
            for spk, counts in obj.get("voiced_history", {}).items():
                if spk not in voiced_recent and \
                        isinstance(counts, list) and len(counts) == 2:
                    seed_window(spk, counts[0], counts[1])
            print(f"restored dedupe window of {len(recent_lines)}"
                  f"; voiced history for {len(voiced_history)} speaker(s)",
                  flush=True)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    register_custom_voices(speech)

    port = start_webui({"events": events, "voices": VOICES,
                        "voice_import": voice_import,
                        "uploads_dir": str(UPLOADS),
                        "unknown": unknown_speakers, "metrics_fn": metrics,
                        "commands": commands, "observing": observing,
                        "shots_dir": str(SHOTS), "frame_dir": str(FRAME.parent),
                        "rec_dir": REC_DIR,
                        # written by the launcher (repo root), not STATE
                        "log_path": str(ROOT / "live.log"),
                        "recording": recording, "game": game,
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
    # settings.change_gate: false disables the pixel gate entirely;
    # settings.change_gate_frac tunes what share of a box's text pixels may
    # move before it counts as changed (lower = more suspicious = more OCR)
    gate.enabled = bool(VOICES.get("settings", {}).get("change_gate", True))
    gate.frac = float(VOICES.get("settings", {}).get("change_gate_frac",
                                                     gate.frac))
    # settings.anchors: false silences anchor matching entirely;
    # settings.anchor_roi: true additionally lets a matched anchor CROP
    # the frame to its screen kind's ROI before OCR (phase 4b, off by
    # default until the Windows ocr_ms win is measured)
    anchor_state["enabled"] = bool(VOICES.get("settings", {})
                                   .get("anchors", True))
    anchor_state["roi"] = bool(VOICES.get("settings", {})
                               .get("anchor_roi", False))
    global LATE_YIELD
    LATE_YIELD = bool(VOICES.get("settings", {}).get("late_yield", True))

    # The game's own dialogue strings, if the player extracted them. Off
    # unless settings.textmap names a readable file — nothing here ships
    # HoYoverse's text. See tools/textmap.py for what a match has to clear.
    #
    # Per game, and loaded on FIRST USE of that game rather than at startup:
    # a real dump is ~200k entries, which is ~4s to index and ~390MB
    # resident, and the auto-detect profile means the other game's map would
    # otherwise be built for a session that never reads a line of it.
    textmaps = {}
    tm_setting = VOICES.get("settings", {}).get("textmap") or {}
    if isinstance(tm_setting, str):
        # one path, no game named: it belongs to whichever game is read
        tm_setting = {game.profile.name: tm_setting}
    nickname = VOICES.get("settings", {}).get("player_name", "")

    def textmap_for(name):
        """The map for this game, built once, or None."""
        if name not in textmaps:
            path = tm_setting.get(name)
            tm = TextMap.load(path, nickname=nickname) if path else None
            if path:
                print(f"textmap[{name}]: {len(tm)} lines from {path}" if tm
                      else f"textmap[{name}]: {path} unreadable — snapping "
                           f"off for {name}", flush=True)
            textmaps[name] = tm
        return textmaps[name]

    candidate, candidate_count = None, 0
    candidate_growing = False
    candidate_t0 = 0.0          # when the current line was FIRST seen on screen
    last_dup_logged = None
    last_unknown_logged = None
    last_notice_logged = None
    last_fused_logged = None    # last two-rows-in-one-box read written down
    choice_ignored_logged = None  # last prompt dropped for want of a speaker
    choice_prev = ""            # last frame's options (settle check)
    choice_logged = None        # last prompt handled — RAW words, not a norm
    pending_choice = None       # lone option waiting for the line below it
    # long ago: an option held before we have ever spoken shouldn't wait
    speech_busy_t = time.monotonic() - 60.0
    # the line the loop last DEALT with — spoken, or skipped as voiced.
    # Suppresses repeat-logs for the line still on screen; named for
    # handling rather than speaking because a deliberate silence is just as
    # much a decision, and its repeats are just as uninteresting.
    last_handled_norm = None
    fired_norm = None           # line already pushed through the gate once
    unstable_count = 0
    miss_streak = 0             # consecutive frames the detector lost the line
    last_raw_norm = None        # previous frame's UNCLIPPED read (growth check)
    candidate_variants = []     # every raw read of the current line
    last_mtime = 0.0
    last_frame_change = time.monotonic()
    yield_event_id = None
    playing_speaker = None      # whose line is on the speakers right now
    qr_seen, qr_absent = set(), 99      # Quick Read incremental-reading state
    qr_gone_t0 = 0.0                    # when the reader panel first vanished
    reader_prev = set()                 # last frame's panel rows (settle check)
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
    print(f"game: {'auto-detect' if game.auto else 'fixed'} — reading as "
          f"{game.profile.label}", flush=True)
    print("live — watching feed + listening for VO", flush=True)

    try:
        while True:
            time.sleep(0.03)
            handle_commands(speech, recent_lines)
            if lexicon_stale["flag"]:
                # casting changed: rewrite the lexicon and, where the OCR
                # engine actually reads it (Apple Vision), restart the
                # daemon so a newly cast name helps recognition NOW rather
                # than after the next app restart
                lexicon_stale["flag"] = False
                custom_words_file()
                if getattr(ocr, "uses_custom_words", False):
                    ocr.restart()
                    print("[ocr] lexicon refreshed — daemon restarted",
                          flush=True)
            now = time.monotonic()
            if speech.playing:
                # when our voice was last busy — a held choice option waits
                # a beat past this before answering
                speech_busy_t = now

            if device_request["want"] is not None:
                want = device_request["want"]
                # The output device is only where OUR speech goes — nothing
                # to restart, so it lands immediately (and safely mid-
                # recording, unlike a capture swap). "" = system default,
                # which is a real choice: don't drop it as empty.
                out = want.pop("output", None)
                if out is not None:
                    DEVICES["output"] = out
                    VOICES.setdefault("settings", {})["output_device"] = out
                    VOICES_PATH.write_text(
                        json.dumps(VOICES, indent=2, ensure_ascii=False))
                    print(f"[devices] output={out or 'system default'}",
                          flush=True)
                capture = {k: v for k, v in want.items() if v}
                if not capture:
                    device_request["want"] = None
                elif not recording["on"]:
                    device_request["want"] = None
                    DEVICES.update(capture)
                    VOICES.setdefault("settings", {}).update(
                        video_device=DEVICES["video"],
                        audio_device=DEVICES["audio"])
                    VOICES_PATH.write_text(
                        json.dumps(VOICES, indent=2, ensure_ascii=False))
                    print(f"[devices] video={DEVICES['video']} "
                          f"audio={DEVICES['audio']}", flush=True)
                    with video_lock:    # waits out an in-flight swap
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
                    # stays INLINE: t0/s0 must be sampled at the moment the
                    # video starts, or every TTS clip is muxed at the wrong
                    # offset. The lock waits out a swap from a just-stopped
                    # recording rather than racing it for the device.
                    with video_lock:
                        video.restart(record_path=raw)
                        for _ in range(40):      # align t0 with the video start
                            if raw.exists():
                                break
                            time.sleep(0.1)
                    s0 = AUDIO_PCM.stat().st_size if AUDIO_PCM.exists() else 0
                    recording.update(on=True, t0=time.monotonic(), clips=[],
                                     raw=str(raw), s0=s0,
                                     parts=[{"file": str(raw), "t": 0.0}])
                    last_frame_change = time.monotonic()
                    print("[recording started]", flush=True)
                elif not want and recording["on"]:
                    recording["on"] = False
                    s1 = AUDIO_PCM.stat().st_size if AUDIO_PCM.exists() else 0
                    raw, clips = recording["raw"], recording["clips"]
                    parts = (list(recording["parts"])
                             or [{"file": raw, "t": 0.0}])
                    s0 = recording.get("s0", 0)
                    out = raw.replace("_raw.mkv", ".mp4")
                    # clean mkv close, then mux, then respawn — all off the
                    # loop, so reading keeps running through it. The mux is
                    # handed to the swap worker so it starts only once the
                    # MKV is actually closed (see swap_video_async).
                    swap_video_async(
                        video, finalize_first=True,
                        on_finalized=lambda: threading.Thread(
                            target=mux_recording,
                            args=(parts, clips, out, s0, s1),
                            daemon=True).start())
                    last_frame_change = time.monotonic()
                    print("[recording stopped — finalizing]", flush=True)

            # Mid-play yield. Our TTS is NOT in the capture (it plays on the
            # computer's speakers; the card hears only HDMI), so while we're
            # talking, speech evidence in the feed is the game's voice.
            #
            # It reads that evidence at the SAME sensitivity as the decision
            # to speak in the first place, which means the per-speaker prior:
            # for a character the game has voiced before, the softest hint is
            # enough to stand down. Forcing the soft thresholds on regardless
            # was justified as "the worst false positive merely clips our own
            # playback" — but the soft floor is a VAD probability of 0.12
            # over three 32ms chunks, which Natlan's vocal music clears
            # comfortably, and a scene with no voice acting in it at all lost
            # four lines to it, each cut off mid-sentence with nothing
            # audible taking over. Clipping our own playback IS the failure
            # the whole feature exists to avoid.
            yield_soft = (usually_voiced(playing_speaker)
                          if playing_speaker else False)
            # ...and the same prior pointed the other way. A character the
            # game has never once been heard to voice is one whose lines the
            # player is relying on us for, and in a scene with the voice
            # acting off the VAD has nothing but music and effects to score:
            # a Paimon line was cut 0.8s in on three 32ms chunks peaking at
            # 0.66, in a session whose capture contained no game speech at
            # all. Sustained speech may still take the line; a blip may not.
            yield_firm = bool(not yield_soft and playing_speaker
                              and never_voiced(playing_speaker))
            if (speech.playing and speech.t_play
                    and not speech.qr_playing
                    and LATE_YIELD
                    and is_voiced(speech.t_play + 0.2, soft=yield_soft,
                                  firm=yield_firm)):
                # read the evidence BEFORE stopping — stop() clears t_play
                t_play = speech.t_play
                s, w, pk = vad_evidence(t_play + 0.2, soft=yield_soft)
                speech.stop()
                stats["yielded"] += 1
                if yield_event_id:
                    for e in events:
                        if e["id"] == yield_event_id:
                            e["action"], e["cls"] = "yielded to VO", "yield"
                # what it heard, and how far in — a yield that cut a line
                # short reads exactly like a correct one otherwise
                print(f"[yielded to late VO — {time.monotonic() - t_play:.1f}s in,"
                      f" peak {pk:.2f}, strong {s}, weak {w}"
                      f"{', soft' if yield_soft else ''}"
                      f"{', firm' if yield_firm else ''}]", flush=True)

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

            if video_swapping():
                # capture is being respawned off-loop: the frame file goes
                # briefly stale between the old process exiting and the new
                # one writing. That is a handover, not a stall — respawning
                # on top of it would fight the swap for the device.
                last_frame_change = now
            elif now - last_frame_change > 10:
                stalled = now - last_frame_change
                print(f"[capture stalled {stalled:.0f}s — respawning]",
                      flush=True)
                with video_lock:
                    # keeps an in-progress recording going into a new
                    # segment rather than ending it where the stall began
                    respawn_capture(video)
                last_frame_change = time.monotonic()
                gate.reset()          # baseline belongs to the dead capture
                continue

            try:
                mtime = FRAME.stat().st_mtime
            except FileNotFoundError:
                continue
            if mtime == last_mtime:
                continue
            last_mtime = mtime
            last_frame_change = now

            # cheap pixel gate first: while the text region is identical to
            # the previous frame, REPLAY the previous blocks through the
            # normal path instead of paying for OCR. Replaying (not
            # skipping) keeps stabilization counting, chat settle checks
            # and panel-close detection ticking exactly as before.
            # Gate ONLY while a line is on screen, watching that line's own
            # blocks. Falling back to every block when there was no line
            # looked like the safe direction — more boxes, more ways to
            # notice a change — but the gate can only see where text ALREADY
            # was, so a line appearing on a screen that had none lands
            # outside every box it is watching and reads as unchanged.
            # Measured over 1650 frames of a Genshin conversation: that
            # fallback accounted for 10 of the 17 stale verdicts, and
            # dropping it costs 11% of the skips to remove 76% of them.
            if gate.unchanged(FRAME, latest_ocr["text_blocks"]):
                blocks = latest_ocr["blocks"]
                fresh_read = False
                was_crop = False
            else:
                # Anchors are matched BEFORE OCR so a match can pay for its
                # cost: with settings.anchor_roi on, matched chrome implies
                # a screen kind and OCR reads only that kind's ROI. The
                # pack is the STICKY game's — pre-OCR there is no fresh
                # classify — which is right: during a game switch the old
                # game's chrome stops matching, so the frames the switch
                # decision needs are read whole.
                roi = (match_anchors(game.profile.name)
                       if anchor_state["enabled"] else None)
                crop = None
                if roi is not None and anchor_state["roi"]:
                    if anchor_state["crop_run"] >= ANCHOR_MAX_CROP_RUN:
                        # deferred long enough — read the whole frame so
                        # text outside the crop can't stay invisible, and
                        # re-arm (the change gate's MAX_SKIP_RUN medicine)
                        anchor_state["crop_run"] = 0
                    else:
                        crop = crop_frame(FRAME, roi, CROP)
                t0 = time.time()
                blocks = ocr.recognize(CROP if crop else FRAME)
                if blocks is None:      # daemon died; it respawned itself
                    continue
                stats["ocr_ms"].append(int((time.time() - t0) * 1000))
                was_crop = crop is not None
                if was_crop:
                    anchor_state["crop_run"] += 1
                    anchor_state["crops"] += 1
                    # the daemon normalizes to the image it was handed —
                    # remap here, at the call boundary, so NOTHING
                    # downstream ever sees crop-normalized coordinates
                    blocks = [remap_box(b, crop) for b in blocks]
                else:
                    anchor_state["crop_run"] = 0
                latest_ocr["blocks"] = blocks
                latest_ocr["text_blocks"] = None    # until classify sets it
                fresh_read = True
            if not blocks:
                # NO blocks at all means we failed to read the frame (a torn
                # JPEG mid-rewrite, common under recording load), not that
                # the screen is empty. Counting it as evidence made reader
                # panels look closed while they were plainly on screen —
                # which stopped the read and dropped its queue.
                # A CROPPED read is the exception: the crop was cut from a
                # verified-complete frame, so [] is a genuinely empty ROI
                # (a fade, dialogue chrome up before text) — not a lost
                # frame, but still no evidence to act on.
                if not was_crop:
                    lost_frames["n"] += 1
                continue

            # which game's layout to read this frame with (sticky; only
            # switches on sustained chrome from another game)
            screens = game.observe(blocks)

            # A read that fused two dialogue rows into one box is not this
            # line — it is the two rows woven together (see
            # profiles.base.fused_rows). Drop the frame the way a lost one
            # is dropped: the clean read alternates with it on the same
            # motionless screen, usually within a second, and a dropped
            # frame costs nothing but that wait. Deliberately NOT a partial
            # rescue — there is no honest way to unweave the box, and the
            # text it produced was spoken forty times as if it were the
            # game's own. Never on a REPLAY: those blocks came from a read
            # already judged here.
            fused = screens.fused_rows(blocks) if fresh_read else []
            if fused:
                lost_frames["n"] += 1
                stats["fused_reads"] += 1
                # One event per fused LINE, not per fused frame. The
                # alternation runs at the sampling rate for as long as the
                # player leaves the line up — a count-based limit still put
                # an event in the log every few seconds, which is the noise
                # this drop exists to remove. Keyed on the text, like the
                # unknown-speaker skip: the weave differs slightly on every
                # read ("god a" / "godma"), so same_line collapses them and
                # a genuinely different line still logs once.
                ftext = " · ".join(b["text"] for b in fused)
                fnorm = normalize_text(ftext)
                if not same_line(fnorm, last_fused_logged):
                    add_event("OCR fused two rows — frame dropped", "yield",
                              None, ftext, shot=True)
                    # anchored on what the LOG already says, not on the last
                    # frame: the weave drifts, and comparing to the previous
                    # frame lets it drift past the cutoff a step at a time.
                    # Over the 106 fused frames recorded so far (four
                    # distinct lines) this writes 7 events; the old
                    # one-in-twelve rule wrote 380 in two minutes.
                    last_fused_logged = fnorm
                latest_ocr["blocks"] = []       # never replay a fused read
                continue

            # --- Reading-mode screens (Quick Read books, info/profile
            # screens, message/group-chat panels): incremental reading ---
            qr = screens.classify_quickread(blocks)
            if qr is None:
                qr = screens.classify_infoscreen(blocks)
            chat = None if qr is not None else screens.classify_chat(blocks)
            if qr is not None or chat is not None:
                qr_absent = 0
                reader_closed = False
                items = [(None, t) for t in qr] if qr is not None else chat
                # A row is queued the instant it's seen, so a frame caught
                # mid fade-in gets read verbatim — that is where "started
                # shan ing (ocation" came from; the same text reads at 0.98+
                # confidence once settled. Require a row to survive one more
                # frame before reading it.
                #
                # It does the same job for a row caught mid-SCROLL. Moving
                # is not itself the problem — a row that is fully drawn
                # reads the same text wherever it sits, settles at once and
                # is spoken while the panel is still moving, which is what
                # we want. The problem is a row drawn in HALF as it slides
                # under the panel's clip edge: that OCRs as garbage, or as a
                # fragment dedupe can't match against the whole row it
                # becomes, so it would be read and then read again complete.
                # A half-drawn row reads differently every frame while it
                # moves, so it can't settle until it is whole.
                cur = {normalize_text(t) for _, t in items}
                settled = {c for c in cur
                           if any(same_line(c, p, 0.92) for p in reader_prev)}
                reader_prev = cur
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
                    # Held until here ON PURPOSE, with the rest of the
                    # panel's state. Cleared on every frame that failed to
                    # see the panel, a detector that merely FLICKERS — one
                    # frame missed to a confidence dip or a stray block —
                    # can never satisfy the settle check, because the row
                    # it should be matched against was thrown away in
                    # between. Nothing is then read for as long as the
                    # flicker lasts, which looks exactly like the panel
                    # being ignored. Two seconds of grace here costs
                    # nothing: the rows are only ever used as the thing a
                    # later frame is compared AGAINST.
                    reader_prev = set()

            # pump the reading queue when the voice is idle
            if read_queue and not speech.playing:
                spk, text = read_queue.popleft()
                voice, base_speed = pick_voice(spk)
                audio, speed, _ = speech.synth(text, voice, base_speed)
                speech.play(audio, qr=True)
                stats["spoken"] += 1
                last_handled_norm = normalize_text(text)   # suppress its repeats
                kind = ("chat" if spk else
                        "chat notice" if chat is not None
                        else screens.READER_LABEL)
                add_event(kind, "spoken", spk, text, voice, speed,
                          can_replay=True, shot=True)
                print(f"[{kind}{' ' + spk if spk else ''} → {voice}] "
                      f"{text[:70]}", flush=True)
            if qr is not None or chat is not None:
                continue

            state = screens.classify(blocks)
            # Narrow the gate to the blocks this line was built from. Handed
            # every block on the frame it watches the HUD and the UID too,
            # which sit over open world — see tools/change_gate.py.
            # ONLY when there is a line: a screen with no dialogue can still
            # leave a lone nameplate-shaped block behind, and narrowing onto
            # that one box pointed the gate at a scrap of static UI, which
            # then reported "unchanged" for as long as it sat there. With no
            # line to watch, watch everything and let the gate fail open.
            latest_ocr["text_blocks"] = (state.get("boxes")
                                         if state["dialogue"] else None)

            # Choice prompts. Up to TWO options are read aloud: a lone
            # option is the game putting words in the player character's
            # mouth, and a pair still reads as the player weighing their
            # answer — both land as part of the scene (the two-option read
            # is a user preference, 2026-08-12; it was previously lone-only).
            # Three or more ARE a menu — reading those would narrate a UI —
            # so they're logged and left unspoken.
            #
            # Either way it takes the same read twice: the option list renders
            # all at once rather than typing, but OCR still jitters the first
            # sighting. Handled before the branches below so a prompt is
            # logged even when the line under it is skipped.
            opts = state["choices"]
            # A prompt the profile REFUSED is invisible otherwise, and a
            # missing read is the hardest thing to diagnose from a log —
            # there is nothing in it to notice. Genshin drops a prompt that
            # has no nameplate beside it (the teleport map lists its
            # waypoints in the same column at the same left edge and has
            # none), so a genuine prompt over an empty dialogue box is
            # dropped with it. Reported once per distinct prompt: a map on
            # screen would otherwise write a row per frame.
            if not opts:
                shown = " · ".join(b["text"]
                                   for b in screens.choice_blocks(blocks))
                snorm = normalize_text(shown)
                if snorm and not same_line(snorm, choice_ignored_logged):
                    choice_ignored_logged = snorm
                    add_event("choice prompt (ignored — no speaker)", "choice",
                              None, shown, shot=True)
            opts_raw = " ".join(opts)
            opts_norm = normalize_text(opts_raw)
            settled = bool(opts_norm) and opts_norm == choice_prev
            # `choice_logged` keeps the WORDS of the prompt already handled,
            # not its norm: same_option has to be able to drop the first one
            # (see there — the bullet is fused into it and re-read the same
            # prompt aloud).
            fresh = settled and not (choice_logged
                                     and same_option(opts_raw, choice_logged))
            if fresh and len(opts) > 2:
                choice_logged = opts_raw
                add_event("choice prompt (not read)", "choice", None,
                          " · ".join(opts), shot=True)
            elif fresh:
                # Held, not read yet: it has to land AFTER the line it sits
                # above, and it beats that line onto the screen — the bubble
                # appears whole while the line is still typing. Remember
                # which line that is; the read waits for it.
                #
                # Marked as seen HERE, not when it is finally read. The
                # bubble stays on screen for as long as the player takes to
                # click it, and every one of those frames is another
                # "settled and not seen before" — so the hold was rebuilt
                # from scratch several times a second, resetting its arm
                # flag and its clock. Nothing that has to survive a frame
                # could: the read only ever landed if arming and a gap in
                # the talking happened to fall on the same pass.
                choice_logged = opts_raw
                # Two options join with an ellipsis: punctuation only, no
                # invented words, and Kokoro reads it as the beat between
                # alternatives. `opts` (not the joined text) rides along so
                # each option can enter the dedupe window separately — the
                # game echoes whichever ONE the player picks as the next
                # dialogue line, and the joined norm would never match it.
                pending_choice = {"text": " … ".join(opts), "opts": opts,
                                  "seen": opts_raw, "armed": False,
                                  "line": normalize_text(state["dialogue"]),
                                  "t": time.monotonic()}
            if pending_choice:
                if not pending_choice["armed"]:
                    # The bubble floats above whatever the box below shows
                    # RIGHT NOW, and it renders whole while that line is
                    # still typing — or while the PREVIOUS line is still up.
                    # A norm frozen at the option's first settle therefore
                    # never matches the completed line that fires, and the
                    # option sat unarmed to its 20s TTL and dropped as "too
                    # late" while the player was still on the screen
                    # (12:02:49, 2026-08-12: option over "It must be a
                    # pretty powerful one…" — the line fired at 12:02:30,
                    # but against a mid-typewriter snapshot). Track the
                    # line as it grows instead of freezing the first
                    # sighting; the empty case ("…", or OCR reading
                    # nothing) keeps its grace-then-arm.
                    below = normalize_text(state["dialogue"])
                    if below:
                        pending_choice["line"] = below
                    elif (not pending_choice["line"]
                            and time.monotonic() - pending_choice["t"]
                            >= CHOICE_EMPTY_GRACE):
                        pending_choice["armed"] = True
                        pending_choice["t"] = time.monotonic()
                # ARMED once the line below has been through the gate —
                # `fired_norm` covers it whether it was spoken, deduped or
                # skipped as voiced. Deliberately NOT conditional on the
                # option still being on screen: the player often clicks
                # through while we're still reading the line under it, and
                # dropping the option then would mean it is almost never
                # read at a natural pace.
                if (not pending_choice["armed"]
                        and same_line(fired_norm, pending_choice["line"])):
                    pending_choice["armed"] = True
                    pending_choice["t"] = time.monotonic()
                # While the option is still ON SCREEN the read cannot be
                # "late" — the game is paused waiting for the player. The
                # stale clock must measure time since the option LEFT the
                # screen (the scene moved on), so it refreshes on every
                # frame that still shows the prompt. Without this the 8s
                # window raced the under-line's own voiceover: arming
                # happens at gate-fire, which is the START of the VO, so
                # any option under a line voiced longer than ~8s was
                # dropped as too late while the NPC was still speaking —
                # two in a row in the 2026-08-12 11:52 Snezhnaya session.
                if (pending_choice["armed"]
                        and same_option(opts_raw, pending_choice["seen"])):
                    pending_choice["t"] = time.monotonic()
                if time.monotonic() - pending_choice["t"] > (
                        CHOICE_STALE_AFTER if pending_choice["armed"]
                        else CHOICE_PENDING_TTL):
                    if (not pending_choice["armed"]
                            and same_option(opts_raw, pending_choice["seen"])):
                        # 20s and the line under it never cleared the gate —
                        # but the prompt is STILL ON SCREEN, so the game is
                        # waiting on the player and OCR may simply never
                        # manage that line. A rare talk-over beats a skipped
                        # line: arm it and read at the next quiet gap, same
                        # as if the line had fired.
                        pending_choice["armed"] = True
                        pending_choice["t"] = time.monotonic()
                    else:
                        # armed but never found a gap to speak in (the scene
                        # ran on), or the line never fired and the prompt is
                        # already gone
                        add_event("choice prompt (not read — too late)",
                                  "choice", None, pending_choice["text"])
                        choice_logged = pending_choice["text"]
                        pending_choice = None
            if (pending_choice and pending_choice["armed"]
                    and not speech.playing
                    and now - speech_busy_t >= CHOICE_LEAD_IN
                    and not is_voiced(time.monotonic() - CHOICE_VO_LOOKBACK)):
                # our own voice has been idle for a beat and the game's has
                # stopped — the line under it may be voiced even when the
                # option is not
                text = fix_ocr_text(pending_choice["text"])
                # The option is the player character's own words, and the
                # game gives it no nameplate. Cast it under their name —
                # Traveler, Trailblazer — so it gets a Casting row with a
                # voice to change, rather than falling to the narrator and
                # showing up in the log with no speaker at all.
                spk = normalize_speaker(
                    VOICES.get("settings", {}).get("choice_speaker")
                    or screens.PLAYER_NAME)
                voice, base_speed = pick_voice(spk)
                audio, speed, _ = speech.synth(text, voice, base_speed)
                speech.play(audio)          # not qr: a late VO should cut it
                stats["spoken"] += 1
                choice_logged = text
                last_handled_norm = normalize_text(text)
                # into the dedupe window: picking an option usually makes
                # the game say it back as a dialogue line, which would
                # otherwise be read a second time. Each option enters
                # SEPARATELY — the echo is whichever one the player picked,
                # and a joined two-option norm matches neither. Stacked,
                # not replacing: the dialogue line still on screen keeps
                # its slot (see remember_line).
                for opt in pending_choice["opts"]:
                    remember_line(recent_lines, spk,
                                  normalize_text(fix_ocr_text(opt)),
                                  stack=True)
                pending_choice = None
                yield_event_id = add_event(
                    "choice (read)", "spoken", spk, text, voice, speed,
                    can_replay=True, shot=True)
                print(f"[choice → {voice}] {text[:70]}", flush=True)
            choice_prev = opts_norm

            loading = screens.classify_loading(blocks)
            # chrome-free lore/loading cards (title + prose, no story-chrome
            # hint, no UID strip, no HUD) — classify() sees the title as a
            # nameplate, so without this they're skipped as unknown speakers
            lore = None if loading else screens.classify_lore_screen(blocks)
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
                overlay = screens.classify_overlay(blocks)
                narration = screens.classify_narration(blocks)
                if overlay:
                    # floating host bubble — voice set by settings.overlay_speaker
                    state = {"speaker": VOICES.get("settings", {}).get(
                                 "overlay_speaker"),
                             "dialogue": overlay, "choices": []}
                    screen_kind = "overlay"
                elif narration and (screens.trusts_dialogue(blocks)
                                    or frame_is_dark()
                                    or narration_self_certain(narration)):
                    # narration requires the game's story chrome — menu
                    # banners and event-hub screens must not be narrated
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
                # dialogue from an UNKNOWN speaker needs the game's story
                # chrome (HSR's Continue hint, Genshin's Auto toggle);
                # boards/menus fake the layout but show other hints
                spk = normalize_speaker(state["speaker"])
                known = (spk in VOICES["characters"]
                         or (spk or "").lower() == "narrator"
                         or spk in VOICES.get("always_voiced", []))
                if not known and not screens.trusts_dialogue(blocks):
                    # a comms message floats over the live HUD with no
                    # chrome at all — its left-anchored plate geometry is
                    # the trust signal instead, and it carries the speaker
                    # find_plate's centered band can't take
                    comms = screens.classify_comms(blocks)
                    if comms:
                        state = {"speaker": comms[0], "dialogue": comms[1],
                                 "choices": []}
                        screen_kind = "comms"
                    else:
                        # visible in the log (once per line): silent drops
                        # here made missing-speaker/missing-hint issues
                        # undiagnosable. Keyed on TEXT ONLY — the speaker
                        # read jitters too ("Goldy" / "MysteriousGoldy")
                        # and would defeat this.
                        utext = normalize_text(state["dialogue"])
                        if utext and not same_line(utext, last_unknown_logged):
                            last_unknown_logged = utext
                            add_event(
                                "skipped (unknown speaker, no story chrome)",
                                "skip", spk, state["dialogue"], shot=True)
                        candidate, candidate_count = None, 0
                        continue

            miss_streak = 0          # a real read: the line is on screen
            state["speaker"] = normalize_speaker(state["speaker"])
            state["dialogue"] = fix_ocr_text(state["dialogue"])
            # BEFORE streaming: the health warning is long enough that the
            # first sentence would be spoken while the rest is still being
            # matched, and there is no taking that back.
            if boot_notice(state["dialogue"]):
                ntext = normalize_text(state["dialogue"])
                if not same_line(ntext, last_notice_logged):
                    last_notice_logged = ntext
                    add_event("skipped (legal notice)", "skip", None,
                              state["dialogue"], shot=True)
                candidate, candidate_count = None, 0
                continue
            conf = state.get("conf", 1.0)   # 1.0 = engine has no confidences
            # MID-LINE STREAMING: only while the raw read is actually GROWING
            # frame over frame. Clipping a static line would be a trap — its
            # text never changes again, so the tail would never arrive as an
            # extension and the second half would be lost.
            raw_norm = normalize_text(state["dialogue"])
            typing = (last_raw_norm is not None and raw_norm != last_raw_norm
                      and raw_norm.startswith(last_raw_norm))
            last_raw_norm = raw_norm
            if typing and not state["dialogue"].rstrip().endswith(LINE_END):
                head = stream_prefix(state["dialogue"])
                if head:
                    # the clipped head repeats identically while the rest is
                    # typed, so it stabilizes in STABLE_READS frames (~0.3s)
                    # instead of waiting out the patient mid-sentence hold
                    state["dialogue"] = head
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
                candidate_variants.append((state["dialogue"], conf))
            elif jitter:
                # Same on-screen line, slightly different read (". mongrel."
                # vs ".mongrel."). Restarting the count here made lines
                # re-stabilize forever: they'd re-enter dedupe and log a
                # skip every few seconds. Keep counting, adopt the latest.
                candidate = key
                candidate_count += 1
                candidate_variants.append((state["dialogue"], conf))
            else:
                candidate_variants = [(state["dialogue"], conf)]
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
            complete = state["dialogue"].rstrip().endswith(LINE_END)
            if complete and not candidate_growing:
                required = STABLE_READS
            elif complete:
                # SENTENCE STREAMING: the text is still growing but pauses at
                # a sentence boundary (HSR's typewriter pauses exactly there).
                # Speak what's complete now instead of waiting the patient +4;
                # if more text follows, it arrives as growth and the extension
                # path speaks only the remainder — after the prefix finishes.
                # A high-confidence read doesn't need the extra cushion — the
                # cushion exists to ride out shaky mid-render reads, and the
                # recognizer already vouches for this one.
                required = STABLE_READS + (0 if conf >= CONF_TRUSTED else 1)
            else:
                required = STABLE_READS + 4
            if conf < CONF_SHAKY:
                # mid-fade / half-rendered text scores visibly below settled
                # text (a settled chat line reads at 0.98+; the mid-fade
                # "started shan ing (ocation" class doesn't) — make a shaky
                # read earn one extra sighting before it can be spoken
                required += 1
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
                         if normalize_text(v[0]) == key[1]]
            if len(same_norm) > 1:
                # real-word fraction first (measured: the correct split was a
                # 2-of-29 minority, so majority voting picks wrong); engine
                # confidence breaks the ties word-count can't see
                best = max(same_norm,
                           key=lambda v: (text_quality(v[0]), v[1]))[0]
                if best != state["dialogue"]:
                    state["dialogue"] = best

            # Snap to the game's own line. Done HERE, once per stabilized
            # line rather than per frame: the lookup costs ~11ms against a
            # 100k-line map, which is worth paying for a line about to be
            # spoken and not worth paying six times a second. Everything
            # downstream — the log, dedupe, casting, synthesis — then works
            # from the text the game wrote, which is the point: a repaired
            # line is not just pronounced right, it MATCHES the next read
            # of itself, so the jitter that makes a line read twice stops
            # at the source.
            textmap = textmap_for(screens.name)
            if textmap is not None:
                snapped = textmap.snap(state["dialogue"])
                if snapped:
                    # logged only when WORDS changed: a restored full stop
                    # matters to sentence streaming but is not news, and a
                    # line of log per line of dialogue is what this session
                    # spent the afternoon removing
                    if normalize_text(snapped) != key[1]:
                        print(f"[snap] {state['dialogue'][:60]}\n"
                              f"    -> {snapped[:60]}", flush=True)
                        stats["snapped"] += 1
                    state["dialogue"] = snapped
            new_norm = normalize_text(state["dialogue"])

            # Compare against the recent window. Three outcomes:
            #   dup       — jitter variant / repeat → skip
            #   extension — line grew after we spoke a stable prefix
            #               (typewriter race) → speak only the remainder
            #   new       — speak in full
            dup, ext_base = window_verdict(new_norm, state["speaker"],
                                           recent_lines)
            if dup:
                # Log only genuinely INTERESTING repeats — a line we spoke
                # long ago coming round again. A re-read of the line still
                # on screen (or the one we just spoke) is noise: it answers
                # no question and buries the real log.
                # Window persists via spoken_cache.json.
                #
                # The prefix test carries its own weight: the line handled a
                # moment ago is still being typed, so what comes back is not
                # a re-read of it but a LONGER version, and past about 25
                # extra characters the similarity ratio falls under the
                # cutoff (0.89 for one 105-character line that grew by 26 —
                # 2026-08-12 18:20:00). Growth of the line on screen is the
                # same non-answer as a re-read of it.
                if not (same_line(new_norm, last_handled_norm)
                        or (last_handled_norm
                            and new_norm.startswith(last_handled_norm))
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
                remember_line(recent_lines, state["speaker"], new_norm)
            SPOKEN_CACHE.write_text(json.dumps(
                {"window": [[e["speaker"], e["norm"]] for e in recent_lines],
                 "saved_at": time.time(),
                 "voiced_history": voiced_history,
                 "voiced_recent": {k: "".join(w)
                                   for k, w in voiced_recent.items()}}))

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
            mid_up, side_up, sustain = center_burst(t_stable)
            # center SFX (explosions, magic flashes) are mid-panned like VO —
            # demand at least faint speechiness so booms don't count
            vad_peak = max((p for t, p in vad_history
                            if t >= max(t_stable - 1.2, gate_since)),
                           default=0.0)
            # A decisive burst answers for itself. Both other guards are
            # there to keep center-panned SFX out, and both were refusing
            # real voiceover instead: across thirteen sessions this layer
            # fired ZERO times, while the side-flat cap alone rejected 24 of
            # the 46 lines the VAD had independently called voiced (their
            # side channel runs p50 3.8dB, well over the 2.5 cap), and the
            # speechiness floor rejected nearly every line we spoke. A
            # Paimon line went out over her own voiceover at mid+17.3
            # side+5.2 — 12.1dB of centre burst — because her processed
            # squeak scores 0.00 to a speech model built on human speech,
            # which is the exact case this layer exists for.
            decisive = mid_up - side_up >= ENERGY_DECISIVE_OVER_SIDE
            if not voiced and center_energy_voiced(mid_up, side_up, vad_peak):
                # believed outright with any corroboration — faint
                # speechiness or a usually-voiced record. With neither, the
                # burst must also LAST like speech: a dialogue-advance
                # click is decisive on the numbers (mid+13.0 side+1.8
                # against quiet music) but over in ~0.2s, and it silenced
                # a streamed first sentence ("I was a disappointment.")
                # whose speaker the game had never voiced.
                if (vad_peak >= 0.15 or usually_voiced(state["speaker"])
                        or sustain >= ENERGY_SUSTAIN_S):
                    voiced = True
                    print(f"[voiced — center energy] mid+{mid_up:.1f}dB "
                          f"side+{side_up:.1f}dB peak={vad_peak:.2f} "
                          f"sustain={sustain:.2f}s"
                          f"{' decisive' if decisive else ''}", flush=True)
                else:
                    print(f"[center burst too brief for VO — speaking] "
                          f"mid+{mid_up:.1f}dB side+{side_up:.1f}dB "
                          f"sustain={sustain:.2f}s < {ENERGY_SUSTAIN_S}s",
                          flush=True)
            synth_thread.join()
            if ext_base and not voiced:
                # the remainder continues a line we're still speaking —
                # let the prefix finish instead of cutting it off
                wait_until = time.monotonic() + 15
                while speech.playing and time.monotonic() < wait_until:
                    time.sleep(0.05)
            record_voiced(state["speaker"], voiced)
            if voiced:
                stats["skipped_voiced"] += 1
                skip_label = ("skipped (voiced — soft gate)" if soft
                              else "skipped (voiced)")
                if screen_kind != "spoken":
                    skip_label += f" · {screen_kind}"
                add_event(skip_label, "skip", state["speaker"],
                          state["dialogue"], shot=True, extend=True)
                # the line has been HANDLED, silently but deliberately, so
                # the next read of it is not an interesting repeat — before
                # this, every voiced skip was followed by a "repeat
                # (deduped)" row for its own line
                last_handled_norm = new_norm
                print(f"[voiced — skipping mid+{mid_up:.1f} side+{side_up:.1f}] "
                      f"{state['dialogue'][:60]}", flush=True)
                continue

            speech.play(spec.get("audio"))
            speed = spec.get("speed")
            stats["spoken"] += 1
            last_handled_norm = new_norm
            yield_event_id = add_event(
                screen_kind, "spoken", state["speaker"], speak_text,
                voice, speed, can_replay=True, shot=True)
            playing_speaker = state["speaker"]
            gate_max = max((p for t, p in vad_history
                            if t >= gate_since), default=-1.0)
            tag = "" if screen_kind == "spoken" else f"{screen_kind}: "
            said = tts_text(speak_text)
            print(f"[{tag}{state['speaker'] or 'Narrator'} → {voice} ×{speed} "
                  f"gate={gate_max:.2f} mid+{mid_up:.1f} side+{side_up:.1f}] "
                  f"{speak_text}"
                  + (f"\n  ↳ synth heard: {said}" if said != speak_text else ""),
                  flush=True)
    finally:
        speech.stop()
        # let an in-flight swap finish first: killing mid-swap leaves the
        # worker to respawn ffmpeg AFTER we quit, and an orphaned capture
        # keeps overwriting the frame file for the next run
        t = video_swap["thread"]
        if t is not None:
            t.join(timeout=10)
        with video_lock:
            video.kill()
        audio_cap.kill()
        ocr.kill()


if __name__ == "__main__":
    main()
