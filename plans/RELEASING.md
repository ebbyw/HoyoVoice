# Cutting a release

Repeatable steps. The one that's easy to miss is the last: **pushing a tag
does not publish a release.** GitHub's Releases sidebar lists only
*published* releases, so tags alone leave it advertising an old version —
v0.5.1, v0.6.0 and v0.6.1 were all tagged and pushed while the repo page
still showed 0.5.0.

## 1. Changelog

Move everything under `## [Unreleased]` into a dated section, leaving
`[Unreleased]` empty above it:

```
## [Unreleased]

## [0.7.0] - 2026-08-14
```

Fold fixes to features that never shipped into the feature entry they
belong to — a bug-by-bug diary of getting a new feature right is noise to
anyone reading released history. Keep as **Fixed** only what affected
behaviour of the *previous release*. (The detail lives in commit
messages, which is why releases merge rather than squash.)

## 2. Version

`VERSION` in `tools/webui.py` — the single source of truth; the dashboard
header and the downloaded log render it through `BUILD` (VERSION plus the
running commit's sha). Patch for fixes, minor for features.

## 3. Verify before tagging

```sh
for t in tools/test_*.py; do .venv/bin/python "$t" || break; done

./hoyovoice.sh start && sleep 40
curl -s http://127.0.0.1:8470/ | grep -o 'v[0-9][^<]*'   # header
curl -s http://127.0.0.1:8470/log.txt | head -1           # downloaded log
./hoyovoice.sh stop
```

Both must show the new number, or the bump didn't land everywhere. The
suffix in parentheses is the running commit's sha, and `-dirty` is
EXPECTED at this step — step 4's commit hasn't happened yet; only the
version number before the parenthesis has to be the new one. (The old
grep `v[0-9.]*` matched every bare `v` on the page; the `[^<]` form
isolates the one version string.)

If the release touches `FIXES`/`TERMS` in `tools/pronounce_names.py`, say so in
the changelog entry with the `--write` line: `voices.json` is gitignored and
per-machine, so a pull does not update anyone's pronunciations, and the second
machine is always the one that reports the fix "not working".

## 4. Commit, tag, push

```sh
git commit -am "Release 0.7.0 — <one-line summary>"
git tag -a v0.7.0 -m "HoyoVoice 0.7.0

<short summary>"
git push origin main
git push origin v0.7.0
```

Always `-a` (annotated): v0.3.0–v0.5.1 are lightweight and carry no tagger
date, which the changelog audit had to work around; every tag since 0.6.0 is
annotated and must stay that way. The `<short summary>` line is optional in
practice — the GitHub release body (step 5) carries the prose.

## 5. Publish the GitHub release — don't skip

```sh
V=0.7.0
python3 - <<PY
import re, pathlib
s = pathlib.Path('CHANGELOG.md').read_text()
m = re.search(r"## \[$V\][^\n]*\n(.*?)(?=\n## \[)", s, re.S)
pathlib.Path('/tmp/notes.md').write_text(m.group(1).strip() + "\n")
PY
gh release create "v$V" --title "HoyoVoice $V" --notes-file /tmp/notes.md --latest
gh release list | head -3      # confirm it reads "Latest"
```

Using the changelog section as the release body means the release page
explains itself instead of being a bare tag.

## 6. Branch hygiene

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
