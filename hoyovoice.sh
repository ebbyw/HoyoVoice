#!/bin/zsh
# Compatibility wrapper for the original macOS command. The Python launcher
# owns a verified pidfile and a dedicated process group; broad process-name
# kills here could stop an unrelated capture session or another checkout.
ROOT="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$ROOT/hoyovoice.py" "$@"
