"""ARGUS against a deliberately simple baseline, on the same scenarios, seeds and disturbances.

The baseline (fsoc_tracker/control/baseline.py) takes the brightest spot and steers toward it with
proportional control: no matched filter, no confirmation, no prediction, no gating, no identity,
no faint path, no search. Running both through the same simulator, gimbal and metrics shows what
each part of the design is worth. Every scenario is listed, including any where the baseline does
as well or better; there is no single overall score.

    python tools/compare_trackers.py                       # the scenario pack, seeds 0-2, 15 s
    python tools/compare_trackers.py --seeds 0-4 --duration 20
    -> docs/BASELINE_COMPARISON.md
"""
from __future__ import annotations

import argparse
import math
import platform
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fsoc_tracker.engine.config import RunConfig  # noqa: E402
from fsoc_tracker.engine.metrics import SPEC  # noqa: E402
from fsoc_tracker.engine.simulation import Simulation  # noqa: E402

KEYS = ("acquisition_time_s", "tracking_err_mean_px", "centroid_err_mean_px", "lock_retention_pct")


def run(path: Path, seed: int, duration: float, algorithm: str) -> dict:
    c = RunConfig.load(path)
    c.seed, c.duration_s, c.tracker.algorithm = seed, duration, algorithm
    s = Simulation(c, None, write_csv=False).run()
    v = dict(s.values)
    v["passes"] = all(ok for ok in s.passed.values() if ok is not None)
    return v


def agg(rows: list[dict], key: str) -> float:
    a = np.array([r.get(key, float("nan")) for r in rows], float)
    return float(np.nanmean(a)) if np.isfinite(a).any() else float("nan")


def fmt(x: float, unit: str) -> str:
    return "never" if (unit == "s" and not math.isfinite(x)) else ("n/a" if not math.isfinite(x) else f"{x:.2f}{unit}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="0-2")
    ap.add_argument("--duration", type=float, default=15.0)
    ap.add_argument("--out", default=str(ROOT / "docs" / "BASELINE_COMPARISON.md"))
    a = ap.parse_args(argv)
    lo, _, hi = a.seeds.partition("-")
    seeds = list(range(int(lo), int(hi or lo) + 1))
    scenarios = sorted(p for p in (ROOT / "configs" / "scenarios").glob("*.yaml") if not p.name.startswith("TEMPLATE"))
    lines = ["# ARGUS against a simple baseline", "",
             f"Measured by `tools/compare_trackers.py` on {time.strftime('%Y-%m-%d')} ({platform.system()} {platform.machine()}): "
             f"every scenario in `configs/scenarios`, seeds {a.seeds}, {a.duration:g} s runs, the same simulator, gimbal "
             "limits and metrics for both. The baseline (`fsoc_tracker/control/baseline.py`) takes the brightest spot and "
             "steers toward it with proportional control; it has no matched filter, confirmation, prediction, gating, "
             "identity, faint path or search. Means over the seeds; `n/a` means no seed acquired, so there is no error to average. \"PS pass\" counts the "
             "runs that meet every PS performance limit (rows 16 to 20). Every scenario is listed, including any where the "
             "baseline does as well.", "",
             "| Scenario | Acquisition (s) ARGUS / baseline | Tracking error (px) | Centroiding error (px) | Lock (%) | PS pass |",
             "|---|---|---|---|---|---|"]
    tally = {"argus": 0, "baseline": 0, "runs": 0}
    for path in scenarios:
        res = {alg: [run(path, sd, a.duration, alg) for sd in seeds] for alg in ("argus", "baseline")}
        n = len(seeds)
        pa, pb = sum(r["passes"] for r in res["argus"]), sum(r["passes"] for r in res["baseline"])
        tally["argus"] += pa; tally["baseline"] += pb; tally["runs"] += n
        cell = lambda k, u: f"{fmt(agg(res['argus'], k), u)} / {fmt(agg(res['baseline'], k), u)}"
        lines.append(f"| {path.stem} | {cell('acquisition_time_s', '')} | {cell('tracking_err_mean_px', '')} | "
                     f"{cell('centroid_err_mean_px', '')} | {cell('lock_retention_pct', '')} | {pa}/{n} / {pb}/{n} |")
        print(lines[-1], flush=True)
    lines += ["", f"Runs meeting every PS limit: ARGUS {tally['argus']} of {tally['runs']}, baseline {tally['baseline']} of {tally['runs']}.",
              "", "PS limits used: " + ", ".join(f"{k} {op} {lim:g}" for k, (op, lim) in SPEC.items()) + "."]
    Path(a.out).write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"-> {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
