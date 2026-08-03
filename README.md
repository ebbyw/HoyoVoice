# HoyoVoice

**Live TTS voiceover for the dialogue Hoyoverse forgot to voice.**

*Runs on macOS (Apple Silicon) and Windows 10/11 — see [Requirements](#requirements).*

Genshin Impact and Honkai: Star Rail voice some quest dialogue but leave many lines — and sometimes entire quests — silent. HoyoVoice watches your game feed, notices when a line has no voiceover, and reads it aloud in a per-character artificial voice within about a second. Lines the game *does* voice are left untouched. Everything runs locally on your own machine: no cloud, no API keys, no game modification.

```
console ──HDMI──► capture card ──USB──► your computer
                                         │
              ┌───────── video ──────────┤────────── audio ──────┐
              ▼                                                  ▼
       rolling frame (6 fps)                          48 kHz PCM stream
              │                                                  │
            OCR                                          Silero VAD
       (screen classification)                     (is the game talking?)
              │                                                  │
              └──────────────► orchestrator ◄────────────────────┘
                                    │  new line + no game VO
                                    ▼
                         Kokoro-82M TTS (local) ──► speakers
                                    │
                     web dashboard · http://127.0.0.1:8470
```

Every stage above is platform-native, selected at startup by `hv_platform/`:

| Stage | macOS | Windows |
|---|---|---|
| Video | ffmpeg + AVFoundation | ffmpeg + DirectShow |
| Audio | sox + CoreAudio | in-process WASAPI (`sounddevice`) |
| OCR | Apple Vision (`tools/ocrd`) | RapidOCR on DirectML, or built-in Windows OCR (`tools/ocrd_win.py`) |
| TTS | Kokoro-82M on MLX (GPU) | Kokoro-82M on ONNX Runtime |
| Playback | `afplay` | `sounddevice` |

## Requirements

**Platform: macOS on Apple Silicon (M1+, macOS 14+ recommended), or Windows 10/11.** Intel Macs and Linux are not supported: the macOS TTS path needs Apple Silicon for MLX. See `plans/WINDOWS-TESTING.md` for the Windows first-run checklist and platform quirks.

You'll also need:

- A UVC HDMI capture card (built with a Genki ShadowCast 3; any UVC device should work — even a webcam pointed at a screen, selectable in the dashboard)
- A console or device running the game (on PS5, **disable HDCP** in Settings → System → HDMI or you'll capture black)
- macOS: Homebrew, Xcode Command Line Tools (`xcode-select --install`), Python 3.13 (`brew install python@3.13`)
- Windows: winget (ships with Windows) — `setup.ps1` installs ffmpeg and Python itself. Any GPU is strongly recommended: `setup.ps1` installs DirectML, which runs the accurate OCR engine at ~150ms/frame instead of ~4s on CPU (without it the app falls back to the built-in Windows OCR, which misreads small game fonts).
- ~2 GB of disk for models and the Python environment; the game feed itself never leaves your machine

## Quick start

macOS:

```sh
git clone <this repo> && cd HoyoVoice
./setup.sh              # deps (ffmpeg, sox, espeak-ng, python env), OCR daemon, VAD model
./hoyovoice.sh start    # first run downloads the Kokoro TTS model (~360 MB)
```

Windows (PowerShell):

```powershell
git clone <this repo> ; cd HoyoVoice
powershell -ExecutionPolicy Bypass -File setup.ps1   # deps + VAD + Kokoro models (~340 MB)
python hoyovoice.py start
```

Open **http://127.0.0.1:8470** — the app starts **paused**. Pick your video and audio devices from the dropdowns above the preview if they aren't auto-selected, then hit **Resume** and play. Unvoiced lines are spoken about half a second after their text settles.

> **Important (macOS):** audio must be captured with sox (the app does this itself). ffmpeg's AVFoundation audio input silently drops ~12% of samples — if you ever refactor capture, don't route audio through ffmpeg. On Windows, audio is captured in-process via WASAPI; both paths write the same 48 kHz stereo PCM stream that the VAD and the recorder depend on.

## The dashboard

- **Status & controls** — Pause/Resume observation (feed preview blanks while paused), live analytics (VAD health, spoken/skipped/yielded counts, synth/OCR timings, lines per minute).
- **Device pickers** — choose any connected video/audio device; Apply hot-swaps capture and persists the choice.
- **Casting** — every speaker the OCR meets appears here, and each new character is **auto-cast** with a distinct voice from a gender-guessed pool (marked "(auto)" until you choose). Assign a voice (instantly re-reads their last line so you can audition), tick **muted** for characters whose real VO the detector can't hear (creature voices), ✕ deletes bogus entries. **Add cast** pre-assigns a voice to a character before they first appear.
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
| Lore cards (centered title + prose, no UI chrome) | Title + blurb read by narrator |
| System screens (version string, no UID — e.g. epilepsy warning) | Silent |
| Quick Read book screens | Read incrementally as you scroll; Back stops mid-sentence |
| Info screens (Participant Details…) | Read top-to-bottom via the same reader |
| Floating host bubbles (portrait, no nameplate) | Spoken as `settings.overlay_speaker` |
| Menus, boards, HUDs | Ignored (dialogue must be centered; unknown speakers need the Continue hint) |

## How it stays out of the way

- **Text stabilization** — a line must OCR identically on consecutive frames, with extra patience while text is still growing (the typewriter pauses at sentence ends).
- **Two-tier VAD gate** — a strong speech spike *or* ~¼s of sustained moderate speech marks a line as voiced; short soft lines ("Which king?") are caught.
- **Center-energy detector** — game VO is mixed to the stereo center; a mid-channel burst with flat sides (plus a minimum speechiness) catches robot/vocoder voices the speech model can't recognize.
- **Per-speaker voiced prior** — once a character has consistently turned out to be voiced, much weaker audio evidence is enough to stay quiet for them. Some voiceover is quiet enough to sit below any threshold that could be used safely, and for a character with a real voice, silence is the better error. Self-correcting: lines HoyoVoice does speak for them count against the prior.
- **Late-VO yield** — if voiceover starts while HoyoVoice is talking, it shuts up instantly.
- **Sliding dedupe window** — a line only counts as a repeat if it's within the last 3 messages (fuzzy-matched, so OCR jitter like "l"/"I" can't re-trigger it); replaying a quest re-voices everything.
- **OCR repair** — the game font's I/l confusion, dropped apostrophes ("youre" → "you're"), decorative glyphs, and spelled-out interjections ("shh" → "shush") are all fixed before synthesis; Apple Vision is fed a custom vocabulary built from your casting and `settings.custom_words`.
- **Pronunciations** — `settings.pronunciations` substitutes spoken forms at synthesis only ("Wishpower" → "Wish power"); logs keep the real spelling.
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
    "text_fixes": {"lason": "Iason"},       // proper nouns OCR keeps mangling
    "pronunciations": {"Wishpower": "Wish power"},  // spoken form only
    "custom_words": ["Wishpower", "Planarcadia"],   // OCR vocabulary hints
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
| `hv_platform/` | Platform backends (capture, audio, OCR daemon, TTS, playback) — `darwin.py` / `win32.py` behind `base.py` |
| `tools/ocrd.swift` | Apple Vision OCR daemon (compiled to `tools/ocrd` by setup) |
| `tools/ocrd_win.py` | Windows OCR daemon (RapidOCR / Windows.Media.Ocr, same protocol) |
| `tools/classify.py` | OCR blocks → screen type + speaker/dialogue/choices |
| `tools/vad.py` | Silero VAD onnx wrapper (torch-free) |
| `tools/webui.py` | Dashboard (Flask, single page) |
| `voices.json` | Casting + settings |
| `hoyovoice.sh` / `hoyovoice.py` | start / stop / status / log / restart (macOS shell / cross-platform) |

## Troubleshooting

- **Black preview:** HDCP is on (console setting), or the wrong video device is selected.
- **Your capture card isn't in the dropdowns:** it's off the USB bus — replug it; capture auto-recovers within ~10s.
- **Recording sounds fast or crackly:** you've rerouted audio through ffmpeg — don't; sox only (see warning above).
- **A character talks over their own VO:** tick their **muted** box; some processed voices are invisible to speech detection.
- **You hear VO but the VAD never sees speech (max stays 0.00 at a healthy dB):** your console negotiated surround over the passthrough chain, and game dialogue lives in the center channel — the card's 2-channel USB audio only gets front L/R. Set the console's audio output to stereo (PS5: Settings → Sound → Audio Output → Linear PCM, Number of Channels 2.0).
- **A menu/board screen gets narrated:** file an issue with the log tail and a screenshot — screen detectors are cheap to add. Every logged event also saves the raw OCR blocks to `captures/shots/<id>.json`, which is what a fix needs.
- **Capture device busy:** close OBS/QuickTime; the card allows one client.
- **Windows: lines are slow to appear or misread.** Check the startup log for the OCR engine: `engine: rapid (directml, …)` is the good path (~150 ms/frame). If it says `windows`, DirectML didn't install — rerun `setup.ps1`, or `.venv\Scripts\pip install onnxruntime-directml`. The built-in Windows engine is only a fallback and misreads small game fonts. Force a choice with the `HOYOVOICE_OCR_ENGINE` environment variable (`auto`, `rapid`, `windows`).
- **Windows: dashboard won't load / app won't start.** An orphaned instance is holding port 8470 — `python hoyovoice.py stop`, then check Task Manager for stray `python.exe` / `ffmpeg.exe`.

## Contributing / releases

Changes go in `CHANGELOG.md` under *Unreleased* (Keep a Changelog, SemVer). Most-wanted contribution: a Genshin Impact layout profile — see `PROFILE` in `tools/classify.py` for the shape; calibration needs only screenshots of each screen type.

## Disclaimer

Fan-made accessibility tool. Not affiliated with or endorsed by HoYoverse/miHoYo. It only observes an HDMI feed and plays audio on your computer — it does not modify the game, inject input, or touch game files. Voices are synthetic and are not intended to imitate the games' official voice actors.

## License

[MIT](LICENSE)
