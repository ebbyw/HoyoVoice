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
.venv/bin/pip install mlx-audio soundfile pillow onnxruntime -q
# misaki pins a spacy version that fights py3.13 wheels — install around it
.venv/bin/pip install --only-binary :all: spacy -q
.venv/bin/pip install --no-deps misaki -q
.venv/bin/pip install num2words regex phonemizer-fork espeakng-loader -q

echo "== compiling OCR daemon"
(cd tools && swiftc -O ocrd.swift -o ocrd)

echo "== downloading Silero VAD model"
[ -f tools/silero_vad.onnx ] || curl -sL -o tools/silero_vad.onnx \
  https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx

mkdir -p captures tts_out
[ -f voices.json ] || cp voices.example.json voices.json

echo "== verifying capture device"
ffmpeg -hide_banner -f avfoundation -list_devices true -i "" 2>&1 | grep -i shadowcast \
  || echo "WARNING: no ShadowCast device found — plug in your capture card and check live.py CAPTURE_INPUT indices"

echo
echo "Setup complete. Start with: ./hoyovoice.sh start"
echo "(First run downloads the Kokoro TTS model, ~360 MB.)"
