"""Command line entry point.

    fsoc-tracker run   --scenario configs/scenarios/clear_line.yaml [--seed N] [--duration S] [--out DIR]
    fsoc-tracker video path/to/file.mp4 [--scenario cfg.yaml] [--out DIR]
    fsoc-tracker batch --scenario a.yaml [b.yaml ...] --seeds 0-49 [--out DIR]
    fsoc-tracker gui
"""
from __future__ import annotations

import argparse
import numpy as np
import json
import sys
import time
from pathlib import Path

from .engine.config import RunConfig
from .engine.naming import run_label
from .engine.report import write_report
from .engine.simulation import Simulation


def _load(path: str | None) -> RunConfig:
    return RunConfig.load(path) if path else RunConfig()


def _run_one(cfg: RunConfig, out: Path, quiet: bool = False) -> dict:
    sim = Simulation(cfg, out)
    t0 = time.perf_counter()

    def prog(i, n):
        if not quiet:
            print(f"\r  {cfg.name} seed {cfg.seed}: frame {i}/{n}", end="", file=sys.stderr)

    summary = sim.run(prog)
    if not quiet:
        print(file=sys.stderr)
    write_report(cfg, sim.telemetry.records, summary, sim.files["report"])
    v = summary.values
    if not quiet:
        print(f"  frames {v.get('frames')}  fps {v.get('fps_mean', 0):.1f}  acq {v.get('acquisition_time_s', float('nan')):.2f}s  "
              f"track err {v.get('tracking_err_mean_px', float('nan')):.2f}px  centroid err {v.get('centroid_err_mean_px', float('nan')):.3f}px  "
              f"tracked {v.get('tracked_pct', 0):.1f}%  lock {v.get('lock_retention_pct', 0):.1f}%  wall {time.perf_counter()-t0:.1f}s")
        print(f"  -> {out}")
    return {"name": cfg.name, "seed": cfg.seed, **v, "passed": summary.passed}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="fsoc-tracker", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run one scenario in the simulator")
    r.add_argument("--scenario", "-s", default=None)
    r.add_argument("--seed", type=int, default=None, help="-1 for a random seed")
    r.add_argument("--duration", type=float, default=None)
    r.add_argument("--out", "-o", default=None)

    v = sub.add_parser("video", help="Benchmark 2: run the tracker on an .mp4 file")
    v.add_argument("path")
    v.add_argument("--scenario", "-s", default=None)
    v.add_argument("--duration", type=float, default=None)
    v.add_argument("--out", "-o", default=None)

    b = sub.add_parser("batch", help="run scenarios over many seeds and aggregate")
    b.add_argument("--scenario", "-s", nargs="+", required=True)
    b.add_argument("--seeds", default="0-9", help="range like 0-49 or list like 1,2,3")
    b.add_argument("--duration", type=float, default=None)
    b.add_argument("--out", "-o", default="results/batch")

    sub.add_parser("gui", help="launch the desktop application")

    a = ap.parse_args(argv)
    stamp = time.strftime("%Y%m%d_%H%M%S")

    if a.cmd == "gui":
        from .gui.app import main as gui_main
        return gui_main()

    if a.cmd == "run":
        cfg = _load(a.scenario)
        if a.seed is not None:
            cfg.seed = a.seed if a.seed >= 0 else int(np.random.default_rng().integers(0, 10 ** 6))
        if a.duration is not None:
            cfg.duration_s = a.duration
        out = Path(a.out) if a.out else Path(cfg.output_dir) / run_label(cfg)
        _run_one(cfg, out)
        return 0

    if a.cmd == "video":
        cfg = _load(a.scenario)
        cfg.video = a.path
        cfg.name = Path(a.path).stem
        cfg.duration_s = a.duration if a.duration is not None else 0.0
        out = Path(a.out) if a.out else Path(cfg.output_dir) / run_label(cfg)
        _run_one(cfg, out)
        return 0

    if a.cmd == "batch":
        seeds = _parse_seeds(a.seeds)
        out = Path(a.out) / stamp
        out.mkdir(parents=True, exist_ok=True)
        rows = []
        for sc in a.scenario:
            for sd in seeds:
                cfg = RunConfig.load(sc)
                cfg.seed = sd
                if a.duration is not None:
                    cfg.duration_s = a.duration
                rows.append(_run_one(cfg, out / f"{cfg.name}_seed{sd}", quiet=True))
                r0 = rows[-1]
                print(f"{cfg.name:<24} seed {sd:<3} acq {r0.get('acquisition_time_s', float('nan')):5.2f}s  "
                      f"err {r0.get('tracking_err_mean_px', float('nan')):6.2f}px  lock {r0.get('lock_retention_pct', 0):5.1f}%  "
                      f"fps {r0.get('fps_mean', 0):5.1f}")
        with open(out / "envelope.json", "w", encoding="utf-8") as f:
            json.dump(rows, f, indent=2)
        _envelope(rows, out / "envelope.md")
        print(f"-> {out}")
        return 0


def _parse_seeds(s: str) -> list[int]:
    if "-" in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(x) for x in s.split(",")]


def _envelope(rows: list[dict], path: Path):
    import numpy as np
    by = {}
    for r in rows:
        by.setdefault(r["name"], []).append(r)
    lines = ["| scenario | runs | acq mean/max (s) | track err mean/max (px) | centroid err mean (px) | lock min (%) | fps min | all pass |",
             "|---|---|---|---|---|---|---|---|"]
    for name, rs in by.items():
        def col(k):
            a = np.array([r.get(k, float('nan')) for r in rs], float)
            a = a[np.isfinite(a)]
            return a
        acq, te, ce, lk, fps = col("acquisition_time_s"), col("tracking_err_mean_px"), col("centroid_err_mean_px"), col("lock_retention_pct"), col("fps_mean")
        allp = all(all(v for v in r["passed"].values() if v is not None) for r in rs)
        f = lambda a, fn: (f"{fn(a):.2f}" if len(a) else "n/a")
        lines.append(f"| {name} | {len(rs)} | {f(acq, np.mean)} / {f(acq, np.max)} | {f(te, np.mean)} / {f(te, np.max)} | {f(ce, np.mean)} | {f(lk, np.min)} | {f(fps, np.min)} | {'yes' if allp else 'no'} |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
