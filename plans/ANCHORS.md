# Phase 4 — UI anchors and ROI profiles

Companion to [OCR-INTEGRATION-PLAN.md](OCR-INTEGRATION-PLAN.md) phase 4, which
says this phase earns its own doc when started. This is that doc: the design,
the coordinate-space gotcha table, and the sequencing with the evidence gates
between stages.

## Why this phase got promoted from "optional"

The plan called phase 4 optional — weigh it against hand-calibrating the last
screens. Three data points since have tipped the scale:

- The world-dialogue bug (0.10.2): a fixed Y band missed a real layout by
  **0.0003**. The band was measured carefully and was still wrong, because a
  second layout existed that the calibration capture never showed.
- Two more screens (readable articles, world dialogue) each needed a fresh
  round of hand-measured bands, a calibration capture, and a release.
- Every band in `tools/profiles/genshin.py` is a number defending against a
  specific failure. That knowledge doesn't transfer: the next screen starts
  from zero.

Anchors don't replace the bands — they replace the *screen identification*
those bands currently do double duty for, and they buy ROI cropping, which is
the real detector-cost lever on the Windows box (~554ms/frame RapidOCR there;
detector cost scales with area).

## What an anchor is

A small grayscale template of game *chrome* — an icon the game draws
pixel-identically on every frame of a given screen kind: Star Rail's ✕-circle
next to `Continue`, Genshin's auto-play toggle. Matched by normalized
cross-correlation (NCC) inside a small, fixed search region on a half-scale
grayscale decode of the frame (the same draft-mode decode the change gate
uses, ~960px wide, a few ms).

Chrome icons, not text. OCR already reads the text — `trusts_dialogue` is
text-anchoring — and an anchor that needs OCR can't run *before* OCR, which
is where it has to sit to pay for ROI cropping. The icon is also stabler than
its label: Vision returns `Continue`, `✕ Continue`, `Continue e` for the same
chrome, while the pixels of the glyph don't jitter.

Anchor data lives under `tools/profiles/anchors/`:

```
anchors/
  hsr.json          one spec per game: anchors, cut rects, search regions,
  genshin.json      thresholds, ROIs — pure numbers, facts about layout
```

**Template PNGs do not ship** (2026-08-13): they are crops of the games' own
chrome — the one game-derived binary the repo ever carried — so the spec now
ships the `cut` rect instead and the pack **self-calibrates**: live.py cuts
the template from the user's own capture on the first BOOT_HOLD consecutive
frames where the classifier trusts the game's dialogue chrome (the same
OCR-text ground truth the thresholds here were measured against), verifies
the cut against a later trusted frame at the spec threshold — a fade or
motion-blurred cut fails the verify and is thrown away — and persists it to
`captures/anchors/<game>/<name>.png` with a ref sidecar. Validated on the
regression recordings: self-cut templates score 0.985+ on their own game's
later frames and ≤0.47 cross-game, the same margins as the hand-measured
originals; both replays self-calibrate at 1.00 and read identically.
Replay runs bootstrap into their throwaway state dir, so they exercise the
path every run without touching the user's templates. One loose coupling
to know about: the cut's pixels come from the change gate's decode of the
frame file, while the trust verdict comes from the OCR daemon's read of
it — under capture load ffmpeg can rewrite the file between the two, so
cut and verdict can be one frame apart. The verify-against-a-later-frame
step is what makes that safe rather than wrong: a cut from a frame the
verdict didn't describe fails the verify and is retried.

A template records the *reference geometry* it was cut at (frame width/height
at half scale, in the user-dir sidecar) so a capture at a different
resolution is detected rather than silently mis-matched — see the gotcha
table.

## Coordinate spaces — the gotcha table

Three coordinate conventions meet in this feature. Every one of these has
already cost someone a debugging session somewhere in this repo; write the
conversion once, in `tools/anchors.py`, and nowhere else.

