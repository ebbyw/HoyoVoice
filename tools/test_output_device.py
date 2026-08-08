#!/usr/bin/env python3
"""Checks for the dashboard-selectable OUTPUT device (Windows backend).

    .venv/bin/python tools/test_output_device.py

The picker persists a device NAME, and the Player has to turn that back into
a PortAudio index at play time. The traps this pins down, none of which need
a sound card:

  * one physical device is listed once per host API — the picker must show
    it once (WASAPI's view), and matching must prefer that entry, because
    MME truncates names to ~31 chars;
  * "" means "follow the system default" and must reach sd.play as device
    None, not as an empty name that matches nothing;
  * a name that no longer resolves (headset unplugged) must fall back to the
    default and keep talking, and must not re-query on every single line;
  * changing the setting from the dashboard must take effect on the NEXT
    line, without restarting anything.
"""
import sys
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# device table: one WASAPI entry and one truncated MME entry per device,
# exactly the shape sounddevice reports on Windows
DEVICES = [
    dict(name="Microphone (ShadowCast 3)", hostapi=0,
         max_input_channels=2, max_output_channels=0),
    dict(name="Speakers (Realtek(R) Audio)", hostapi=0,
         max_input_channels=0, max_output_channels=2),
    dict(name="Headphones (Arctis Nova Pro Wire", hostapi=0,
         max_input_channels=0, max_output_channels=2),
    dict(name="Microphone (ShadowCast 3)", hostapi=1,
         max_input_channels=2, max_output_channels=0),
    dict(name="Speakers (Realtek(R) Audio)", hostapi=1,
         max_input_channels=0, max_output_channels=2),
    dict(name="Headphones (Arctis Nova Pro Wireless)", hostapi=1,
         max_input_channels=0, max_output_channels=2),
]
HOSTAPIS = [dict(name="MME"), dict(name="Windows WASAPI")]


class FakeSd(types.ModuleType):
    """The slice of sounddevice the backend touches."""

    def __init__(self, fail_on=()):
        super().__init__("sounddevice")
        self.fail_on = set(fail_on)     # indices whose stream won't open
        self.plays = []                 # device index per play() call
        self.queries = 0                # how often the table was walked

    def query_devices(self):
        self.queries += 1
        return list(DEVICES)

    def query_hostapis(self):
        return list(HOSTAPIS)

    def play(self, data, samplerate, device=None):
        if device in self.fail_on:
            raise RuntimeError("Error opening OutputStream: Device unavailable")
        self.plays.append(device)

    def stop(self):
        pass


def load_backend(sd):
    sys.modules["sounddevice"] = sd
    for mod in [m for m in sys.modules if m.startswith("hv_platform")]:
        del sys.modules[mod]
    import hv_platform.win32 as win32
    return win32


fails = []


