# OCR/Vision Optimization — Integration Plan

Companion to `plans/OCR-VISION-RESEARCH.md` (2026-08-04). Grounded in the current code: the main loop in `live.py` (mtime check → `ocr.recognize` → reader-panel branch → `classify()` → candidate/`STABLE_READS` stabilization → dedupe → speak), `tools/ocrd_win.py` / `tools/ocrd.swift` daemons, and `tools/classify.py`.

Ground rules: every phase lands as its own branch → main, validated through `tools/replay.py` on the regression recordings (and the sandbox frame-corpus diff for OCR-level changes) BEFORE hardware testing. Fix in the repo, push, pull on the Windows box — never hand-edit there. Version bump in `tools/webui.py` + CHANGELOG per release.

## Status (2026-08-08)

**Phases 0–3 shipped in 0.7.3.** The English recognition model, the pixel change
gate (`tools/change_gate.py`, pinned by `tools/test_change_gate.py`) and
confidence-aware stabilization are all in `main`; the changelog entry for 0.7.3
carries the measured results and the two mistakes the gate design had to survive
(watching every block on the frame instead of the line's own, and averaging the
diff instead of counting moved bright pixels). Baseline numbers are below.

**Phase 4 is next and is the large one.** Genshin support arrived ahead of it
in 0.7.0 as hand-written geometry in `tools/profiles/genshin.py` rather than as
anchor data, so phase 4's framing has shifted: it is no longer the enabler for
Genshin, it is what would make the *remaining* Genshin screens (the book /
reading UI) captures rather than code, and what would cut OCR cost by cropping
to a band. Weigh it against just calibrating the last screens by hand.

**Phase 5 stays blocked** on datamined text that cannot ship in a public repo.

**Phase 6** hasn't been needed; labelling by hand hasn't become annoying enough.

