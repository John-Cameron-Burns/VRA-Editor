#!/bin/bash
# Builds the macOS .app completely from scratch: wipes any existing
# venv/build state, reinstalls dependencies, rebuilds with PyInstaller.
#
# Produces: distributions/VRA Editor.app
#
# Double-click this in Finder to run it, or run it from a shell
# directly -- either way it always operates on the repo root (this
# file's own directory), regardless of where it's launched from.
#
# If VRA Editor.app is already running, PyInstaller's cleanup step will
# fail with a "file in use"-style error -- close it first if that
# happens; this script won't force-quit it for you (could discard
# unsaved edits in an open record).

set -e

cd "$(dirname "$0")"

echo "=== Cleaning previous build state ==="
rm -rf .venv build "distributions/VRA Editor.app"

echo
echo "=== Creating virtual environment ==="
python3 -m venv .venv

echo
echo "=== Installing dependencies ==="
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt pyinstaller -q

echo
echo "=== Building with PyInstaller ==="
.venv/bin/python -m PyInstaller packaging/VRA_Editor.spec --noconfirm --distpath distributions

# The BUNDLE step's own .app is fully self-contained (a copy, not a
# reference) -- the plain "VRA Editor" folder alongside it is just
# PyInstaller's intermediate COLLECT output, redundant clutter once the
# .app exists.
rm -rf "distributions/VRA Editor"

echo
echo "=== Done ==="
echo "App: distributions/VRA Editor.app"

# Keeps the window open with the summary visible when launched by
# double-clicking in Finder (Terminal may otherwise close it immediately).
read -n 1 -s -r -p "Press any key to close this window..."
echo
