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
| OCR | Apple Vision (`tools/ocrd`) | RapidOCR on DirectML (English rec model), or built-in Windows OCR (`tools/ocrd_win.py`) |
| TTS | Kokoro-82M on MLX (GPU) | Kokoro-82M on ONNX Runtime |
| Playback | `afplay` | `sounddevice` |

## Requirements

**Platform: macOS on Apple Silicon (M1+, macOS 14+ recommended), or Windows 10/11.** Intel Macs and Linux are not supported: the macOS TTS path needs Apple Silicon for MLX. See `plans/WINDOWS-TESTING.md` for the Windows first-run checklist and platform quirks.

You'll also need:

- A UVC HDMI capture card (built with a Genki ShadowCast 3; any UVC device should work — even a webcam pointed at a screen, selectable in the dashboard)
- A console or device running the game (on PS5, **disable HDCP** in Settings → System → HDMI or you'll capture black)
- macOS: Homebrew, Xcode Command Line Tools (`xcode-select --install`), Python 3.13 (`brew install python@3.13`)
- Windows: winget (ships with Windows) — `setup.ps1` installs ffmpeg and Python itself. Any GPU is strongly recommended: `setup.ps1` installs DirectML, which runs the accurate OCR engine at ~115ms/frame instead of ~4s on CPU (without it the app falls back to the built-in Windows OCR, which misreads small game fonts). `setup.ps1` also fetches an English recognition model (~8 MB) into `models\`.
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
- **Add voice file** — import a Kokoro voice pack (`.pt`, `.safetensors`, `.npy`, `.npz`, `.bin`). It's verified by actually synthesizing with it, auditioned on the spot, and then castable like any built-in voice; ✕ removes one. See [Adding your own voice actors](#adding-your-own-voice-actors).
- **Recording** — ⏺ captures game video + game audio, tracks every TTS clip with wall-clock timestamps, and on ⏹ muxes everything into one MP4 (TTS boosted +8dB over the game bed, clips trimmed where real VO interrupted them). Files land in the configurable save folder; raw capture is crash-safe MKV until the mux succeeds.
- **Log** — every decision with the voice used and what kind of screen it came from (`chat`, `lore card`, `loading screen`, `narration`…), a 📷 screenshot hover-preview per event, replay buttons, Hide/Clear controls, and **⤓ Download log** — one text file with the environment, analytics, casting, the full decision log and the console log. That file is what to attach when reporting a problem.

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
| Message / group-chat panels | Each message in its sender's cast voice, incrementally as you scroll; system notices ("… started sharing location") read by the narrator |
| Info screens (Participant Details…) | Read top-to-bottom via the same reader |
| Floating host bubbles (portrait, no nameplate) | Spoken as `settings.overlay_speaker` |
| Choice prompt, one option | Read as the player character (`Traveler` / `Trailblazer`), after the line it sits above |
| Choice prompt, two or more options | Logged, never spoken — that's a menu |
| Menus, boards, HUDs | Ignored (dialogue must be centered; unknown speakers need the Continue hint) |

## How it stays out of the way

- **Change gate** — OCR is the expensive step, and the frame file is rewritten continuously whether or not anything on screen changed. Before each call the pixels under the last read's text are compared against the previous frame; if none of them moved, that read is replayed instead of paying for a new one. `ocr saved` in the dashboard counts the calls skipped, and `settings.change_gate: false` turns it off.
- **Text stabilization** — a line must OCR identically on consecutive frames, with extra patience while text is still growing, and a short tolerance for frames where the detector loses the line entirely. Where the engine reports confidence, a read it vouches for settles sooner and a visibly shaky one has to earn an extra sighting.
- **Sentence streaming** — a sentence is spoken as soon as it finishes typing, not when the line does. The typewriter pauses at sentence boundaries, and even when it doesn't, a line that is still growing past a closed sentence is read up to that boundary; the remainder follows once it renders, after the first part finishes. Ellipses and abbreviations ("Mr.") are not boundaries, and a line that has stopped changing is always spoken whole.
- **Two-tier VAD gate** — a strong speech spike *or* ~¼s of sustained moderate speech marks a line as voiced; short soft lines ("Which king?") are caught.
- **Center-energy detector** — game VO is mixed to the stereo center; a mid-channel burst with flat sides (plus a minimum speechiness) catches robot/vocoder voices the speech model can't recognize.
- **Per-speaker voiced prior** — once a character has consistently turned out to be voiced, much weaker audio evidence is enough to stay quiet for them. Some voiceover is quiet enough to sit below any threshold that could be used safely, and for a character with a real voice, silence is the better error. Self-correcting: lines HoyoVoice does speak for them count against the prior.
- **Late-VO yield** — if voiceover starts while HoyoVoice is talking, it shuts up instantly, judging the evidence at the same sensitivity that decided to speak: for a character the game has voiced before, the faintest hint is enough. `settings.late_yield: false` turns it off, for a quest with no voice acting in it where every yield is by definition a false one.
- **Sliding dedupe window** — a line only counts as a repeat if it's within the last 3 messages (fuzzy-matched, so OCR jitter like "l"/"I" can't re-trigger it); replaying a quest re-voices everything.
- **OCR repair** — the game font's I/l confusion, dropped apostrophes ("youre" → "you're"), decorative glyphs, and spelled-out interjections ("shh" → "shush") are all fixed before synthesis.
  - *macOS:* Apple Vision is fed a custom vocabulary built from your casting and `settings.custom_words`.
  - *Windows:* RapidOCR reads with an English-trained recognition model (`models\rec_en.onnx`, downloaded by `setup.ps1`). Without it RapidOCR falls back to its bundled Chinese-trained model, which drops spaces — so punctuation spacing is still restored and fused word pairs are still split ("mercyis" → "mercy is"), with capitalised tokens protected so game proper nouns survive. Where several reads of one line disagree, the one that scans as the most real words is the one spoken.
- **Pronunciations** — `settings.pronunciations` substitutes spoken forms at synthesis only ("Wishpower" → "Wish power"); logs, dedupe and casting keep the real spelling. Ships with 69 character names Kokoro reads wrong, because it applies English spelling rules to pinyin and romaji: x becomes /z/ ("Xiao" → "ZY-ah-oh"), q becomes /k/ ("Qiqi" → "KIH-kee"), zh becomes /ʒ/, and a final -e disappears ("Shenhe" → "shenh"). `python tools/pronounce_names.py` prints what the synthesizer says for every name with and without its entry, checked against the same phonemizer Kokoro uses; `--write` merges the table into your `voices.json` and `--custom-words` also feeds both games' full rosters to the OCR vocabulary. Matching is case-insensitive so OCR case jitter can't miss a name — for a name that is *also* an ordinary word ("Gaming", and any entry you add for Jade, Sunday, Hook, Blade, Archer, Robin), list it in `settings.pronunciations_exact` and only the capitalised spelling is respelled.
- **Sentiment pacing** — positive/exclamatory lines read slightly faster, somber ones slower (±~10%).
- **Choice prompts** — a *lone* option is read aloud (with nothing to choose between, the game is putting words in the player character's mouth rather than offering a menu), always after the line it sits above and only into a gap in the talking. It's cast under the player character's name for the current game — `Traveler` in Genshin, `Trailblazer` in Star Rail — so it appears in Casting like anyone else and you can give it whatever voice you want; `settings.choice_speaker` overrides the name. Two or more options are a menu, so they are logged and left unspoken. Either way the prompt appears in the dashboard log, including when it went unread.

## Casting — `voices.json`

```jsonc
{
  "characters": {"Rin Tohsaka": {"voice": "af_heart", "speed": 1.0}},
  "defaults":   {"female": "af_nova", "male": "am_michael", "narrator": "bm_george"},
  "always_voiced": ["Reporting Furb"],      // the dashboard "muted" checkboxes
  "settings": {
    "game": "auto",                         // auto | hsr | genshin
    "recordings_dir": "~/Videos",
    "overlay_speaker": "Rin Tohsaka",       // voice for floating host bubbles
    "choice_speaker": "Aether",             // rename the player character
                                            // (default: Traveler/Trailblazer)
    "video_device": "ShadowCast 3",
    "audio_device": "ShadowCast 3",
    "text_fixes": {"lason": "Iason"},       // proper nouns OCR keeps mangling
    "pronunciations": {"Wishpower": "Wish power"},  // spoken form only
    "custom_words": ["Wishpower", "Planarcadia"],   // OCR vocabulary hints
    "change_gate": true,                    // skip OCR while the text is static
    "late_yield": true,                     // stop talking if game VO starts
    "dashboard_bind": "127.0.0.1"           // "0.0.0.0" to reach the dashboard
  }                                         // from other machines you trust —
                                            // it has no authentication
}
```

Everything above is editable live from the dashboard. Kokoro ships ~50 voices (`af_*`/`am_*` American, `bf_*`/`bm_*` British); `af_nicole` is broken in the packaged model. OCR misreads within ~80% similarity of a known name snap to it; names in quotes are distinct characters from the narrator.

### Adding your own voice actors

Casting is per character, and every character is one entry in `voices.json`. There are three levels to this: assigning one of the voices you have (the everyday case), adding a voice you don't have yet, and replacing the TTS engine entirely.

**From the dashboard (do it this way).** A character appears in **Casting** the moment OCR reads their nameplate, already auto-cast with a distinct voice from a gender-guessed pool and marked `(auto)`. Pick a different voice from their dropdown and they are re-cast immediately — HoyoVoice re-reads their last line in the new voice so you can audition it in context. To cast someone before they first speak, type their **exact** nameplate spelling into **Add cast**, choose a voice, and hit Add; matching is fuzzy to ~80%, so near-misses still land, but a wrong name silently creates a second character. The **muted** checkbox means *never speak for this character* — use it for characters whose real VO the detector can't hear. ✕ deletes an entry, including bogus ones OCR invented. The **Test TTS** box speaks any text in any voice, which is the fastest way to compare candidates before assigning one.

**By hand, in `voices.json`.** Same thing, plus `speed` (1.0 is normal; ~0.85–1.15 is the useful range before it sounds processed):

```jsonc
"characters": {
  "Rin Tohsaka": {"voice": "af_heart", "speed": 1.05},
  "Reporting Furb": {"voice": "am_puck", "speed": 1.0}
}
```

`defaults` sets the fallback voices — `narrator` is used for true narration, lore cards, loading-screen blurbs and system notices, and `female`/`male` seed auto-casting. `always_voiced` is the muted list. `settings.overlay_speaker` and `settings.choice_speaker` name the character that floating host bubbles and lone choice prompts are cast as, so those get voices the same way everyone else does.

> Edit the file with the app **stopped** (`./hoyovoice.sh stop` / `python hoyovoice.py stop`). It is read once at startup and written back on every casting change, so hand-edits made while it's running are overwritten.

**Adding a voice the app doesn't ship with.** **Add voice file** in the dashboard takes a Kokoro voice pack, verifies it, and puts it in the voice menu. Choose the file, optionally give it a name, hit **Add & verify**. From then on it is in *every* voice dropdown — each Casting row, **Add cast**, and **Test TTS** — shown as `Rin (CU)`, and castable to anyone exactly like a packaged voice. It's the same control whether the dashboard is open on this machine or another one: pick a file and it uploads; leave the picker empty and it asks for a path to a file already on the machine running HoyoVoice.

Where those files come from: any Kokoro-82M voice repo (`hexgrad/Kokoro-82M` is the upstream one), or the model's own extra voices — the packaged model carries ~54, of which the menu shows the 28 English ones, and the rest are Spanish (`ef_`/`em_`), French (`ff_`), Hindi (`hf_`/`hm_`), Italian (`if_`/`im_`), Japanese (`jf_`/`jm_`), Portuguese (`pf_`/`pm_`) and Mandarin (`zf_`/`zm_`). Those speak English text through the American English phonemizer, so what you get is a different-sounding *speaker*, not a language switch. On macOS they're the `.safetensors` files under `~/.cache/huggingface/hub/models--prince-canuma--Kokoro-82M/snapshots/*/voices/`; on Windows they're all inside `models\voices-v1.0.bin` — point the picker at that file and name the one you want in the **voice in pack** box, since a pack holds many.

`.pt`, `.safetensors`, `.npy`, `.npz` and `.bin` are all read (`tools/voicepack.py`), no torch required. **Verified means synthesized**, not parsed: a file that reads as a correctly shaped tensor can still be noise or a style vector from another model, so the voice is installed, run through the real engine on a test line, and checked for audible output before it is written into `voices.json` — anything short of that is rolled back, and the reason appears next to the button. A voice that passes is auditioned immediately so you can hear what you just added.

Installed voices are copied into `voices_custom/` and listed under the button; ✕ removes one, and any character cast to it goes back to auto-casting. They survive restarts, and they're the reason casting keeps working after you delete the download. A `.pt` is a pickle — i.e. arbitrary code, in the general case — so the reader for it is a restricted unpickler that will build tensors and nothing else; `tools/test_voicepack.py` includes a hostile file that tries to run a command and pins that it can't.

Two things this doesn't do. It doesn't clone a voice from your own recordings — that's a different model, not a file format, and swapping the engine means accepting its latency, since the pipeline is built around a line being spoken within about a second of settling. And it doesn't add anything to *auto-casting*: new characters still claim built-in voices from `VOICE_POOLS` (`live.py`), so an installed voice is one you cast deliberately. If you'd rather widen the built-in menu instead, `VOICE_CATALOG` in `tools/webui.py` is the packaged-voice list, and it's also the validation gate the cast and test endpoints check against.

**A different TTS engine** is still a code change: synthesis is one class per platform, `Tts` in `hv_platform/darwin.py` (MLX) and `hv_platform/win32.py` (ONNX). Both expose `synth(text, voice, speed)` returning mono float32 at 24 kHz, plus `register_voice`/`forget_voice` for installed packs; everything upstream only ever passes a voice ID through from `voices.json`, so an engine that honors that contract needs no changes anywhere else.

## Games

Reading a screen means knowing where that game draws its nameplate, its dialogue, its choice list, and the chrome that says "this is story, not a menu". Those bands live in `tools/profiles/`, one profile per game; everything else in the pipeline is game-agnostic.

| Game | Status |
|---|---|
| Honkai: Star Rail | Complete — dialogue, narration, lore cards, loading screens, overlays, Quick Read, info screens, chat panels |
| Genshin Impact | **Most screens** — dialogue, choice prompts, full-screen narration, loading-screen tips; all calibrated against a real session. No book/reading UI yet |

`settings.game` picks a profile: `hsr`, `genshin`, or `auto` (the default), which starts on Star Rail and switches when a sustained run of frames carries chrome unique to the other game — Star Rail's `✕ Continue` hint, Genshin's bottom-right UID. The dashboard has the same control, and shows which profile is actually being read in auto mode.

For Genshin, cast **Paimon** and your Traveler by name early: a line from an unknown speaker is only read when the game's story chrome is on screen, and a cast character is trusted without it.

Calibrating a screen type takes captures, not guesswork: every logged event saves the raw OCR blocks to `captures/shots/<id>.json`, and `python tools/replay.py <recording> --game genshin` runs a whole session back through the real classifier.

## Project layout

| Path | Purpose |
|---|---|
| `live.py` | Orchestrator: capture, classify, gate, synthesize, play, record, serve |
| `hv_platform/` | Platform backends (capture, audio, OCR daemon, TTS, playback) — `darwin.py` / `win32.py` behind `base.py` |
| `tools/ocrd.swift` | Apple Vision OCR daemon (compiled to `tools/ocrd` by setup) |
| `tools/ocrd_win.py` | Windows OCR daemon (RapidOCR / Windows.Media.Ocr, same protocol) |
| `tools/classify.py` | Game-agnostic entry point to classification |
| `tools/profiles/` | Per-game screen layouts — `hsr.py` / `genshin.py` behind `base.py` |
| `tools/vad.py` | Silero VAD onnx wrapper (torch-free) |
| `tools/webui.py` | Dashboard (Flask, single page) + `VERSION` |
| `tools/replay.py` | Replay a recording through the real pipeline (see below) |
| `tools/pronounce_names.py` | Character-name spoken forms + roster fetch; audits them against Kokoro's phonemizer |
| `tools/voicepack.py` | Reads/verifies an imported voice pack (`.pt`, `.safetensors`, `.npy`, `.npz`, `.bin`) |
| `voices.json` | Casting + settings |
| `voices_custom/` | Voice packs added from the dashboard, in canonical form |
| `setup.sh` / `setup.ps1` | One-time install (macOS / Windows) |
| `hoyovoice.sh` / `hoyovoice.py` | start / stop / status / log / restart (macOS shell / cross-platform) |
| `plans/` | Windows first-run checklist, pre-merge notes |

## Debugging a session

Two things make problems reproducible without re-playing the game:

1. **⤓ Download log** in the dashboard — environment, analytics, casting, every decision, and the console log in one file.
2. **Record the session** (⏺), then replay it through the real pipeline:

```sh
python tools/replay.py ~/Videos/rec_20260803_112929.mp4 --start 68 --duration 30
```

That runs the actual OCR daemon, classifier, stabilization, dedupe, VAD gate and yield against the recording — only capture, TTS and playback are simulated — in a throwaway state directory, so it can't touch your casting or caches. Most behaviour questions ("why did it read that twice?") are answerable this way in about a minute. Runs on either platform.

## Troubleshooting

- **Black preview:** HDCP is on (console setting), or the wrong video device is selected.
- **Your capture card isn't in the dropdowns:** it's off the USB bus — replug it; capture auto-recovers within ~10s.
- **Recording sounds fast or crackly:** you've rerouted audio through ffmpeg — don't; sox only (see warning above).
- **A character talks over their own VO:** tick their **muted** box; some processed voices are invisible to speech detection.
- **You hear VO but the VAD never sees speech (max stays 0.00 at a healthy dB):** your console negotiated surround over the passthrough chain, and game dialogue lives in the center channel — the card's 2-channel USB audio only gets front L/R. Set the console's audio output to stereo (PS5: Settings → Sound → Audio Output → Linear PCM, Number of Channels 2.0).
- **A menu/board screen gets narrated:** file an issue with the log tail and a screenshot — screen detectors are cheap to add. Every logged event also saves the raw OCR blocks to `captures/shots/<id>.json`, which is what a fix needs.
- **Capture device busy:** close OBS/QuickTime; the card allows one client.
- **Windows: lines are slow to appear or misread.** Check the startup log for the OCR engine: `engine: rapid (directml, …)` is the good path (~115 ms/frame). If it says `windows`, DirectML didn't install — rerun `setup.ps1`, or `.venv\Scripts\pip install onnxruntime-directml`. The built-in Windows engine is only a fallback and misreads small game fonts. Force a choice with the `HOYOVOICE_OCR_ENGINE` environment variable (`auto`, `rapid`, `windows`).

  The line above it should read `[ocrd_win] rec model: rec_en.onnx`. Without it RapidOCR is recognising English with its bundled Chinese-trained model, which fuses words ("fora", "RinTohsaka") — rerun `setup.ps1`, or point `HOYOVOICE_REC_MODEL` and `HOYOVOICE_REC_KEYS` at the model and its dictionary.

- **Words are being spoken half-typed, or the log looks like it stopped reading.** The change gate skips OCR while the text region is unchanged, so a bug there shows up as either stale text or no savings. `ocr saved` in the dashboard metrics is the count of skipped calls: zero on static dialogue means it is failing open on every frame, and lines cut mid-word mean it is skipping when it shouldn't. `settings.change_gate: false` turns it off, which is the fastest way to tell whether it is involved at all.
- **Windows: dashboard won't load / app won't start.** An orphaned instance is holding port 8470 — `python hoyovoice.py stop`, then check Task Manager for stray `python.exe` / `ffmpeg.exe`.

## Contributing / releases

Changes go in `CHANGELOG.md` under *Unreleased* (Keep a Changelog, SemVer). Most-wanted contribution: finishing the Genshin Impact layout profile — see **Games** above and the `CALIBRATE` comments in `tools/profiles/genshin.py`; each one names the screen a capture is needed of.

## Disclaimer

Fan-made accessibility tool. Not affiliated with or endorsed by HoYoverse/miHoYo. It only observes an HDMI feed and plays audio on your computer — it does not modify the game, inject input, or touch game files. Voices are synthetic and are not intended to imitate the games' official voice actors.

That last point is yours to keep once you import a voice: **Add voice file** will load any Kokoro voice pack you point it at, and the licence of a pack you downloaded — and whether it is a clone of a real person's voice — is between you and wherever you got it. Imported packs stay on your machine (`voices_custom/` is gitignored) and this project neither ships nor endorses any of them.

## License

[MIT](LICENSE)
