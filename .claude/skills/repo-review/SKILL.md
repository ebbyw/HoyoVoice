---
name: repo-review
description: Periodic full-repo review for HoyoVoice — hygiene, optimization, TODO audit, docs/release/changelog/tags consistency, and HoYoverse IP/legal exposure. Use when the user asks for a "hygiene pass", "repo review", "release review", "changelog review", "legal pass", or general pre-release cleanup.
---

# Repo review — five passes

Run the passes as parallel read-only subagents (Explore), then triage
findings into: fix now (this branch), spawn task, or explicitly rejected
(write the rejection into the relevant doc so it isn't re-litigated).

Read `plans/ANCHORS.md` and `plans/RELEASING.md` first for current phase
state and the release process. Respect the repo's standing rule: comments
and plans document *why* — a pass that proposes something a comment
already rejects is noise, not a finding.

## Pass 1 — Hygiene

- Dead code: unused functions/imports/branches; orphaned files nothing
  references (cross-check `tools/*.py` imports, `hv_platform` usage).
- Stale references both directions: docs → vanished code/settings, code →
  moved docs.
- `.gitignore` coverage of generated state (captures/, shots/, logs/,
  `__pycache__`, venv, built `ocrd` binary) and `.gitattributes` sanity.
- Drift pairs: `setup.sh` vs `setup.ps1`; `voices.example.json` vs the
  `settings.*` keys live.py actually reads; duplicated constants.
- Test hygiene: tests of deleted functions; untested modules that peers
  all have tests for.

## Pass 2 — Optimization

Hot path is live.py's frame loop (~6 fps). Only findings with measurable
impact: per-frame allocations, redundant decodes/encodes, regex compiled
in loops, unbounded session-growth state (dedupe lists, histories), JSON
re-parsed per frame, blocking calls that could overlap the existing
threading design (don't propose breaking it). Estimate impact
(ms/frame, unbounded growth, minor). Anything real gets a measurement
plan before a change — this repo doesn't merge unmeasured perf claims.

## Pass 3 — TODO audit

Grep code + docs for TODO/FIXME/XXX/HACK/TBD/"for now"/"owed"/"not
yet"/"later"/"temporary". Verdict per hit: KEEP / DONE-remove /
STALE-rewrite / PROMOTE-to-plan. Also diff plans/*.md stated future work
against actual code state (phase gates in ANCHORS.md especially).

## Pass 4 — Legal / IP (HoYoverse)

The repo is a public fan tool. Exposure ranked:

- **Game assets committed** — any pixels/audio from the games
  (anchor template PNGs are the known case: keep them tiny UI-chrome
  crops, or move to generate-at-setup from the user's own capture).
- **Verbatim game text** — dialogue passages in tests/docs beyond what
  a fair-use test fixture needs; never commit TextMap data or tell users
  to datamine it (point at their own capture/OCR output instead).
- **Media** — no gameplay frames/recordings tracked; check git *history*
  for large blobs, not just the tip.
- **Trademarks** — README needs a non-affiliation disclaimer naming
  HoYoverse/miHoYo; project name itself noted as a risk we accept.
- **ToS** — passive screen capture only; flag anything that reads game
  memory, injects, or automates input.

Legal findings are report-first: removal from history rewrites shared
history — surface, don't execute, unless the user says go.

## Pass 5 — Docs / release / changelog / tags

- CHANGELOG sections ↔ git tags: every section tagged, every tag
  sectioned, dates match tag dates.
- Unreleased section ↔ `git log <last-tag>..HEAD`: complete both ways.
- RELEASING.md process matches reality (tag style, version strings).
- README: every documented setting exists in code; every user-facing
  change in recent CHANGELOG sections reflected; install steps match
  setup scripts; relative links resolve.
- Tags annotated with useful messages.

## Wrap-up

One consolidated report: findings by pass, each tagged fix-now /
task-spawned / rejected-with-reason. Apply fix-now items, run the test
suite (`python3 -m pytest tools/ -q` or per-file `python3 tools/test_*.py`
if pytest absent), update CHANGELOG Unreleased if anything user-facing
changed.
