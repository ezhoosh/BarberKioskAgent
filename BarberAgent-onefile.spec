# -*- mode: python ; coding: utf-8 -*-

import sys

ICON_FILE = "statics/logo.ico" if sys.platform.startswith("win") else "statics/logo.icns"

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=[
        ("statics/YekanBakh-Regular.ttf", "statics"),
        ("statics/YekanBakh-Bold.ttf", "statics"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

# One-file executable (single BarberAgent.exe on Windows)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="BarberAgent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[ICON_FILE],
)

