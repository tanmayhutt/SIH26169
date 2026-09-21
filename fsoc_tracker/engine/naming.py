"""One naming scheme for every run's output.

Folder:  results/FSOC_<kind>_<name>_seed<N>_<YYYYMMDD-HHMMSS>/     kind = sim | video
Files:   <label>_report.pdf   <label>_frames.csv   <label>_summary.json   <label>_scenario.yaml

The label repeats the folder name, so a report copied out of its folder still says which
scenario, seed and time it belongs to. Video runs carry the video's file name instead of a seed.
"""
from __future__ import annotations

import re
import time
from pathlib import Path

FILES = {"report": "report.pdf", "frames": "frames.csv", "summary": "summary.json", "scenario": "scenario.yaml"}


def _clean(text: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip()).strip("-._")
    return text[:48] or "run"


def run_label(cfg, stamp: str | None = None) -> str:
    """FSOC_sim_clear_line_seed3_20260922-101530, or FSOC_video_<file>_20260922-101530."""
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    if cfg.video:
        return f"FSOC_video_{_clean(Path(cfg.video).stem)}_{stamp}"
    return f"FSOC_sim_{_clean(cfg.name)}_seed{cfg.seed}_{stamp}"


def output_paths(out_dir: Path, label: str) -> dict[str, Path]:
    """The four files of a run, named with the run label."""
    return {k: out_dir / f"{label}_{v}" for k, v in FILES.items()}


def label_from_dir(out_dir: Path, cfg) -> str:
    """A run written into a folder that already follows the scheme keeps that label; any other
    folder (an explicit --out, a batch cell) gets a fresh label from the configuration."""
    return out_dir.name if out_dir.name.startswith("FSOC_") else run_label(cfg)
