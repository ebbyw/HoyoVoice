#!/usr/bin/env python3
"""Concurrency check for the off-loop capture swap in live.py.

    .venv/bin/python tools/test_video_swap.py

Recording stop used to run `video.finalize()` (seconds, while ffmpeg flushes
the MKV) and `video.restart()` inline, freezing the reading loop for the
whole window — the tail of a line that read ~23s late. Both now run on a
worker. That buys back the stall at the cost of three things this test pins
down, none of which the replay harness can reach (it never records):

  * a single ffmpeg owns BOTH the capture device and the live frame file,
    so two of them must never overlap, whoever starts them;
  * the mux must not begin until finalize has actually closed the MKV;
  * shutdown must not race the worker into respawning an orphan capture.

Uses a fake capture with ffmpeg-like timing, so it runs in about two
seconds and needs no hardware.
"""
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
try:
    import live
except Exception as e:                      # platform backend / deps missing
    print(f"SKIP: cannot import live.py here ({e.__class__.__name__}: {e})")
    raise SystemExit(0)


class FakeCapture:
    """Mimics the VideoCapture contract and asserts the core invariant:
    never two live capture processes at once."""

    def __init__(self):
        self.live = 0
        self.max_live = 0
        self.violations = []
        self.log = []
        self._lk = threading.Lock()

    def _open(self):
        with self._lk:
            self.live += 1
            self.max_live = max(self.max_live, self.live)
            if self.live > 1:
                self.violations.append("two captures live at once")

    def _close(self):
        with self._lk:
            self.live -= 1

    def restart(self, record_path=None):
        if self.live:
            self._close()
        time.sleep(0.15)                    # device re-negotiation
        self._open()
        self.log.append(f"restart(record={bool(record_path)})")

    def finalize(self, timeout=8.0):
        time.sleep(0.60)                    # mkv flush
        self._close()
        self.log.append("finalize")

    def kill(self):
        if self.live:
            self._close()
        self.log.append("kill")


FAILURES = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail else ''}")
    if not ok:
        FAILURES.append(name)


def test_loop_is_not_blocked():
    v = FakeCapture()
    v.restart()
    t0 = time.monotonic()
    live.swap_video_async(v, finalize_first=True)
    returned = time.monotonic() - t0
    check("stop-swap returns immediately", returned < 0.05,
          f"{returned * 1000:.0f}ms")
    check("swap reports itself in flight", live.video_swapping())
    ticks = 0
    while live.video_swapping():            # the loop keeps turning
        ticks += 1
        time.sleep(0.01)
    check("loop ticked during the swap", ticks > 40, f"{ticks} iterations")
    check("finalize ran before restart",
          v.log[-2:] == ["finalize", "restart(record=False)"], str(v.log))
    check("one capture live afterwards", v.live == 1)


def test_restart_recording_does_not_race_the_swap():
    v = FakeCapture()
    v.restart()
    live.swap_video_async(v, finalize_first=True)
    time.sleep(0.05)                        # user hits record again at once
    with live.video_lock:
        v.restart(record_path="x.mkv")
    check("no overlapping captures on stop->start", not v.violations,
          str(v.violations))
    check("never more than one capture live", v.max_live == 1,
          f"max_live={v.max_live}")
    check("the recording capture is the survivor",
          v.log[-1] == "restart(record=True)", str(v.log))


def test_stall_watchdog_is_suppressed():
    v = FakeCapture()
    v.restart()
    live.swap_video_async(v, finalize_first=True)
    # the loop's watchdog, with an already-expired stall timer: without the
    # swap guard it would respawn on top of the worker every iteration
    respawns = 0
    last_frame_change = time.monotonic() - 30
    while live.video_swapping():
        now = time.monotonic()
        if live.video_swapping():
            last_frame_change = now
        elif now - last_frame_change > 10:
            respawns += 1
            with live.video_lock:
                v.restart()
            last_frame_change = time.monotonic()
        time.sleep(0.01)
    check("watchdog suppressed during the swap", respawns == 0,
          f"{respawns} respawns")
    check("swap left no overlap", not v.violations and v.live == 1,
          str(v.violations))


def test_mux_waits_for_the_mkv_to_close():
    v = FakeCapture()
    v.restart()
    order = []
    plain_finalize = v.finalize

    def traced_finalize(timeout=8.0):
        plain_finalize(timeout)
        order.append(("finalized", v.live))

    v.finalize = traced_finalize
    # v.live == 0 at mux time means ffmpeg had already released the file
    live.swap_video_async(v, finalize_first=True,
                          on_finalized=lambda: order.append(("mux", v.live)))
    live.video_swap["thread"].join(timeout=10)
    check("mux starts after finalize", [o[0] for o in order] ==
          ["finalized", "mux"], str(order))
    check("mux sees a closed recording", order and order[-1][1] == 0,
          str(order))
    check("capture respawned after the handoff",
          v.live == 1 and v.log[-1].startswith("restart"), str(v.log))


def test_shutdown_leaves_no_orphan():
    v = FakeCapture()
    v.restart()
    live.swap_video_async(v, finalize_first=True)
    t = live.video_swap["thread"]
    t.join(timeout=10)
    with live.video_lock:
        v.kill()
    check("no capture running after shutdown", v.live == 0)
    check("kill is the last action", v.log[-1] == "kill", str(v.log))


if __name__ == "__main__":
    for fn in (test_loop_is_not_blocked,
               test_restart_recording_does_not_race_the_swap,
               test_stall_watchdog_is_suppressed,
               test_mux_waits_for_the_mkv_to_close,
               test_shutdown_leaves_no_orphan):
        fn()
    print("\n" + ("ALL PASS" if not FAILURES else f"FAILURES: {FAILURES}"))
    raise SystemExit(1 if FAILURES else 0)
