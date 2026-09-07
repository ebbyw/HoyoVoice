"""Pins what `pronounce_names.py --write` does to a voices.json it merges into.

The shipped value wins for a shipped key, by design: this is how a corrected
respelling reaches the Windows machine, where voices.json never comes from
git. Two things around that rule are worth pinning. A key the user added
themselves is never touched. And the file is replaced atomically — a merge
interrupted mid-write used to leave a half-written voices.json, which turned
the next launch into a JSON parse error rather than a stale respelling.

Run directly or under pytest:

    python tools/test_pronounce_merge.py
"""
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pronounce_names as pn                        # noqa: E402


def test_merge_keeps_user_keys_and_names_replacements():
    shipped_key = next(iter(pn.TERMS))
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "voices.json"
        path.write_text(json.dumps({"settings": {"pronunciations": {
            "Zzyzx": "ZY-zix",                  # the user's own entry
            shipped_key: "something else",      # a hand-tuned shipped key
        }}}))
        out = io.StringIO()
        with redirect_stdout(out):
            pn.merge(path, {}, custom_words=False)
        pron = json.loads(path.read_text())["settings"]["pronunciations"]
        assert pron["Zzyzx"] == "ZY-zix", "a user key must survive a merge"
        assert pron[shipped_key] == pn.TERMS[shipped_key], \
            "the shipped value wins for a shipped key"
        assert f"replaced {shipped_key}: 'something else'" in out.getvalue(), \
            "a replaced hand edit must be named, not silently overwritten"
        assert not list(Path(d).glob(".*.tmp")), "temp file left behind"
        assert sorted(os.listdir(d)) == ["voices.json"]


def test_merge_writes_through_a_temp_file():
    """The file that exists between the write starting and finishing is the
    old one, in full: os.replace swaps a completed temp file over it."""
    seen = []
    real_replace = os.replace

    def spy(src, dst):
        seen.append((Path(src).name, json.loads(Path(dst).read_text())))
        real_replace(src, dst)

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "voices.json"
        path.write_text(json.dumps({"settings": {"pronunciations": {}}}))
        pn.os.replace = spy
        try:
            with redirect_stdout(io.StringIO()):
                pn.merge(path, {}, custom_words=False)
        finally:
            pn.os.replace = real_replace
    assert seen and seen[0][0] == ".voices.json.tmp", seen
    assert seen[0][1] == {"settings": {"pronunciations": {}}}, \
        "the live file must still be the old one until the swap"


if __name__ == "__main__":
    test_merge_keeps_user_keys_and_names_replacements()
    test_merge_writes_through_a_temp_file()
    print("ok")
