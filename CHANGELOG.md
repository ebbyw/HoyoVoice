# Changelog

All notable changes to HoyoVoice are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).
Add entries under **Unreleased** as you work; move them into a dated version section when you tag a release.

## [Unreleased]

## [0.7.1] - 2026-08-07

### Changed

- **A choice prompt with a single option is now read aloud.** With nothing to choose between, the game isn't offering a menu so much as putting words in the player character's mouth, and the option reads as part of the scene; two or more options are a real menu and stay logged-only, as before. `settings.choice_speaker` gives the option a voice — the Traveler, say — otherwise the narrator reads it.

  Getting the order right is the whole problem: the option bubble renders complete while the line beneath it is still typing, so a naive read speaks the answer before the question. The option is therefore held until the line under it has been through the gate (spoken, deduped, or skipped as voiced), then read into the first gap where our own voice is idle and the game's has stopped — the line may be voiced even when the option is not. It is deliberately not conditional on the option still being on screen: players click through while the line is still being read, and requiring it would mean the option is almost never read at a natural pace. What bounds it instead is time — an option that finds no gap within 8 seconds is dropped rather than arriving several beats late, and logged as `choice prompt (not read — too late)`. A spoken option also joins the dedupe window, since picking a lone option usually makes the game say it straight back as a dialogue line.

  Both paths verified against the calibration recording: the prompt in a stretch with a pause was read in order, after its line; the one in wall-to-wall dialogue found no gap and was logged unread.

## [0.7.0] - 2026-08-07

### Added

- **Per-game layout profiles (`tools/profiles/`), and the beginning of Genshin Impact support.** Screen classification was written against Honkai: Star Rail and had its geometry and chrome assumptions spread through one module — including the rule that gates every unknown speaker's line on the `✕ Continue` hint, which Genshin does not draw at all. That single check is why a Genshin frame whose nameplate and line both read correctly still ended in `skipped (unknown speaker, no Continue hint)`. The bands and detectors now live in a profile per game behind a shared base, and the gate asks the active profile what its story chrome looks like — Star Rail's Continue hint, Genshin's auto-play toggle. `settings.game` (`auto` | `hsr` | `genshin`) and a dashboard dropdown select one; `auto` switches on a sustained run of frames carrying chrome unique to the other game, deliberately sticky so a single misread can't swap layouts mid-conversation. `tools/replay.py --game` pins a profile for a replay. The Star Rail path is unchanged — verified by fuzzing 20,000 randomized frames through the pre-refactor classifier and the new profile side by side, all ten detectors exercised, zero differences.
- **The Genshin profile, calibrated against a real session** (a 4-minute Natlan world quest: 198 dialogue frames of 281). Dialogue screens, choice prompts, full-screen narration and loading-screen tips are all read from measurements off that capture; nothing is enabled on a guessed band, because a wrong one doesn't fail quietly — it narrates menus. Each `CALIBRATE` comment in `tools/profiles/genshin.py` names the capture still needed for what remains. What the capture changed, measured over those frames — 0 lines readable before, 196 parsed cleanly after:
  - Genshin's nameplate can carry a second, smaller line: the speaker's role ("Pucli" over "Entertainment Supervisor"). It lands exactly where the first dialogue row would, and was being read aloud as the opening words of every one of that NPC's lines — 100 frames of the capture. What separates it from a real row is how tightly it hugs the plate (0.023–0.031 below its baseline, against 0.041–0.063 for a first dialogue row); font size does *not*, since Vision returns anything from 0.016 to 0.029 for the same subtitle depending on which glyphs it catches.
  - Rows are accepted across the whole text column instead of by Star Rail's centered-seed test. Genshin centers each row, but only once it is fully typed — the typewriter reveals a row rightward from its final left edge, so a half-typed row's center sits far left of the axis, and the centered test dropped those rows entirely.
  - Stylized nameplates read weakly: 25 of 197 plate reads came back at confidence ≤0.5 (`"Tenoyollotzin"` on 22 of them) against 1.0 for the dialogue rows. The plate slot now has its own lower floor — it is constrained by geometry rather than by text — because at 0.8 those frames lost their speaker *and* fell back to the plate-less band, which is what pulled the role subtitle in.
  - Loading-screen tips ("Elements", "Elemental Reaction") are read by the narrator. These were being caught by the Star Rail *lore card* detector, which happens to work only when the OCR engine misses the permanent bottom-right UID — true for the Windows recogniser on that art, false for Apple Vision, so the same screen read on one platform and was silent on the other. Genshin's own detector tolerates the bottom strip, which is on screen in every context here. It needs two signals to fire, not geometry alone: once the strip is discounted, a loading card and a dialogue box have the *same* shape — a short centered heading over centered prose, in the same band — so a loose rule doesn't merely miss loading screens, it swallows every line of dialogue and narrates it, nameplate included (measured: 117 of 281 frames, before the chrome and plate-floor tests were added; 1 after, the loading frame itself).
  - Choice prompts are parsed: options float right of the box, left-aligned past a chat-bubble icon at x 0.686–0.689. A wrapped option's second row is set smaller than its first (0.019 against 0.024), so Star Rail's 0.020 height floor cut it off mid-sentence. Two findings came out of the same frames: a pending choice **hides** the auto-play toggle, so `trusts_dialogue` counts an on-screen option as story chrome in its own right — otherwise a not-yet-cast speaker is skipped at exactly the moment the game is asking the player something — and the teleport map lists its waypoints in the same column at the same left edge, reading as a three-option prompt, so both the trust rule and the choice list require a nameplate, which the map has none of.
  - Star Rail's "a plate with nothing under it is not a plate" re-parse is off here. Genshin's plate band starts above any dialogue row, so the re-parse has nothing to rescue and would read the plate's own rows as speech.

