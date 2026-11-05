#!/usr/bin/env bash
# Luma launcher for Linux / macOS – creates a virtual environment on first run.
cd "$(dirname "$0")" || exit 1
PY=${PYTHON:-python3}
if [ ! -d .venv ]; then
  echo "Setting up Luma (first run only)..."
  "$PY" -m venv .venv || { echo "Creating the virtual environment failed (Debian/Ubuntu: sudo apt install python3-venv)"; exit 1; }
  ./.venv/bin/pip install --upgrade pip >/dev/null
  ./.venv/bin/pip install -r requirements.txt || exit 1
fi
exec ./.venv/bin/python luma.py "$@"
