"""Pins that the macOS compatibility launcher delegates scoped lifecycle work."""
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def main():
    script = (ROOT / "hoyovoice.sh").read_text()
    if "pkill" in script:
        print("FAIL  wrapper still kills processes by global name")
        return 1
    out = subprocess.run(["zsh", str(ROOT / "hoyovoice.sh"), "invalid"],
                         capture_output=True, text=True, timeout=10)
    if out.returncode or "usage:" not in out.stdout:
        print(f"FAIL  wrapper did not delegate usage: {out.stdout}{out.stderr}")
        return 1
    print("ok    wrapper delegates lifecycle commands to the scoped launcher")
    return 0


if __name__ == "__main__":
    sys.exit(main())
