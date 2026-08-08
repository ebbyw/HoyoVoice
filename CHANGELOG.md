# Changelog

All notable changes to HoyoVoice are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows [SemVer](https://semver.org/).
Add entries under **Unreleased** as you work; move them into a dated version section when you tag a release.

## [Unreleased]

### Added

- **`*cough*` can be an actual cough.** `settings.sound_effects` maps the inside of a stage direction to an audio file, spliced into the line where the direction sat — `{"cough": "sounds/cough.wav"}` — or to words to speak in its place, `{"sigh": "Ahem."}`, for the sounds Kokoro can manage on its own. Relative paths resolve from the project directory, any sample rate and channel count is accepted (decoded once, mixed to mono, resampled to 24 kHz and cached), and a file that won't load costs the effect, not the line: the read goes ahead without it and the reason is logged once. A direction with no entry is read as the bare word, exactly as before; mapping one to `""` cuts it silently.

  This needed asterisks to survive OCR repair, which used to strip them as decoration. They now do, but only in pairs around a short phrase — that's the games' notation for a noise the character makes, where a lone asterisk is ornament or a multiplication sign and still goes. So the dashboard log shows `*cough*` as written, and `＊` normalizes to `*`.

- **Pick which speakers HoyoVoice talks through (Windows).** Playback went to the Windows default output, so on a machine with two sets of speakers the only way to move the reads was to move the whole system — game audio and everything else with them. The dashboard's device row now has a third picker, **speaks to**: any output device, or **System default** to keep following Windows. It's persisted as `settings.output_device` ("" = system default), and it only affects our own speech — capture is untouched, so the setting applies to the next line with no restart, and unlike a video/audio swap it's allowed mid-recording.

  The picker stores a device *name*, never an index: PortAudio indices shift as devices come and go (an index has already, once, turned into a webcam). Resolution is shared with the existing input matching — WASAPI's view of a device is preferred, because sounddevice lists each physical device once per host API and MME truncates names at ~31 chars ("Headphones (Arctis Nova Pro Wire"), so an exact-name match against the wrong host API's list silently fails. The resolved index is cached across lines (querying the device table per line is slow), re-resolved at once when the setting changes, and after a miss re-checked only every 10s — a headset that's off shouldn't print the same complaint under every spoken line.

  **A missing device never costs you a line.** If the saved name doesn't resolve, or the stream refuses to open (device asleep, or held in exclusive mode), the line is spoken on the system default and the log says why, with the outputs it could see. The dashboard also keeps a chosen-but-missing device listed as "(not found)" rather than quietly resetting the setting to System default on the next Apply. `tools/test_output_device.py` covers all of it against a fake sounddevice — host-API preference, "" meaning default, the cache, both failure paths, and the dashboard round trip — so it runs on either platform with no sound card.

  macOS plays through `afplay`, which has no device selection, so that backend reports no output list and the picker shows System default alone (route per-app from Sound settings there). Backends now take the live devices dict in `create_player(devices)` and `list_devices()` returns a third list; see `hv_platform/base.py`.

### Fixed

- **"Huh!? You... You're Paimon!" read as one slurred blob.** A run of terminal punctuation reaches Kokoro as two punctuation tokens in a row, and that pair is rare enough in what it was trained on that the stop after the word collapses — the interjection runs straight into the next one. Synthesis now gets a single mark: `?` whenever the run contains one, because a mixed run is a question asked with force and it's the rising contour that carries the surprise, and `!` otherwise. Like the pronunciation respellings this is a delivery fix, so the log, dedupe and casting all keep what the game actually wrote.

- **Sentiment pacing scored the respelled line, not the written one.** Speed was picked after `spoken_form()` had already turned names into nonsense words, and it would also have read the collapsed punctuation above. It now scores the line as the game wrote it, so `Huh!?` still earns its exclamation bump.

- **A chosen output device was ignored: speech still came out of the Windows default.** The system default reaches PortAudio through a host API that resamples whatever it's given; a *named* WASAPI endpoint doesn't — in shared mode the stream has to match the endpoint's mix format, so 24 kHz mono TTS was rejected outright (`-9997 invalid sample rate`) and the "never lose a line" fallback did what it says and spoke on the default. The Player now walks the same format ladder `AudioCapture` already needed for input: WASAPI auto-convert, then the audio as-is, then resampled to the endpoint's native rate and duplicated to stereo here. The rung that works is remembered, so only the first line of a session pays for the search, and the conversion is lazy — nothing is resampled on the common path where the endpoint takes the audio directly.

### Changed

- **Paimon is now respelled `Pie-mahn` (`pˈImˈɑn`), not `Pah-ee-mahn` (`pˈɑˈimˈɑn`).** The old form spelled the diphthong out as two syllables; this one is the way the games say it. Hyphenated rather than spaced: `Pie mahn` phonemizes to the same sounds but as two words (`pˈI mˈɑn`), which puts a word break in the middle of the name.

## [0.8.0] - 2026-08-08

### Added

- **`tools/pronounce_names.py` — spoken forms for both games' casts, and the rosters to check them against.** Kokoro phonemizes English spelling rules, so Chinese and Japanese names fail in a specific, predictable way: pinyin x reads as /z/ ("Xiao" → `zˈIəˌO`, "ZY-ah-oh"), q as /k/ ("Qiqi" → `kˈɪki`), zh as /ʒ/ ("Zhongli" → `ʒˈɑŋɡli`), and a final -e vanishes ("Shenhe" → `ʃˈɛnh`). The script fetches the live Genshin (119) and Star Rail (84) rosters, holds a respelling for the 66 names the phonemizer gets wrong, and prints every one with its reading before and after so the table can be *audited* rather than trusted; `--write` merges it into `voices.json`, `--custom-words` also feeds both rosters to the OCR vocabulary. Names it already says correctly ("Ningguang", "Hu Tao", "Yao Guang") deliberately have no entry.

  A name that is also an ordinary English word needs `settings.pronunciations_exact`. Matching is case-insensitive so OCR case jitter can't miss a name, which means the "Gaming" entry would also respell "gaming" in ordinary prose — listing the name there matches the capitalised spelling only. The same trap is waiting for Jade, Sunday, Hook, Blade, Archer, Robin and March 7th, all of which are Star Rail characters.

  Respellings, not IPA. misaki accepts inline phonemes, but the Windows backend (kokoro-onnx) doesn't, and markup that only works on one platform is worse than an approximation that works on both. Each respelling was checked against the same g2p Kokoro runs, which has three traps worth knowing: a hyphen chunk is its own word, so a chunk-final "eh" reads /eɪ/ ("Freh-mee-nay" → "FRAY-mee-nay", fixed as "Frem-ee-nay"); an unreadable initial cluster is spelled out letter by letter ("Shway" → "S-H-way", so shw/chw/hw/lw are avoided); and "ge" is soft, so Gepard needs "Ghep-ard" to keep its hard g.

- **"Add voice file" in the dashboard: import a Kokoro voice pack, and have it verified before it can be cast.** Using a voice the app didn't ship with meant editing `VOICE_CATALOG` in the source, and there was no way at all to use a pack downloaded from a voice repo. Now it's a file picker: choose a `.pt` / `.safetensors` / `.npy` / `.npz` / `.bin`, and the voice joins the menu, castable to anyone, surviving restarts (the canonical copy is kept in `voices_custom/`, so deleting the download doesn't silence a character). ✕ removes one and hands any character cast to it back to the auto-caster. The picker uploads, so it works from a dashboard open on another machine; leaving it empty asks for a path instead, which skips the copy when the file is already on the machine running HoyoVoice.

  **Verified means synthesized.** Shape-checking the tensor is not enough — a (510, 1, 256) float32 array can still be noise, zeros, or a style vector from a different model, none of which is visible until something is spoken with it, and the failure mode is a character who silently produces nothing mid-quest. So a pack is installed, registered with the real engine, run on a real line, and checked for audible output (rms) before it is written into `voices.json`; anything short of that is rolled back to no trace — no file, no registration, no entry — and the reason is shown next to the button. What passes is auditioned immediately, because the only check that answers "is this the voice I wanted" is hearing it.

  **Reading a `.pt` without torch.** Voice packs ship in whatever format their repo used, and the most common is a torch pickle — i.e. arbitrary code in the general case. This project has no torch dependency (the VAD is onnx for the same reason) and adding ~200 MB of it to read 522 KB of floats is a bad trade, so `tools/voicepack.py` reads the zip and unpickles it under a restricted unpickler that resolves exactly two things, a storage id and the tensor rebuilder, and refuses every other global. `tools/test_voicepack.py` builds its fixtures by hand-emitting pickle opcodes (Python's own pickler won't write a global it can't import) — including a hostile file that names `os.system`, pinning that reading it neither imports nor runs it. Verified against the real upstream `af_bella.pt`: byte-identical to the packaged macOS voice.

  Both runtimes learned `register_voice` / `forget_voice`. macOS passes mlx-audio the installed file's path, which is why everything is normalized to single-tensor `.safetensors`; Windows can't add to the read-only `voices-v1.0.bin`, so it keeps the array and passes it to kokoro-onnx in place of a name.

- **README: "Adding your own voice actors."** The casting section documented the *shape* of `voices.json` but not how to actually cast someone, so each level of it now has a section: assigning voices from the dashboard (auto-cast, Add cast, the audition-on-assign behaviour, muted, the Test TTS box) and by hand — including the trap that the file is read once at startup and written back on every casting change, so hand-edits made while the app is running are overwritten; importing a voice pack, and where packs come from, including the model's own ~54 voices where the menu shows 28 (the rest speak English text through the American phonemizer — verified: a different-sounding speaker, not a language switch); and what is still a code change, with the `synth(text, voice, speed)` → mono float32 @ 24 kHz contract the two `Tts` classes hold.

### Changed

- **Reading now starts when the first sentence finishes typing, not when the line does.** Sentence streaming only fired when the typewriter happened to *pause* on a sentence end — the read waited out a full-line hold (`STABLE_READS + 4`, ~1s at 6fps) whenever the next sentence had already started rendering, which is most multi-sentence lines. A line whose text is still growing frame over frame is now clipped to its longest closed sentence, and the clipped head repeats identically while the rest types, so it stabilizes in the normal two reads (~0.3s) instead. The remainder is spoken afterwards through the existing extension path, which diffs against what was already said.

  Two guards keep it from chopping a single thought in half. The clip only applies while the raw read is actually *growing* — clipping a static line would be a trap, because its text never changes again, so the tail would never arrive as an extension and half the line would be lost (OCR does drop a final period). And a boundary is terminal punctuation followed by the start of a new sentence, so "3.50 mora" and "Mr. Ito" don't qualify; "…" is deliberately excluded, since in these games it is a pause the typewriter runs straight through. `tools/test_stream_prefix.py` pins both directions. Verified against a recorded HSR scene: same lines covered, each one's decision reached a sentence earlier.

- **Names Kokoro read wrong now have spoken forms — including 66 character names.** Paimon came out "PAY-mun" (`pˈAmən`) and is respelled `Pah-ee-mahn` → `pˈɑˈimˈɑn`; Reignbow came out "ree-INE-bow" (`ɹˌiˈInbO`) → `Rainbow`; Ishtar came out "ISH-tar" (`ˈɪʃtˌɑɹ`) → `Esh-taar`. `settings.pronunciations` applies at synthesis only, so logs, dedupe and casting keep the real spellings — and the substitution is case-insensitive and word-bounded, so possessives ("Ishtar's") carry through.

## [0.7.3] - 2026-08-08

### Fixed

- **Lines were cut off mid-sentence in a scene with no voice acting in it.** The late-VO yield stops playback the moment the game starts talking over us, and it was reading the feed at the most sensitive setting the app has, unconditionally — a VAD probability of 0.12 across three 32ms chunks. Natlan's vocal music clears that comfortably. Four lines of one Genshin quest were cut off partway with nothing audible taking over, and in the recording of it the captured audio is silent for eleven seconds after the cut. The comment justifying the setting said the worst case was "merely clips our own playback", which is the failure the feature exists to prevent, not an acceptable cost of it.

  The yield now reads the evidence at the same sensitivity that decided to speak in the first place — the per-speaker prior, so the faintest hint still stands us down for a character the game has voiced before, while a character it has never voiced needs real speech. `settings.late_yield: false` turns it off outright, which is the one-line way to prove whether a yield is involved at all. Every yield now logs how far into playback it fired and what it heard (peak probability, strong and weak hit counts): a yield that saved you from talking over the game and one that swallowed half a line were previously the same line in the log, and they want opposite fixes.

- **A stalled capture silently amputated the recording in progress.** One ffmpeg owns both the capture device and the recording, and the stall watchdog respawned it with no record path — so video stopped at the stall while `recording["on"]` stayed true, and clips and the audio slice kept accruing on wall clock. The session that found it muxed a 28.5s video against 264.9s of sound: every line of the dialogue it was recording had no picture, and the file was useless as a replay case. The recording now continues into a new segment, which the mux stream-copies back together, and the window where nothing was captured is cut out of the audio and out of the TTS clip offsets so everything after a stall stays in sync.

  How long that window was has to be **measured**, not inferred. The first attempt took it from how long the stall watchdog had been waiting, which sounds equivalent and isn't: the frame file stops updating before the encoder does, so a real stall that the watchdog timed at 10.4s had only lost 6.2s of video, 4.2s too much came out of the audio, and everything after the gap was 4.2s out — a recording that looks fine until the voices drift. The mux now ffprobes each segment and takes the gap as the wall time between the end of one segment's video and the start of the next. If ffprobe can't answer, nothing is cut rather than guessed. `tools/test_video_swap.py` pins the respawn, the measurement and the gap arithmetic.

- **The dashboard's feed preview returned a 500 on Windows.** ffmpeg replaces `live_frame.jpg` by rename, and opening it in the instant between the two raises `PermissionError` there rather than returning stale bytes — so a preview refresh landed a Flask traceback in the session log. One retry covers the rename window; a second failure returns a 503 the dashboard simply refreshes past. Also swaps `Image.getdata()`, deprecated and removed in Pillow 14, for its replacement where the installed Pillow is new enough to have it.

### Added

- **A pixel change gate skips OCR while the dialogue is static.** ffmpeg rewrites the frame file continuously, so mtime can't tell a static line from a new one — the loop paid a full OCR call per sampled frame (115ms on DirectML, a Vision call on macOS) even while text sat unchanged on screen, which is most of the time. `tools/change_gate.py` decodes the frame at half scale (~1ms) and compares the pixels under the blocks the last read built its line from, counting how many *bright* ones moved: game text is light-on-dark, so the world animating behind a static line moves dark pixels while any text change — including brand-new text — moves bright ones.

  Two things about that comparison are what make it safe, and a Genshin session taught both. It has to watch the line's own blocks rather than every block on the frame: Genshin's UID sits bottom-right and the HUD top-left, so the union of all of them is the whole screen, and the verdict ends up being about the scenery. And it has to count the pixels that moved rather than average them — a mean is diluted by everything in the region that didn't change, and on a daylit scene a few hundred new glyph pixels averaged out to 0.06 against a threshold of 6.0. Under those two faults the gate called a frame unchanged while the typewriter was still typing, and four of nineteen lines in that session were spoken half-typed ("…friends with the great sh", with "aman Citlali…" arriving after it as a separate line). The allowance for what may move is capped below a single glyph, so a box full of bright scenery can't buy itself one.

  An "unchanged" verdict replays the previous blocks through the normal pipeline rather than skipping the iteration, so stabilization counting, chat settle checks and panel-close detection tick exactly as before; every ambiguous case (torn frame, moved boxes, no box with text in it) fails open to a real OCR call.

  The gate may *defer* an OCR call but never cancel one, and that is a stronger guarantee than it sounds: a wrong "unchanged" replays blocks that describe the same boxes, which are still unchanged, so nothing inside the loop breaks the cycle. A session found exactly that — a screen with no dialogue left a lone nameplate-shaped block behind, the gate narrowed onto that one scrap of static UI, and the pipeline read nothing for 47 seconds until the capture respawned and broke it. So no more than twelve frames may be skipped in a row: any wrong verdict costs about two seconds instead of the rest of the session.

  It also does not run at all until there is a line on screen. Watching every block on a frame with no dialogue looked like the safe direction — more boxes, more ways to notice a change — but the gate can only see where text *already was*, so a line appearing on a screen that had none lands outside every box it is watching and reads as unchanged. Measured against ground-truth OCR over 1650 frames of a Genshin conversation, that accounted for 10 of 17 stale verdicts; waiting for a line costs 11% of the skips and removes 76% of them.

  `settings.change_gate: false` disables it, `settings.change_gate_frac` tunes it, and the dashboard shows OCR calls saved. `tools/test_change_gate.py` pins thirteen invariants — synthetic frames, no hardware, ~1s — including a bright scene with chrome in the block list walked through the typewriter one glyph at a time, and a frozen screen that must still be re-read. Measured over that same recording: 23% of OCR calls skipped, with lines spoken identical to 0.7.2 and settling about 0.12s sooner (numbers and method in `plans/OCR-INTEGRATION-PLAN.md`).

### Changed

- **Stabilization listens to the recognizer's confidence.** `classify()` now reports the weakest confidence among the blocks that made the line, and the stabilizer uses it two ways: a high-confidence read (≥0.97) at a typewriter pause skips the sentence-streaming cushion read — the cushion exists to ride out shaky mid-render reads, and the recognizer already vouches for this one — while a shaky read (<0.85, the mid-fade "started shan ing" class) must earn one extra sighting before it can be spoken. Confidence also breaks ties in best-read voting when the real-word fraction can't. Engines without confidences report 1.0, leaving behavior exactly as before; measured on an 81-shot corpus, settled lines sit at 0.97+ (55 of 78 with the English rec model) and only visibly damaged reads fall under 0.85.

- **Windows OCR reads English at the source.** RapidOCR's bundled recognition model is Chinese-trained; on English game text it drops spaces ("Everythingis going smoothlymy nobleKing.", "RinTohsaka") and the pipeline repaired the damage statistically after the fact. `tools/ocrd_win.py` now loads an English-trained recognition model (en_PP-OCRv5_mobile_rec, ONNX) when present — `setup.ps1` downloads it to `models\` (~8 MB), `HOYOVOICE_REC_MODEL`/`HOYOVOICE_REC_KEYS` override the path, and deleting the files falls back to the bundled model. Detection is untouched, so box geometry and every classify decision stay put. Measured over an 81-shot corpus: fusion-class defects 333 → 144, 22 frames of nameplate fixes ("MysteriousGoldy" → "Mysterious Goldy", "Sparxile" → "Sparxie"), two frames where a dropped nameplate came back, three info screens that had been misread as loading/dialogue now classify as reader panels with clean text, zero regressions.

## [0.7.2] - 2026-08-07

### Fixed

- **A spoken choice option had no speaker to cast.** It fell through to the narrator and logged with an em dash where the name goes, so there was no Casting row and no way to give the player character a voice of their own. Options are now cast under the player character's name for the active game — `Traveler` in Genshin, `Trailblazer` in Star Rail, `Player` otherwise — which auto-casts on first use and appears in Casting like any other character. `settings.choice_speaker` still overrides the name (for a Traveler you've named Aether, say).

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