| Space | Origin | Units | Used by |
|---|---|---|---|
| Vision-normalized | bottom-left | 0–1 | OCR daemons, classify, profiles, `shots/*.json` |
| Image pixels | top-left | px | PIL/numpy, templates, NCC |
| Crop-normalized | bottom-left | 0–1 *of the crop* | daemon output when handed a cropped frame (phase b) |

- **Y flips between the first two.** `py = (1 − (y + h)) · H` for a top edge.
  The change gate's `_box()` is the reference implementation.
- **The daemons normalize to whatever image they're handed.** Hand them a
  crop and every returned box is normalized to the *crop*. The remap back is
  `x_full = cx0 + x_crop · cw`, `y_full = cy0 + y_crop · ch` where
  `(cx0, cy0, cw, ch)` is the crop rect in full-frame Vision-normalized
  space; `w`, `h` scale by `cw`/`ch`. classify() must never see
  crop-normalized coordinates — the remap happens in live.py at the OCR call
  boundary, so everything downstream is untouched.
- **No daemon protocol change in phase (a) or (b).** The line protocol is
  `path in → JSON out`; a crop is just a different path (written to the state
  dir like `live_frame.jpg` is). The protocol only changes if crops-by-rect
  ever move in-process — not planned.
- **Resolution is an assumption, not a fact.** Everything is calibrated at
  1920×1080 (replay re-scales to 1920; capture negotiates it). Templates are
  cut from half-scale decodes of 1080p frames. anchors.py compares the
  decoded frame's size against the template's recorded reference and *stands
  down* (no match attempted, logged once) on mismatch rather than matching at
  the wrong scale — NCC across scales fails quietly with mid scores, and a
  mid score against a fixed threshold is exactly the kind of coin-flip this
  repo's rules exist to prevent.
- **JPEG draft decode rounds dimensions.** `draft("L", …)` at scale 2 on
  1920×1080 yields 960×540, but other source sizes can round oddly. Search
  regions are normalized and converted per-frame, so rounding costs at most a
  pixel of search margin — pad search regions by the template size, not by
  guesswork.

## Matching — semantics that must hold

- **Absence of an anchor is weak evidence; presence is strong.** Motion blur,
  a fade, or the capture card's chroma subsampling can dent a match score for
  a frame or two. Nothing downstream may ever *drop* a line because an anchor
  went missing — anchors gate *cost* (where to OCR), never *speech*. The
  full-frame fallback is the load-bearing rule: no match → today's behavior,
  full frame, every band active.
- **Force a full-frame OCR every N seconds regardless.** The change gate
  needed `MAX_SKIP_RUN` because a wrong "unchanged" latches; a wrong "crop
  here" latches the same way — text appearing outside the crop is invisible,
  and nothing inside the crop will ever disagree. Same medicine: a bounded
  run (`ANCHOR_MAX_CROP_RUN`, ~2s of frames), then one full-frame read to
  re-arm. The failure mode was paid for once already; don't rediscover it.
- **Anchors run on fresh-OCR frames only.** A gate-unchanged frame replays
  the previous blocks — the screen provably didn't change where text was, and
  re-matching anchors on it buys nothing.
- **Threshold per anchor, measured not chosen.** Stage (a) exists to produce
  the score distributions; the threshold goes in the spec file next to the
  measurement that justified it, like every band in the profiles.

## Sequencing

### (a) Anchors as log-only evidence — changes nothing

`tools/anchors.py` + packs for both games (HSR: ✕-Continue glyph; Genshin:
auto-play toggle). live.py matches on fresh-OCR frames and logs
`[anchors] name=score…` whenever the *set of matched anchors* changes, plus
an `anchor_ms` stat. No decision reads the result. `settings.anchors: false`
turns it off.

Trust gate to pass before (b): over replayed HSR recordings, on frames where
the classifier itself trusted dialogue chrome (`trusts_dialogue` true on the
OCR text), the continue-anchor must agree ≳99%; on overworld/menu frames it
must stay silent; `anchor_ms` must stay single-digit on this Mac.

#### Measured — 2026-08-09, this Mac

Corpus: 960 HSR frames (two recordings, 2 fps, dialogue + overworld) and
600 Genshin frames (the 0.10.0 regression recording), ground truth derived
per frame by running ocrd + both profiles' `trusts_dialogue` on the text.