- **Choice prompts appear in the log, and are never spoken.** The options are not reliably one kind of text — sometimes a menu the player picks from, sometimes the player character's own lines about to be said aloud — so reading them would be right half the time, and wrong here means talking over the scene. They're logged as `choice prompt (not read)`, once per prompt, before the branches that might skip the line itself, so the options are visible even when the line is not. Applies to both games; a prompt has to survive two frames before it is logged, since OCR jitters the first sighting.

### Fixed

- **`tools/replay.py` could not replay anything on macOS.** The replay backend imported the *Windows* OCR daemon unconditionally ("same daemon, runs anywhere") — but it needs `rapidocr`/`winsdk`, so on macOS it died on every frame and respawned in a loop until the replay ended, having read no text at all. The host's daemon is chosen now; both speak the same protocol. The documented claim that replays run on either platform is true for the first time.

- **Stopping a recording froze reading for several seconds.** The main loop closed the recording MKV and respawned the capture inline, so `finalize()` — which waits for ffmpeg to flush, seconds on a long take — held up OCR and every reading decision at exactly the moment a line is usually on screen. Both steps now run on a worker; the loop reads straight through the handover, and the stall watchdog stands down while a swap is in flight rather than respawning on top of it. Because one ffmpeg owns both the capture device and the live frame file, every restart and finalize — on the loop or off it — is serialised behind a single lock, the mux is sequenced after the MKV is genuinely closed instead of racing it, and shutdown waits out an in-flight swap so the worker can't respawn an orphan capture over the next run's frames. `tools/test_video_swap.py` pins all four invariants against a fake capture with ffmpeg-like timing, in about two seconds and with no hardware.

- **Short dialogue lines were read as the nameplate, and vanished.** The nameplate was picked as the *tallest* candidate in the plate band — but HSR renders dialogue in a larger font than the nameplate, and a short line ("The beach!", "A bicycle station.") is narrow enough to pass the plate width filter and sits at cy≈0.189, just inside the plate band. So the line itself became the speaker and the dialogue band, anchored below it, came up empty. Un-nameplated narration was dropped in complete silence — the skip log only fires when there *is* text — while a nameplated short line flickered between correct and hijacked frame to frame, resetting stabilisation until it eventually read tens of seconds late. The nameplate is now the *topmost* candidate, a plate that yields no dialogue is discarded and the frame re-parsed without it, and the fallback dialogue band was widened to 0.21 so a row jittering upward is not clipped. Measured on a session recording: "A bicycle station." 0 → 34 usable frames, `"?" you wonder.` 0 → 24, "The beach!" 15 → 39.

