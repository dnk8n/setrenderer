#!/usr/bin/env bash
# One-command install: ffmpeg (Homebrew) + a local Python venv with setrender.
set -euo pipefail
cd "$(dirname "$0")"
command -v ffmpeg >/dev/null || brew install ffmpeg
command -v uv >/dev/null || { echo "install uv first: https://docs.astral.sh/uv/"; exit 1; }
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.lock
uv pip install --python .venv/bin/python --no-deps -e .
echo "done. Try:  .venv/bin/setrender render your_set.wav --duration 30"
