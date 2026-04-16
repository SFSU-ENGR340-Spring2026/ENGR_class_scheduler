# ENGR_Scheduler.spec
# PyInstaller spec file — builds the ENGR Class Scheduler into a standalone Mac .app.
#
# ── PREREQUISITES ──────────────────────────────────────────────────────────────
#   pip install pyinstaller ortools PySide6 plotly
#
# ── HOW TO BUILD ───────────────────────────────────────────────────────────────
#   1. Put all five files in one folder:
#        gui.py  solver.py  db.py  tabs.py  db_classes.db  ENGR_Scheduler.spec
#   2. Open Terminal in that folder and run:
#        pyinstaller ENGR_Scheduler.spec
#   3. Your app appears at:   dist/ENGR_Scheduler.app
#
# ── HOW TO DISTRIBUTE ──────────────────────────────────────────────────────────
#   • Zip the entire dist/ folder and send it, OR
#   • Copy ENGR_Scheduler.app to /Applications.
#   • On first launch the app copies db_classes.db next to itself automatically.
#     Users can then point the app at any folder containing their own DB via Browse.
# ───────────────────────────────────────────────────────────────────────────────

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# NOTE: block_cipher was removed in PyInstaller 6 — do not add it back.

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
        # Bundle the default database. On first launch gui.py copies it from
        # _MEIPASS to the user-writable project folder automatically.
        + [("db_classes.db", ".")]
    ),
    hiddenimports=[
        # OR-Tools
        "ortools",
        "ortools.sat",
        "ortools.sat.python",
        "ortools.sat.python.cp_model",
        # Plotly
        "plotly",
        "plotly.graph_objects",
        "plotly.io",
        # PySide6 / Qt
        "PySide6",
        "PySide6.QtCore",
        "PySide6.QtGui",
        "PySide6.QtWidgets",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineCore",
        "PySide6.QtNetwork",
        # stdlib
        "sqlite3",
        "collections",
        "pathlib",
        "shutil",
        "subprocess",
        "platform",
        # project modules
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
    console=False,           # no Terminal window
    disable_windowed_traceback=False,
    target_arch=None,  # native arch only; set "universal2" only if ALL deps are fat binaries
    codesign_identity=None,
    entitlements_file=None,
    icon=None,               # replace with "icon.icns" if you have one
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

app = BUNDLE(
    coll,
    name="ENGR_Scheduler.app",
    icon=None,               # replace with "icon.icns" if you have one
    bundle_identifier="edu.sfsu.engr.scheduler",
    info_plist={
        "NSHighResolutionCapable": True,
        "NSPrincipalClass": "NSApplication",
        # Allow the WebEngine to load local/CDN content for the Gantt chart
        "NSAppTransportSecurity": {
            "NSAllowsArbitraryLoads": True,
        },
    },
)
