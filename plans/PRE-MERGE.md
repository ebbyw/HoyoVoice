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

- **`wordfreq` on macOS.** `setup.ps1` installs it; `setup.sh` does not.
  The run-on/best-read repairs are optional-import, so macOS silently
  skips them — correct today because Vision spaces text properly. Decide
  whether that asymmetry is intentional (it currently is) and say so in
  the README if it stays.
- **README wording.** Windows is described as "experimental". It has now
  had several clean end-to-end sessions; decide whether that still holds.
- **`plans/PLAN-WINDOWS.md`** is historical now — the plan it describes is
  built. Either mark it as such or fold the still-true parts into
  `WINDOWS-TESTING.md`.
