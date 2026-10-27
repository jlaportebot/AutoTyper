# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the AutoTyper Windows executable.

Build with:
    pyinstaller --clean --noconfirm AutoTyper.spec

Produces a single, windowed ``AutoTyper.exe`` in ``dist/``.

The icon and the Windows version resource are only applied when the build
runs on Windows, so the spec stays importable on other platforms (CI lints it
and developers can smoke-test the bundle locally).
"""

import os
import sys

block_cipher = None

PROJECT_ROOT = os.path.abspath(os.getcwd())
IS_WINDOWS = sys.platform == "win32"
ICON_PATH = os.path.join(PROJECT_ROOT, "assets", "autotyper.ico")
VERSION_PATH = os.path.join(PROJECT_ROOT, "version_info.txt")

a = Analysis(
    ["main.pyw"],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib",
        "numpy",
        "pandas",
        "PyQt5",
        "PySide2",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="AutoTyper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICON_PATH if IS_WINDOWS else None,
    version=VERSION_PATH if IS_WINDOWS else None,
)
