# PyInstaller spec: builds the standalone desktop application.
#   .venv/bin/pyinstaller fsoc_tracker.spec
# Output: dist/ARGUS/  (one folder, run ARGUS inside it; ARGUS-cli.exe on Windows for the terminal)
# Built for Windows, Linux and macOS (Intel and Apple silicon) by .github/workflows/build.yml.
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

import os
root = Path(SPECPATH)
# The user manual and the technical report are kept outside this repository (the team's records
# folder, a sibling named SIH169-records, deliverables/; override with ARGUS_DOCS). When it is
# present they are bundled next to the application, so the Manual button opens the PDF offline.
docs = Path(os.environ.get("ARGUS_DOCS", root.parent / "SIH169-records" / "deliverables"))
datas = [
    (str(root / "configs" / "scenarios"), "configs/scenarios"),
    *[(str(docs / f), "docs") for f in ("USER_MANUAL.pdf", "TECHNICAL_REPORT.pdf") if (docs / f).exists()],
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
    name="ARGUS",
    console=False,
    icon=None,
)
extra = []
if sys.platform == "win32":
    # Windowed executables print nothing on Windows; this second entry point is the command line tool.
    extra.append(EXE(pyz, a.scripts, [], exclude_binaries=True, name="ARGUS-cli", console=True, icon=None))
coll = COLLECT(exe, *extra, a.binaries, a.datas, strip=False, upx=False, name="ARGUS")
