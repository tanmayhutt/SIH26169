# PyInstaller spec: builds the standalone desktop application.
#   .venv/bin/pyinstaller fsoc_tracker.spec
# Output: dist/FSOC-Tracker/  (one folder, run FSOC-Tracker inside it; FSOC-Tracker-cli.exe on Windows for the terminal)
# Built for Windows, Linux and macOS (Intel and Apple silicon) by .github/workflows/build.yml.
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

root = Path(SPECPATH)
datas = [
    (str(root / "configs" / "scenarios"), "configs/scenarios"),
    (str(root / "docs" / "USER_MANUAL.md"), "docs"),
    *([(str(root / "docs" / "USER_MANUAL.pdf"), "docs")] if (root / "docs" / "USER_MANUAL.pdf").exists() else []),
    *([(str(root / "docs" / "TECHNICAL_REPORT.pdf"), "docs")] if (root / "docs" / "TECHNICAL_REPORT.pdf").exists() else []),
]
if (root / "models" / "beacon_heatmap.onnx").exists():
    datas.append((str(root / "models" / "beacon_heatmap.onnx"), "models"))
datas += collect_data_files("pyqtgraph", includes=["**/*.ui", "**/*.png", "**/*.svg"])

hidden = collect_submodules("fsoc_tracker") + ["onnxruntime", "scipy.optimize", "matplotlib.backends.backend_pdf",
                                               "matplotlib.backends.backend_agg", "pyqtgraph.graphicsItems"]

a = Analysis(
    [str(root / "fsoc_tracker" / "launcher.py")],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    excludes=["torch", "onnx", "tkinter", "IPython", "jupyter", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="FSOC-Tracker",
    console=False,
    icon=None,
)
extra = []
if sys.platform == "win32":
    # Windowed executables print nothing on Windows; this second entry point is the command line tool.
    extra.append(EXE(pyz, a.scripts, [], exclude_binaries=True, name="FSOC-Tracker-cli", console=True, icon=None))
coll = COLLECT(exe, *extra, a.binaries, a.datas, strip=False, upx=False, name="FSOC-Tracker")
