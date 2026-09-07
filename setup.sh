#!/bin/zsh
# HoyoVoice one-time setup. Run from the repo root: ./setup.sh
set -e
cd "$(dirname "$0")"

echo "== checking prerequisites"
command -v brew >/dev/null || { echo "Homebrew required: https://brew.sh"; exit 1; }
command -v ffmpeg >/dev/null || brew install ffmpeg
command -v espeak-ng >/dev/null || brew install espeak-ng
command -v sox >/dev/null || brew install sox   # audio capture — REQUIRED
command -v swiftc >/dev/null || { echo "Xcode Command Line Tools required: xcode-select --install"; exit 1; }

PY=python3.13
command -v $PY >/dev/null || { echo "python3.13 required: brew install python@3.13"; exit 1; }

echo "== creating venv + installing python deps"
[ -d .venv ] || $PY -m venv .venv
.venv/bin/pip install --upgrade pip -q
# flask (dashboard) and vaderSentiment (delivery pacing) are NOT pulled in
# by anything else — a fresh clone fails at import without them.
# NOTE: wordfreq is deliberately absent. Its OCR repairs exist for the
# Windows recogniser, which drops spaces; Apple Vision spaces correctly, so
# on macOS they are a no-op with a small false-positive risk. The import is
# optional, so the code simply skips them here. See plans/PRE-MERGE.md.
# huggingface_hub is a direct import (hv_platform/darwin.py model
# download), not just mlx-audio's transitive dep — pin it explicitly so
# an upstream dep change can't break a fresh clone
.venv/bin/pip install mlx-audio soundfile pillow onnxruntime numpy \
  flask vaderSentiment huggingface_hub -q
# misaki pins a spacy version that fights py3.13 wheels — install around it
.venv/bin/pip install --only-binary :all: spacy -q
.venv/bin/pip install --no-deps misaki -q
.venv/bin/pip install num2words regex phonemizer-fork espeakng-loader -q

echo "== compiling OCR daemon"
(cd tools && swiftc -O ocrd.swift -o ocrd)

echo "== downloading Silero VAD model"
# Pinned to a commit and checked against a SHA-256 the maintainer computed
# from that commit: the VAD gate runs this model on every line, so a
# replaced file on a mutable URL would run whatever it was replaced with.
SILERO_URL=https://github.com/snakers4/silero-vad/raw/bfdc0193023f121ea5b3cc7b176dbed570a68a59/src/silero_vad/data/silero_vad.onnx
SILERO_SHA256=1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3
if [ ! -f tools/silero_vad.onnx ]; then
  curl -sL -o tools/silero_vad.onnx "$SILERO_URL"
  if ! echo "$SILERO_SHA256  tools/silero_vad.onnx" | shasum -a 256 -c --status; then
    rm -f tools/silero_vad.onnx
    echo "ERROR: silero_vad.onnx checksum mismatch — download corrupted or file changed upstream" >&2
    exit 1
  fi
fi

mkdir -p captures tts_out
[ -f voices.json ] || cp voices.example.json voices.json

echo "== verifying capture device"
ffmpeg -hide_banner -f avfoundation -list_devices true -i "" 2>&1 | grep -i shadowcast \
  || echo "WARNING: no ShadowCast device found — plug in your capture card (any UVC device works; pick it from the dashboard dropdowns)"

echo
echo "Setup complete. Start with: ./hoyovoice.sh start"
echo "(First run downloads the Kokoro TTS model, ~360 MB.)"
