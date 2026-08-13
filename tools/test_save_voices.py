"""Pins that a hand edit to voices.json survives the app rewriting it.

voices.json is rewritten whenever casting changes — an auto-cast, a
dashboard reassignment, an installed pack — from the copy the app read at
STARTUP. So a setting added by hand mid-session lasted until the next
auto-cast and then vanished, with nothing said: `settings.textmap` and
`settings.player_name` were added at 20:03 on 2026-08-12, wiped by the
session running since 19:50, and the restart meant to pick them up read a
file that no longer had them.

Run directly or under pytest:

    python tools/test_save_voices.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A child process, because live.py binds its paths at import from
# HOYOVOICE_STATE_DIR and the point is to exercise the real module.
CHILD = r'''
import json, sys
sys.path.insert(0, {root!r})
sys.path.insert(0, {tools!r})
import live

# the app changes casting, as an auto-cast would
live.VOICES["characters"]["Paimon"] = {{"voice": "af_bella", "speed": 1.0}}
# and meanwhile the file on disk grew a setting the app has never heard of
path = live.VOICES_PATH
on_disk = json.loads(path.read_text())
on_disk.setdefault("settings", {{}})["textmap"] = "/maps/genshin.json"
on_disk["settings"]["player_name"] = "Ebby"
path.write_text(json.dumps(on_disk))

live.save_voices()
print(json.dumps(json.loads(path.read_text())))
'''


def main():
    state = Path(tempfile.mkdtemp(prefix="hv_save_"))
    (state / "voices.json").write_text(json.dumps({
        "characters": {}, "defaults": {"narrator": "bm_lewis",
                                       "female": ["af_bella"],
                                       "male": ["am_eric"]},
        "settings": {"game": "genshin"}}))
    # HOYOVOICE_STATE_DIR, exactly: getting the name wrong points the
    # child at the real installation and edits the real casting
    env = dict(os.environ, HOYOVOICE_STATE_DIR=str(state))
    try:
        out = subprocess.run(
            [sys.executable, "-c", CHILD.format(root=str(ROOT),
                                                tools=str(ROOT / "tools"))],
            capture_output=True, text=True, env=env, timeout=180)
        if out.returncode:
            print("FAIL  could not run live.py:\n" + out.stderr[-1200:])
            return 1
        saved = json.loads(out.stdout.strip().splitlines()[-1])
    finally:
        shutil.rmtree(state, ignore_errors=True)

    bad = 0
    settings = saved.get("settings", {})
    if settings.get("textmap") != "/maps/genshin.json":
        print(f"FAIL  a hand-added setting was wiped: {settings}")
        bad += 1
    else:
        print("ok    a setting added by hand mid-session survives the write")
    if settings.get("player_name") != "Ebby":
        print(f"FAIL  player_name was wiped: {settings}")
        bad += 1
    else:
        print("ok    so does a second one")
    if settings.get("game") != "genshin":
        print(f"FAIL  a setting the app already had was lost: {settings}")
        bad += 1
    else:
        print("ok    settings the app already knew are untouched")
    if "Paimon" not in saved.get("characters", {}):
        print("FAIL  the casting change the write existed for was lost")
        bad += 1
    else:
        print("ok    the casting change still lands")

    print("FAILURES:", bad) if bad else print("all good")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