- **`hsr.continue`**: on the 819 frames the classifier trusted, scores were
  min 0.981 / median 0.996 — **819/819 over the 0.75 threshold**. On the 141
  frames it didn't, max 0.449. The gap the threshold sits in is ±0.27 wide
  on either side.
- **`genshin.auto`**: median 0.997 on dialogue frames; 451/534 over
  threshold. The 83 below it are **choice-prompt frames — the game hides
  the Auto/Confirm chrome while a prompt is up** (already documented in the
  profile) — plus fades. The 3 frames scoring ≥0.95 where the classifier
  said *not* dialogue were mid-fade frames with the chrome fully drawn and
  no text yet: the anchor was right and the OCR-text ground truth was
  blind. Both directions confirm the design rule: presence is strong,
  absence is weak.
- **Cross-game rejection**: `hsr.continue` ≤0.347 on every Genshin frame —
  including nine narration cards whose *text* says Continue (0.247; the
  glyph is a different drawing, which is the point of matching pixels).
  `genshin.auto` ≤0.468 on every HSR frame.
- **Cost**: 4.4–4.8 ms/frame including the half-scale decode, against a
  budget of single-digit ms. `anchor_ms` on the dashboard metrics carries
  this forward.
- Both replays (HSR and Genshin, 40 s each through `tools/replay.py`) read
  every line exactly as before, with `[anchors]` lines appearing on the
  expected screens.

