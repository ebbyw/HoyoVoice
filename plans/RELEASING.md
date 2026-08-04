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
header, the downloaded log and `hoyovoice.py` all read it. Patch for
fixes, minor for features.

## 3. Verify before tagging

```sh
./hoyovoice.sh start && sleep 40
curl -s http://127.0.0.1:8470/ | grep -o 'v[0-9.]*'   # header
curl -s http://127.0.0.1:8470/log.txt | head -1        # downloaded log
./hoyovoice.sh stop
```

Both must show the new number, or the bump didn't land everywhere.

## 4. Commit, tag, push

```sh
git commit -am "Release 0.7.0 — <one-line summary>"
git tag -a v0.7.0 -m "HoyoVoice 0.7.0

<short summary>"
git push origin main
git push origin v0.7.0
```

## 5. Publish the GitHub release — don't skip

```sh
V=0.7.0
python3 - <<PY
import re, pathlib
s = pathlib.Path('CHANGELOG.md').read_text()
m = re.search(rf"## \[$V\][^\n]*\n(.*?)(?=\n## \[)", s, re.S)
pathlib.Path('/tmp/notes.md').write_text(m.group(1).strip() + "\n")
PY
gh release create "v$V" --title "HoyoVoice $V" --notes-file /tmp/notes.md --latest
gh release list | head -3      # confirm it reads "Latest"
```

Using the changelog section as the release body means the release page
explains itself instead of being a bare tag.
