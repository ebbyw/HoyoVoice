#!/usr/bin/env python3
"""Measure the OCR, so a change to it can be judged by numbers.

Every OCR fix so far has been signature-by-signature — fused rows, a bullet
glyph welded to a word, a garbled re-read — because there was no way to ask
"is the reader better than it was yesterday?" This is that way.

    python tools/ocr_bench.py extract ~/Videos/rec_X.mp4 --out bench/snez
    python tools/ocr_bench.py stability bench/snez --scale 1 --scale 2
    python tools/ocr_bench.py accuracy  bench/snez --scale 1 --scale 2

Two metrics, because they answer different questions and only one of them
needs a human:

  STABILITY needs no ground truth at all. The game holds a line on screen
  for seconds at a time, so consecutive frames of a static screen must read
  identically — and when they don't, that alone is the bug: a line that
  reads two ways alternately defeats the dedupe window and is spoken twice
  (2026-08-12, forty times in two minutes). Frames are grouped into runs of
  the same screen, and the score is the share of frames that disagree with
  their run's majority read. It can be run over hundreds of frames the
  moment a recording exists.

  ACCURACY needs `truth.json` in the corpus directory — {frame: line} typed
  by a human looking at the frame. It reports exact-match rate and
  character error rate. Small by nature; it is the only thing that can
  catch an error every frame agrees on.

A corpus is a directory of full-resolution PNG frames plus an optional
truth.json. Frames are NOT committed (they are screenshots of a game, and
large); rebuild one from any session recording with `extract`.
"""
import argparse
import difflib
import json
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from anchors import crop_frame, remap_box                          # noqa: E402
from profiles import get_profile                        # noqa: E402


def norm(s):
    return " ".join((s or "").split())


def cer(got, want):
    """Character error rate: edits per character of truth."""
    want = norm(want)
    got = norm(got)
    if not want:
        return 0.0 if not got else 1.0
    same = sum(b.size for b in difflib.SequenceMatcher(
        None, want, got).get_matching_blocks())
    return max(0.0, (len(want) - same)) / len(want)


