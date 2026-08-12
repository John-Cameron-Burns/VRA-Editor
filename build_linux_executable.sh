#!/bin/bash
# Builds the Linux executable completely from scratch: wipes any
# existing venv/build state, reinstalls dependencies, rebuilds with
# PyInstaller.
#
# Produces: distributions/VRA Editor/VRA Editor
#
# For an installable .deb instead (Start Menu entry, apt-managed
# dependencies, clean uninstall via apt/dpkg), use
# packaging/build_linux_deb.sh instead of this script.
#
# System packages this needs (Debian/Ubuntu names; install once with
# sudo apt install <these>): python3-venv, plus the runtime libs
# PySide6/Qt6 needs at import time -- libgl1 libegl1 libxkbcommon0
# libxkbcommon-x11-0 libdbus-1-3 libfontconfig1 libxcb-cursor0
# libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0
# libxcb-render-util0 libxcb-shape0 libxcb-xfixes0 libxcb-xinerama0
# libxcb-glx0
#
# If VRA Editor is already running, PyInstaller's cleanup step will
# fail with a "file in use"-style error -- close it first if that
# happens; this script won't force-kill it for you (could discard
# unsaved edits in an open record).

set -e

cd "$(dirname "$0")"

echo "=== Cleaning previous build state ==="
rm -rf .venv build "distributions/VRA Editor"

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

echo
echo "=== Done ==="
echo "Executable: distributions/VRA Editor/VRA Editor"
