"""Pins the Windows recording encoder probe (hv_platform/win32.py).

The recording encoder is chosen by running each hardware candidate once
against real hardware and keeping the first that works, falling back to
libx264 — because ffmpeg lists every encoder it was compiled with whether
or not the GPU exists, and a guessed encoder is a recording that never
starts. The probe runner is injected, so this runs anywhere. Run directly
or under pytest:

    python tools/test_record_encoder.py
"""
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hv_platform import win32                   # noqa: E402


def _runner(works):
    """A subprocess.run stand-in: exit 0 for the encoders in `works`."""
    calls = []

    def run(cmd, **kw):
        codec = cmd[cmd.index("-c:v") + 1]
        calls.append(codec)
        return subprocess.CompletedProcess(cmd, 0 if codec in works else 1)
    run.calls = calls
    return run


def test_first_working_hardware_encoder_wins():
    win32._record_encoder["c"] = None
    run = _runner({"h264_qsv", "h264_amf"})
    assert win32.record_encoder("ffmpeg", run) == "h264_qsv"
    assert run.calls == ["h264_nvenc", "h264_qsv"]      # stops at the first hit


def test_no_hardware_falls_back_to_x264_and_caches():
    win32._record_encoder["c"] = None
    run = _runner(set())
    assert win32.record_encoder("ffmpeg", run) == "libx264"
    assert run.calls == list(win32.HW_ENCODERS)
    run2 = _runner({"h264_nvenc"})
    assert win32.record_encoder("ffmpeg", run2) == "libx264"   # chosen once
    assert run2.calls == []


def test_probe_failure_is_a_no():
    def boom(cmd, **kw):
        raise OSError("ffmpeg missing")
    assert win32._encoder_works("ffmpeg", "h264_nvenc", boom) is False


def test_probe_encodes_synthetic_frames_to_nowhere():
    seen = {}

    def run(cmd, **kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0)
    assert win32._encoder_works("/x/ffmpeg", "h264_amf", run) is True
    cmd = seen["cmd"]
    assert cmd[0] == "/x/ffmpeg" and "lavfi" in cmd and cmd[-2:] == ["null", "-"]
    assert cmd[cmd.index("-c:v") + 1] == "h264_amf"
    assert "-nostdin" in cmd                 # never waits on a console


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    win32._record_encoder["c"] = None