# ---------------------------------------------------------------- extract
def extract(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if args.start:
        cmd += ["-ss", str(args.start)]
    if args.duration:
        cmd += ["-t", str(args.duration)]
    cmd += ["-i", str(Path(args.recording).expanduser()),
            "-vf", f"fps={args.fps}", str(out / "%05d.png")]
    subprocess.run(cmd, check=True)
    frames = sorted(out.glob("*.png"))
    print(f"{len(frames)} frames → {out}")
    print("next: type ground truth into truth.json for the frames you want "
          "scored, or run `stability` right now — it needs none")


def capture(args):
    """Frames from the LIVE capture file, which is not the same thing.

    A recording is a second ffmpeg encode of the feed; its frames are whole
    by construction. The frames the app actually reads are single JPEGs
    rewritten in place six times a second, and the misreads that matter —
    two rows fused into one box, a glyph welded to a word — do not survive
    into the recording: replaying rec_20260812_174047.mp4 reads its line
    once, cleanly, while the live session read it forty times, wrongly. To
    measure the reader as it runs, sample what it reads.

    Run this with the app up and the misbehaving screen on screen.
    """
    import time
    src = Path(args.frame).expanduser()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    seen, n, end = None, 0, time.time() + args.seconds
    while time.time() < end:
        try:
            mtime = src.stat().st_mtime
        except FileNotFoundError:
            sys.exit(f"{src} not there — is the app running?")
        if mtime != seen:
            seen = mtime
            data = src.read_bytes()
            # whole JPEGs only: a torn one is a different bug and would
            # score as a misread here
            if len(data) > 1024 and data[:2] == b"\xff\xd8" \
                    and data[-2:] == b"\xff\xd9":
                n += 1
                (out / f"{n:05d}.jpg").write_bytes(data)
        time.sleep(0.02)
    print(f"{n} frames → {out}")


# ------------------------------------------------------------------ reads
def read_frames(frames, game, scale, ocr, roi=None):
    """(frame, dialogue, blocks) for each frame, at the given scale/ROI.

    Boxes come back in FULL-FRAME coordinates whatever was handed to the
    recognizer, so the profile sees what it always sees — the same
    remapping live.py does at the OCR call boundary.
    """
    profile = get_profile(game)
    tmp = Path(tempfile.mkdtemp(prefix="hv_bench_"))
    try:
        for f in frames:
            path, crop = f, None
            if scale != 1 or roi:
                path = tmp / "scaled.png"
                crop = crop_frame(f, roi or (0.0, 0.0, 1.0, 1.0), path, scale)
                if crop is None:
                    # crop_frame verifies a whole JPEG — that check is for
                    # the live capture, and a PNG corpus fails it. Same
                    # crop, done plainly.
                    from PIL import Image
                    img = Image.open(f)
                    W, H = img.size
                    x0, y0, x1, y1 = roi or (0.0, 0.0, 1.0, 1.0)
                    px = (int(x0 * W), int((1 - y1) * H),
                          int(x1 * W), int((1 - y0) * H))
                    img = img.crop(px)
                    img.resize((img.width * scale, img.height * scale),
                               Image.Resampling.LANCZOS).save(path)
                    crop = (px[0] / W, (H - px[3]) / H,
                            (px[2] - px[0]) / W, (px[3] - px[1]) / H)
            blocks = ocr.recognize(path)
            if blocks is None:
                blocks = []
            if crop is not None:
                blocks = [remap_box(b, crop) for b in blocks]
            yield f, norm(profile.classify(blocks).get("dialogue")), blocks
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def make_ocr():
    sys.path.insert(0, str(ROOT))
    from hv_platform import darwin
    words = ROOT / "captures" / "custom_words.txt"
    if not words.exists():
        words.parent.mkdir(parents=True, exist_ok=True)
        words.write_text("")
    return darwin.create_ocr(ROOT, words)


# -------------------------------------------------------------- stability
def runs_of(reads, cutoff=0.6):
    """Group consecutive frames showing the same screen.

    Similarity, not equality — the point is to group frames that SHOULD
    read the same, including the ones that misread. A new line scores far
    below any misreading of the old one; 0.6 sits in the gap. A frame with
    no line at all breaks the run (menus, fades).
    """
    groups, cur = [], []
    for frame, text, _ in reads:
        if not text:
            if cur:
                groups.append(cur)
                cur = []
            continue
        if cur and difflib.SequenceMatcher(
                None, cur[-1][1], text).ratio() < cutoff:
            groups.append(cur)
            cur = []
        cur.append((frame, text))
    if cur:
        groups.append(cur)
    return [g for g in groups if len(g) >= 2]


def corpus_frames(where):
    d = Path(where)
    return sorted([*d.glob("*.png"), *d.glob("*.jpg")])


def stability(args):
    frames = corpus_frames(args.corpus)
    if not frames:
        sys.exit(f"no frames in {args.corpus}")
    ocr = make_ocr()
    try:
        for scale in args.scale:
            reads = list(read_frames(frames, args.game, scale, ocr,
                                     args.roi))
            groups = runs_of(reads)
            total = sum(len(g) for g in groups)
            odd = []
            for g in groups:
                best, _ = Counter(t for _, t in g).most_common(1)[0]
                odd += [(f, t, best) for f, t in g if t != best]
            pct = 100 * len(odd) / total if total else 0
            print(f"\nscale ×{scale}: {len(groups)} runs, {total} frames, "
                  f"{len(odd)} disagree with their run ({pct:.1f}%)")
            for f, got, best in odd[:args.show]:
                print(f"   {f.name}\n     read  {got[:96]}\n"
                      f"     modal {best[:96]}")
    finally:
        ocr.kill()


# ----------------------------------------------------------------- policy
def emissions(texts, policy, dedupe=0.9):
    """What a stabilization policy would hand downstream, in order.

    The screen holds ONE line, so anything past the first emission is a
    line spoken twice. `consecutive` accepts a read once the frame before
    it agreed — today's rule, and two identical misreads in a row are
    enough. `consensus` keeps the last three reads and accepts the text at
    least two of them agree on, which a misread has to win twice inside a
    sliding window to do.
    """
    out, prev, window = [], None, []
    for t in texts:
        take = None
        if policy == "consecutive":
            if t == prev:
                take = t
            prev = t
        else:
            window = (window + [t])[-3:]
            text, n = Counter(window).most_common(1)[0]
            if n >= 2:
                take = text
        if take and not (out and difflib.SequenceMatcher(
                None, out[-1], take).ratio() >= dedupe):
            out.append(take)
    return out


def policy(args):
    frames = corpus_frames(args.corpus)
    ocr = make_ocr()
    try:
        reads = list(read_frames(frames, args.game, args.scale[0], ocr,
                                 args.roi))
    finally:
        ocr.kill()
    groups = runs_of(reads)
    print(f"{len(groups)} runs of a held line — each SHOULD emit once\n")
    for name in ("consecutive", "consensus"):
        per_run = [len(emissions([t for _, t in g], name)) for g in groups]
        extra = sum(max(0, n - 1) for n in per_run)
        print(f"{name:12} emissions per run {per_run}  "
              f"→ {extra} line(s) that would be read again")
        if args.show:
            for g, n in zip(groups, per_run):
                if n > 1:
                    for e in emissions([t for _, t in g], name)[:args.show]:
                        print(f"     {e[:100]}")


# --------------------------------------------------------------- accuracy
def accuracy(args):
    corpus = Path(args.corpus)
    truth_path = corpus / "truth.json"
    if not truth_path.exists():
        sys.exit(f"{truth_path} missing — accuracy needs typed ground truth "
                 f"(stability does not)")
    truth = json.loads(truth_path.read_text())
    frames = [corpus / name for name in sorted(truth)]
    missing = [f.name for f in frames if not f.exists()]
    if missing:
        sys.exit(f"truth.json names frames that aren't here: {missing[:3]}")
    ocr = make_ocr()
    try:
        for scale in args.scale:
            exact = 0
            errs = []
            for f, got, _ in read_frames(frames, args.game, scale, ocr,
                                         args.roi):
                want = truth[f.name]
                if norm(got) == norm(want):
                    exact += 1
                else:
                    errs.append((f, got, want, cer(got, want)))
            n = len(frames)
            mean_cer = sum(e[3] for e in errs) / n if n else 0
            print(f"\nscale ×{scale}: {exact}/{n} exact "
                  f"({100 * exact / n:.0f}%), mean CER {100 * mean_cer:.2f}%")
            for f, got, want, c in sorted(errs, key=lambda e: -e[3])[:args.show]:
                print(f"   {f.name}  CER {100 * c:.0f}%\n"
                      f"     read {got[:96]}\n     true {want[:96]}")
    finally:
        ocr.kill()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="frames from a session recording")
    e.add_argument("recording")
    e.add_argument("--out", required=True)
    e.add_argument("--fps", default="1")
    e.add_argument("--start", type=float, default=0.0)
    e.add_argument("--duration", type=float, default=0.0)
    e.set_defaults(func=extract)

    c = sub.add_parser("capture", help="frames from the LIVE capture file")
    c.add_argument("--out", required=True)
    c.add_argument("--seconds", type=float, default=60)
    c.add_argument("--frame", default=str(ROOT / "captures" / "live_frame.jpg"))
    c.set_defaults(func=capture)

    for name, fn in (("stability", stability), ("accuracy", accuracy),
                     ("policy", policy)):
        p = sub.add_parser(name)
        p.add_argument("corpus")
        p.add_argument("--game", default="genshin")
        p.add_argument("--scale", type=int, action="append", default=[])
        p.add_argument("--show", type=int, default=6,
                       help="worst N examples to print")
        p.add_argument("--roi", default=None,
                       help="crop before reading: y0,y1 normalized "
                            "(bottom-left origin), e.g. 0,0.45")
        p.set_defaults(func=fn)

    args = ap.parse_args()
    if getattr(args, "scale", None) == []:
        args.scale = [1]
    if getattr(args, "roi", None):
        y0, y1 = (float(v) for v in args.roi.split(","))
        args.roi = (0.0, y0, 1.0, y1)
    args.func(args)


if __name__ == "__main__":
    main()
