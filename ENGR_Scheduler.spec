# ENGR_Scheduler.spec
# PyInstaller spec file — builds ENGR Class Scheduler for Mac (.app) and Windows (.exe).
#
# ── PREREQUISITES ──────────────────────────────────────────────────────────────
#   pip install pyinstaller ortools PySide6 plotly
#
# ── HOW TO BUILD ───────────────────────────────────────────────────────────────
#   Put all these files in one folder:
#       gui.py  solver.py  db.py  tabs.py  db_classes.db  ENGR_Scheduler.spec
#
#   Mac:
#       pyinstaller ENGR_Scheduler.spec
#       → dist/ENGR_Scheduler.app
#
#   Windows (run in Command Prompt or PowerShell):
#       pyinstaller ENGR_Scheduler.spec
#       → dist/ENGR_Scheduler/ENGR_Scheduler.exe
#
# ── DISTRIBUTE ─────────────────────────────────────────────────────────────────
#   Mac:     Zip dist/ENGR_Scheduler.app and share, or copy to /Applications
#   Windows: Zip the entire dist/ENGR_Scheduler/ folder and share
# ───────────────────────────────────────────────────────────────────────────────

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

IS_MAC     = sys.platform == "darwin"
IS_WIN     = sys.platform == "win32"

ortools_datas = collect_data_files("ortools")
plotly_datas  = collect_data_files("plotly")
pyside6_datas = collect_data_files("PySide6")
ortools_libs  = collect_dynamic_libs("ortools")

a = Analysis(
    ["gui.py"],
    pathex=["."],
    binaries=ortools_libs,
    datas=(
        ortools_datas
        + plotly_datas
        + pyside6_datas
        + [("db_classes.db", ".")]
    ),
    hiddenimports=[
        "ortools",
        "ortools.sat",
        "ortools.sat.python",
        "ortools.sat.python.cp_model",
        "plotly",
        "plotly.graph_objects",
        "plotly.io",
        "PySide6",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtNetwork",
        "sqlite3",
        "collections",
        "pathlib",
        "shutil",
        "subprocess",
        "platform",
        "db",
        "tabs",
        "solver",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ENGR_Scheduler",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Windows icon (.ico) / Mac icon (.icns) — replace None with path if you have one
    icon="icon.ico" if IS_WIN else ("icon.icns" if IS_MAC else None),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="ENGR_Scheduler",
)

# Mac-only: wrap in .app bundle
if IS_MAC:
    app = BUNDLE(
        coll,
        name="ENGR_Scheduler.app",
        icon="icon.icns" if os.path.exists("icon.icns") else None,
        bundle_identifier="edu.sfsu.engr.scheduler",
        info_plist={
            "NSHighResolutionCapable": True,
            "NSPrincipalClass": "NSApplication",
            "NSAppTransportSecurity": {
                "NSAllowsArbitraryLoads": True,
            },
        },
    )
