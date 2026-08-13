# Windows first-run testing checklist

## Status

Windows is a supported platform, not an experiment: many clean end-to-end
sessions on real hardware since 2026-07-28. Verified there: setup, device
enumeration, DirectShow video capture, WASAPI audio capture (48k stereo
contract holds), OCR → classify → speaker detection → auto-casting, Kokoro TTS
(~0.9–1.1s synth), playback, dedupe, recording + mux, the output-device picker,
and both games' profiles.

**Use RapidOCR on DirectML** (~115ms/frame with the English recognition model,
154ms without it). The built-in Windows engine mangles this font
("rabbit-head Nt bad or clown"), reports no confidence — so the
`MIN_CONF` junk filter (`tools/profiles/base.py`) does nothing — and is only
a fallback.

The checklist below is still the way to bring up a *new* Windows box, or to
isolate a subsystem when one misbehaves: each step exercises one file.

The work reaches that machine through git only. Fix in the repo, push, pull
there — never hand-edit files on it.

Gotchas found the hard way (all fixed in code — listed so they aren't
re-diagnosed):

| Symptom | Cause |
|---|---|
| `setup.ps1` parse errors | PS 5.1 reads BOM-less scripts as ANSI; UTF-8 em-dashes decoded into a smart quote that terminated strings. Keep the script ASCII-only. |
| ffmpeg "not found" after winget installed it | The launching shell predates the PATH edit; that stale PATH follows into subprocesses. Backend re-reads PATH from the registry. |
| Process dies on the first spoken line | cp1252 stdout can't encode `→`. UTF-8 is forced now. |
| PortAudio -9984 | WASAPI settings passed to a non-WASAPI device entry. |
| Flood of "The image is unrecognized" | Reading `live_frame.jpg` while ffmpeg rewrites it — **99/120 naive reads are torn**. Frames are read as validated bytes and decoded from memory. |
| VAD says 0.00 during real VO | The tail-reader fell behind under load and judged "now" using stale audio. Backlogs >1s are dropped; the dashboard shows `LAG Xs`. |
| Loading screens read as dialogue | The build/UID strip is one block in Vision, split (and underscore-less) in Windows OCR. Matched on the joined strip now. |
| Extra console windows | `DETACHED_PROCESS` + `CREATE_NO_WINDOW` are mutually exclusive. |
| A line takes tens of seconds to speak | The detector loses light subtitles over bright backgrounds — 12/37 frames on a measured capture — and every miss reset stabilization. Fixed by background flattening in the daemon (30/37) plus `MISS_TOLERANCE` in the orchestrator. Note: encoder load during recording was ruled out; the recordings kept up with wall clock (177s captured of 180s). |
| Words fused together ("RinTohsaka", "fora") | RapidOCR's bundled recognition model is Chinese-trained and Chinese has no spaces. `setup.ps1` now downloads `models\rec_en.onnx`; the startup log must read `[ocrd_win] rec model: rec_en.onnx`. |
| The dashboard preview 500s | ffmpeg replaces `live_frame.jpg` by rename, and opening it mid-rename raises `PermissionError` on Windows rather than returning stale bytes. One retry, then a 503 the dashboard refreshes past. |
| A pronunciation fix "didn't land" after a pull | `voices.json` is gitignored and per-machine. Stop the app and run `python tools/pronounce_names.py --write`. |
| Speech comes out of the wrong speakers | `settings.output_device`; the console log says which output it resolved (`[audio] output → …`) and lists what it can see when a saved name no longer matches. |
| Dashboard won't load / app won't start | An orphaned instance is holding port 8470 — `python hoyovoice.py stop`, then check Task Manager for stray `python.exe` / `ffmpeg.exe`. |

Work through the list below in order on a fresh box — each step isolates one
subsystem, so a failure points at exactly one file. It was written when the
backend (`hv_platform/win32.py`, `tools/ocrd_win.py`, `setup.ps1`,
`hoyovoice.py`) had been verified only off-Windows, against the golden frame
(`captures/frame_001.png`) and a stub-backend smoke test; those references are
still the fastest way to tell "this machine is wrong" from "this code is
wrong".

## 0. Setup

```powershell
git clone <repo> ; cd HoyoVoice
powershell -ExecutionPolicy Bypass -File setup.ps1
```

- If ffmpeg/Python were just installed by winget, open a **new** terminal and re-run `setup.ps1` (PATH refresh).
- Expected downloads: Silero VAD (~2 MB), Kokoro ONNX model + voices (~340 MB).
- Also verify on the Mac after pulling: `./hoyovoice.sh start` still works — the refactor is supposed to be behavior-neutral there. Do this FIRST if the Mac is handy.

## 1. Device enumeration

```powershell
.venv\Scripts\python.exe -c "from hv_platform import get_backend; v,a = get_backend().list_devices(); print('video:', v); print('audio:', a)"
```

- ShadowCast should appear in the video list (dshow names) and its mic input in the audio list (sounddevice/WASAPI names — these are intentionally different enumerators).
- If the video list is empty: check Windows Settings → Privacy → Camera (dshow can be silently blocked), and that OBS isn't holding the device.
- If parsing misses devices, run `ffmpeg -f dshow -list_devices true -i dummy` and compare against `_list_dshow_video()` — ffmpeg's stderr format varies by version and the parser handles two known layouts.

## 2. Video capture alone

```powershell
.venv\Scripts\python.exe -c "from pathlib import Path; import time; from hv_platform import get_backend; b = get_backend(); v = b.create_video_capture({'video':'<EXACT NAME>','audio':''}, Path('captures/live_frame.jpg'), 6); v.restart(); time.sleep(5); print('alive:', v.alive); v.kill()"
```

