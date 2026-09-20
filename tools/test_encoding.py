"""Pins that every text read and write names its encoding.

Python opens a text file in the locale's encoding, which is UTF-8 on macOS
and cp1252 on the Windows box. Every file this app writes is UTF-8 —
voices.json is written with `ensure_ascii=False`, so one accented roster
name puts a real multi-byte character in it — and reading that back under
cp1252 is not a wrong character but a crash:

    UnicodeDecodeError: 'charmap' codec can't decode byte 0x9d in position
    56908: character maps to <undefined>

which is what `pronounce_names.py --write --custom-words` died with on
Windows (2026-09-20) after the roster names went into `custom_words`. The
same call reads fine on macOS, so this is a class of bug the mac can't
feel: pin it here instead.
"""
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP = {".venv", ".claude", ".git", "captures"}
# Image.open and io.BytesIO take no encoding; a bare open() does.
TEXT_IO = {"read_text", "write_text", "open"}


def offenders(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = (func.attr if isinstance(func, ast.Attribute)
                else getattr(func, "id", ""))
        if name not in TEXT_IO:
            continue
        if name == "open":
            if isinstance(func, ast.Attribute):     # Image.open, tar.open
                continue
            mode = (node.args[1].value
                    if len(node.args) > 1 and isinstance(node.args[1],
                                                         ast.Constant)
                    else "r")
            if "b" in str(mode):                    # bytes need no encoding
                continue
        if any(kw.arg == "encoding" for kw in node.keywords):
            continue
        yield node.lineno, name


def main():
    found = []
    for path in sorted(ROOT.rglob("*.py")):
        if SKIP & set(path.relative_to(ROOT).parts):
            continue
        found += [f"{path.relative_to(ROOT)}:{line}: {name}()"
                  for line, name in offenders(path)]
    if found:
        print("FAIL  text I/O without an explicit encoding:")
        for f in found:
            print(f"      {f}")
        return 1
    print("ok    every text read and write names its encoding")
    return 0


if __name__ == "__main__":
    sys.exit(main())
