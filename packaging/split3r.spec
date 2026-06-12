# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Split3r Clone.

Build from the repository root with:
    pyinstaller packaging/split3r.spec --clean --noconfirm
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).resolve().parent
if ROOT.name == "packaging":
    ROOT = ROOT.parent

APP_NAME = "Split3rClone"

_datas = []
_binaries = []
_hiddenimports = []


def _collect_package(package: str) -> None:
    """Collect package metadata/binaries defensively for heavy GUI/VTK deps."""
    try:
        datas, binaries, hiddenimports = collect_all(package)
    except Exception:
        datas, binaries, hiddenimports = [], [], collect_submodules(package)
    _datas.extend(datas)
    _binaries.extend(binaries)
    _hiddenimports.extend(hiddenimports)


for _package in (
    "PyQt6",
    "pyvista",
    "pyvistaqt",
    "vtk",
    "vtkmodules",
    "trimesh",
    "networkx",
    "lxml",
    "scipy",
    "matplotlib",
):
    _collect_package(_package)

# Keep the app package explicit and include small intentionally-versioned assets.
_hiddenimports.extend(collect_submodules("app"))
if (ROOT / "assets").exists():
    _datas.append((str(ROOT / "assets"), "assets"))

_excludes = [
    "pytest",
    "tests",
    "cv2",
    "moviepy",
    "speech_recognition",
]

_a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=_binaries,
    datas=_datas,
    hiddenimports=sorted(set(_hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=_excludes,
    noarchive=False,
    optimize=0,
)

_pyz = PYZ(_a.pure)

_exe = EXE(
    _pyz,
    _a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
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
)

_coll = COLLECT(
    _exe,
    _a.binaries,
    _a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
