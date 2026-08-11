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

import sys
from pathlib import Path

block_cipher = None
repo_root = Path(SPECPATH).resolve().parent
resources_dir = repo_root / 'vra_editor' / 'resources'
images_dir = repo_root / 'vra_editor' / 'images'

RESOURCE_FILES = ['vra_core4.xsd', 'vra_core4_strict.xsd', 'xml.xsd', 'user_manual.md']
IMAGE_FILES = [p.name for p in images_dir.iterdir() if p.is_file()]

a = Analysis(
    [str(repo_root / 'main.py')],
    pathex=[str(repo_root)],
    binaries=[],
    datas=(
        [(str(resources_dir / name), 'vra_editor/resources') for name in RESOURCE_FILES]
        + [(str(images_dir / name), 'vra_editor/images') for name in IMAGE_FILES]
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
    icon=None,
    bundle_identifier='com.impactdatametrics.vraeditor',
    info_plist={
        'CFBundleName': 'VRA Editor',
        'CFBundleDisplayName': 'VRA Core 4 XML Editor',
        'CFBundleShortVersionString': '1.0.0',
        'NSHumanReadableCopyright': 'Copyright © 2026 John Burns and Impact Data Metrics Limited. Licensed under CC BY-NC 4.0.',
        'NSHighResolutionCapable': True,
    },
)
