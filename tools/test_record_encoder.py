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
    # the probe asks for the recording's own shape: a 256x256 yuv420p
    # probe passed on a GPU whose NVENC then refused the 1080p 4:2:2
    # capture stream with "No capable devices found"
    assert "1920x1080" in cmd[cmd.index("-i") + 1]
    assert cmd[cmd.index("-pix_fmt") + 1] == win32.RECORD_PIX_FMT == "yuv420p"


class _Proc:
    """A Popen stand-in that either dies at once or keeps running."""
    def __init__(self, cmd, dies):
        self.cmd, self.dies, self.stdin = cmd, dies, None

    def wait(self, timeout=None):
        if self.dies:
            return 1
        raise subprocess.TimeoutExpired(self.cmd, timeout)

    def poll(self):
        return 1 if self.dies else None

    def kill(self):
        pass


def _capture(spawned, dying):
    """A VideoCapture whose ffmpeg is a _Proc: dies when its encoder is
    in `dying`."""
    cap = win32.VideoCapture({"video": "card"}, "frame.jpg", 6)
    saved = (win32.subprocess.Popen, win32.ensure_ffmpeg)

    def popen(cmd, **kw):
        codec = cmd[cmd.index("-c:v") + 1] if "-c:v" in cmd else None
        spawned.append(codec)
        return _Proc(cmd, codec in dying)
    win32.subprocess.Popen, win32.ensure_ffmpeg = popen, lambda: "ffmpeg"
    return cap, saved


def test_recording_pins_yuv420p_for_every_encoder():
    win32._record_encoder["c"] = "h264_nvenc"
    spawned, cmds = [], []
    cap, saved = _capture(spawned, dying=set())
    real_popen = win32.subprocess.Popen

    def popen(cmd, **kw):
        cmds.append(cmd)
        return real_popen(cmd, **kw)
    win32.subprocess.Popen = popen
    try:
        cap.restart("rec.mkv")
        cap.restart()                      # plain capture: no recording map
    finally:
        win32.subprocess.Popen, win32.ensure_ffmpeg = saved
        win32._record_encoder["c"] = None
    rec, plain = cmds
    i = rec.index("-c:v")
    assert rec[i - 2:i] == ["-pix_fmt", "yuv420p"] and rec[i + 1] == "h264_nvenc"
    assert "-pix_fmt" not in plain and "-c:v" not in plain


def test_dead_hardware_encoder_falls_back_to_x264_once():
    win32._record_encoder["c"] = "h264_nvenc"
    spawned = []
    cap, saved = _capture(spawned, dying={"h264_nvenc"})
    try:
        cap.restart("rec.mkv")
        assert spawned == ["h264_nvenc", "libx264"]
        assert win32._record_encoder["c"] == "libx264"
        assert cap.proc.poll() is None     # the libx264 process is the live one
        cap.restart("rec2.mkv")            # demoted for the session: no retry
        assert spawned == ["h264_nvenc", "libx264", "libx264"]
    finally:
        win32.subprocess.Popen, win32.ensure_ffmpeg = saved
        win32._record_encoder["c"] = None


def test_live_hardware_encoder_is_kept():
    win32._record_encoder["c"] = "h264_qsv"
    spawned = []
    cap, saved = _capture(spawned, dying=set())
    try:
        cap.restart("rec.mkv")
        assert spawned == ["h264_qsv"] and win32._record_encoder["c"] == "h264_qsv"
    finally:
        win32.subprocess.Popen, win32.ensure_ffmpeg = saved
        win32._record_encoder["c"] = None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
    win32._record_encoder["c"] = None
