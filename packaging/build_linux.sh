#!/bin/bash
# Full Linux packaging pipeline: venv/deps -> PyInstaller -> .deb.
# Run from anywhere -- cd's to the repo root (this script's own
# grandparent directory) first.
#
# Produces:
#   dist/VRA Editor/VRA Editor          (portable app -- see VRA_Editor.spec)
#   installer_output/vra-editor_<version>_amd64.deb   (installable package)
#
# System packages this needs (Debian/Ubuntu names; install once with
# sudo apt install <these>): python3-venv fakeroot dpkg-dev, plus the
# runtime libs PySide6/Qt6 needs at import time -- libgl1 libegl1
# libxkbcommon0 libxkbcommon-x11-0 libdbus-1-3 libfontconfig1
# libxcb-cursor0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1
# libxcb-randr0 libxcb-render-util0 libxcb-shape0 libxcb-xfixes0
# libxcb-xinerama0 libxcb-glx0 -- these are also declared as Depends:
# in packaging/debian/control, so `apt install ./file.deb` (not plain
# dpkg -i) pulls them in automatically on a machine that lacks them.
#
# If VRA Editor is already running, PyInstaller's cleanup of dist/ will
# fail with a "file in use" style error -- this script doesn't try to
# detect or kill that for you, since force-closing it could discard an
# open record's unsaved edits. Close it yourself first if you hit that.

set -e

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

if [ ! -f ".venv/bin/python" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo
echo "=== Installing/updating dependencies ==="
.venv/bin/python -m pip install --upgrade pip -q
.venv/bin/python -m pip install -r requirements.txt pyinstaller -q

echo
echo "=== Building with PyInstaller ==="
.venv/bin/python -m PyInstaller packaging/VRA_Editor.spec --noconfirm

echo
echo "=== Assembling .deb ==="
VERSION=$(grep '^Version:' packaging/debian/control | awk '{print $2}')
STAGING="$REPO_ROOT/installer_output/vra-editor_${VERSION}_amd64"
rm -rf "$STAGING"

mkdir -p "$STAGING/DEBIAN"
mkdir -p "$STAGING/opt/vra-editor"
mkdir -p "$STAGING/usr/bin"
mkdir -p "$STAGING/usr/share/applications"
mkdir -p "$STAGING/usr/share/pixmaps"

cp packaging/debian/control "$STAGING/DEBIAN/control"
cp -a "dist/VRA Editor/." "$STAGING/opt/vra-editor/"
cp packaging/debian/vra-editor.desktop "$STAGING/usr/share/applications/vra-editor.desktop"
cp vra_editor/images/logo.png "$STAGING/usr/share/pixmaps/vra-editor.png"

cat > "$STAGING/usr/bin/vra-editor" <<'WRAPPER'
#!/bin/sh
exec "/opt/vra-editor/VRA Editor" "$@"
WRAPPER
chmod 755 "$STAGING/usr/bin/vra-editor"

fakeroot dpkg-deb --build --root-owner-group "$STAGING" \
    "$REPO_ROOT/installer_output/vra-editor_${VERSION}_amd64.deb"

echo
echo "=== Done ==="
echo "Portable app: dist/VRA Editor/VRA Editor"
echo "Package:      installer_output/vra-editor_${VERSION}_amd64.deb"
