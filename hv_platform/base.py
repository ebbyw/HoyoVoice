"""Interface contract every platform backend must satisfy.

A backend is a module providing these factory functions:

    list_devices() -> (video_names: [str], audio_names: [str])
        Names shown in the dashboard pickers. Audio names must be the
        names the backend's AudioCapture accepts (they may come from a
        different enumerator than the video names).

    create_video_capture(devices: dict, frame_path: Path, sample_fps: int)
        -> VideoCapture
    create_audio_capture(devices: dict, pcm_path: Path) -> AudioCapture
        Both receive the live DEVICES dict {"video": name, "audio": name}
        and must re-read it on every (re)start so dashboard hot-swaps work.
    create_ocr(root: Path, custom_words: Path) -> OcrDaemon
    create_tts() -> Tts
    create_player() -> Player

Shared data contracts (identical on every platform — the orchestrator,
VAD tail-reader, and recording mux all depend on them):

    frame_path   : single JPEG, atomically overwritten at sample_fps.
    pcm_path     : continuously appended s16le 48 kHz STEREO PCM
                   (192,000 bytes/sec). (Re)starting capture truncates it.
    OCR blocks   : list of {"text", "confidence", "x", "y", "w", "h"} with
                   coordinates NORMALIZED 0-1, origin BOTTOM-LEFT (Apple
                   Vision convention — classify.py assumes it).
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

    OcrDaemon.recognize(image_path) -> blocks | None
        None means the engine failed this call; the daemon must have
        already begun respawning itself. .kill() for shutdown.

    Tts.synth(text, voice, speed) -> np.float32 array | None
    Tts.warm_up()   # optional pre-load; called once at startup
    Tts.register_voice(voice_id, path)   # installed voice pack (a
        # (510, 1, 256) float32 .safetensors written by tools/voicepack.py);
        # after this, synth() must accept voice_id like any built-in voice
    Tts.forget_voice(voice_id)           # undo a registration

    Player.play(wav_path, audio, samplerate)   # audio = float32 array;
        # backends use whichever of path/array is cheaper for them
    Player.stop() -> bool                      # True if it interrupted playback
    Player.playing -> bool
"""
