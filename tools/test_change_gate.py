"""Pins the change-gate invariants — synthetic frames, no hardware, ~1s.

The invariants matter more than the numbers: a false "unchanged" swallows
a line, so every ambiguous situation must come back "changed" (= run OCR,
yesterday's behavior). Run directly or under pytest:

    python tools/test_change_gate.py
"""
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np                             # noqa: E402
from PIL import Image, ImageDraw               # noqa: E402
from change_gate import ChangeGate             # noqa: E402

W, H = 1920, 1080


def draw_text(img, xy, text, scale=2):
    """Game-sized text: PIL's default bitmap font is ~11px, half the height
    of real HSR dialogue, so render it small and paste it upscaled — the
    thick blocky strokes survive JPEG + the gate's half-scale decode the
    way real game glyphs do (measured: a real dialogue row keeps ~150+
    bright pixels at half scale)."""
    w = int(len(text) * 7 * 1.2) + 8
    pad = Image.new("L", (w, 16), 0)
    ImageDraw.Draw(pad).text((2, 2), text, fill=255)
    big = pad.resize((pad.width * scale, pad.height * scale), Image.NEAREST)
    img.paste((245, 245, 245), (xy[0], xy[1],
                                xy[0] + big.width, xy[1] + big.height), big)


def make_frame(path, text="Some dialogue line.", bg=30, noise_seed=None,
               extra=None, truncate=False):
    """Game-like frame: light text near the dialogue band over a dark,
    optionally noisy (=animated) background."""
    rng = np.random.default_rng(noise_seed if noise_seed is not None else 0)
    arr = np.full((H, W), bg, dtype=np.uint8)
    if noise_seed is not None:                  # "animated world": dark noise
        arr = np.clip(arr + rng.integers(0, 60, (H, W)), 0, 120
                      ).astype(np.uint8)
    img = Image.fromarray(arr).convert("RGB")
    draw_text(img, (760, 180), "Sparxie")
    draw_text(img, (650, 230), text)
    if extra:
        draw_text(img, extra[0], extra[1])
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    data = buf.getvalue()
    if truncate:
        data = data[: len(data) // 2]           # torn mid-rewrite
    with open(path, "wb") as f:
        f.write(data)


# blocks as the daemon reports them: normalized, bottom-left origin
BLOCKS = [
    {"text": "Sparxie", "confidence": 0.98,
     "x": 760 / W, "w": 80 / W, "y": 1 - 200 / H, "h": 20 / H},
    {"text": "Some dialogue line.", "confidence": 0.98,
     "x": 650 / W, "w": 400 / W, "y": 1 - 250 / H, "h": 20 / H},
]


def run():
    tmp = tempfile.mkdtemp()
    frame = os.path.join(tmp, "live_frame.jpg")

    # 1. no baseline yet → changed (must OCR)
    g = ChangeGate()
    make_frame(frame)
    assert not g.unchanged(frame, BLOCKS), "first frame must run OCR"

    # 2. identical frame → unchanged
    assert g.unchanged(frame, BLOCKS), "identical frame must be gated"
    assert g.skips == 1

    # 3. background animates, text static → still unchanged (masked diff)
    make_frame(frame, noise_seed=1)
    g2 = ChangeGate()
    assert not g2.unchanged(frame, BLOCKS)      # baseline
    make_frame(frame, noise_seed=2)
    assert g2.unchanged(frame, BLOCKS), \
        "dark-pixel background animation must not defeat the gate"

    # 4. the text itself changes → changed
    make_frame(frame, text="A different line entirely.", noise_seed=2)
    assert not g2.unchanged(frame, BLOCKS), "text change must run OCR"

    # 5. new text appears BELOW (typewriter wrapping a new row, inside the
    #    bottom padding) → changed even though old text is untouched
    g3 = ChangeGate()
    make_frame(frame)
    g3.unchanged(frame, BLOCKS)
    assert g3.unchanged(frame, BLOCKS)
    make_frame(frame, extra=((650, 262), "and a wrapped second row"))
    assert not g3.unchanged(frame, BLOCKS), \
        "new row under the line must open the gate"

    # 6. torn frame → changed (OCR daemon owns the retries), and the stale
    #    baseline is dropped so the next complete frame re-baselines
    g4 = ChangeGate()
    make_frame(frame)
    g4.unchanged(frame, BLOCKS)
    make_frame(frame, truncate=True)
    assert not g4.unchanged(frame, BLOCKS), "torn frame must not be gated"
    make_frame(frame)
    assert not g4.unchanged(frame, BLOCKS), \
        "first complete frame after a tear re-baselines, not skips"

    # 7. block geometry moved (new line, new union box) → changed
    g5 = ChangeGate()
    make_frame(frame)
    g5.unchanged(frame, BLOCKS)
    moved = [dict(b, y=b["y"] - 0.1) for b in BLOCKS]
    assert not g5.unchanged(frame, moved), "moved box must re-baseline"

    # 8. disabled gate never claims unchanged
    g6 = ChangeGate(enabled=False)
    make_frame(frame)
    g6.unchanged(frame, BLOCKS)
    assert not g6.unchanged(frame, BLOCKS)

    # 9. empty/None blocks → changed (nothing to compare against)
    g7 = ChangeGate()
    assert not g7.unchanged(frame, [])
    assert not g7.unchanged(frame, None)

    print("test_change_gate: all invariants hold")


def test_change_gate():                         # pytest entry point
    run()


if __name__ == "__main__":
    run()
