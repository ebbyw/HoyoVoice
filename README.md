# HoyoVoice

> Fan-made accessibility tool. **Not affiliated with or endorsed by HoYoverse/miHoYo**; Genshin Impact, Honkai: Star Rail and their text, art and marks are theirs. HoyoVoice only observes an HDMI feed and plays audio on your computer — it does not modify the game, inject input, or touch game files, and no game content ships in this repository. See the full [Disclaimer](#disclaimer) and [NOTICE](NOTICE).

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
- **Device pickers** — choose any connected video/audio device; Apply hot-swaps capture and persists the choice. **speaks to** picks which output device HoyoVoice talks through (Windows), so its reads can go to your headset while the game keeps the desktop speakers, or the other way round — leave it on **System default** to follow whatever Windows is set to. It applies to the next line, without restarting capture, so it's safe to change mid-session or mid-recording. (macOS plays on the system default; route per-app from Sound settings.)
- **Casting** — every speaker the OCR meets appears here, and each new character is **auto-cast** with a distinct voice from a gender-guessed pool (marked "(auto)" until you choose). Assign a voice (instantly re-reads their last line so you can audition), tick **muted** for characters whose real VO the detector can't hear (creature voices), ✕ deletes bogus entries. **Add cast** pre-assigns a voice to a character before they first appear.
- **Test box** — type anything, pick a voice, hear it.
- **Voice packs page** — importing voice packs and blending voices live on their own page (**Voice packs — add & blend** under the Test box) rather than in the main controls, since neither is a mid-session activity. **Add voice file** imports a Kokoro voice pack (`.pt`, `.safetensors`, `.npy`, `.npz`, `.bin`); **Blend voices** mixes any voices in the menu, by weight, into a new one. Both are verified by actually synthesizing with the result, auditioned on the spot, and then castable like any built-in voice; ✕ removes one. See [Adding your own voice actors](#adding-your-own-voice-actors).
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
| Quick Read book screens (Star Rail) | Read incrementally as you scroll; Back stops mid-sentence |
| Readable articles (Genshin — "Investigative Report…") | Title then body by the narrator, incrementally as you scroll; Return stops mid-sentence |
| Message / group-chat panels | Each message in its sender's cast voice, incrementally as you scroll; system notices ("… started sharing location") read by the narrator |
| Info screens (Participant Details…) | Read top-to-bottom via the same reader |
| Floating host bubbles (portrait, no nameplate) | Spoken as `settings.overlay_speaker` |
| Comms messages (Genshin — left-anchored nameplate over the HUD, e.g. "Eye of Graeae") | Spoken in the sender's cast voice; the anchored-plate geometry stands in for story chrome |
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
- **Sliding dedupe window** — a line counts as a repeat only against the line spoken immediately before it, and only when the same character said both (fuzzy-matched, so OCR jitter like "l"/"I" can't re-trigger it). Anyone else speaking in between makes it a fresh line, so a character can say the same words twice in a scene, and two characters can echo each other word for word, and both get read. Replaying a quest re-voices everything. The window survives a restart for 10 minutes, so a crash mid-scene doesn't re-read the line still on screen — and **Clear** in the dashboard empties it along with the log, for when you restart *into* the same content and want it read as new. The line already on screen is never re-read by that: it has already fired, and Clear can't make the app start talking at you.
- **OCR repair** — the game font's I/l confusion, dropped apostrophes ("youre" → "you're") and decorative glyphs are all fixed before synthesis.
  - *macOS:* Apple Vision is fed a custom vocabulary built from your casting and `settings.custom_words`.
  - *Windows:* RapidOCR reads with an English-trained recognition model (`models\rec_en.onnx`, downloaded by `setup.ps1`). Without it RapidOCR falls back to its bundled Chinese-trained model, which drops spaces — so punctuation spacing is still restored and fused word pairs are still split ("mercyis" → "mercy is"), with capitalised tokens protected so game proper nouns survive. Where several reads of one line disagree, the one that scans as the most real words is the one spoken.
- **Snapping to the game's text** — `settings.textmap` names a file of the game's own dialogue strings, per game (`{"genshin": "…/TextMapEN.json", "hsr": "…/TextMapEN.json"}`; a bare string is taken as the current game's). A settled line is matched back to the line it came from before anything else sees it, which repairs the everyday damage at the source: `Ves.` becomes `Yes.`, `Choosel"harbor repairs"` becomes `Choose "harbor repairs"`, a dropped full stop comes back (sentence streaming reads punctuation), and the repaired line then *matches the next read of itself*, so the jitter that makes a line read twice stops before dedupe ever sees it. A match has to score 0.82 and beat the runner-up by 0.05, or the read is kept exactly as it was — measured on 164 real misreads from recorded sessions, 113 were repaired to the right line, 51 refused, and none snapped to a wrong one. Refusals are the point: a garbled line read aloud sounds worse, but a confident wrong sentence *is* worse.

  Set `settings.player_name` to your character's in-game name. Thousands of entries carry a `{NICKNAME}` placeholder the game substitutes at runtime, and without it every one of those lines is unmatchable. The rest of a dump's markup is unwrapped the way the game draws it — the `#` sentinel, `{F#…}{M#…}` gender pairs (both indexed, since the game picks one), `{RUBY#…}` glosses (drawn above the word, not in the line), `<color>`/`<unbreak>`/`<i>` spans, escaped newlines — and an entry still holding a runtime placeholder is dropped rather than indexed subtly wrong. A map loads on first use of its game — the current full dumps are 398k usable lines (Genshin) and 315k (Star Rail), which cost ~9 s to index and 600-770 MB resident, so the other game's map is never built for a session that doesn't read it. A lookup is ~20 ms against a dump that size, paid once per spoken line.

  **Check a dump before trusting it:** `python tools/textmap.py <map.json> --nickname <name>` scores it against the lines this install has actually read. A dump built for the patch you are playing scores most of them 0.95+; a stale one leaves them under 0.60, because those lines are simply not in it and snapping will do nothing at all. Plain text (one line per entry), a JSON array, or a JSON object of id → line. **No such file ships with HoyoVoice, and this project does not help you obtain one** — the games' text is HoYoverse's. If you have such a file, the setting will use it; leave it empty and nothing changes.

- **Pronunciations** — `settings.pronunciations` substitutes spoken forms at synthesis only ("Wishpower" → "Wish power"); logs, dedupe and casting keep the real spelling. Ships with ~76 character names Kokoro reads wrong, because it applies English spelling rules to pinyin and romaji: x becomes /z/ ("Xiao" → "ZY-ah-oh"), q becomes /k/ ("Qiqi" → "KIH-kee"), zh becomes /ʒ/, and a final -e disappears ("Shenhe" → "shenh"). Lore terms live in the same map but a separate table (`TERMS`), since no roster lists them and the coverage report can't check them — an invented word is exactly what English spelling rules mangle, so they ship for the same reason, and `--custom-words` feeds them to OCR too. `python tools/pronounce_names.py` prints what the synthesizer says for every entry with and without its respelling, checked against the same phonemizer Kokoro uses; `--check` reports what your own `voices.json` would actually say and what it's missing; `--write` merges the table in, and `--custom-words` also feeds both games' full rosters to the OCR vocabulary. Matching is case-insensitive so OCR case jitter can't miss a name — for a name that is *also* an ordinary word ("Gaming", and any entry you add for Jade, Sunday, Hook, Blade, Archer, Robin), list it in `settings.pronunciations_exact` and only the capitalised spelling is respelled.
- **Startup health warning** — the ~150-word epilepsy notice both games open on is skipped, and appears in the log as `skipped (legal notice)` so it's clear it was seen rather than missed. It has to be recognised by what it says: it renders as a chrome-free title + prose card, structurally identical to a real lore card. The markers are all medical (`epilep`, `consult your physician`, `seek medical attention`, `immediately stop playing`) and none are from the title — `before playing` would catch it too, but also catches "Read the notice before playing", and silently eating a real line is the worse failure. Several markers rather than one, so a single OCR slip inside a word can't hand you the whole wall of text.
- **Sentence-by-sentence synthesis** — Kokoro predicts prosody for a whole utterance in one pass, and a long line degrades its own opening: `Huh!? You… You're Paimon, travel companion of the great hero Ebby!` hisses through the interjection and into the word after it, while `Huh!?` and the rest of the line each come out clean synthesized alone. So a settled line is split at sentence ends, each sentence is synthesized on its own, and the pieces are spliced with an 80 ms pause (`SENTENCE_GAP`). Found by bisection against the failing line, which also ruled out the `!?`, the ellipsis and the name's respelling — all three A/B'd identical. A single-sentence line is one call and one piece exactly as before, so the common case costs nothing; the extra call on a two-sentence line is invocation overhead, not synthesis, and measured at ~50 ms. `…` is not a boundary here, same as in sentence streaming.
- **Stage directions** — `*cough*` is a noise rather than a word, so `settings.sound_effects` maps the inside of a stage direction to an audio file, spliced into the line where the direction sat (Kokoro can't cough; the only convincing cough is a recording), or to a respelling to speak in its place: `{"cough": "sounds/cough.wav", "sigh": "Ahem."}`. Relative paths are from the project directory, any sample rate and channel count is accepted, and a direction with no entry is read as the bare word exactly as before — which for `*sigh*` is what you want anyway. Map one to `""` to cut it silently.
- **Interjections and stammers** — a noise written out is not a word, and the phonemizer treats it as one. `Shh` spells itself ("S-H-H"), `Uhm` is `ˈum` ("oom"), `Aaah` is `ˈææə`; they read as `shush`, `um` and `ah`. Stammers are worse, and these games write them constantly: a lone initial is read as the **letter's name** — `W-what` was "DOUBLE-YOU-what", `N-no` "EN-no", `A-aah` "AY-ah". Spelling the stammer as a syllable fixes it (`Wuh-what`, `Nuh-no`, `Ah-ah`), and the repair only fires when the initial matches the word after it, so `X-ray`, `T-shirt` and `e-mail` are untouched. `E`/`I`/`O` are left alone — they already read as sounds (`I-I'm` → `ˌIˌIm`). All of it runs in the same synthesis-only pass as the name respellings, so the log keeps `Shh` and `W-what` as written and the `↳ synth heard:` line shows what was said instead.
- **Sentiment pacing** — positive/exclamatory lines read slightly faster, somber ones slower (±~10%). Scored on the line as the game wrote it, before the respellings turn names into nonsense words.
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
    "output_device": "",                    // where WE speak; "" = whatever
                                            // the OS default output is
    "text_fixes": {"lason": "Iason"},       // proper nouns OCR keeps mangling
    "pronunciations": {"Wishpower": "Wish power"},  // spoken form only
    "sound_effects": {"cough": "sounds/cough.wav",  // *stage directions* — a
                      "sigh": "Ahem."},             // file, or words to say
    "custom_words": ["Wishpower", "Planarcadia"],   // OCR vocabulary hints
    "textmap": {"genshin": "", "hsr": ""},  // the games' own dialogue strings;
                                            // "" = off (see below)
    "player_name": "",                      // your character's in-game name,
                                            // for the map's {NICKNAME} entries
    "change_gate": true,                    // skip OCR while the text is static
    "change_gate_frac": 0.01,               // gate sensitivity: share of a
                                            // box's text pixels that may move
    "anchors": true,                        // match game-chrome templates
                                            // (log + ROI evidence)
    "anchor_roi": true,                     // crop OCR to the matched screen's
                                            // ROI (measured ~42% off Windows
                                            // ocr_ms; false = full frames)
    "late_yield": true,                     // stop talking if game VO starts
    "dashboard_bind": "127.0.0.1"           // "0.0.0.0" to reach the dashboard
  }                                         // from other machines you trust —
                                            // it has no authentication
}
```

Everything above is editable live from the dashboard. The packaged model ships ~54 voices across eight languages (see [Adding your own voice actors](#adding-your-own-voice-actors)); `af_nicole` is broken in the packaged model. OCR misreads within ~80% similarity of a known name snap to it; names in quotes are distinct characters from the narrator.

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

**Adding a voice the app doesn't ship with.** **Add voice file** on the dashboard's **Voice packs** page takes a Kokoro voice pack, verifies it, and puts it in the voice menu. Choose the file, optionally give it a name, hit **Add & verify**. From then on it is in *every* voice dropdown — each Casting row, **Add cast**, and **Test TTS** — shown as `Rin (CU)`, and castable to anyone exactly like a packaged voice. It's the same control whether the dashboard is open on this machine or another one: pick a file and it uploads; leave the picker empty and it asks for a path to a file already on the machine running HoyoVoice.

**Making a voice out of the ones you have.** A Kokoro voice is a style tensor in a continuous embedding space, so a weighted average of two (or more) is another plausible speaker — that's all **Blend voices** does. Pick voices, give each a weight, and the mix installs like an imported pack: same verification by synthesis, same immediate audition, same ✕ to remove. Weights are relative and normalized before mixing — 3 and 1 mean 75% and 25% — because a combination whose weights sum above 1 inflates the style vectors into overdriven prosody, and below 1 into mumbling. The recipe is kept as the voice's source (hover its pill), so a good mix can be reproduced or refined later. Blends of blends work; blending across accents and genders works and is where the interesting voices are — audition before casting.

Where those files come from: any Kokoro-82M voice repo (`hexgrad/Kokoro-82M` is the upstream one). The packaged model's own ~54 voices are all in the menu already — the English ones (`af_`/`am_` American, `bf_`/`bm_` British) plus Spanish (`ef_`/`em_`), French (`ff_`), Hindi (`hf_`/`hm_`), Italian (`if_`/`im_`), Japanese (`jf_`/`jm_`), Portuguese (`pf_`/`pm_`) and Mandarin (`zf_`/`zm_`). The non-English ones speak English text through the American English phonemizer, so what you get is a different-sounding *speaker*, not a language switch — audition before casting, since their English varies from a pleasant accent to barely intelligible.

`.pt`, `.safetensors`, `.npy`, `.npz` and `.bin` are all read (`tools/voicepack.py`), no torch required. **Verified means synthesized**, not parsed: a file that reads as a correctly shaped tensor can still be noise or a style vector from another model, so the voice is installed, run through the real engine on a test line, and checked for audible output before it is written into `voices.json` — anything short of that is rolled back, and the reason appears next to the button. A voice that passes is auditioned immediately so you can hear what you just added.

Installed voices are copied into `voices_custom/` and listed under the button; ✕ removes one, and any character cast to it goes back to auto-casting. They survive restarts, and they're the reason casting keeps working after you delete the download. A `.pt` is a pickle — i.e. arbitrary code, in the general case — so the reader for it is a restricted unpickler that will build tensors and nothing else; `tools/test_voicepack.py` includes a hostile file that tries to run a command and pins that it can't.

Two things this doesn't do. It doesn't clone a voice from your own recordings — that's a different model, not a file format, and swapping the engine means accepting its latency, since the pipeline is built around a line being spoken within about a second of settling. And it doesn't add anything to *auto-casting*: new characters still claim built-in voices from `VOICE_POOLS` (`live.py`), so an installed voice is one you cast deliberately. If you'd rather widen the built-in menu instead, `VOICE_CATALOG` in `tools/webui.py` is the packaged-voice list, and it's also the validation gate the cast and test endpoints check against.

**A different TTS engine** is still a code change: synthesis is one class per platform, `Tts` in `hv_platform/darwin.py` (MLX) and `hv_platform/win32.py` (ONNX). Both expose `synth(text, voice, speed)` returning mono float32 at 24 kHz, plus `register_voice`/`forget_voice` for installed packs; everything upstream only ever passes a voice ID through from `voices.json`, so an engine that honors that contract needs no changes anywhere else.

## Games

Reading a screen means knowing where that game draws its nameplate, its dialogue, its choice list, and the chrome that says "this is story, not a menu". Those bands live in `tools/profiles/`, one profile per game; everything else in the pipeline is game-agnostic.

| Game | Status |
|---|---|
| Honkai: Star Rail | Complete — dialogue, narration, lore cards, loading screens, overlays, Quick Read, info screens, chat panels |
| Genshin Impact | **All screens** — dialogue, choice prompts, full-screen narration, loading-screen tips, readable articles and books opened from the inventory archive, and the Snezhnaya update's comms messages (left-anchored sender over the live HUD); all calibrated against real sessions. The archive books turned out to be the same reading panel the articles use — a 2026-08-09 session read a 60-page play script from it end to end |

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
| `tools/change_gate.py` | Pixel gate that skips OCR while on-screen text is static |
| `tools/anchors.py` | Game-chrome template matching + ROI cropping (`tools/profiles/anchors/`) |
| `tools/textmap.py` | Snap a read line back to the game's own text (`settings.textmap`); also the dump checker CLI |
| `tools/ocr_bench.py` | OCR timing benchmark for gate/ROI measurements |
| `tools/vad.py` | Silero VAD onnx wrapper (torch-free) |
| `tools/webui.py` | Dashboard (Flask, single page) + `VERSION` |
| `tools/replay.py` | Replay a recording through the real pipeline (see below) |
| `tools/pronounce_names.py` | Character-name spoken forms + roster fetch; audits them against Kokoro's phonemizer |
| `tools/voicepack.py` | Reads/verifies an imported voice pack (`.pt`, `.safetensors`, `.npy`, `.npz`, `.bin`) |
| `voices.json` | Casting + settings |
| `voices_custom/` | Voice packs added from the dashboard, in canonical form |
| `setup.sh` / `setup.ps1` | One-time install (macOS / Windows) |
| `hoyovoice.sh` / `hoyovoice.py` | start / stop / status / log / restart (macOS shell / cross-platform) |
| `plans/` | Release process, pre-merge checklist, Windows first-run checklist, OCR roadmap, anchor/ROI design, OCR engine research |

## Debugging a session

Two things make problems reproducible without re-playing the game:

1. **⤓ Download log** in the dashboard — environment, analytics, casting, every decision, and the console log in one file. A line the TTS path changed carries a second `↳ synth heard:` line with what the synthesizer was actually handed; respellings and delivery fixes are invisible everywhere else by design, which otherwise leaves "is that fix even running on this machine?" unanswerable from a log.
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
- **Nothing comes out of the device you picked in "speaks to":** the console log says which output it resolved (`[audio] output → …`) and lists what it can see when a saved name no longer matches — a device that's off or asleep drops off that list, and HoyoVoice keeps talking on the system default until it's back.
- **Windows: lines are slow to appear or misread.** Check the startup log for the OCR engine: `engine: rapid (directml, …)` is the good path (~115 ms/frame). If it says `windows`, DirectML didn't install — rerun `setup.ps1`, or `.venv\Scripts\pip install onnxruntime-directml`. The built-in Windows engine is only a fallback and misreads small game fonts. Force a choice with the `HOYOVOICE_OCR_ENGINE` environment variable (`auto`, `rapid`, `windows`).

  The line above it should read `[ocrd_win] rec model: rec_en.onnx`. Without it RapidOCR is recognising English with its bundled Chinese-trained model, which fuses words ("fora", "RinTohsaka") — rerun `setup.ps1`, or point `HOYOVOICE_REC_MODEL` and `HOYOVOICE_REC_KEYS` at the model and its dictionary.

- **Words are being spoken half-typed, or the log looks like it stopped reading.** The change gate skips OCR while the text region is unchanged, so a bug there shows up as either stale text or no savings. `ocr saved` in the dashboard metrics is the count of skipped calls: zero on static dialogue means it is failing open on every frame, and lines cut mid-word mean it is skipping when it shouldn't. `settings.change_gate: false` turns it off, which is the fastest way to tell whether it is involved at all.
- **A name is still mispronounced after you pulled a fix for it.** `voices.json` is gitignored — it's yours, seeded from `voices.example.json` on first run only — so a pull never updates the spoken forms in it. Stop the app and run `python tools/pronounce_names.py --write`, which merges the shipped table in and overwrites any entry that has since changed. The `↳ synth heard:` line in the log tells you which respelling is actually in play, and second machines are the usual culprit: each one has its own `voices.json`, seeded whenever *it* was first run.
- **Windows: dashboard won't load / app won't start.** An orphaned instance is holding port 8470 — `python hoyovoice.py stop`, then check Task Manager for stray `python.exe` / `ffmpeg.exe`.

## Contributing / releases

Changes go in `CHANGELOG.md` under *Unreleased* (Keep a Changelog, SemVer). Both game profiles are fully calibrated today; the most-wanted contribution is captures of screens that misbehave — every logged event saves its raw OCR blocks to `captures/shots/<id>.json`, and that file plus the log tail is what a new detector or band fix needs (see **Debugging a session**).

## Disclaimer

Fan-made accessibility tool. Not affiliated with or endorsed by HoYoverse/miHoYo. It only observes an HDMI feed and plays audio on your computer — it does not modify the game, inject input, or touch game files. Voices are synthetic and are not intended to imitate the games' official voice actors.

That last point is yours to keep once you import a voice: **Add voice file** will load any Kokoro voice pack you point it at, and the licence of a pack you downloaded — and whether it is a clone of a real person's voice — is between you and wherever you got it. Imported packs stay on your machine (`voices_custom/` is gitignored) and this project neither ships nor endorses any of them.

## License

[MIT](LICENSE)
