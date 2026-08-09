#!/usr/bin/env python3
"""UI anchors: find game chrome by pixels, before (and without) OCR.

An anchor is a small grayscale template of chrome the game draws
pixel-identically on every frame of a screen kind — Star Rail's ✕-circle
next to 'Continue', Genshin's auto-play toggle. It is matched by
normalized cross-correlation inside a small fixed search region on a
half-scale grayscale decode of the frame (the same draft-mode decode the
change gate uses). Design and the coordinate-space gotcha table:
plans/ANCHORS.md.

Phase (a): matches are log-only evidence. Nothing downstream reads them.
Presence of an anchor is strong evidence; absence is weak (motion blur or
a fade dents a score for a frame) — anchors may gate COST, never speech.

Spec file, one per game (tools/profiles/anchors/<game>.json):

    {"anchors": [{"name": "continue",
                  "template": "hsr/continue.png",
                  "search": {"x": [0.86, 1.0], "y": [0.0, 0.10]},
                  "threshold": 0.75,
                  "ref": [960, 540]}]}

`search` is Vision-normalized (origin bottom-left, 0-1) like every band
in tools/profiles/. `ref` is the half-scale decode size the template was
cut at; a frame decoding to a different size stands the anchor down
rather than matching at the wrong scale — NCC across scales fails
quietly with mid scores, and a mid score against a threshold is a
coin-flip.

CLI:
    python tools/anchors.py extract <game> <name> <frame.jpg> x0 x1 y0 y1
        cut a template from a frame (region Vision-normalized); pads the
        search region by the template size and writes/updates the spec
    python tools/anchors.py match <game> <frame.jpg> [...]
        print scores for every anchor against the frame(s)
"""
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ANCHOR_DIR = Path(__file__).resolve().parent / "profiles" / "anchors"
DRAFT_SCALE = 2          # same half-scale draft decode as the change gate
# Search regions are padded by this much of the template's own size on
# each side at extract time, so chrome that shifts a few pixels between
# sessions (aspect letterboxing, capture cropping) stays inside the box.
SEARCH_PAD = 1.0


