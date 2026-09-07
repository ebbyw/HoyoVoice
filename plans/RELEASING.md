# Cutting a release

`release-please` (`.github/workflows/release-please.yml`) owns the version
bump, the tag, and publishing the GitHub release — the step that used to get
missed, since pushing a tag alone doesn't publish a release and the repo page
kept advertising an old version (v0.5.1, v0.6.0, v0.6.1 all shipped that way).
It does **not** touch `CHANGELOG.md` — `release-please-config.json` sets
`skip-changelog`, because this repo's changelog is hand-written prose with the
evidence in it, and release-please only knows how to synthesize one bullet per
commit subject. That split is deliberate: automate the mechanical, error-prone
part (tag + publish), keep the part that requires judgment (what's worth
saying, and how) manual.

## 1. Changelog

Move everything under `## [Unreleased]` into a dated section, leaving
`[Unreleased]` empty above it:

```
## [Unreleased]

## [0.12.0] - 2026-09-01
```

Fold fixes to features that never shipped into the feature entry they belong
to — a bug-by-bug diary of getting a new feature right is noise to anyone
reading released history. Keep as **Fixed** only what affected behaviour of
the *previous release*. (The detail lives in commit messages, which is why
topic branches merge rather than squash — see Branch hygiene below.)

Commit and push this directly to `main`:

```sh
git commit -am "docs: cut 0.12.0 in the changelog"
git push origin main
```

If the release touches `FIXES`/`TERMS` in `tools/pronounce_names.py`, say so
in the changelog entry with the `--write` line: `voices.json` is gitignored
and per-machine, so a pull does not update anyone's pronunciations, and the
second machine is always the one that reports the fix "not working".

## 2. Verify before merging the release PR

```sh
for t in tools/test_*.py; do .venv/bin/python "$t" || break; done
```

## 3. The release-please PR

The push in step 1 (or any `fix:`/`feat:` commit before it) triggers
release-please to open or update a PR titled `chore(main): release X.Y.Z`.
It bumps `VERSION` in `tools/webui.py` (marked with the
`# x-release-please-version` comment release-please's `extra-files` config
looks for) and `version.txt` at the repo root, computing the bump — patch for
`fix:`, minor for `feat:` — from conventional commit types since the last
tag. If that doesn't match the version you just wrote into the changelog
heading, add a `Release-As: 0.12.0` footer to a commit to override it.

**Replace the notes in the PR's description** with the changelog section
from step 1 (the prose, not release-please's auto-generated commit list) —
release-please reads the PR body live at merge time for the GitHub Release
notes, so this is what readers see on the Releases page. It does not read
`CHANGELOG.md` itself for this, since release-please never touched that file.

Replace **only the part between the two `---` rules**. The first line, the
`---` under it, the `## [0.12.1](…compare…)` heading and the footer are how
release-please recognises its own PR after the merge; with them gone it
logs `could not parse pull request body as a release PR`, never tags, and
opens a fresh PR proposing the *next* version instead (0.12.1: the body was
swapped wholesale, the merge went unrecognised, and a phantom "0.13.0" PR
appeared listing every commit in the repo — the tag and release had to be
made by hand with `gh release create v0.12.1 --target <merge sha>
--notes-file …`). Keep this shape:

```
:robot: I have created a release *beep* *boop*
---


## [0.12.1](https://github.com/ebbyw/HoyoVoice/compare/v0.12.0...v0.12.1) (2026-09-07)

<the changelog section's prose>

---
This PR was generated with [Release Please](https://github.com/googleapis/release-please). See [documentation](https://github.com/googleapis/release-please#release-please).
```

Merge with a merge commit (not squash) once the PR's diff (`VERSION` and
`version.txt`, nothing else) and description look right.

## 4. After merge

Merging the PR is what tags and publishes:

```sh
gh release list | head -3      # confirm 0.12.0 shows and reads "Latest"
git pull origin main            # bring the bumped VERSION locally
```

Then verify the running app matches:

```sh
./hoyovoice.sh start && sleep 40
curl -s http://127.0.0.1:8470/ | grep -o 'v[0-9][^<]*'   # header
curl -s http://127.0.0.1:8470/log.txt | head -1           # downloaded log
./hoyovoice.sh stop
```

Both must show the new number — the suffix in parentheses is the running
commit's sha. (The old grep `v[0-9.]*` matched every bare `v` on the page;
the `[^<]` form isolates the one version string.)

## 5. Branch hygiene

Topic branches merge with `--no-ff` (`Merge <branch>: <one-line summary>`) —
**never squash**. The measurements that justify each fix live in the commit
messages, and the collapsed changelog entry deliberately doesn't carry them.

Afterwards, remove the worktree and delete the branch, but confirm the tip is
an ancestor of `origin/main` first:

```sh
git merge-base --is-ancestor <branch> origin/main && git branch -d <branch>
git worktree remove .claude/worktrees/<name>
```

`git worktree remove` warns about "discarded commits" when the branch ref is
the only thing left pointing at them. That warning is expected once the
ancestor check above has passed.