## [0.6.1] - 2026-08-03

### Fixed

- `setup.sh` did not install `flask` or `vaderSentiment`, and nothing else pulls them in — a fresh macOS clone installed cleanly and then failed at import. Both are now declared, along with `numpy`, which `live.py` imports directly but only received as a transitive dependency. The no-capture-device warning also pointed at a `live.py` constant removed several releases ago; devices are chosen by name from the dashboard.

### Changed

- README documents what 0.6.0 actually shipped: message/group-chat panel reading, sentence streaming, screen-kind labels in the log, and the log download button. OCR repair is now split by platform, since the Windows text repairs (space restoration, run-on splitting, best-read selection) exist for a recogniser macOS doesn't use. Adds a **Debugging a session** section covering the log download and `tools/replay.py`. `setup.sh` records why `wordfreq` is deliberately absent there but present in `setup.ps1`.

## [0.6.0] - 2026-08-03

### Added

- **Windows 10/11 support.** The pipeline now has a platform backend layer (`hv_platform/`) and runs natively on Windows: DirectShow video capture, in-process WASAPI audio, an OCR daemon (`tools/ocrd_win.py`) speaking the same protocol and coordinate convention as the Apple Vision one, Kokoro TTS through ONNX Runtime, `setup.ps1`, and a cross-platform `hoyovoice.py` launcher. `voices.json` carries over unchanged — the voice IDs are identical on both platforms. RapidOCR on DirectML is the recommended engine (~120ms/frame); the built-in Windows OCR is a fallback. Getting there meant solving a series of platform-specific problems, all handled internally: frames are read as validated complete images (a JPEG caught mid-rewrite yields no text at all), the background is flattened before recognition so light subtitles survive a blown-out sky, playback tracks the duration implied by its own sample count because PortAudio reports a stream idle while WASAPI is still sounding, and the Chinese-trained recognition model's habit of dropping spaces is repaired in post. See `plans/WINDOWS-TESTING.md` for the first-run checklist and the platform quirks worth knowing.
- **Message/group-chat panel reading.** Phone conversations are read incrementally as you scroll, each sender in their own cast voice, with system notices ("… started sharing location") read by the narrator since they're events rather than speech. Sender labels are canonicalised per conversation — OCR renders the same small label several ways — and messages whose label has scrolled off-screen inherit the conversation's name rather than falling back to the narrator.
- **Lore cards** — full-screen title-and-prose screens carrying no UI chrome — are recognised and read by the narrator. Their title reads as a nameplate to the dialogue classifier, so they were previously skipped as an unknown speaker.
- **Sentence streaming.** The typewriter pauses at sentence boundaries, so a completed sentence is spoken at that pause instead of waiting for the whole line; the remainder follows once it renders, after the first part finishes.
- **Per-speaker voiced prior ("soft gate").** Some voiceover sits below every audio threshold that can safely be used: measured on a real capture, a voiced line peaked at 0.18 on the speech detector while a genuinely *unvoiced* line in the same scene showed more sub-threshold activity — no global threshold separates them, and lowering one would silence the unvoiced lines this app exists to fill in. HoyoVoice now tracks how often each speaker turns out to be voiced and, once that's consistent, accepts much weaker evidence before talking over them. For a character with a real voice, silence is the safer error. It self-corrects: every line spoken for a character counts against the prior.
- **Session replay harness (`tools/replay.py`).** Any dashboard recording replays through the real pipeline — actual OCR daemon, classification, stabilisation, dedupe, VAD gate and yield, with only capture, TTS and playback simulated — in a throwaway state directory that can't touch real casting or caches. Every reported problem becomes a reproducible test case.
- **"⤓ Download log" button** in the dashboard. Saves one text file with the environment, live analytics, the casting table, the full decision log and the noise-filtered console log — enough to diagnose a session without a screenshot.
- **Screen kinds are labelled in the log** (`loading screen`, `lore card`, `narration`, `overlay`, `chat`, `chat notice`), on skips as well as reads, plus a `lost frames` analytic counting frames the OCR daemon couldn't read at all.

