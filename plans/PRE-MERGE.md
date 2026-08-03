# Pre-merge checklist — `windows-support` → `main`

Things that should happen before this branch merges. Written down because
they're easy to forget once the branch looks finished.

## 1. Collapse branch-only fixes in the CHANGELOG

The Unreleased section currently carries ~23 Fixed entries, and a large
share of them fix features that **only ever existed on this branch** — the
chat-panel reader in particular (scroll cutting the read, the "R" glyph,
clipped-tail re-reads, mid-animation garbling, the sender-label
inheritance). To anyone reading the released changelog those are noise:
the feature never shipped in a broken state.

Before merging, fold those into the feature entry they belong to, so the
public history reads:

> **Added** — group-chat/message panel reading: messages read
> incrementally, each sender in their own cast voice, system notices in
> the narrator's.

rather than a bug-by-bug diary of getting there.

**Keep as separate Fixed entries** anything that affected behaviour users
already had on `main`:

- VAD tail-reader lag (spoke over real voiceover)
- the dedupe window never expiring (loading-screen lore silently skipped)
- lines never spoken when the stability threshold dropped mid-count
- the mid-play yield being too strict to ever fire

The measurements in the collapsed entries (frame counts, VAD
probabilities, audio durations) are worth preserving somewhere — they are
the reason each fix is shaped the way it is. Commit messages already hold
them, so losing them from the changelog is acceptable.

## 2. Version + release section

`VERSION` lives in `tools/webui.py` (shown in the dashboard header). Bump
it and date the section when cutting the release.

## 3. Re-verify both platforms after the final squash/rebase

- macOS: `./hoyovoice.sh start`, play a scene, confirm dialogue + gating
  are unchanged. The platform split was meant to be behaviour-neutral
  there; this is the check that it stayed that way.
- Windows: one clean session — dialogue, a chat conversation, a loading
  screen — then **⤓ Download log** and skim it.

## 4. Decisions to confirm

- **`wordfreq` on macOS — DECIDED: no, keep it Windows-only.** Measured
  rather than assumed:
  - The repair is a **no-op on Vision output** — the golden frame passes
    through unchanged. Vision spaces text correctly; the whole reason
    run-on repair exists is that RapidOCR's recognition model is
    Chinese-trained and Chinese has no spaces.
  - It carries a small but real **downside**: run over 3204 words of
    correct English prose it still rewrites 3 tokens (all code/URL
    strings). Non-zero risk, zero upside, on a platform that doesn't
    need it.
  - The other half — best-read selection (`text_quality`) — is
    platform-independent in principle, but only bites when several
    *different* raw reads of one line normalise identically. Vision is
    stable enough that the variants are usually the same string, so
    there is rarely anything to choose between.

  The optional import already handles this: without `wordfreq` both
  repairs no-op, so macOS behaviour is unchanged. Revisit if macOS ever
  moves off Vision.
- **README wording.** Windows is described as "experimental". It has now
  had several clean end-to-end sessions; decide whether that still holds.
- **`plans/PLAN-WINDOWS.md`** is historical now — the plan it describes is
  built. Either mark it as such or fold the still-true parts into
  `WINDOWS-TESTING.md`.