- `captures/live_frame.jpg` should exist and refresh (~6 fps). Open it — you should see the console feed (remember: PS5 HDCP off).
- If ffmpeg exits instantly: the card may not accept `-video_size 1920x1080 -framerate 30` via dshow — check its modes with `ffmpeg -f dshow -list_options true -i video="<NAME>"` and adjust `win32.py` if needed.

## 3. Audio capture alone

Same pattern with `create_audio_capture`, then check `captures/game_audio_48k.pcm` grows at **exactly 192,000 bytes/sec** (contract: 48 kHz stereo s16). Sanity-listen: `ffplay -f s16le -ar 48000 -ch_layout stereo captures\game_audio_48k.pcm`.

- Wrong growth rate → WASAPI auto-convert didn't engage (old sounddevice/PortAudio) or the device opened mono; both paths exist in `AudioCapture` — instrument with prints.
- Crackles/gaps here will show up later as VAD misses — fix before moving on.

## 4. OCR bake-off

With the game showing a dialogue box (or using saved 1920px frames):

```powershell
echo captures/frame_001.png | .venv\Scripts\python.exe tools\ocrd_win.py
$env:HOYOVOICE_OCR_ENGINE="windows"; echo captures/frame_001.png | .venv\Scripts\python.exe tools\ocrd_win.py
```

- Compare both against `captures/frame_001.ocr.json` (Vision's golden output) — feed each through `python tools\classify.py` and diff the speaker/dialogue.
- **Resolved (rapid):** the space-dropping ("RinTohsaka") was the Chinese-trained recognition model, not resolution. `setup.ps1` downloads an English-trained one to `models\rec_en.onnx`; `HOYOVOICE_REC_MODEL` / `HOYOVOICE_REC_KEYS` override the path, and deleting the files falls back to the bundled model. Fusion-class defects over an 81-shot corpus: 333 → 144.
- **Still true (windows engine):** Windows.Media.Ocr reports no confidence (hardcoded 1.0), so the `MIN_CONF` junk filter (`tools/profiles/base.py`) does nothing and confidence-aware stabilization degrades to yesterday's behaviour — watch for HUD noise classified as dialogue.
- Timing: ~115 ms/frame on DirectML with the English model. Over ~600 ms will lag the 6 fps loop; prefer the faster engine that still classifies correctly. The change gate removes most of these calls on static text anyway (`ocr saved` in the dashboard).
- Force an engine with `HOYOVOICE_OCR_ENGINE` (`auto`, `rapid`, `windows`).

## 5. TTS + playback

```powershell
.venv\Scripts\python.exe -c "from hv_platform import get_backend; import time; b = get_backend(); t = b.create_tts(); p = b.create_player(); a = t.synth('Testing, one two three.', 'af_nova', 1.0); print(len(a)/24000, 'sec'); import soundfile as sf; sf.write('tts_out/win_test.wav', a, 24000); p.play('tts_out/win_test.wav', a); time.sleep(1); print('playing:', p.playing); print('interrupted:', p.stop())"
```

- Measure synth time for a ~10-word line; budget expectation on CPU is 0.5–1.5 s.
- `p.stop()` must cut audio near-instantly (this is the late-VO yield path).

## 6. Full app

```powershell
python hoyovoice.py start
python hoyovoice.py log
```

- Dashboard at http://127.0.0.1:8470: device pickers populated, Resume, preview updates, VAD metric shows channel activity (not "NO AUDIO").
- Play an unvoiced quest: lines spoken ~1–2 s after text settles; voiced lines skipped; late-VO yield works.
- Hot-swap devices from the dashboard; unplug/replug the card (watchdog recovery within ~10 s).
- `python hoyovoice.py stop` — verify no orphaned `ffmpeg.exe`/`python.exe` in Task Manager (taskkill /T should get the tree).

## 7. Recording

- ⏺ then ⏹ after ~30 s with a few TTS lines. The MP4 must have: video, game audio, TTS at correct offsets, +8 dB TTS over bed.
- This exercises the Windows-specific `finalize()` ('q' on stdin instead of SIGINT) — a corrupt/truncated MKV means that path failed.
- libx264 veryfast is the current recording encoder; if CPU is tight during gameplay, try `h264_nvenc`/`h264_qsv` (small `win32.py` change).

## Known open items

- Auto-pick GPU (DirectML) for TTS — deliberately out of scope; synthesis on
  CPU is inside the latency budget.
- Same-PC window capture (no capture card) — future idea, separate backend.
- Windows OCR remains noisier than Apple Vision even with the English model.
  Canonical-text snapping (`settings.textmap`, phase 5 of
  [OCR-INTEGRATION-PLAN.md](OCR-INTEGRATION-PLAN.md)) shipped as the lever —
  user-seeded and local-only, so it only helps a box whose user points it at
  a map.
- **Open bug: book-page rows misread as `hum`/`Ium` on Windows.** Smells like
  detector/frame rather than glyph shape; diagnosis waits on this box's
  `captures/shots/*.json` from a session that reproduces it.
- The Windows `ocr_ms` measurement for `settings.anchor_roi` (phase 4b) is
  still owed: replay a scroll-heavy recording here with `anchor_roi: true`
  and compare `ocr_ms` on vs off. The setting stays off by default until
  this is done.

- `Player.playing` still reads sounddevice's module-level stream
  (`sd.get_stream().active`), and `play()` still goes through `sd.play` — now
  with an explicit `device=` for the output picker. If playback ever overlaps
  or stutters, this is still the first suspect; the fix is an explicit
  `OutputStream` the player owns.
