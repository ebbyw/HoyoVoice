"""Interface contract every platform backend must satisfy.

A backend is a module providing these factory functions:

    list_devices() -> (video_names, audio_names, output_names) : [str] x3
        Names shown in the dashboard pickers. Audio names must be the
        names the backend's AudioCapture accepts, output names the ones
        its Player accepts (they may come from different enumerators than
        the video names). An empty output list means the backend can only
        play on the system default; the picker then offers just that.

    create_video_capture(devices: dict, frame_path: Path, sample_fps: int)
        -> VideoCapture
    create_audio_capture(devices: dict, pcm_path: Path) -> AudioCapture
    create_player(devices: dict) -> Player
        All three receive the live DEVICES dict
        {"video": name, "audio": name, "output": name} and must re-read it
        on every (re)start / play so dashboard hot-swaps work. An empty
        "output" means the system default.
    create_ocr(root: Path, custom_words: Path) -> OcrDaemon
    create_tts() -> Tts

Shared data contracts (identical on every platform — the orchestrator,
VAD tail-reader, and recording mux all depend on them):

    frame_path   : single JPEG, atomically overwritten at sample_fps.
    pcm_path     : continuously appended s16le 48 kHz STEREO PCM
                   (192,000 bytes/sec). (Re)starting capture truncates it.
    OCR blocks   : list of {"text", "confidence", "x", "y", "w", "h"} with
                   coordinates NORMALIZED 0-1, origin BOTTOM-LEFT (Apple
                   Vision convention — tools/profiles/ and tools/anchors.py
                   assume it).
    TTS audio    : float32 numpy array, 24 kHz mono, roughly [-1, 1].

Behavioral contracts:

    VideoCapture.restart(record_path=None)
        Kill any running capture and start fresh (re-negotiates the
        device). With record_path, additionally write a crash-safe
        1080p30 MKV there.
    VideoCapture.finalize(timeout=8.0)
        Cleanly close a recording MKV (platform-specific graceful stop),
        leaving capture STOPPED — caller restarts.
    VideoCapture.alive / .kill()

    AudioCapture.restart() / .alive / .kill()
        restart() truncates pcm_path (the VAD tail-reader detects the
        shrink and rejoins at the live edge).

    OcrDaemon.recognize(image_path, roi=None) -> blocks | None
        None means nothing was read: the file was not a complete image
        (torn mid-rewrite — the daemon answers `null`), or the engine
        died (the daemon must have already begun respawning itself).
        Either way the frame is lost, not empty. .kill() for shutdown.
        `roi` ({"x": (x0, x1), "y": (y0, y1)}, Vision-normalized) reads
        only that region; the blocks come back normalized to the WHOLE
        image either way — no caller ever sees region-relative boxes.
    OcrDaemon.supports_regions() -> bool
        Whether the running daemon understands a region on the request
        line (probe_regions() below). A caller with a region must ask
        first: a daemon built before regions takes the whole line for a
        path and answers [] to every region request — an invisible
        failure, since an empty region read is a legitimate answer.

    Tts.synth(text, voice, speed) -> np.float32 array | None
    Tts.register_voice(voice_id, path)   # installed voice pack (a
        # (510, 1, 256) float32 .safetensors written by tools/voicepack.py);
        # after this, synth() must accept voice_id like any built-in voice
    Tts.forget_voice(voice_id)           # undo a registration
    Tts.voice_style(voice_id) -> np.float32 (510, 1, 256)
        # the style tensor behind any voice synth() accepts — packaged or
        # registered — read from wherever this platform keeps it. This is
        # what voice blending mixes; it never touches the engine itself.

    Player.play(wav_path, audio, samplerate)   # audio = float32 array;
        # backends use whichever of path/array is cheaper for them
    Player.stop() -> bool                      # True if it interrupted playback
    Player.playing -> bool
"""
import json


def request_line(image_path, roi=None):
    """One OCR daemon request: the image path, plus a TAB and "x y w h"
    (Vision-normalized, bottom-left origin) when only that region should
    be read. tools/ocrd and tools/ocrd_win.py parse exactly this line and
    answer with boxes normalized to the whole image either way. TAB, not
    space, because a path may contain spaces; `roi` is the
    {"x": (x0, x1), "y": (y0, y1)} region dict tools/anchors.py produces."""
    line = str(image_path)
    if roi is not None:
        (x0, x1), (y0, y1) = roi["x"], roi["y"]
        line += f"\t{x0:.6f} {y0:.6f} {x1 - x0:.6f} {y1 - y0:.6f}"
    return line + "\n"


def probe_regions(daemon):
    """Ask a freshly spawned daemon whether it understands regions, once.
    An empty request line is the probe: a daemon that knows regions
    answers [{"protocol": 2}], an older build answers [] (it tried to
    open "" as a file). Cached on the daemon as `regions` until its next
    spawn; a daemon that answers nothing at all (died) is left unprobed
    so the next call asks again. The warning is printed once per spawn,
    because the symptom otherwise — whole frames read, roi_crops stuck at
    0 — looks like anchors never matching."""
    if getattr(daemon, "regions", None) is not None:
        return daemon.regions
    try:
        daemon.proc.stdin.write("\n")
        raw = daemon.proc.stdout.readline()
    except (BrokenPipeError, OSError):
        raw = ""
    if not raw:
        return False
    try:
        reply = json.loads(raw)
    except ValueError:
        reply = []
    ok = any(isinstance(b, dict) and b.get("protocol", 0) >= 2
             for b in (reply or []))
    daemon.regions = ok
    if not ok:
        print("[ocr] daemon predates region requests — reading whole "
              "frames; rebuild it (setup.sh / setup.ps1) to restore ROI "
              "reads", flush=True)
    return ok