def decode_half(path_or_bytes):
    """Half-scale grayscale decode, or None for a torn/partial JPEG.
    Same contract as the change gate's _decode: None means 'can't judge',
    never 'empty screen'."""
    data = (path_or_bytes if isinstance(path_or_bytes, bytes)
            else Path(path_or_bytes).read_bytes())
    if not (len(data) > 1024 and data[:2] == b"\xff\xd8"
            and data[-2:] == b"\xff\xd9"):
        return None
    img = Image.open(io.BytesIO(data))
    img.draft("L", (max(1, img.width // DRAFT_SCALE),
                    max(1, img.height // DRAFT_SCALE)))
    return np.asarray(img.convert("L"), dtype=np.float32)


def _to_px(region, W, H):
    """Vision-normalized region → pixel rect (x0, y0, x1, y1), top-left
    origin. The Y flip: normalized y is measured up from the bottom."""
    (nx0, nx1), (ny0, ny1) = region["x"], region["y"]
    return (max(0, int(nx0 * W)), max(0, int((1.0 - ny1) * H)),
            min(W, int(nx1 * W)), min(H, int((1.0 - ny0) * H)))


def _ncc(window, tmpl):
    """Peak normalized cross-correlation of tmpl over window, and where.
    Plain numpy sliding windows: regions are small (a few thousand
    positions), so this stays a few ms without OpenCV."""
    th, tw = tmpl.shape
    wh, ww = window.shape
    if wh < th or ww < tw:
        return -1.0, (0, 0)
    t = tmpl - tmpl.mean()
    tn = np.sqrt((t * t).sum())
    if tn < 1e-6:
        return -1.0, (0, 0)          # flat template matches anything
    views = np.lib.stride_tricks.sliding_window_view(window, (th, tw))
    v = views - views.mean(axis=(2, 3), keepdims=True)
    denom = np.sqrt((v * v).sum(axis=(2, 3))) * tn
    with np.errstate(invalid="ignore", divide="ignore"):
        scores = np.where(denom > 1e-6,
                          (v * t).sum(axis=(2, 3)) / denom, -1.0)
    idx = np.unravel_index(np.argmax(scores), scores.shape)
    return float(scores[idx]), (int(idx[1]), int(idx[0]))


def remap_box(block, crop):
    """A daemon box normalized to a CROP → full-frame normalized.
    `crop` is (cx0, cy0, cw, ch) in full-frame Vision space. The daemons
    normalize to whatever image they are handed, so every box that came
    from a cropped frame must pass through here before classify() sees
    it. Pinned by tools/test_anchors.py."""
    cx0, cy0, cw, ch = crop
    out = dict(block)
    out["x"] = cx0 + block["x"] * cw
    out["y"] = cy0 + block["y"] * ch
    out["w"] = block["w"] * cw
    out["h"] = block["h"] * ch
    return out


class Anchor:
    def __init__(self, name, template, search, threshold, ref):
        self.name = name
        self.template = template          # float32 gray, half-scale px
        self.search = search              # Vision-normalized region
        self.threshold = float(threshold)
        self.ref = tuple(ref)             # (W, H) the template was cut at
        self.scale_warned = False

    def match(self, gray):
        """(score, matched) against a half-scale gray frame. A frame at a
        different decode size than the template's reference stands down
        (score -1) instead of matching at the wrong scale."""
        H, W = gray.shape
        if (W, H) != self.ref:
            return -1.0, False
        x0, y0, x1, y1 = _to_px(self.search, W, H)
        score, _ = _ncc(gray[y0:y1, x0:x1], self.template)
        return score, score >= self.threshold


class AnchorPack:
    """Every anchor for one game, or an empty pack if none are defined —
    a game without anchor data must behave exactly as before."""

    def __init__(self, game):
        self.game = game
        self.anchors = []
        spec = ANCHOR_DIR / f"{game}.json"
        if not spec.exists():
            return
        for a in json.loads(spec.read_text()).get("anchors", []):
            png = ANCHOR_DIR / a["template"]
            tmpl = np.asarray(Image.open(png).convert("L"), dtype=np.float32)
            self.anchors.append(Anchor(a["name"], tmpl, a["search"],
                                       a["threshold"], a["ref"]))

    def match(self, gray):
        """{name: score} for matched anchors only. `gray` from
        decode_half(); None (torn frame) matches nothing."""
        if gray is None:
            return {}
        out = {}
        for a in self.anchors:
            score, ok = a.match(gray)
            if ok:
                out[a.name] = score
        return out


# ---------------------------------------------------------------------
# CLI: template extraction and offline matching
# ---------------------------------------------------------------------

def _extract(game, name, frame, nx0, nx1, ny0, ny1):
    gray = decode_half(frame)
    if gray is None:
        sys.exit(f"can't decode {frame}")
    H, W = gray.shape
    x0, y0, x1, y1 = _to_px({"x": (nx0, nx1), "y": (ny0, ny1)}, W, H)
    tmpl = gray[y0:y1, x0:x1]
    out = ANCHOR_DIR / game
    out.mkdir(parents=True, exist_ok=True)
    png = out / f"{name}.png"
    Image.fromarray(tmpl.astype(np.uint8)).save(png)
    # search region: the extraction region padded by the template's own
    # size, so chrome that shifts a few px between sessions stays inside
    pw, ph = (nx1 - nx0) * SEARCH_PAD, (ny1 - ny0) * SEARCH_PAD
    search = {"x": [round(max(0.0, nx0 - pw), 4),
                    round(min(1.0, nx1 + pw), 4)],
              "y": [round(max(0.0, ny0 - ph), 4),
                    round(min(1.0, ny1 + ph), 4)]}
    spec_path = ANCHOR_DIR / f"{game}.json"
    spec = (json.loads(spec_path.read_text()) if spec_path.exists()
            else {"anchors": []})
    spec["anchors"] = [a for a in spec["anchors"] if a["name"] != name]
    spec["anchors"].append({"name": name, "template": f"{game}/{name}.png",
                            "search": search,
                            "threshold": 0.75,     # placeholder — measure!
                            "ref": [W, H]})
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"{png} {tmpl.shape[1]}x{tmpl.shape[0]}px search={search}"
          f" — threshold is a PLACEHOLDER; measure score distributions"
          f" (tools/anchors.py match) before trusting it")


def _match_cli(game, frames):
    pack = AnchorPack(game)
    if not pack.anchors:
        sys.exit(f"no anchor pack for {game}")
    for f in frames:
        gray = decode_half(f)
        if gray is None:
            print(f"{f}: torn/undecodable")
            continue
        scores = {a.name: a.match(gray)[0] for a in pack.anchors}
        print(f"{f}: " + "  ".join(f"{n}={s:.3f}" for n, s in scores.items()))


if __name__ == "__main__":
    if len(sys.argv) >= 9 and sys.argv[1] == "extract":
        _extract(sys.argv[2], sys.argv[3], sys.argv[4],
                 *map(float, sys.argv[5:9]))
    elif len(sys.argv) >= 4 and sys.argv[1] == "match":
        _match_cli(sys.argv[2], sys.argv[3:])
    else:
        sys.exit(__doc__)
