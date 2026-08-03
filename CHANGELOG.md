# Changelog

All notable changes to HoyoVoice are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).
Add entries under **Unreleased** as you work; move them into a dated version section when you tag a release.

## [Unreleased]

### Added
- **Group-chat/message panel reading** — messages read incrementally, each sender in their own cast voice.
- **Windows support (experimental, untested on hardware)**: new `hv_platform/` backend layer — DirectShow video capture, in-process WASAPI audio capture (replaces sox's role), `tools/ocrd_win.py` OCR daemon (RapidOCR or Windows.Media.Ocr, same JSON protocol and Vision-style coordinates), Kokoro TTS via kokoro-onnx on CPU (same voice IDs — `voices.json` carries over), sounddevice playback, `setup.ps1`, and a cross-platform `hoyovoice.py` launcher. See `plans/WINDOWS-TESTING.md` for the first-run checklist.

### Changed
- Platform code (capture, audio, OCR daemon, TTS, playback) extracted from `live.py` into `hv_platform/darwin.py` and `hv_platform/win32.py` behind a shared interface (`hv_platform/base.py`). macOS behavior is intentionally unchanged.

### Added
- Chrome-free lore/loading cards (centered title + prose, no Continue hint, no UID strip, no HUD) are recognized and read by the narrator. `classify()` sees their title as a nameplate, so they were previously skipped as an unknown speaker; stylized titles that OCR runs together ("CindearthAge") are split for speech.

### Added
- **Session replay harness (`tools/replay.py`).** Any dashboard recording now replays through the REAL pipeline — actual OCR daemon, classification, stabilization, dedupe, VAD gate, and yield, with only capture/TTS/playback simulated — in a throwaway state dir that can't touch real casting or caches. Every reported bug becomes a reproducible test case; this diagnosed and verified the two fixes below. (`HOYOVOICE_STATE_DIR`, `HOYOVOICE_BACKEND=replay`, `HOYOVOICE_PORT` are the supporting hooks.)
- **Sentence streaming.** The typewriter pauses at sentence boundaries; HoyoVoice now starts speaking a completed sentence at that pause instead of waiting out the full patient threshold, and the existing extension machinery speaks only the remainder once the rest renders (after the first part finishes playing). Long lines start ~0.5s after their first sentence completes rather than after the whole line.
- **Group-chat/message panel reading** — messages read incrementally, each sender in their own cast voice.
- **Per-speaker voiced prior ("soft gate").** Some voiceover sits below every audio threshold that can be used safely: measured on a real capture, a voiced line peaked at 0.18 on the speech detector with 4 blocks above 0.12, while a genuinely *unvoiced* line in the same scene had 5 — no global threshold separates them, and lowering one would silence the unvoiced lines this app exists to fill in. HoyoVoice now tracks, per speaker, how often the game turned out to be voicing them; once a speaker is consistently voiced (3+ observations, 75%+), much weaker evidence is enough to stay quiet for them. The trade-off is deliberate: for a character with a real voice, staying silent is the safer error. It self-corrects — every line spoken for a character counts against the ratio — and the history persists across restarts in `captures/spoken_cache.json`. Skips taken this way are logged as "skipped (voiced — soft gate)".

### Fixed
- Chat sender labels are OCR-jittered ("Ashveil"/"Ashvell"/"Ashval"), which auto-cast one character three ways and re-queued every message per variant (repeats while scrolling or idling, interleaved out-of-order reads). Senders now canonicalize per chat session, messages dedupe on text alone (fuzzy), and only short echoes keep the sender in the key.
- Repeated log spam for a single on-screen line: dedupe and unknown-speaker entries are now collapsed on fuzzy text alone, since the speaker read jitters independently ("Goldy" vs "MysteriousGoldy").
- **Talking over voiceover without yielding ("double voices").** Reconstructed via replay: a line appears, its VO starts a beat late or too quietly for the strict gate's 0.2s window, HoyoVoice speaks — and the old mid-play yield used the same strict thresholds, so it never cut playback. The yield now uses the aggressive soft thresholds unconditionally: our TTS plays on the computer's speakers and is NOT in the capture, so any speech evidence during playback is by definition game VO. Worst-case false positive merely clips our own audio. Verified in replay: the same line now speaks and yields the moment the ongoing voice registers.
- **Lines over bright backgrounds took tens of seconds to speak (or never did).** The OCR detector loses light subtitles against a blown-out sky: measured on a real capture, only 12 of 37 frames of one line were detected at all, and the reads were truncated. Since every miss reset stabilization, the line rarely reached consecutive matching reads. Two independent fixes: the Windows OCR daemon now flattens the background (subtracting a blurred copy, so text pops regardless of absolute brightness) — 30/37 detection with the full line read — and stabilization tolerates a short run of dropped frames instead of discarding accumulated progress. Same clip, time-to-speak fell from ~3.2s to ~1.3s with far less tail risk.
- A line could be skipped entirely when its stabilization threshold dropped mid-count (a jittered read adds the closing period, so the extra patience for incomplete lines disappears). The count is compared with `>=` now, with a guard against re-firing the same line.
- Punctuation repair for the Windows OCR path: its recognition model is Chinese-trained, so it drops the space after punctuation ("Patience,Sparxie,patience.Once"). Spaces are restored, runs of dots collapse to a single ellipsis, and a lone period between two lowercase words is corrected to a comma — wrong sentence breaks were the biggest hit to TTS delivery. Numbers ("1,000", "2.5") and initials ("H.Q.") are left alone, and correctly-spaced text (the macOS/Vision path) is unaffected.
- A line already on screen no longer re-triggers: the nameplate read jitters independently of the line ("Goldy" vs "MysteriousGoldy"), and since stabilization was keyed on (speaker, text) that restarted the whole cycle every few seconds. Jittered re-reads now continue stabilizing the same candidate, while typewriter growth and genuinely new lines still start a fresh one. Partial nameplate reads also snap to the cast member by containment, so a dropped first word can no longer auto-cast a second character with a different voice.
- Repeated log spam for a single on-screen line: repeats of the line just spoken are no longer logged at all, and remaining entries collapse on fuzzy text alone.
- Windows frames are read as validated complete images and decoded from memory: reading the frame file while ffmpeg rewrote it corrupted the overwhelming majority of frames (99/120 in a reproduction), which stalled line stabilization for tens of seconds and caused repeat reads.
- Loading-screen and system-screen detection no longer depends on how an OCR engine chunks the bottom-left build string: the marker is matched on the joined strip and tolerates dropped underscores, so loading-screen lore is read (and epilepsy-style system screens stay silent) on both engines.
- VAD tail-reader can no longer trail the live audio edge under load — stale audio stamped with fresh timestamps made the gate judge "now" against minutes-old sound, so real voiceover was spoken over. Backlogs >1s are dropped and the dashboard shows `LAG Xs`.

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
