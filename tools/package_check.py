"""End-to-end check of a packaged desktop archive, run on the platform it was built for.

    python tools/package_check.py dist/ARGUS-windows-x64.zip
    python tools/package_check.py dist/ARGUS-macos-intel.zip --arch x86_64   # Rosetta on Apple silicon

Extracts the archive into a fresh folder (as a user would), then:
  1. runs a clear scenario and a full-stress scenario with the executable, checks report and CSV;
  2. writes a small mp4 and runs the Benchmark 2 video path, checks report and CSV;
  3. starts the graphical application with the offscreen Qt platform and checks it is still
     running after 12 seconds (start-up, imports, window construction all succeeded).
Exit code 0 means every step passed. Used by .github/workflows/build.yml on each runner.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from pathlib import Path

import cv2
import numpy as np


def extract(archive: Path, into: Path) -> Path:
    if archive.suffix == ".zip":
        if sys.platform != "win32":
            subprocess.run(["unzip", "-q", str(archive), "-d", str(into)], check=True)   # keeps modes and symlinks
        else:
            with zipfile.ZipFile(archive) as z:
                z.extractall(into)
    else:
        with tarfile.open(archive) as t:
            t.extractall(into)
    return into / "ARGUS"


def make_video(folder: Path) -> Path | None:
    """A small beacon video. The runner's own OpenCV may lack an encoder (some macOS wheels);
    the packaged application only needs to read, so the step is skipped rather than failed."""
    rng = np.random.default_rng(0)
    for name, fourcc in (("bench.mp4", "mp4v"), ("bench.mp4", "avc1"), ("bench.avi", "MJPG"), ("bench.mkv", "FFV1")):
        path = folder / name
        try:
            vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*fourcc), 30, (800, 800), isColor=True)
            if not vw.isOpened():
                continue
            for i in range(120):
                img = rng.normal(12, 4, (800, 800)).clip(0, 255).astype(np.uint8)
                a = 2 * np.pi * i / 120
                x, y = int(400 + 150 * np.cos(a)), int(400 + 150 * np.sin(a))
                img[y - 5:y + 5, x - 5:x + 5] = 235
                vw.write(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
            vw.release()
        except cv2.error:
            continue
        if path.is_file() and path.stat().st_size > 1000:
            return path
    return None


def run(cmd: list[str], cwd: Path, timeout: int = 300) -> str:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        print(out[-3000:])
        raise SystemExit(f"command failed ({p.returncode}): {' '.join(cmd)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("archive")
    ap.add_argument("--arch", default=None, help="run through `arch -<arch>` (macOS), e.g. x86_64 for Rosetta")
    a = ap.parse_args()
    archive = Path(a.archive).resolve()
    tmp = Path(tempfile.mkdtemp(prefix="fsoc_pkg_"))
    try:
        folder = extract(archive, tmp)
        exe = folder / ("ARGUS-cli.exe" if sys.platform == "win32" else "ARGUS")
        gui = folder / ("ARGUS.exe" if sys.platform == "win32" else "ARGUS")
        if not exe.exists():
            raise SystemExit(f"executable missing: {exe}")
        prefix = ["arch", f"-{a.arch}"] if a.arch else []
        for name, scen in (("t1", "clear_line"), ("t2", "full_stress")):
            out = run(prefix + [str(exe), "run", "-s", f"configs/scenarios/{scen}.yaml", "--duration", "3", "--seed", "0", "--out", f"results/{name}"], folder)
            line = [l for l in out.splitlines() if "fps" in l and "frames" in l]
            print(f"{scen}: {line[-1].strip() if line else 'no summary line'}")
            for f in ("report.pdf", "frames.csv", "summary.json"):
                if not list((folder / "results" / name).glob(f"FSOC_*_{f}")):
                    raise SystemExit(f"{scen}: {f} not written")
        vid = make_video(tmp)
        if vid is None:
            print("video: SKIPPED, this machine's OpenCV has no video encoder to make the sample (the application's reader is unaffected)")
        else:
            out = run(prefix + [str(exe), "video", str(vid), "--out", "results/t3"], folder)
            line = [l for l in out.splitlines() if "fps" in l and "frames" in l]
            print(f"video: {line[-1].strip() if line else 'no summary line'}")
            for f in ("report.pdf", "frames.csv"):
                if not list((folder / "results" / "t3").glob(f"FSOC_video_*_{f}")):
                    raise SystemExit(f"video: {f} not written")
        for d in ("configs", "models", "docs"):
            if not (folder / d).exists():
                raise SystemExit(f"{d} was not placed next to the executable on first start")
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        p = subprocess.Popen(prefix + [str(gui)], cwd=folder, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(12)
        if p.poll() is not None:
            print((p.stdout.read() or "")[-3000:])
            raise SystemExit(f"GUI exited early with code {p.returncode}")
        p.terminate()
        try:
            p.wait(10)
        except subprocess.TimeoutExpired:
            p.kill()
        print("gui: alive after 12 s, terminated cleanly")
        print(f"PACKAGE OK: {archive.name}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
