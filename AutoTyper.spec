# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for AutoTyper on Windows, macOS and Linux.

Build with:
    pyinstaller --clean --noconfirm AutoTyper.spec

What it produces depends on the operating system running the build:

    Windows  dist/AutoTyper.exe   one-file, windowed, icon + version resource
    macOS    dist/AutoTyper.app   windowed .app bundle (one-dir inside the bundle)
    Linux    dist/AutoTyper       one-file, windowed executable

PyInstaller cannot cross-compile, so each platform is built on its own runner.
Every platform-specific setting is chosen with the ``IS_*`` flags below, which
keeps the spec evaluable on any machine (CI lints it and the test suite
executes it against fake PyInstaller classes for all three platforms).
"""

import os
import sys

block_cipher = None

PROJECT_ROOT = os.path.abspath(os.getcwd())
sys.path.insert(0, PROJECT_ROOT)

from autotyper import __version__ as APP_VERSION  # noqa: E402

APP_NAME = "AutoTyper"
BUNDLE_IDENTIFIER = "com.jlaportebot.autotyper"
MACOS_MINIMUM_VERSION = "11.0"
COPYRIGHT = "© 2026 jlaportebot"

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

ICON_WINDOWS = os.path.join(PROJECT_ROOT, "assets", "autotyper.ico")
ICON_MACOS = os.path.join(PROJECT_ROOT, "assets", "autotyper.icns")
ICON_LINUX = os.path.join(PROJECT_ROOT, "assets", "autotyper.png")
VERSION_PATH = os.path.join(PROJECT_ROOT, "version_info.txt")

# The input backends are imported lazily, so name the third-party pieces they
# need explicitly. The frozen app then has the same backend as a source install.
PLATFORM_HIDDEN_IMPORTS = {
    "windows": [],
    "macos": ["Quartz", "AppKit", "objc", "Foundation", "ApplicationServices", "HIServices"],
    "linux": ["Xlib", "Xlib.ext.xtest", "Xlib.protocol.event"],
}

if IS_WINDOWS:
    platform_key, icon, version = "windows", ICON_WINDOWS, VERSION_PATH
elif IS_MACOS:
    platform_key, icon, version = "macos", None, None
else:
    platform_key, icon, version = "linux", ICON_LINUX, None

a = Analysis(
    ["main.pyw"],
    pathex=[PROJECT_ROOT],
    binaries=[],
    datas=[],
    hiddenimports=PLATFORM_HIDDEN_IMPORTS[platform_key],
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

exe_options = dict(
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=IS_WINDOWS,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon,
    version=version,
)

if IS_MACOS:
    # A .app bundle is a folder, so the executable inside it stays one-dir:
    # it starts faster than a self-extracting one-file build and codesigns cleanly.
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **exe_options)
    collected = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name=APP_NAME,
    )
    app = BUNDLE(
        collected,
        name=APP_NAME + ".app",
        icon=ICON_MACOS,
        bundle_identifier=BUNDLE_IDENTIFIER,
        info_plist={
            "CFBundleName": APP_NAME,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleIdentifier": BUNDLE_IDENTIFIER,
            "CFBundleShortVersionString": APP_VERSION,
            "CFBundleVersion": APP_VERSION,
            "CFBundleExecutable": APP_NAME,
            "LSMinimumSystemVersion": MACOS_MINIMUM_VERSION,
            "NSHighResolutionCapable": True,
            "NSHumanReadableCopyright": COPYRIGHT,
        },
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [], **exe_options)
