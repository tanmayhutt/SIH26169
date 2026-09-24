"""Recompute a run's metrics from its per-frame log and check them against its summary.

Every run writes `<label>_frames.csv` (one row per frame) and `<label>_summary.json` (the
metrics). This module rebuilds the metrics from the CSV alone, with the same code that made them
(metrics.summarise), and compares them field by field, so anyone holding the two files can
confirm the reported numbers come from the logged frames and nothing else.

    fsoc-tracker verify results/FSOC_sim_clear_line_seed1_20260924-101530
    fsoc-tracker verify results/batch/20260924_101530/*          # several runs

The CSV holds floats to 4 decimals, so a value counts as reproduced when it agrees within
1e-3 absolute or 1e-4 relative. `fps_wall` depends on the wall clock of the whole run, which the
CSV only samples (t_wall per frame); it is reported but never fails the check.
"""
from __future__ import annotations

import csv
import dataclasses
import json
import math
from pathlib import Path

from .metrics import summarise
from .telemetry import Record

LOOSE = {"fps_wall"}       # wall-clock based: shown, not judged


def load_records(path: Path) -> list[Record]:
    """The per-frame CSV back into Record objects (the columns are Record's fields)."""
    kinds = {f.name: f.type for f in dataclasses.fields(Record)}
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            vals = {}
            for name, kind in kinds.items():
                raw = row.get(name, "")
                if kind in ("int", int):
                    vals[name] = int(float(raw)) if raw not in ("", "nan") else 0
                elif kind in ("float", float):
                    vals[name] = float(raw) if raw != "" else float("nan")
                else:
                    vals[name] = raw
            out.append(Record(**vals))
    return out


def _same(a, b) -> bool:
    if a is None or b is None:
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
            return True
        return abs(a - b) <= max(1e-3, 1e-4 * max(abs(a), abs(b)))
    return a == b


def verify_run(folder: str | Path) -> dict:
    """Rebuild a run's metrics from its CSV and compare them with its summary JSON.
    Returns {"folder", "ok", "checked", "mismatches": [(name, stored, recomputed)], "loose": [...]}."""
    folder = Path(folder)
    frames = sorted(folder.glob("*_frames.csv"))
    summaries = sorted(folder.glob("*_summary.json"))
    if not frames or not summaries:
        return {"folder": str(folder), "ok": False, "checked": 0, "error": "no *_frames.csv and *_summary.json in this folder",
                "mismatches": [], "loose": []}
    stored = json.load(open(summaries[0], encoding="utf-8"))
    records = load_records(frames[0])
    cfg = stored.get("config", {})
    cam = cfg.get("camera", {})
    ifov = float(cam.get("fov_w_deg", 4.0)) / float(cam.get("width", 640))
    wall = max((r.t_wall for r in records), default=0.0)
    # the change descriptions are text in the summary; the segments themselves come from the CSV
    changes = [{"segment": g["segment"], "what": g["change"]} for g in stored.get("segments", []) if g.get("segment", 0) > 0]
    again = summarise(records, ifov, wall, changes)
    mismatches, loose, checked = [], [], 0
    for name, value in (stored.get("values") or {}).items():
        mine = again.values.get(name)
        if name in LOOSE:
            loose.append((name, value, mine))
            continue
        checked += 1
        if not _same(value, mine):
            mismatches.append((name, value, mine))
    for name, ok in (stored.get("passed") or {}).items():
        checked += 1
        if again.passed.get(name) != ok:
            mismatches.append((f"passed.{name}", ok, again.passed.get(name)))
    for a, b in zip(stored.get("segments", []), again.segments):
        for key in ("frames", "tracking_err_mean_px", "centroid_err_mean_px", "lock_retention_pct"):
            checked += 1
            if not _same(a.get(key), b.get(key)):
                mismatches.append((f"segment{a.get('segment')}.{key}", a.get(key), b.get(key)))
    return {"folder": str(folder), "ok": not mismatches, "checked": checked, "mismatches": mismatches, "loose": loose,
            "frames": len(records)}


def print_result(r: dict) -> None:
    if r.get("error"):
        print(f"FAIL  {r['folder']}: {r['error']}")
        return
    head = "OK  " if r["ok"] else "FAIL"
    print(f"{head}  {r['folder']}: {r['checked']} values recomputed from {r['frames']} frames, "
          f"{len(r['mismatches'])} differ")
    for name, a, b in r["mismatches"]:
        print(f"        {name}: summary {a!r}, recomputed {b!r}")
