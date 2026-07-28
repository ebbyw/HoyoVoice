# Windows first-run testing checklist

## Status (2026-07-28, first hardware session)

Verified working on real hardware: setup, device enumeration, DirectShow
video capture, WASAPI audio capture (48k stereo contract holds), OCR →
classify → speaker detection → auto-casting, Kokoro TTS (~0.9–1.1s synth),
playback, dedupe, recording + mux. **RapidOCR on DirectML: 154ms/frame** —
use it; the built-in Windows engine mangles this font ("rabbit-head Nt bad
or clown") and is only a fallback.

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


The Windows backend (`hv_platform/win32.py`, `tools/ocrd_win.py`, `setup.ps1`, `hoyovoice.py`) was written and structurally verified off-Windows: everything compiles, the OCR daemon's RapidOCR engine reproduces Apple Vision's classify output on the golden frame (`captures/frame_001.png` → same speaker + dialogue), and the refactored `live.py` passes a stub-backend smoke test. **None of it has touched real Windows hardware yet.** Work through this list in order on the Windows box — each step isolates one subsystem, so a failure points at exactly one file.

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
- **Known risk (rapid):** RapidOCR drops inter-word spaces on low-res text ("RinTohsaka") — confirmed on 854px thumbnails, absent at native 1920px in sandbox testing. If it appears on live frames, switch to the windows engine or add an English recognition model.
- **Known risk (windows):** Windows.Media.Ocr reports no confidence (hardcoded 1.0), so `classify.py`'s `MIN_CONF=0.8` junk filter does nothing — watch for HUD noise being classified as dialogue.
- Timing: rapid was ~380 ms/frame on a modest sandbox CPU. Over ~600 ms will lag the 6 fps loop; prefer the faster engine that still classifies correctly.
- Set the winning engine permanently via `HOYOVOICE_OCR_ENGINE` (or make it a `voices.json` setting — small follow-up).

## 5. TTS + playback

```powershell
.venv\Scripts\python.exe -c "from hv_platform import get_backend; import time; b = get_backend(); t = b.create_tts(); p = b.create_player(); a = t.synth('Testing, one two three.', 'af_nova', 1.0); print(len(a)/24000, 'sec'); import soundfile as sf; sf.write('tts_out/win_test.wav', a, 24000); p.play('tts_out/win_test.wav', a); time.sleep(1); print('playing:', p.playing); print('interrupted:', p.stop())"
```

- Measure synth time for a ~10-word line; budget expectation on CPU is 0.5–1.5 s. Record it — the README latency table needs a Windows column.
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

- `Player.playing` uses sounddevice's module-level stream — if the qr-reader pump misbehaves (overlapping or stuttering reads), this is the first suspect; replace with an explicit OutputStream.
- Auto-pick GPU (DirectML) for TTS — deliberately out of scope for v1.
- Same-PC window capture (no capture card) — future idea, separate backend.
