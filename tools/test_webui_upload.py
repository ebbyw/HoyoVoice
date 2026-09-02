"""Pins that queued browser uploads never share a staging path."""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from webui import _upload_destination


def main():
    with tempfile.TemporaryDirectory(prefix="hv_upload_") as tmp:
        first = _upload_destination(tmp, "A voice!.pt")
        second = _upload_destination(tmp, "A voice!.pt")
    if first == second:
        print("FAIL  same-named uploads share a staging path")
        return 1
    if first.parent != second.parent or not first.name.endswith("A_voice_.pt"):
        print(f"FAIL  upload path changed its safe location/name: {first}")
        return 1
    print("ok    same-named uploads receive separate safe staging paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
