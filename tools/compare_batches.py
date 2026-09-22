"""Compare two regression batches run by run, the check every engine change must pass.

    fsoc-tracker batch -s configs/scenarios/*.yaml --seeds 0-2 --duration 15 --out results/batch_before
    ... change the code ...
    fsoc-tracker batch -s configs/scenarios/*.yaml --seeds 0-2 --duration 15 --out results/batch_after
    python tools/compare_batches.py results/batch_before results/batch_after

A run counts as worse when lock retention drops by more than 2 points or the mean tracking error
grows by more than 20 percent plus 1 px. Exit code 1 if any run is worse. FPS is printed but not
judged, because it depends on what else the machine is doing.
"""
from __future__ import annotations

import glob
import json
import os
import sys


def load(root: str) -> dict:
    out = {}
    for d in glob.glob(os.path.join(root, "*", "*_seed*")) + glob.glob(os.path.join(root, "*_seed*")):
        sj = glob.glob(os.path.join(d, "*summary.json"))
        if sj:
            out[os.path.basename(d)] = json.load(open(sj[0]))["values"]
    return out


def f(x) -> str:
    return "%.2f" % x if isinstance(x, (int, float)) and x == x else "n/a"


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__); return 2
    before, after = load(sys.argv[1]), load(sys.argv[2])
    if not after:
        print("no runs found in", sys.argv[2]); return 2
    worse = better = same = new = 0
    for k in sorted(after):
        vn = after[k]
        if k not in before:
            new += 1; print(f"NEW    {k:30s} lock {f(vn.get('lock_retention_pct'))}"); continue
        vb = before[k]
        lb, ln = vb.get("lock_retention_pct") or 0, vn.get("lock_retention_pct") or 0
        eb, en = vb.get("tracking_err_mean_px"), vn.get("tracking_err_mean_px")
        bad = ln < lb - 2 or (en == en and eb == eb and en is not None and eb is not None and en > eb * 1.2 + 1)
        good = ln > lb + 2
        tag = "WORSE " if bad else ("better" if good else "same  ")
        worse += bad; better += good and not bad; same += not bad and not good
        print(f"{tag} {k:30s} acq {f(vb.get('acquisition_time_s'))}>{f(vn.get('acquisition_time_s'))}  err {f(eb)}>{f(en)}  "
              f"lock {f(lb)}>{f(ln)}  fps {f(vb.get('fps_mean'))}>{f(vn.get('fps_mean'))}")
    print(f"\nruns compared {same + worse + better}: same {same}, better {better}, worse {worse}; new {new}")
    return 1 if worse else 0


if __name__ == "__main__":
    sys.exit(main())
