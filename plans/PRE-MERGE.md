# Pre-merge checklist

What should happen before a topic branch merges into `main`. Written down
because it's all easy to forget once the branch looks finished. Originally the
`windows-support` checklist; that branch merged at 0.6.0 and the parts of it
that were about *that* work have been dropped, leaving what turned out to be
general.

## 1. Collapse branch-only fixes in the CHANGELOG

A long branch accumulates Fixed entries for features that **only ever existed
on the branch** — the chat-panel reader was the worst case: scroll cutting the
read, the "R" glyph, clipped-tail re-reads, mid-animation garbling, sender-label
inheritance. To anyone reading released history those are noise, because the
feature never shipped broken. Fold them into the feature entry:

> **Added** — group-chat/message panel reading: messages read incrementally,
> each sender in their own cast voice, system notices in the narrator's.

**Keep as separate Fixed entries** anything that changed behaviour users already
had on `main`. From that branch, the ones that qualified were the VAD
tail-reader lag, the dedupe window never expiring, lines never spoken when the
stability threshold dropped mid-count, and the mid-play yield being too strict
to fire.

The measurements inside collapsed entries (frame counts, VAD probabilities,
audio durations) are the reason each fix is shaped the way it is. Commit
messages hold them, which is why releases merge rather than squash — losing
them from the changelog is acceptable, losing them entirely is not.

## 2. Version + release section

See **[RELEASING.md](RELEASING.md)** for the sequence. In short: `VERSION` in
`tools/webui.py` is the single source of truth, bump it and date the changelog
section, then publish a GitHub release with `gh release create` — pushing the
tag alone leaves the repo page advertising the previous version.

## 3. Re-verify both platforms after the final rebase

- macOS: `./hoyovoice.sh start`, play a scene, confirm dialogue and gating are
  unchanged.
- Windows: one clean session — dialogue, a chat conversation, a loading screen
  — then **⤓ Download log** and skim it. Remember the Windows box takes its
  changes through git only.
- Anything touching the synthesis text pipeline also needs
  `python tools/pronounce_names.py --check` on both machines, since `voices.json`
  is per-machine and a pull doesn't update it.

## 4. Run the tests, then replay

```bash
for t in tools/test_*.py; do .venv/bin/python "$t" || break; done
```

Then replay a recording that exercises the area you changed
(`python tools/replay.py <recording> --game <hsr|genshin>`). A branch that only
has unit coverage has not been verified against real frames, and every
interesting bug in this project so far has been about real frames.

## 5. Settled decisions worth not relitigating

- **`wordfreq` stays Windows-only.** Measured rather than assumed: the run-on
  repair is a **no-op on Apple Vision output** — Vision spaces text correctly,
  and the repair exists because RapidOCR's bundled recognition model is
  Chinese-trained. It also carries a small real downside: over 3204 words of
  correct English prose it still rewrites 3 tokens (code/URL strings). Non-zero
  risk, zero upside. The other half — best-read selection (`text_quality`) — is
  platform-independent in principle but only bites when several *different* raw
  reads normalise identically, and Vision is stable enough that the variants are
  usually the same string. The optional import already handles it: without
  `wordfreq` both repairs no-op. Revisit only if macOS moves off Vision.
- **Windows is not "experimental".** Several clean end-to-end sessions on real
  hardware; README and changelog say so.
- **Planning docs live in `archive/`, which is gitignored.** `PLAN.md` and
  `PLAN-WINDOWS.md` went there once built; `WINDOWS-TESTING.md` carries what is
  still true.

## 6. Known, and deliberately not fixed

Recorded so they aren't mistaken for oversights.

- **PS5 system menus are read before the game starts.** Ranked P3, leave it.
  They're rejected as unknown speakers so nothing is spoken; the log just fills
  with rejections.
- **Word-level OCR fusions survive on Windows, at a much lower rate.** The
  English recognition model (0.7.3) took fusion-class defects from 333 to 144
  over an 81-shot corpus. Run-on repair only splits into two known words, so
  three-way fusions still get through. The remaining lever is canonical-text
  snapping — phase 5 of [OCR-INTEGRATION-PLAN.md](OCR-INTEGRATION-PLAN.md), and
  blocked on data that can't ship publicly.
