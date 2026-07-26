# HoyoVoice

**Live TTS voiceover for the dialogue Hoyoverse forgot to voice.**

*Requires macOS on Apple Silicon — see [Requirements](#requirements).*

Genshin Impact and Honkai: Star Rail voice some quest dialogue but leave many lines — and sometimes entire quests — silent. HoyoVoice watches your game feed, notices when a line has no voiceover, and reads it aloud in a per-character artificial voice within about a second. Lines the game *does* voice are left untouched. Everything runs locally on your Mac: no cloud, no API keys, no game modification.

```
console ──HDMI──► capture card ──USB──► Mac
                                         │
              ┌───── ffmpeg (video) ─────┤───── sox (audio) ─────┐
              ▼                                                  ▼
       rolling frame (6 fps)                          48 kHz PCM stream
              │                                                  │
       Apple Vision OCR                                   Silero VAD
       (screen classification)                     (is the game talking?)
              │                                                  │
              └──────────────► orchestrator ◄────────────────────┘
                                    │  new line + no game VO
                                    ▼
                     Kokoro-82M TTS (local, MLX) ──► speakers
                                    │
                     web dashboard · http://127.0.0.1:8470
```

## Requirements

**Platform: macOS on Apple Silicon only.** (M1 or newer, macOS 14 Sonoma or later recommended.) This is a hard requirement, not a packaging gap — the pipeline is built on Apple-only frameworks: TTS runs on MLX (Apple Silicon GPU), OCR uses the Apple Vision framework, and capture uses AVFoundation/CoreAudio. Intel Macs won't run the MLX TTS; Windows and Linux are not supported and would need every pipeline stage replaced.

You'll also need:

- A UVC HDMI capture card (built with a Genki ShadowCast 3; any UVC device should work — even a webcam pointed at a screen, selectable in the dashboard)
- A console or device running the game (on PS5, **disable HDCP** in Settings → System → HDMI or you'll capture black)
- Homebrew, Xcode Command Line Tools (`xcode-select --install`), Python 3.13 (`brew install python@3.13`)
- ~2 GB of disk for models and the Python environment; the game feed itself never leaves your machine

## Quick start

```sh
git clone <this repo> && cd HoyoVoice
./setup.sh              # deps (ffmpeg, sox, espeak-ng, python env), OCR daemon, VAD model
./hoyovoice.sh start    # first run downloads the Kokoro TTS model (~360 MB)
```

Open **http://127.0.0.1:8470** — the app starts **paused**. Pick your video and audio devices from the dropdowns above the preview if they aren't auto-selected, then hit **Resume** and play. Unvoiced lines are spoken about half a second after their text settles.

> **Important:** audio must be captured with sox (the app does this itself). ffmpeg's AVFoundation audio input silently drops ~12% of samples on macOS — if you ever refactor capture, don't route audio through ffmpeg.

## The dashboard

- **Status & controls** — Pause/Resume observation (feed preview blanks while paused), live analytics (VAD health, spoken/skipped/yielded counts, synth/OCR timings, lines per minute).
- **Device pickers** — choose any connected video/audio device; Apply hot-swaps capture and persists the choice.
- **Casting** — every speaker the OCR meets appears here. Assign a voice (instantly re-reads their last line so you can audition), tick **muted** for characters whose real VO the detector can't hear (creature voices), ✕ deletes bogus entries.
- **Test box** — type anything, pick a voice, hear it.
- **Recording** — ⏺ captures game video + game audio, tracks every TTS clip with wall-clock timestamps, and on ⏹ muxes everything into one MP4 (TTS boosted +8dB over the game bed, clips trimmed where real VO interrupted them). Files land in the configurable save folder; raw capture is crash-safe MKV until the mux succeeds.
- **Log** — every decision with the voice used, a 📷 screenshot hover-preview per event for diagnostics, replay buttons, Hide/Clear controls.

## What it recognizes

| Screen | Behavior |
|---|---|
| Standard dialogue (nameplate + centered line) | Spoken in the character's cast voice; VAD-gated against real VO |
| Choice options | Detected, not spoken |
| Full-screen black narration | Narrator voice (requires the ✕ Continue hint) |
| Loading screens (version string + UID) | Lore blurb read by narrator |
| System screens (version string, no UID — e.g. epilepsy warning) | Silent |
| Quick Read book screens | Read incrementally as you scroll; Back stops mid-sentence |
| Info screens (Participant Details…) | Read top-to-bottom via the same reader |
| Floating host bubbles (portrait, no nameplate) | Spoken as `settings.overlay_speaker` |
| Menus, boards, HUDs | Ignored (dialogue must be centered; unknown speakers need the Continue hint) |

## How it stays out of the way

- **Text stabilization** — a line must OCR identically on consecutive frames (typewriter effect).
- **Two-tier VAD gate** — a strong speech spike *or* ~¼s of sustained moderate speech marks a line as voiced; short soft lines ("Which king?") are caught.
- **Late-VO yield** — if voiceover starts while HoyoVoice is talking, it shuts up instantly.
- **Sliding dedupe window** — a line only counts as a repeat if it's within the last 3 messages (fuzzy-matched, so OCR jitter like "l"/"I" can't re-trigger it); replaying a quest re-voices everything.
- **OCR repair** — the game font's I/l confusion is fixed before synthesis.
- **Sentiment pacing** — positive/exclamatory lines read slightly faster, somber ones slower (±~10%).

## Casting — `voices.json`

```jsonc
{
  "characters": {"Rin Tohsaka": {"voice": "af_heart", "speed": 1.0}},
  "defaults":   {"female": "af_nova", "male": "am_michael", "narrator": "bm_george"},
  "always_voiced": ["Reporting Furb"],      // the dashboard "muted" checkboxes
  "settings": {
    "recordings_dir": "~/Videos",
    "overlay_speaker": "Rin Tohsaka",       // voice for floating host bubbles
    "video_device": "ShadowCast 3",
    "audio_device": "ShadowCast 3",
    "dashboard_bind": "127.0.0.1"           // "0.0.0.0" to reach the dashboard
  }                                         // from other machines you trust —
                                            // it has no authentication
}
```

Everything above is editable live from the dashboard. Kokoro ships ~50 voices (`af_*`/`am_*` American, `bf_*`/`bm_*` British); `af_nicole` is broken in the packaged model. OCR misreads within ~80% similarity of a known name snap to it; names in quotes are distinct characters from the narrator.

## Project layout

| Path | Purpose |
|---|---|
| `live.py` | Orchestrator: capture, classify, gate, synthesize, play, record, serve |
| `tools/ocrd.swift` | Apple Vision OCR daemon (compiled to `tools/ocrd` by setup) |
| `tools/classify.py` | OCR blocks → screen type + speaker/dialogue/choices |
| `tools/vad.py` | Silero VAD onnx wrapper (torch-free) |
| `tools/webui.py` | Dashboard (Flask, single page) |
| `voices.json` | Casting + settings |
| `hoyovoice.sh` | start / stop / status / log / restart |

## Troubleshooting

- **Black preview:** HDCP is on (console setting), or the wrong video device is selected.
- **Your capture card isn't in the dropdowns:** it's off the USB bus — replug it; capture auto-recovers within ~10s.
- **Recording sounds fast or crackly:** you've rerouted audio through ffmpeg — don't; sox only (see warning above).
- **A character talks over their own VO:** tick their **muted** box; some processed voices are invisible to speech detection.
- **A menu/board screen gets narrated:** file an issue with the log tail and a screenshot — screen detectors are cheap to add.
- **Capture device busy:** close OBS/QuickTime; the card allows one client.

## Contributing / releases

Changes go in `CHANGELOG.md` under *Unreleased* (Keep a Changelog, SemVer). Most-wanted contribution: a Genshin Impact layout profile — see `PROFILE` in `tools/classify.py` for the shape; calibration needs only screenshots of each screen type.

## Disclaimer

Fan-made accessibility tool. Not affiliated with or endorsed by HoYoverse/miHoYo. It only observes an HDMI feed and plays audio on your computer — it does not modify the game, inject input, or touch game files. Voices are synthetic and are not intended to imitate the games' official voice actors.

## License

[MIT](LICENSE)