### Changed

- Platform code (capture, audio, OCR daemon, TTS, playback) moved out of `live.py` into `hv_platform/darwin.py` and `hv_platform/win32.py` behind a shared interface (`hv_platform/base.py`). macOS behaviour is intentionally unchanged.

### Fixed

- **Real voiceover was spoken over when the audio reader fell behind.** Under load the VAD tail-reader could trail the live edge, stamping stale audio with fresh timestamps — so the gate judged "now" against sound from minutes earlier. Backlogs over a second are dropped and the dashboard shows `LAG Xs`.
- **HoyoVoice kept talking when voiceover started mid-line.** The late-VO yield used the same strict thresholds as the gate, so it often never fired. Our own TTS is not in the capture — it plays on the computer's speakers — so any speech heard during playback is game voiceover by definition, and the yield now acts on much weaker evidence.
- **Loading-screen lore was silently skipped as a repeat.** The dedupe window persists across restarts so that restarting mid-scene doesn't re-read the line still on screen, but it never expired — so a loading screen seen every session was suppressed by a read from the previous one. It now goes stale after ten minutes.
- **A line already on screen could re-trigger, and a partly-read nameplate could split a character in two.** Stabilisation was keyed on speaker *and* text, but the nameplate read jitters independently of the line ("Goldy" for "Mysterious Goldy"), restarting the cycle. Jittered re-reads now continue stabilising the same line, and partial nameplates snap to the cast member by containment instead of auto-casting a duplicate with a different voice.

## [0.5.1] - 2026-07-27

### Fixed
- **False "skipped (voiced)" on fast subtitle transitions**: the VAD gate's 2s lookback could reach back before the current line appeared, so the *previous* speaker's voice-over tail counted as evidence that the new line was voiced (confirmed by replaying a session recording through the gate). The gate window — including the wait loops, center-energy speechiness floor, and the `gate=` log value — is now anchored to when the line first appeared on screen.

## [0.5.0] - 2026-07-26

### Added
- **Center-energy VO detector**: mid/side stereo analysis with a speechiness floor catches robot and vocoder voices the speech model can't recognize — music swells (both channels) and center-panned SFX (no speechiness) are rejected
- `settings.pronunciations`: spoken-form substitutions applied at synthesis only ("Wishpower" → "Wish power")
- `settings.custom_words` + casting names fed to Apple Vision as a recognition vocabulary
- Reading repairs: OCR-dropped apostrophes restored via a safe contraction dictionary ("youre" → "you're"), decorative glyphs stripped ("~"), interjections voiced as words ("shh" → "shush"), expanded I/l fixes incl. capitals and stutters
- Bright cutscene narration reads via prose self-certification (previously only black screens)

### Fixed
- Ghost-box double reads (text fade-in makes Vision return overlapping stale + full boxes)
- Tail-fragment re-reads when VFX briefly hide a text row (substring/containment dedupe)
- Dialogue split across OCR fragments rejoins its visual row
- Log text selection is no longer interrupted by the refresh; recordings list is a fixed scrollable panel

### Removed
- Legacy `tools/ocr.swift` one-shot (superseded by the `ocrd` daemon)

## [0.4.0] - 2026-07-26

### Added
- **Auto-casting**: every newly met character claims a distinct voice from a gender-guessed pool instead of sharing one default — scenes full of new NPCs sound like an ensemble. Auto-cast entries show as "(auto)" in Casting and persist; a manual assignment clears the tag. Pools reuse the least-assigned voice only when exhausted.

## [0.3.0] - 2026-07-26

