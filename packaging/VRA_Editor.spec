# PyInstaller spec for the VRA Core 4 XML Editor desktop app.
#
# Build (from the repo root, with the project venv active):
#   pyinstaller packaging/VRA_Editor.spec --noconfirm
#
# Produces dist/VRA Editor.app (macOS) or dist/VRA Editor/ (other
# platforms) alongside a matching entry under dist/.
#
# Bundles vra_editor/resources/ (the VRA Core 4 XSD, the W3C xml.xsd it
# imports, and the stylesheet) at the same relative path the app expects
# at runtime, since DocumentController/SchemaValidator locate the XSD via
# Path(__file__).resolve().parent.parent / "resources" -- that resolves
# correctly inside a frozen PyInstaller bundle too, as long as the data
# files land at that same relative path.

import sys
from pathlib import Path

block_cipher = None
repo_root = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(repo_root / 'main.py')],
    pathex=[str(repo_root)],
    binaries=[],
    datas=[
        (str(repo_root / 'vra_editor' / 'resources'), 'vra_editor/resources'),
    ],
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
