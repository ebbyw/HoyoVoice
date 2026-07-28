#!/usr/bin/env python3
"""HoyoVoice control script (cross-platform).

    python hoyovoice.py {start|stop|status|log|restart}

On Windows this is THE launcher. On macOS ./hoyovoice.sh still works and
does the same job; this script is equivalent there.

Uses a pidfile + process groups: live.py's children (ffmpeg, the OCR
daemon, sox on macOS) die with it — live.py's own SIGTERM/finally cleanup
handles them, and the process-group/tree kill is the backstop.
"""
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PIDFILE = ROOT / "hoyovoice.pid"
LOG = ROOT / "live.log"
WIN = sys.platform == "win32"
VENV_PY = ROOT / (".venv/Scripts/python.exe" if WIN else ".venv/bin/python")

LOG_NOISE = re.compile(
    "pixel format|Supported|uyvy|yuyv|nv12|0rgb|bgr0|in#0|Fetching|vad: chunks")


def read_pid():
    try:
        return int(PIDFILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return None


def pid_alive(pid):
    if pid is None:
        return False
    if WIN:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def port_busy(port=8470):
    import socket
    s = socket.socket()
    s.settimeout(0.5)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def start():
    if pid_alive(read_pid()):
        print("already running")
        return
    if port_busy():
        print("dashboard port 8470 is in use — an orphaned instance is still "
              "running.\nWindows: taskkill /F /IM ffmpeg.exe & check Task "
              "Manager for python.exe\nmacOS: ./hoyovoice.sh stop")
        sys.exit(1)
    if not VENV_PY.exists():
        print(f"venv python not found: {VENV_PY}\n"
              f"run {'setup.ps1' if WIN else './setup.sh'} first")
        sys.exit(1)
    log = open(LOG, "w")
    kw = {}
    if WIN:
        # CREATE_NO_WINDOW (hidden console, inherited by ffmpeg/ocr children)
        # — do NOT combine with DETACHED_PROCESS: they're mutually exclusive,
        # and a detached parent makes each console child pop its own window
        kw["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP
                               | subprocess.CREATE_NO_WINDOW)
    else:
        kw["start_new_session"] = True   # group leader → killpg reaches children
    p = subprocess.Popen([str(VENV_PY), str(ROOT / "live.py")],
                         cwd=str(ROOT), stdout=log, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, **kw)
    PIDFILE.write_text(str(p.pid))
    print(f"started (pid {p.pid}) — tail with: python hoyovoice.py log")


def stop():
    pid = read_pid()
    if not pid_alive(pid):
        print("not running")
        PIDFILE.unlink(missing_ok=True)
        return
    if WIN:
        # /T kills the whole tree (live.py + ffmpeg + ocrd_win)
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True)
    else:
        try:                     # graceful first: live.py's finally cleans up
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
        for _ in range(20):
            if not pid_alive(pid):
                break
            time.sleep(0.2)
        if pid_alive(pid):
            try:
                os.killpg(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    time.sleep(0.5)
    PIDFILE.unlink(missing_ok=True)
    print("failed to stop" if pid_alive(pid) else "stopped")


def status():
    pid = read_pid()
    if pid_alive(pid):
        print(f"running (pid {pid})")
        try:
            spoken = sum(1 for ln in LOG.read_text(errors="ignore").splitlines()
                         if "→" in ln)
            print(f"lines spoken this session: {spoken}")
        except FileNotFoundError:
            pass
    else:
        print("not running")


def log():
    try:
        lines = [ln for ln in LOG.read_text(errors="ignore").splitlines()
                 if not LOG_NOISE.search(ln)]
    except FileNotFoundError:
        print("no log yet")
        return
    print("\n".join(lines[-30:]))


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "start":
        start()
    elif cmd == "stop":
        stop()
    elif cmd == "restart":
        stop()
        start()
    elif cmd == "status":
        status()
    elif cmd == "log":
        log()
    else:
        print(f"usage: {sys.argv[0]} {{start|stop|status|log|restart}}")


if __name__ == "__main__":
    main()
