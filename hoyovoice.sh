#!/bin/zsh
# HoyoVoice control script: ./hoyovoice.sh {start|stop|status|log|restart}
ROOT="$(cd "$(dirname "$0")" && pwd)"
LOG="$ROOT/live.log"
# shared with hoyovoice.py — a .sh-started instance must be visible to
# `python hoyovoice.py status/stop`, and the two are documented as
# interchangeable
PIDFILE="$ROOT/hoyovoice.pid"

is_running() { pgrep -fi "python live.py" > /dev/null 2>&1 }

kill_all() {
  pkill -fi "python live.py" 2>/dev/null
  pkill -f "tools/ocrd" 2>/dev/null
  pkill -f "ffmpeg.*avfoundation" 2>/dev/null
  pkill -f "sox.*coreaudio" 2>/dev/null
  sleep 1
  # orphans whose parent died
  for pid in $(pgrep -f avfoundation 2>/dev/null); do
    [ "$(ps -o ppid= -p $pid | tr -d ' ')" = "1" ] && kill -9 $pid 2>/dev/null
  done
  rm -f "$PIDFILE"
}

case "$1" in
  start)
    if is_running; then echo "already running"; exit 0; fi
    cd "$ROOT" && nohup .venv/bin/python live.py > "$LOG" 2>&1 < /dev/null &
    echo $! > "$PIDFILE"
    echo "started — tail with: ./hoyovoice.sh log"
    ;;
  stop)
    kill_all
    is_running && echo "failed to stop" || echo "stopped"
    ;;
  restart)
    kill_all
    cd "$ROOT" && nohup .venv/bin/python live.py > "$LOG" 2>&1 < /dev/null &
    echo $! > "$PIDFILE"
    echo "restarted"
    ;;
  status)
    if is_running; then
      echo "running (pid $(pgrep -fi "python live.py"))"
      grep -cE "→" "$LOG" 2>/dev/null | xargs -I{} echo "lines spoken this session: {}"
    else
      echo "not running"
    fi
    ;;
  log)
    # keep in sync with LOG_NOISE in tools/webui.py (the source of truth,
    # which hoyovoice.py imports; zsh can't)
    grep -vE "pixel format|Supported|uyvy|yuyv|nv12|0rgb|bgr0|in#0|Fetching|vad: chunks" "$LOG" | tail -30
    ;;
  *)
    echo "usage: $0 {start|stop|status|log|restart}"
    ;;
esac