def check(name, cond, detail=""):
    print(f"{'ok  ' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    if not cond:
        fails.append(name)


sd = FakeSd()
win32 = load_backend(sd)

# --- the picker's list ------------------------------------------------
outputs = win32._list_names(output=True)
check("outputs listed once each, WASAPI's view",
      outputs == ["Speakers (Realtek(R) Audio)",
                  "Headphones (Arctis Nova Pro Wireless)"], repr(outputs))
check("inputs unchanged by the shared helper",
      win32._list_names() == ["Microphone (ShadowCast 3)"])
win32._list_dshow_video = lambda: ["ShadowCast 3"]     # no ffmpeg here
check("list_devices() returns video, audio, output",
      win32.list_devices() == (["ShadowCast 3"],
                               ["Microphone (ShadowCast 3)"], outputs),
      repr(win32.list_devices()))

# --- name -> index ----------------------------------------------------
idx, dev = win32._match_device("Headphones (Arctis Nova Pro Wireless)",
                               output=True)
check("exact name resolves to the WASAPI entry, not MME's truncation",
      idx == 5, f"idx={idx}")
idx, _ = win32._match_device("realtek", output=True)
check("substring match prefers the WASAPI entry too", idx == 4, f"idx={idx}")
idx, _ = win32._match_device("Speakers (Realtek(R) Audio)")   # inputs only
check("an output name does NOT match as an input", idx is None)
check("empty name never matches", win32._match_device("", output=True)[0] is None)

# --- Player -----------------------------------------------------------
devices = {"video": "x", "audio": "y", "output": ""}
p = win32.Player(devices)
p.play(None, audio=[0.0] * 2400, samplerate=24000)
check("empty setting plays on the system default", sd.plays == [None], repr(sd.plays))

devices["output"] = "Headphones (Arctis Nova Pro Wireless)"   # dashboard swap
p.play(None, audio=[0.0] * 2400, samplerate=24000)
check("a dashboard change lands on the next line, no restart",
      sd.plays[-1] == 5, repr(sd.plays))

before = sd.queries
for _ in range(5):
    p.play(None, audio=[0.0] * 2400, samplerate=24000)
check("resolution is cached across lines", sd.queries == before,
      f"{sd.queries - before} extra device queries")
check("every line went to the chosen device",
      sd.plays[-5:] == [5] * 5, repr(sd.plays[-5:]))

# --- device gone ------------------------------------------------------
sd = FakeSd()
win32 = load_backend(sd)
devices = {"video": "x", "audio": "y", "output": "Beats Studio (offline)"}
p = win32.Player(devices)
p.play(None, audio=[0.0] * 2400, samplerate=24000)
check("an unknown name falls back to the system default", sd.plays == [None])
before = sd.queries
p.play(None, audio=[0.0] * 2400, samplerate=24000)
check("a miss is not re-queried on every line", sd.queries == before,
      f"{sd.queries - before} extra device queries")
p._next_retry = 0.0                      # cooldown elapsed
p.play(None, audio=[0.0] * 2400, samplerate=24000)
check("after the cooldown it looks again (device may be back)",
      sd.queries > before)

# a resolvable device whose stream refuses to open
sd = FakeSd(fail_on={5})
win32 = load_backend(sd)
devices = {"video": "x", "audio": "y",
           "output": "Headphones (Arctis Nova Pro Wireless)"}
p = win32.Player(devices)
p.play(None, audio=[0.0] * 2400, samplerate=24000)
check("a stream that won't open still speaks, on the default",
      sd.plays == [None], repr(sd.plays))


# --- the dashboard round trip -----------------------------------------
# /api/device must forward "" (System default) as a real choice; live.py
# drops blank video/audio names, so a blank output must not look like one.
try:
    import json
    import queue
    import urllib.request

    import webui
except ImportError as e:                 # Flask not installed here
    print(f"\nskipping the dashboard round trip ({e})")
else:
    cmds = queue.Queue()
    shared = {"devices": {"video": "ShadowCast 3", "audio": "ShadowCast 3",
                          "output": "Headphones (Arctis Nova Pro Wireless)"},
              "list_devices_fn": lambda: (["ShadowCast 3"],
                                          ["Microphone (ShadowCast 3)"],
                                          outputs),
              "voices": {"characters": {}}, "commands": cmds}
    port = webui.start_webui(shared, port=8788)

    def api(path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}")
        if body is not None:
            req.data = json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
        for _ in range(40):              # the server thread is still coming up
            try:
                return json.loads(urllib.request.urlopen(req, timeout=2).read())
            except Exception:
                time.sleep(0.05)
        raise RuntimeError(f"dashboard never answered {path}")

    d = api("/api/devices")
    check("/api/devices lists outputs and the current one",
          d["output"] == outputs
          and d["current_output"] == "Headphones (Arctis Nova Pro Wireless)",
          repr(d.get("current_output")))

    api("/api/device", {"video": "ShadowCast 3", "audio": "ShadowCast 3",
                        "output": ""})
    cmd = cmds.get_nowait()
    check("System default reaches live.py as \"\", not as a dropped field",
          cmd == ("setdevice", {"video": "ShadowCast 3",
                                "audio": "ShadowCast 3", "output": ""}),
          repr(cmd))

    api("/api/device", {"video": "ShadowCast 3", "audio": "ShadowCast 3"})
    cmd = cmds.get_nowait()
    check("an older client with no output field leaves the setting alone",
          "output" not in cmd[1], repr(cmd))

print()
print("FAILURES: " + ", ".join(fails) if fails else "all checks passed")
sys.exit(1 if fails else 0)