A third anchor was tried and rejected: Genshin's per-option choice glyph
(the chat-bubble pill). A 15px bubble template matched round bright scenery
(negatives to 0.886); widening it to bubble-plus-pill-cap separated the
negatives (max 0.616) but the *positives* fell to min 0.387 — the pill's
rendering varies with hover state and option wrap. A 7-option choice-stack
prompt WAS captured and measured (rec_20260809_143259; its row geometry
lives in genshin.py's CHOICES comment), but the recording is no longer in
the configured recordings_dir — so a re-cut needs either that file
restored or a fresh 3+ option capture. Two rounds of anchor work
(2026-08-12, 2026-08-13) have since passed without taking this up; treat
it as parked until a choice-anchor win is actually wanted, not as
pending. The choice-prompt case stays covered by OCR text, as today.

### (b) ROI cropping — on by default since 2026-08-13

`settings.anchor_roi` (default true; `false` restores full-frame OCR): when
the matched anchor set implies a screen kind, crop the frame to that kind's
ROI (from the spec file), hand the crop path to the daemon, remap boxes back
to full-frame normalized space. Full-frame fallback when no anchor matches,
plus the bounded crop-run above.

The ROI is the union of every band the profile needs for that screen kind —
plate, dialogue, choices, hint strip, UID corner — not just the dialogue
band. For Genshin dialogue that union is roughly the bottom 62% of the frame:
the honest expectation was a ~35–40% detector-cost cut, not the "well under
100ms" the original plan sketch hoped — and the Windows measurement landed
at ~42% (done 2026-08-13; numbers in the Implemented block below).

Trust gate before defaulting on — BOTH HALVES PASSED, retired 2026-08-13:
the Mac replay half passed as the honest gate (see below on why
byte-identity was the wrong bar), the Windows `ocr_ms` half passed in the
09:56 session.

#### Implemented — 2026-08-12

- ROI values are band unions read off the profiles, not guesses.
  HSR `continue` → `y [0, 0.62]`, full width: bottom hint/UID strip
  (y<0.08), dialogue fallback (0.08–0.21), plate (0.18–0.31), choices
  (0.22–0.62 ceiling). Genshin `auto` → `y [0, 0.66]`, full width: hint
  strip (0–0.10), dialogue (0.10–0.21), plate (0.204–0.28), comms plate
  band, choices (0.22–0.66 ceiling). Both are "the bottom two-thirds",
  which is where the ~35–40% detector-cut expectation comes from.
- The crop is written as PNG (`captures/live_crop.png`,
  `compress_level=1`): the frame is already one JPEG generation old, and
  a second lossy pass softens exactly the small glyphs the crop exists
  to read. `crop_frame()` re-normalizes the returned rect from the
  PIXEL crop, so `remap_box()` is exact under `int()` edge rounding —
  pinned in `tools/test_anchors.py`.
- Anchor matching moved BEFORE the OCR call (it has to be, to pay for
  cropping) and keys off the STICKY game profile, not the fresh
  classify: during a game switch the old game's chrome stops matching,
  so the frames the switch decision needs are read whole.
- An empty CROPPED read does not count as a `lost_frames` torn frame —
  the crop was cut from a verified-complete JPEG, so `[]` is a
  genuinely empty ROI (fade, chrome-before-text). It still short-
  circuits the frame like an empty full read always has.
- `ANCHOR_MAX_CROP_RUN = 12` (~2s at 6fps), same number and same reason
  as the change gate's `MAX_SKIP_RUN`: a wrong "crop here" must be
  bounded, not latched. `roi_crops` on the dashboard metrics carries
  the skip volume.
- Replay trust gate (this Mac): **"byte-identical" turned out to be the
  wrong bar for this harness, and the honest gate passed instead.**
  Wall-clock replay is not deterministic: two runs with the setting OFF
  (same file, same seed, rec_20260812_083939 110–150s Genshin and
  rec_20260727_174535 110–150s HSR) flip the same marginal lines the
  on-vs-off comparison flips — a spoke-then-yielded vs skipped-as-voiced
  Paimon line, a sentence-streaming split point, ±0.3dB on every audio
  gate reading, differing `voiced_history` — because the VAD gate reads
  the audio bed on wall-clock time, and the bed carries the original
  session's TTS (the replay.py caveat). The gate that means something:
  every on-vs-off difference site also differs off-vs-off. That held.
  The single crop-specific artifact outside the noise floor was Vision
  reading one line's mid-sentence punctuation differently on the crop
  ("Here we are." vs "Here we are:") — normalize_text erases it for
  dedupe and both runs skipped the line as voiced. The Windows `ocr_ms`
  half of the gate **passed 2026-08-13** (09:56 session log): anchors
  self-calibrated on the first dialogue (`auto=1.00`), 530 crops,
  `ocr_avg_ms` 321 against the ~554 dialogue baseline — ~42% off, in
  the predicted 35–40% band — zero lost frames, and the four misses in
  that session were all audio-gate (center-energy), not detection.
  `anchor_roi` defaults ON as of that date.

### (c) A screen ships as data

The original candidate is gone: the book/inventory reading UI shipped as
hand-written profile code (`READABLE_*` in `tools/profiles/genshin.py`,
pinned by `tools/test_genshin_readable.py`) before this stage got to it —
the second time a screen has outrun the anchors path. 4c now waits for the
next screen either game adds: when one appears, build it as an anchor pack
+ ROI + bands in the spec file, from captures, with no new detector code in
the profile. That remains the success criterion for the phase — a new
screen becomes a capture session and a JSON edit, not a release. If the
games stop adding screens first, 4c retires with nothing lost: (a) and (b)
carry the ROI cost win on their own.

## Rejected along the way

- **OCR-text anchors** ("look for the word Continue"): already exists as
  `trusts_dialogue`; runs after OCR so it can't cut OCR cost; and the text
  jitters where the icon doesn't.
- **Whole-frame NCC per anchor**: cost scales with frame area × anchor
  count; the search region is what keeps matching a few ms. Anchors are
  chrome — chrome doesn't move, so a small region loses nothing.
- **OpenCV**: `cv2.matchTemplate` would be convenient, but it's a heavy
  dependency for 3–5 small correlations per frame that numpy does in
  milliseconds, and the Windows install is already the fragile one.
- **Matching on the full-resolution frame**: the change gate already
  established that half-scale keeps glyph-level structure (139–232 bright
  pixels per dialogue row at 1/2, 2–8 at 1/4); anchors are bigger than
  glyphs, and half-scale halves the correlation cost fourfold.
