# HoyoVoice — Architecture Plan

Live TTS voiceover for unvoiced dialogue in Genshin Impact / Honkai: Star Rail, captured from a PS5 via Genki ShadowCast 3, running locally on macOS.

## Decisions locked in

- **Mode:** live while playing (~1–1.5s latency target)
- **Voices:** distinct AI voice per character, assigned from a local voice library
- **TTS:** local (Kokoro-82M recommended — runs faster than realtime on Apple Silicon via MLX)
- **Source:** PS5 → Genki 3 → Mac (shows up as a standard UVC webcam + USB audio device)

## Pipeline

```
Genki 3 (video + audio)
   │
   ├─► Frame sampler (5–10 fps, dialogue region crop)
   │      └─► Dialogue box detector ─► OCR (Apple Vision) ─► text + speaker name
   │
   └─► Audio tap ─► VAD (Silero) ─► "is this line already voiced?"
                                          │
              ┌───────────────────────────┘
              ▼
        Orchestrator (state machine)
              │  unvoiced + new line
              ▼
        Voice registry (character → voice) ─► Kokoro TTS ─► speaker output
```

## Components

### 1. Capture
The Genki 3 is a UVC device, so no drivers needed. Grab video via AVFoundation (ffmpeg or OpenCV) and audio via the paired USB audio input. Only sample the dialogue region at 5–10 fps — full-frame full-fps processing is unnecessary.

**PS5 gotcha:** disable HDCP (Settings → System → HDMI) or the capture card gets a black screen. Games work fine with HDCP off; only streaming apps require it.

### 2. Dialogue detection + OCR
Both games use fixed UI layouts: dialogue text bottom-center, speaker nameplate above it. Crop those regions and OCR with Apple Vision framework (on-device, fast, free, handles both games' fonts well; call via pyobjc or a tiny Swift helper).

Handle the typewriter effect: OCR the region each sample and only accept the text once it's stable across ~3 consecutive frames.

Start with the main dialogue box only. HSR side-bubbles, black-screen narration, and Genshin's floating overworld chatter are phase-2 layouts.

### 3. Voiced-line gate
The whole point is filling gaps, so never talk over real VO. After text stabilizes, watch the game audio with Silero VAD for ~800ms. Speech detected → the line is voiced, stay silent. No speech → synthesize. VAD is speech-specific, so music/SFX won't false-positive much; tune threshold against real footage.

### 4. Orchestrator
Python asyncio state machine: `IDLE → TEXT_RENDERING → STABLE → VAD_WAIT → SPEAKING → IDLE`. Rules:

- Dedupe: hash (speaker, text) and never re-read a recently spoken line.
- Interrupt: if the on-screen text changes mid-playback (player advanced), cut the current TTS immediately and process the new line.

### 5. TTS + voice registry
Kokoro-82M via `mlx-audio` — ~50 built-in voices, first audio in ~200–300ms on Apple Silicon. A `voices.json` maps character name → voice ID + speed/pitch tweaks. Unknown characters fall back to defaults (one male, one female, one neutral narrator), and the app logs new names so you can assign voices later. XTTS or F5-TTS are drop-in upgrades if you want richer voices for favorites.

### 6. Output
Play TTS through Mac audio out. Two listening setups work: game audio on the TV + TTS from the Mac, or route both through the Mac (passthrough game audio mixed with TTS) for headphone play.

## Latency budget

Text stable ~300ms + VAD wait ~800ms + TTS first-audio ~300ms ≈ **1.4s** after the line finishes rendering. Since unvoiced lines just sit there waiting for you to click, this feels natural in practice.

## Build phases

1. **Proof of concept** — capture a frame from the Genki feed, crop dialogue region, OCR it, print speaker + text. Validates the whole front half.
2. **Live loop** — continuous sampling, text stabilization, dedupe, line-change interruption.
3. **VAD gate** — skip voiced lines reliably.
4. **TTS** — Kokoro integration, voice registry, playback with interrupt.
5. **Polish** — HSR alternate layouts, narration screens, config UI, per-game profiles.

## Risks / open questions

- **UI variety:** each dialogue layout (bubbles, narration, item text) needs its own region profile. Mitigate by shipping per-game layout configs.
- **OCR misreads on fancy names:** matching OCR'd names against a known character list (both games' rosters are public) fixes most of it.
- **1080p vs 4K capture:** Genki 3 captures at 1080p — plenty for OCR.
- **Future option:** match OCR text against datamined dialogue databases for perfect text + speaker attribution. Not needed for v1.

## Suggested stack

Python 3.11+, OpenCV (capture/crop), Apple Vision via pyobjc (OCR), Silero VAD, mlx-audio + Kokoro (TTS), sounddevice (playback), asyncio orchestrator. Single process, ~4 async tasks.
