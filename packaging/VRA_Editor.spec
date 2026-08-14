# PyInstaller spec for the VRA Core 4 XML Editor desktop app.
#
# Build (from the repo root, with the project venv active):
#   pyinstaller packaging/VRA_Editor.spec --noconfirm
#
# Produces dist/VRA Editor.app (macOS) or dist/VRA Editor/ (other
# platforms) alongside a matching entry under dist/.
#
# Bundles exactly the resource files the app actually reads at runtime
# (see RESOURCES/IMAGES_DIR usage in document_controller.py,
# vra_structure.py, help_dialog.py, and main_window.py/
# background_image_widget.py) -- named individually rather than the
# whole vra_editor/resources/ folder, so a stray file dropped in there
# (an exported doc, a scratch copy) doesn't silently end up in a
# shipped build. Each lands at the same relative path the app resolves
# via Path(__file__).resolve().parent(.parent) / "resources" or
# "images", which holds true inside a frozen bundle too as long as the
# data files land at that same relative path.

import os
import sys
import tempfile
from pathlib import Path

block_cipher = None
repo_root = Path(SPECPATH).resolve().parent
resources_dir = repo_root / 'vra_editor' / 'resources'
images_dir = repo_root / 'vra_editor' / 'images'
icons_dir = repo_root / 'packaging' / 'icons'

# Set by the release workflow from the pushed tag (e.g. "1.2.3" from
# "v1.2.3") so a tagged CI build's .app reports the same version as the
# tag it came from; a plain local build (env var unset) keeps this
# fallback, matching VRA_Editor.iss's #ifndef MyAppVersion default and
# build_linux_deb.sh's packaging/debian/control fallback -- all three
# platforms' "no override" version lives in one place each, but all
# three follow the same env-var-first pattern.
APP_VERSION = os.environ.get('VRA_EDITOR_VERSION', '1.0.0')

# core/update_check.py's get_app_version() reads this back at runtime to
# know its own version (for display in About, and to compare against
# the latest release) -- written to a system temp file rather than
# anywhere under the source tree, so a local build never leaves a
# modified/generated file behind in the actual repo. Named VERSION
# itself, not just placed in a temp dir named that -- a `datas` entry's
# destination is a directory, and PyInstaller keeps the source file's
# own basename when it lands there.
_version_file = Path(tempfile.gettempdir()) / 'VERSION'
_version_file.write_text(APP_VERSION)

RESOURCE_FILES = ['vra_core4.xsd', 'vra_core4_strict.xsd', 'xml.xsd', 'user_manual.md']
IMAGE_FILES = [p.name for p in images_dir.iterdir() if p.is_file()]

# pyexiv2's compiled extension (exiv2api.so/.pyd) links against its
# sibling libexiv2 library with no rpath/DT_NEEDED search path pointing
# at it -- it only resolves at import time because that library happens
# to sit in the same directory the loader falls back to searching
# (dyld on macOS via @rpath fallback; the ELF loader on Linux, where the
# actual on-disk file is an unversioned libexiv2.so despite the compiled
# extension's DT_NEEDED entry naming the SONAME-versioned
# libexiv2.so.28). PyInstaller's own dependency walker can't follow
# either case, so it's added explicitly here, landing next to
# exiv2api.so/.pyd inside the frozen bundle so that same fallback keeps
# working. On Windows this isn't needed -- PyInstaller's walker already
# resolves exiv2.dll fine on its own via plain DLL search order, so the
# glob below simply matches nothing there and EXTRA_BINARIES stays
# empty, same as before. Confirmed via `otool -l`/`DYLD_PRINT_LIBRARIES=1`
# (macOS) and `ldd`/a real Linux build (this gap was silent -- and real
# -- until caught there) against the installed wheel; skipped with a
# warning (not an error) if pyexiv2 isn't installed, so this spec
# doesn't hard-fail for a dev environment missing an optional
# platform-specific piece.
try:
    import pyexiv2
    _pyexiv2_lib_dir = Path(pyexiv2.__file__).resolve().parent / 'lib'
    _libexiv2_lib = (
        next(_pyexiv2_lib_dir.glob('libexiv2*.dylib'), None)
        or next(_pyexiv2_lib_dir.glob('libexiv2*.so*'), None)
    )
except ImportError:
    _libexiv2_lib = None

EXTRA_BINARIES = [(str(_libexiv2_lib), 'pyexiv2/lib')] if _libexiv2_lib else []
if _libexiv2_lib is None:
    print("WARNING: libexiv2 shared library not found next to pyexiv2 -- IPTC/EXIF "
          "features will likely fail to import in the built app.", file=sys.stderr)

a = Analysis(
    [str(repo_root / 'main.py')],
    pathex=[str(repo_root)],
    binaries=EXTRA_BINARIES,
    datas=(
        [(str(resources_dir / name), 'vra_editor/resources') for name in RESOURCE_FILES]
        + [(str(images_dir / name), 'vra_editor/images') for name in IMAGE_FILES]
        + [(str(_version_file), 'vra_editor/resources')]
    ),
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VRA Editor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icons_dir / 'app_icon.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='VRA Editor',
)

app = BUNDLE(
    coll,
    name='VRA Editor.app',
    icon=str(icons_dir / 'app_icon.icns'),
    bundle_identifier='com.impactdatametrics.vraeditor',
    info_plist={
        'CFBundleName': 'VRA Editor',
        'CFBundleDisplayName': 'VRA Core 4 XML Editor',
        'CFBundleShortVersionString': APP_VERSION,
        'NSHumanReadableCopyright': 'Copyright © 2026 John Burns and Impact Data Metrics Limited. Licensed under CC BY-NC 4.0.',
        'NSHighResolutionCapable': True,
    },
)
