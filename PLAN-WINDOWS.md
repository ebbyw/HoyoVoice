# HoyoVoice — Windows Implementation Plan

Goal: one cross-platform codebase. The orchestrator, classifier, VAD, dedupe/gating logic, and dashboard (~80% of the code) are already portable Python. Only the edges touch the OS. Strategy: extract those edges behind a small platform layer, then write Windows backends.

## Decisions locked in

- **Approach:** single codebase, `sys.platform` selects a backend package. No fork.
- **TTS target:** any Windows PC — Kokoro-82M via `kokoro-onnx` on CPU (onnxruntime). No GPU required.
- **Same UX:** same dashboard, same `voices.json` (Kokoro voice IDs are identical across runtimes), same latency philosophy.

## What is actually macOS-specific (audit of current code)

| Concern | Current (macOS) | Where |
|---|---|---|
| Video capture | ffmpeg `-f avfoundation` | `live.py` spawn_capture(), list_devices() |
| Audio capture | sox `-t coreaudio` → appends s16le PCM file | `live.py` spawn_sox() |
| OCR | Apple Vision daemon (`tools/ocrd.swift`, stdin path → stdout JSON) | `live.py` spawn_ocrd() |
| TTS | Kokoro via `mlx_audio` (Apple Silicon GPU) | `live.py` Speaker.synth() |
| Playback | `afplay` subprocess | `live.py` Speaker.play()/stop() |
| Recording finalize | `SIGINT` to ffmpeg for clean MKV close | `live.py` record stop path |
| Process control | zsh + `pgrep`/`pkill`/`nohup` | `hoyovoice.sh` |
| Install | Homebrew, `swiftc` | `setup.sh` |

Everything else — `classify.py`, `vad.py` (onnxruntime, already torch-free), `webui.py`, the state machine, dedupe, sentiment pacing, the mux filtergraph — runs on Windows unmodified.

## Windows backend choices

### 1. Video capture — ffmpeg `-f dshow`
Same ffmpeg binary strategy, different input format. The ShadowCast 3 is UVC, so it appears as a DirectShow device with no driver. Device enumeration: `ffmpeg -f dshow -list_devices true -i dummy` (parse stderr, same as today). Frame sampling, MKV recording, watchdog respawn logic all unchanged.

### 2. Audio capture — in-process WASAPI via `sounddevice`
The sox/CoreAudio choice existed because ffmpeg's AVFoundation audio drops ~12% of samples — a macOS-specific bug. On Windows, rather than porting the sox dependency (`-t waveaudio` is legacy WinMM, mediocre), capture audio **in-process** with `sounddevice` (PortAudio/WASAPI shared mode): a thread opens the capture card's audio input at 48 kHz stereo s16 and appends to the same `game_audio_48k.pcm` file. This preserves the two contracts the rest of the code depends on: the tail-file reader for VAD, and exact byte-offset slicing for recording mux. It also removes a subprocess + watchdog. (Once proven, the Mac side can optionally migrate to the same backend and drop sox.)

### 3. OCR — `tools/ocrd_win.py` speaking the same protocol
The daemon contract is trivial and worth keeping: image path per line on stdin → one JSON array of `{text, confidence, x, y, w, h}` per line on stdout. Two candidate engines:

- **Windows.Media.Ocr** (via `winsdk`/`winocr`): built into Windows 10/11, zero model download, fast. Line-level results; bounding rects come per word — union them per line. No confidence score (emit 1.0). Quality on stylized game fonts is the open question.
- **RapidOCR** (ONNX, no torch — fits the existing onnxruntime dependency): heavier (~15 MB models) but stronger on game-style fonts, gives line boxes + real confidences, and behaves identically on every machine.

Plan: implement both behind the same protocol, calibrate against the golden files already in the repo (`captures/frame_001.png` → `frame_001.ocr.json`), pick the default empirically. Note: Vision reports normalized bottom-left-origin coordinates; whichever engine wins must normalize to that same coordinate convention so `classify.py` is untouched. The I/l OCR-repair table may need Windows-specific entries.

### 4. TTS — `kokoro-onnx`
Same Kokoro-82M weights and the same ~50 voice IDs (`af_*`/`am_*`/`bf_*`/`bm_*`), so `voices.json`, casting, and defaults carry over exactly. CPU inference is roughly realtime for an 82M model; expect first-audio ~0.5–1.5s on a mid CPU vs ~300ms on MLX — still inside the "unvoiced line sits there waiting" tolerance, but the latency budget in the README needs a Windows column. `speed` and `lang_code` map directly. Dependency note: Kokoro phonemization needs espeak-ng (Windows installer exists; setup script handles it). If the machine has a GPU, onnxruntime's DirectML provider is a config-flag upgrade later — not in scope now.