### Added
- Pre-cast characters from the dashboard (**Add cast** form) before they appear in-game
- `settings.text_fixes` lexicon for proper nouns OCR mangles ("lason" → "Iason")
- Gender guess from name shape for unknown speakers (casting table remains authoritative)
- `settings.dashboard_bind` — open the dashboard to other machines you trust
- Dashboard: version in header, friendly voice labels ("Heart (AF)"), scrollable recordings panel, paused-feed placeholder

### Changed
- Dialogue detection is anchored to the nameplate — overworld and cinematic layouts both parse, wherever the box sits
- Split OCR fragments rejoin their visual row ('Error: Term' + '"Berserker"…')
- Typewriter-aware pacing: lines still growing (or ending mid-sentence) wait to be spoken whole; when a split does happen, the remainder is spoken after the prefix finishes instead of being skipped or interrupting it
- Kokoro clip silence trimmed: snappier line starts, tight extension handoffs
- Black narration screens with only the ▼ glyph (no "Continue" text) are read, gated by a dark-frame check

## [0.2.0] - 2026-07-25

### Added
- Web dashboard at http://127.0.0.1:8470 — live log (voice used, per-event 📷 screenshot previews, replay, Hide/Clear), casting table (assign with instant re-read, mute checkboxes, delete), pause/resume, test-speech box
- Live video preview with paused placeholder; video/audio **device pickers** with hot-swap, persisted in settings
- In-app **recording**: game video + game audio + TTS clips muxed at exact wall-clock offsets (+8dB TTS boost, yield-trimmed clips), crash-safe MKV raw, configurable save folder
- Performance analytics: VAD health, OCR/synth timings, spoken/skipped/yielded counts, lines per minute
- Sentiment-aware delivery: line sentiment nudges speech pace (excited faster, somber slower)
- New screen types: Quick Read books (incremental scroll reading), info screens (Participant Details), loading-screen lore, floating host bubbles (`settings.overlay_speaker`), system screens silenced
- Menu/board rejection: dialogue must be centered; unknown speakers and narration require the ✕ Continue hint
- Speaker hygiene: quoted names are distinct characters, org/location names route to narrator, sentence fragments can never register
- App starts paused; resume from the dashboard

### Changed
- Dedupe is a sliding 3-message window (fuzzy-matched) instead of permanent — replayed quests re-voice
- Latency reduced to ~0.5–0.7s (6 fps sampling, speculative synthesis during the VAD gate, 0.2s wait)
- Capture devices selected by name, not index

### Fixed
- Recording audio ran ~12% fast with crackling: ffmpeg's AVFoundation audio input silently drops ~12% of capture-device samples. Audio moved to sox/CoreAudio (bit-perfect); ffmpeg is video-only; recordings slice the continuous sox stream — no resampling anywhere
- Two-tier VAD gate catches short/soft VO that never crosses the strong threshold; VAD pipeline made non-blocking and lag-free
- OCR "l"/"I" confusion repaired before synthesis
- Capture auto-recovers from device resolution changes, unplug/replug, and OCR daemon crashes

## [0.1.0] - 2026-07-25

### Added
- Live capture pipeline: PS5 → Genki ShadowCast 3 → ffmpeg (4 fps frame sampling + 16 kHz audio tap)
- On-device OCR via Apple Vision (`tools/ocrd` daemon, compiled Swift)
- Dialogue classification for Honkai: Star Rail standard layout (speaker / dialogue / choices)
- Full-screen black narration layout detection
- Kokoro-82M local TTS via mlx-audio with per-character voice registry (`voices.json`)
- Voiced-line gate: Silero VAD (onnx, no torch) skips lines the game already voices
- Late-VO yield: our playback cuts instantly if game VO starts mid-line
- `always_voiced` registry list for characters whose VO evades speech detection
- Fuzzy line dedupe (normalized text + similarity match) persisted across restarts
- Startup audio warmup to ignore capture-stream transients
- `hoyovoice.sh` control script (start / stop / status / log / restart)

### Known issues
- `af_nicole` voice is broken in the prince-canuma/Kokoro-82M package
- Genshin Impact layout profile not yet implemented
- Choice options are detected but not spoken