**Two research items were already built before this plan** and the phases below
account for it: `repair_runons`/`text_quality` in `live.py` do wordfreq-based
fusion splitting and best-variant voting (research #6), and the loop already
skipped unchanged *mtimes*.

## Phase 0 — Baseline (half a session)

Before touching anything, capture numbers to beat, from replay runs over the regression corpus: `stats["ocr_ms"]` distribution, per-recording count of fusion-class defects (grep the transcript diff for splits `repair_runons` had to make — each one is a rec-model miss), time-from-first-read-to-spoken per line (stabilization latency), and lost-frame rate. Store the numbers in this file under a Baseline heading so later phases diff against them.

### Baseline — measured 2026-08-07, after the fact

This was skipped at the time and reconstructed afterwards, which changed what it can say. There is no "before" recording of Star Rail through the pre-branch code, so the corpus is instead a single Genshin conversation captured on the branch (`rec_20260807_223122.mp4`, 6m01s, 27 lines, Natlan world quest — Leyla and Paimon, no voice acting in the scene). Both sides replay the *same* file, so the comparison is like-for-like even though the absolute numbers are not the ones the plan imagined.

**Method.** `tools/replay.py` over frames 85–360s (the dialogue, excluding boot and loading), once against this branch and once against a worktree at plain `0.7.2`, same `voices.json`, wall-clock paced. Each line's spoken time is taken from when the decision printed. Gate behaviour is measured separately by running every frame through OCR as ground truth alongside the gate, and counting verdicts where "unchanged" hid a real change.

| | 0.7.2 | branch |
|---|---|---|
| lines spoken | 23 | 23 (identical text, line for line) |
| time-to-spoken, mean | — | **−0.12s** |
| time-to-spoken, median | — | −0.13s |
| best / worst line | — | −0.30s / +0.20s |
| OCR calls on 1650 frames | 1650 | **1274** (376 skipped, 23%) |
| stale gate verdicts | n/a | 4 in 1650 frames (0.2%) |

**Reading the numbers.** The confidence work (Phase 3) is worth about 120ms per line — real and consistent in sign (19 of 23 lines faster), but far smaller than the phase's framing implied, and small enough that it would be invisible by ear. The honest claim is "no slower, slightly faster, and no lines lost", not a latency win worth advertising.

The 23% skip rate is well under Phase 2's ≥60% target. That target assumed the gate could skip freely on static dialogue; two safety limits since imposed cost most of it — OCR is forced every 12 frames so a wrong verdict can't latch, and the gate is off entirely until a line is on screen, because a line *appearing* is invisible to something that only watches where text already was. Both were paid for by real defects, so the target is the thing that should move, not the limits.

**Caveats worth keeping attached to these numbers.** Measured on macOS, so OCR is Apple Vision: `ocr_ms` and the Windows rec-model fusion counts (Phase 1) are not measurable here and are not in the table. The replay's audio bed contains the original session's TTS, so its VAD gate decisions and yields are artifacts — equal on both sides, and the reason lines-spoken agrees despite the yields. One conversation is not a corpus; treat the direction as established and the magnitude as approximate.

## Phase 1 — PP-OCRv5 English rec model (Windows) — small, do first

`tools/ocrd_win.py`: let RapidOCR take a rec model override — `HOYOVOICE_REC_MODEL` env var or a `models/` path checked at startup — pointing at `en_PP-OCRv5_mobile_rec` in ONNX. Detector stays stock, so box geometry, the bottom-left-origin normalization, and `_flatten_background` are untouched; classify.py sees identical coordinates with better text. `setup.ps1` gains an optional model download step (HF: PaddlePaddle/en_PP-OCRv5_mobile_rec; ONNX conversions exist under monkt/paddleocr-onnx — verify opset compatibility with our pinned onnxruntime + DirectML first).

Validation is the established sandbox workflow: RapidOCR-CPU over the frame corpus, old-rec vs new-rec text through `classify()`, diff decisions. Success = fewer fusions ("fora" class) with zero classify regressions on 263 frames, and per-frame rec time within ~20% of current. If the v5 English model fights DirectML, fall back to en_PP-OCRv4 rec — still English-tuned.

Mac is untouched (Apple Vision stays the reference engine).

## Phase 2 — Pixel change gate on the text region (latency + CPU)

Today the loop OCRs every new frame mtime, and ffmpeg rewrites the frame continuously, so we pay 154ms (DirectML) or a Vision call at full loop rate even when the dialogue is static. A whole-frame diff would never report "unchanged" — the game world animates behind the text — so the gate must diff only where text was: the union bbox of `latest_ocr["blocks"]` from the previous read (padded a few %), grayscale, downscaled, mean-absolute-diff against the previous crop.

Semantics that must hold (this is the subtle part):

- **Unchanged ⇒ replay previous blocks, don't skip.** `candidate_count` counts *reads*; if we simply `continue`, stabilization stalls. On an unchanged gate, feed `latest_ocr["blocks"]` through the exact same downstream path as a fresh read. Same behavior, zero OCR cost.
- **Decode failure = torn frame** → existing `lost_frames` path, gate state untouched.
- **No previous blocks** (screen was empty / after reset) → gate open, full OCR.
- **Typewriter** changes the region every frame → gate passes everything during typing, which is correct; the "changed then stable" debounce falls out of the existing candidate logic, no new mechanism.
- Reader panels scroll → region changes → gate opens. The `qr_absent`/`READER_CLOSE_AFTER` logic keys on OCR results, which unchanged-replay still supplies, so panel-close detection is unaffected.

Implementation: pure function `frame_changed(prev_crop, new_crop) -> bool` + a small state holder, in live.py near `frame_is_dark()`; threshold in `voices.json` settings with a measured default; new stat (`gate_skips`) on the dashboard metrics so the win is visible. PIL decode+downscale is a few ms — budget ≤10ms for the whole gate. Unit-pin it like `tools/test_video_swap.py` does: synthetic frames, no hardware (`tools/test_change_gate.py`).

Expected: majority of OCR calls skipped during static dialogue → big CPU/GPU headroom drop on Windows, cooler Mac, less contention during recording (which is when torn frames spike).

## Phase 3 — Confidence-aware stabilization (small, after 2)

Both daemons already emit per-block confidence; stabilization ignores it. Two surgical uses, no rearchitecting:

1. `classify()` result carries `conf` = min confidence over the dialogue blocks (classify.py change + passthrough). In the `required` computation: a complete, non-growing read with conf ≥ 0.97 needs only `STABLE_READS` (or even `STABLE_READS - 1` with the change gate confirming a static region); conf < 0.85 adds one. The chat panel's "reads at 0.98+ once settled" observation says the signal is there.
2. Variant voting: `text_quality` remains primary (measured: majority voting picks wrong), confidence breaks ties.

Validate on replay over recordings that previously produced the phantom-nameplate and mid-fade-in bugs — this touches the same machinery. Watch stabilization latency drop against the Phase 0 baseline without new false fires.

## Phase 4 — UI anchors + ROI profiles (the Genshin enabler — biggest lift)

Goal: screen-mode detection and text ROIs become per-game *data*, not classify.py geometry code, so the pending Genshin profile is "capture some crops" instead of re-deriving layout heuristics.

Design sketch: `tools/anchors.py` with normalized cross-correlation (numpy; no OpenCV dep needed for 3–5 small anchors on a downscaled gray frame) matching per-game anchor crops — autoplay icon, dialogue-advance arrow, chat-panel chrome — stored under `profiles/<game>/` with a JSON mapping: anchor → search region → ROIs relative to the match. Which anchors matched tells us the screen kind (a cheap, OCR-free replacement for some chrome heuristics); the ROI then optionally *crops* the frame before OCR (write crop to the state dir, hand that path to the daemon, remap returned boxes into full-frame normalized coordinates so classify.py is unchanged). Cropping is also the real speed play: detector cost scales with area, so a dialogue-band crop should cut the 154ms DirectML time well under 100ms even before the change gate.

Sequencing inside the phase: (a) anchors as *additional evidence* only — surface matches in the log, change nothing; (b) once trusted on HSR recordings, enable ROI cropping behind a setting; (c) build the Genshin profile from Genshin captures. Full-frame fallback whenever no anchor matches, so unknown screens degrade to today's behavior. This phase gets its own plan doc when started — protocol change to the daemons and coordinate remapping deserve their own gotcha table.

## Phase 5 (experimental) — TextMap canonical-text snapping

The Genshin-Subtitles finding: they don't trust OCR output at all — they fuzzy-match it (n-gram index + Levenshtein) against the game's datamined TextMap (Dimbreath/AnimeGameData for Genshin; HSR equivalents exist) and display the *canonical* line. Adapted to us: after stabilization, snap the line to canonical text before synth. Every residual OCR defect disappears for matched lines, and a strong partial match could fire *before* the typewriter finishes — beating even sentence streaming on latency. Speaker names from the same data would harden `canon_sender` and speaker normalization.

Real constraints, hence experimental: datamined text cannot ship in the public repo (the language packs are fan-datamined; Genshin-Subtitles is Apache-2.0 but the *data* isn't theirs to license) — it must be a local-only optional asset like voices.json, seeded by the user; English TextMap is large, so the n-gram index needs a memory budget (their FNV-1a hashing approach is the reference); player-name interpolation (`{NICKNAME}` → the Trailblazer's nameplate) needs a template-aware matcher or those lines will never match exactly. Prototype offline first: run the matcher over replay transcripts and measure match rate + wrong-match rate before it goes anywhere near the live path. A wrong snap is worse than a fusion — it reads a *different* line confidently.

**Direction settled 2026-08-12 (OCR-stack review):** this phase is the agreed
next ceiling-raiser after 4b — it kills *all* residual OCR defects for matched
lines regardless of font, engine, or platform, where any recognizer-side work
only shrinks them. The "blocked on data" framing softens to "local-only
seeding by design": the user seeds the TextMap locally exactly like
voices.json, nothing ships in the repo, and the offline prototype
(matcher over existing replay transcripts, measuring match rate and
wrong-match rate) needs no live-path work at all. Also weighed and settled in
the same review: acquiring the Genshin font to "help OCR read". Neither
Apple Vision nor Windows.Media.Ocr is trainable, so the font buys nothing
there; fine-tuning the RapidOCR rec model on synthetic renders in the game
font is real but days of pipeline work, and the open Windows book-page bug
(`hum`/`Ium` rows) smells like detector/frame, not glyph shape — diagnosis
still waits on the Windows `captures/shots/*.json`. The font's cheap,
worthwhile use is a synthetic ground-truth eval corpus (phase 6's "labeled
corpus" without hand-labeling): render known lines in the real font at game
sizes over captured backgrounds, keep the font local-only (miHoYo/HanYi
license — never commit it). Fine-tune only if rec errors survive 4b + the
book-page diagnosis + TextMap snapping.

## Phase 6 (backlog) — Florence-2 as offline arbiter

Replay-harness-only: batch low-confidence lines from the regression corpus through Florence-2-base to auto-generate ground-truth labels, so Phases 1–5 get scored against labels instead of eyeballs. Never in the live path. Do whenever labeling by hand gets annoying.

## Order and expected wins

| Phase | Effort | Pain point hit | Success metric | Outcome |
|---|---|---|---|---|
| 0 baseline | 0.5 session | — | numbers recorded | **done** — reconstructed after the fact, see above |
| 1 rec model | small | word fusions | fusion count ↓, 0 classify regressions | **shipped 0.7.3** — 333 → 144 fusions on 81 shots, zero regressions |
| 2 change gate | medium | 154ms/frame burn, recording-load tearing | ≥60% OCR calls skipped on static dialogue | **shipped 0.7.3** — 23%, and the target was wrong (see Baseline) |
| 3 confidence | small | stabilization latency/stalls | time-to-spoken ↓, no new false fires | **shipped 0.7.3** — ~0.12s, no lines lost |
| 4 anchors/ROI | large | OCR speed, remaining Genshin screens, chrome heuristics | screens ship as data, detector cost ↓ | **4a shipped** (log-only, measured); **4b implemented 2026-08-12** behind `settings.anchor_roi` (off by default) — replay decisions byte-identical on/off on this Mac; the Windows `ocr_ms` measurement is still owed before it defaults on. See [plans/ANCHORS.md](ANCHORS.md); 4c pending captures |
| 5 TextMap | experiment | everything OCR, latency ceiling | match rate ≥90%, wrong-match ~0 on replay corpus | blocked on data |
| 6 arbiter | backlog | corpus labeling | labeled corpus | not needed yet |

1→2→3 were independent of 4 and released together in 0.7.3. Phase 4 is now
optional rather than load-bearing: Genshin shipped as profile code in 0.7.0
without it, so what remains for 4 to justify itself is OCR cost and the last
uncalibrated screens. 5 only after 4's profiles exist (it's per-game data too,
same profiles dir).
