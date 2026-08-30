"""Pins the one thing the ⤓ Download log button has to do: hand back a
file, whatever else is going on.

The route iterated the live decision log and the live casting table —
both mutated by the capture thread as lines land and characters are
auto-cast — so a download taken mid-session could raise "dictionary
changed size during iteration" and return a 500, which in a browser is
an error page and no file at all. Under synthetic churn that reproduced
on 8 downloads out of 8; at a real session's rate the window is narrow,
and the fix is a snapshot taken before any of the loops start. The route
also read the launcher's console capture whole in order to keep the last
4000 lines of it, on the thread that answers the dashboard's
once-a-second poll, and truncated it without saying so.

Hardware-free: a synthetic `shared` and a real server on an ephemeral
port. Run directly or under pytest:

    python tools/test_webui_log.py
"""
import os
import socket
import sys
import tempfile
import threading
import time
import urllib.request
from collections import deque
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from webui import LOG_TAIL_BYTES, start_webui        # noqa: E402


class FakeProfile:
    label = "Honkai: Star Rail"


class FakeGame:
    auto = True
    profile = FakeProfile()


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def make_shared(log_path):
    events = deque(maxlen=200)
    for i in range(200):
        events.append({"t": "12:23:23", "speaker": "Lighthouse", "id": i,
                       "action": "spoken", "voice": "am_liam", "cls": "spoken",
                       "text": "I will not back down.", "shot": True,
                       "spoken": "I will not back down."})
    return {
        "events": events,
        # a big cast on purpose: the loop that walks it has to be long
        # enough that the mutating thread can land inside it
        "voices": {"characters": {f"Char {i}": {"voice": "af_heart"}
                                  for i in range(2000)},
                   "always_voiced": [], "settings": {}},
        "unknown": {"Someone"},
        "metrics_fn": lambda: {"uptime": "0:01", "spoken": 30},
        "observing": {"on": True}, "recording": {"on": False},
        "devices": {"video": "ShadowCast 3", "audio": "HD", "output": ""},
        "game": FakeGame(), "log_path": str(log_path),
        "shots_dir": ".", "frame_dir": ".", "uploads_dir": ".",
        "rec_dir": {"path": Path(".")}, "commands": deque(),
        "voice_import": {}, "list_devices_fn": lambda: {},
    }


def main():
    failures = []
    tmp = Path(tempfile.mkdtemp())
    log = tmp / "live.log"
    # a console log twice the tail cap, with a marker in each half
    filler = ("ocr 1080p frame\n" * 40000)
    with open(log, "w", encoding="utf-8") as fh:
        fh.write("OLDEST LINE\n")
        while fh.tell() < LOG_TAIL_BYTES * 2:
            fh.write(filler)
        fh.write("NEWEST LINE\n")

    shared = make_shared(log)
    port = free_port()
    start_webui(shared, port=port)
    url = f"http://127.0.0.1:{port}/log.txt"
    for _ in range(50):                      # the serving thread is starting
        try:
            urllib.request.urlopen(url, timeout=5).read()
            break
        except OSError:
            time.sleep(0.1)

    # 1. served while the capture thread is writing to both structures
    stop = threading.Event()

    def churn():
        # What a live session does, faster: new lines into the decision
        # log, newly met characters into the cast. It has to GROW —
        # add-and-drop leaves the size unchanged at most of the points a
        # dict iterator checks it, and never raises.
        i = 0
        while not stop.is_set():
            i += 1
            shared["events"].append({"t": "12:23:24", "speaker": None,
                                     "id": 1000 + i, "action": "choice",
                                     "cls": "choice", "voice": None,
                                     "text": "churn", "shot": False})
            shared["voices"]["characters"][f"New {i}"] = {"voice": "af_heart"}
            shared["unknown"].add(f"Unknown {i}")
            time.sleep(0.0005)      # or the cast outgrows the download

    t = threading.Thread(target=churn, daemon=True)
    t.start()
    try:
        for attempt in range(8):
            try:
                r = urllib.request.urlopen(url, timeout=30)
                body = r.read().decode("utf-8", "replace")
            except Exception as exc:         # an HTTP 500 lands here too
                failures.append(f"download {attempt} failed: {exc!r}")
                break
            if "INCOMPLETE" in body:
                failures.append(f"download {attempt} assembled with an error")
                break
            for want in ("DECISION LOG", "CASTING", "CONSOLE LOG"):
                if want not in body:
                    failures.append(f"download {attempt} has no {want}")
    finally:
        stop.set()
        t.join(timeout=2)

    # 2. the console capture is tailed, not swallowed whole
    body = urllib.request.urlopen(url, timeout=30).read().decode(
        "utf-8", "replace")
    if "NEWEST LINE" not in body:
        failures.append("tail dropped the newest console line")
    if "OLDEST LINE" in body:
        failures.append("whole console log was read, not the tail")
    if "bytes omitted" not in body:
        failures.append("truncation was silent")

    # 3. a broken session still yields a file, with the reason in it
    shared["metrics_fn"] = lambda: 1 / 0
    try:
        body = urllib.request.urlopen(url, timeout=30).read().decode(
            "utf-8", "replace")
    except Exception as exc:
        failures.append(f"a failure became a dead end: {exc!r}")
        body = ""
    if body and ("INCOMPLETE" not in body
                 or "ZeroDivisionError" not in body):
        failures.append("the failure was not explained in the file")

    for f in failures:
        print("FAIL", f)
    print(f"{3 - len({f.split(' ')[0] for f in failures})}/3 checks pinned"
          if failures else "3/3 checks pinned")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())


def test_webui_log():
    assert main() == 0
