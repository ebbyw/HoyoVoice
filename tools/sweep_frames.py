#!/usr/bin/env python3
"""Frame-corpus classification A/B: prove a profile change moved nothing
it wasn't meant to.

This is the check that cleared the 0.10.2 world-dialogue fix — every
saved frame classified before and after the change, outputs diffed,
zero unintended changes required — promoted from a scratch script to a
tool. The workflow is a snapshot pair:

    # corpus from a recording (frames -> OCR daemon -> one json each);
    # cached, so re-running is free
    python tools/sweep_frames.py ocr rec.mp4 -o corpus/rec1 --fps 2

    git stash            # or checkout the pre-change rev
    python tools/sweep_frames.py snapshot corpus/* -o before.json
    git stash pop
    python tools/sweep_frames.py snapshot corpus/* -o after.json
    python tools/sweep_frames.py diff before.json after.json

`diff` prints one line per frame whose classification moved, per game,
and exits 1 if anything did — so "zero unintended changes" is an exit
code, not a claim. `snapshot` classifies every frame with EVERY
profile: a Genshin band change that moves an HSR menu frame is exactly
the regression this exists to catch.

Raw OCR block json (`captures/shots/<id>.json`, or what `ocr` emits) is
the input everywhere — the same blocks live.py itself classifies from.
"""
import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from profiles import PROFILES, get_profile  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def classify_frame(blocks):
    """Every deterministic classification output, per game profile.
    Anything a profile change could move belongs in here; anything
    non-deterministic (timing, stats) must not."""
    out = {}
    for name in PROFILES:
        p = get_profile(name)
        state = p.classify(blocks)
        out[name] = {
            "speaker": state["speaker"],
            "dialogue": state["dialogue"],
            "choices": state["choices"],
            "trusts": bool(p.trusts_dialogue(blocks)),
            "fingerprint": p.fingerprint(blocks),
            "loading": p.classify_loading(blocks),
            "narration": p.classify_narration(blocks),
            "lore": p.classify_lore_screen(blocks),
            "quickread": p.classify_quickread(blocks),
            "chat": p.classify_chat(blocks),
            "overlay": p.classify_overlay(blocks),
            "infoscreen": p.classify_infoscreen(blocks),
        }
    return out


def cmd_snapshot(args):
    frames = []
    for d in args.corpus:
        d = Path(d)
        frames += sorted(d.glob("*.json")) if d.is_dir() else [d]
    if not frames:
        sys.exit("no *.json frames found")
    snap = {}
    for f in frames:
        try:
            blocks = json.loads(f.read_text())
        except Exception as e:
            print(f"[skip] {f}: {e}", file=sys.stderr)
            continue
        snap[f"{f.parent.name}/{f.name}"] = classify_frame(blocks)
    Path(args.out).write_text(json.dumps(snap, indent=1, sort_keys=True,
                                         ensure_ascii=False))
    print(f"{len(snap)} frames -> {args.out}")


def cmd_diff(args):
    a = json.loads(Path(args.before).read_text())
    b = json.loads(Path(args.after).read_text())
    changed = 0
    for key in sorted(set(a) | set(b)):
        if key not in a or key not in b:
            print(f"{key}: only in {'after' if key not in a else 'before'}")
            changed += 1
            continue
        for game in sorted(set(a[key]) | set(b[key])):
            ga, gb = a[key].get(game, {}), b[key].get(game, {})
            for field in sorted(set(ga) | set(gb)):
                if ga.get(field) != gb.get(field):
                    print(f"{key} [{game}.{field}]\n"
                          f"  before: {json.dumps(ga.get(field), ensure_ascii=False)[:200]}\n"
                          f"  after:  {json.dumps(gb.get(field), ensure_ascii=False)[:200]}")
                    changed += 1
    n = len(set(a) | set(b))
    print(f"{n} frames, {changed} field change(s)")
    sys.exit(1 if changed else 0)


def cmd_ocr(args):
    """Recording (or directory of jpgs) -> one raw-OCR json per frame,
    via this platform's real daemon. Cached: frames whose json already
    exists are skipped, so building a corpus is a one-time cost."""
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    src = Path(args.source)
    if src.is_dir():
        jpgs = sorted(src.glob("*.jpg"))
    else:
        cut = ["-ss", str(args.start)]
        if args.duration:
            cut += ["-t", str(args.duration)]
        tmp = Path(tempfile.mkdtemp(prefix="sweep_frames_"))
        subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error",
                        *cut, "-i", str(src),
                        "-vf", f"fps={args.fps},scale=1920:-2", "-q:v", "3",
                        str(tmp / f"{src.stem}_%05d.jpg"), "-y"], check=True)
        jpgs = sorted(tmp.glob("*.jpg"))
    todo = [j for j in jpgs if not (out / f"{j.stem}.json").exists()]
    print(f"{len(jpgs)} frames, {len(todo)} to OCR")
    if not todo:
        return
    if sys.platform == "win32":
        daemon = [sys.executable, str(ROOT / "tools" / "ocrd_win.py")]
    else:
        daemon = [str(ROOT / "tools" / "ocrd")]
    proc = subprocess.Popen(daemon, stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, bufsize=1)
    done = 0
    for j in todo:
        proc.stdin.write(str(j) + "\n")
        proc.stdin.flush()
        line = proc.stdout.readline()
        try:
            json.loads(line)
        except Exception:
            print(f"[skip] {j.name}: daemon returned no blocks",
                  file=sys.stderr)
            continue
        (out / f"{j.stem}.json").write_text(line)
        done += 1
        if done % 100 == 0:
            print(f"  {done}/{len(todo)}")
    proc.stdin.close()
    print(f"{done} frames -> {out}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("snapshot", help="classify a corpus, save outputs")
    s.add_argument("corpus", nargs="+",
                   help="directories of raw-OCR *.json (or single files)")
    s.add_argument("-o", "--out", required=True)
    s.set_defaults(fn=cmd_snapshot)

    d = sub.add_parser("diff", help="compare two snapshots; exit 1 on change")
    d.add_argument("before")
    d.add_argument("after")
    d.set_defaults(fn=cmd_diff)

    o = sub.add_parser("ocr", help="recording/jpg-dir -> raw-OCR json corpus")
    o.add_argument("source", help="an .mp4 recording or a directory of .jpg")
    o.add_argument("-o", "--out", required=True)
    o.add_argument("--fps", type=float, default=2)
    o.add_argument("--start", type=float, default=0.0)
    o.add_argument("--duration", type=float, default=None)
    o.set_defaults(fn=cmd_ocr)

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