### 5. Playback — `sounddevice` output
Replace the `afplay` subprocess with `sounddevice.play()` on the default output device; `stop()` becomes `sd.stop()`, which is as instant as killing afplay (this is the late-VO yield path, so interrupt latency matters). Bonus: no temp-WAV requirement for playback (still write it for recording clips and replay buttons).

### 6. Recording finalize — 'q' on stdin instead of SIGINT
Windows has no SIGINT delivery to a child ffmpeg. Standard fix: spawn ffmpeg with `stdin=PIPE` and write `q\n` to finalize the MKV cleanly; fall back to `CTRL_BREAK_EVENT` (requires `CREATE_NEW_PROCESS_GROUP`) then kill. Abstract as `capture.finalize()` so the Mac path keeps SIGINT.

### 7. Launcher — replace `hoyovoice.sh` with cross-platform `hoyovoice.py`
`pgrep`/`pkill`/`nohup` don't exist on Windows. A small Python CLI (`hoyovoice.py start|stop|status|log|restart`) using a pidfile + `psutil` for orphan cleanup replaces the shell script on both platforms — one launcher, not two. Keep `hoyovoice.sh` as a thin wrapper for muscle memory.

### 8. Setup — `setup.ps1`
winget installs (ffmpeg, espeak-ng, Python 3.13), venv + pip (`kokoro-onnx onnxruntime sounddevice soundfile pillow flask vaderSentiment` + chosen OCR package), Silero VAD model download (unchanged). No compiler needed on Windows — the OCR daemon is Python. Document the Windows Firewall prompt for the dashboard port (127.0.0.1:8470) and that the capture card must not be open in OBS (same single-client rule).

## Proposed code structure

```
platform/
  __init__.py      # get_backend() → darwin | win32 by sys.platform
  base.py          # interfaces: VideoCapture, AudioCapture, OcrDaemon,
                   #             TtsEngine, Player, list_devices()
  darwin.py        # wraps today's avfoundation/sox/ocrd/mlx/afplay code
  win32.py         # dshow / sounddevice-WASAPI / ocrd_win / kokoro-onnx / sounddevice
tools/
  ocrd.swift       # unchanged (mac)
  ocrd_win.py      # same stdin/stdout JSON protocol
```

`live.py` keeps the orchestration and watchdogs but calls the interfaces instead of spawning platform commands directly.

## Build phases

1. **Extraction refactor (mac-only, zero behavior change).** Move platform code into `platform/darwin.py` behind `base.py`. Regression-test on the Mac rig — this is the risky step and it happens where we can verify.
2. **Windows capture proof.** dshow video frames + WASAPI PCM file on a Windows box with the ShadowCast. Validate: `live_frame.jpg` updates at 6 fps, PCM byte rate is exactly 192,000 B/s, device hot-swap works.
3. **OCR bake-off.** Run `ocrd_win.py` (both engines) against the repo's captured frames; diff against Vision's golden JSON; tune coordinate normalization and the I/l repair table until `classify.py` outputs match.
4. **TTS + playback.** kokoro-onnx synth, sounddevice playback, interrupt/yield timing check (goal: stop latency < 100ms).
5. **Recording + launcher.** 'q'-finalize, mux (pure ffmpeg filtergraph — should just work), `hoyovoice.py`, `setup.ps1`.
6. **End-to-end soak** on real gameplay; update README (Requirements gains a Windows section, latency table), CHANGELOG under *Unreleased*.

Rough effort: phases 1–2 are the bulk; 3 is calibration time; 4–5 are small. Only phases 2–6 need Windows hardware.

## Risks / open questions

- **OCR quality is the make-or-break.** Windows.Media.Ocr on the game font is unproven; if both it and RapidOCR misread nameplates badly, the ~80%-similarity name snapping absorbs some of it, but the stabilization/dedupe logic assumes mostly-consistent reads. Mitigation: the golden-frame corpus decides before any live work.
- **CPU TTS latency spread.** An 82M model is fine on a modern CPU, marginal on an old laptop. Surface synth_ms in the dashboard (already there) and document expectations.
- **WASAPI device quirks.** Some capture cards expose odd sample rates or mono; `sounddevice` must resample/upmix to the fixed 48k stereo contract, or the mux byte-math breaks.
- **Capture card contention** behaves the same (single client), but Windows "camera privacy" settings can silently block dshow — add to Troubleshooting.
- **Not in scope:** PC-native capture of the game running on the same PC (window capture instead of HDMI). Worth a future note — it would drop the capture card requirement entirely on Windows — but it's a different capture backend and an easy scope trap.
