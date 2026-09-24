"""Find code changes that the shared record does not mention yet.

The documents (HANDOVER, KNOWLEDGE_TRANSFER, PROGRESS, progress.json, COMPLIANCE, manual, report)
are the team's shared memory. This tool walks the recent commits and flags every commit that
changed the application but touched none of the record files, so whoever starts a session can
write the missing entries before doing anything else.

    python tools/record_check.py             # last 40 commits
    python tools/record_check.py --since 2026-09-20
    python tools/record_check.py --commits 100

Exit code 1 when something is unrecorded, so it can gate a pull request.
"""
from __future__ import annotations

import argparse
import subprocess
import sys

CODE = ("fsoc_tracker/", "webapp/server.py", "webapp/static/", "configs/", "models/", "tools/", ".github/workflows/", "fsoc_tracker.spec", "pyproject.toml")
RECORD = ("docs/HANDOVER.md", "docs/KNOWLEDGE_TRANSFER.md", "PROGRESS.md", "web/progress.json", "COMPLIANCE.md",
          "docs/USER_MANUAL.md", "docs/TECHNICAL_REPORT.md", "docs/TESTING_GUIDE.md", "docs/PS_AUDIT.md", "CLAUDE.md", "README.md")
IGNORE = ("tests/", "docs/", "context.md")   # tests and docs alone are not an application change
# Code commits written up in a later commit instead of their own (most from before the
# same-commit rule in CLAUDE.md). Checked by hand: the later commit is a descendant and edits the
# record files about that change. New work carries its record update in the same commit.
RECORDED_LATER = {"2bcaee6": "fc4b620", "728cd20": "fc4b620", "e025e91": "fc4b620", "286e508": "fc4b620",
                  "c3a1517": "55c2778", "84dc899": "55c2778", "01750ff": "55c2778", "2905bd7": "3db51ba",
                  "a60a137": "960c02d", "5b11160": "dbc3cf7"}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--commits", type=int, default=40)
    ap.add_argument("--since", default=None, help="date, e.g. 2026-09-20 (overrides --commits)")
    a = ap.parse_args(argv)
    rng = ["--since", a.since] if a.since else ["-n", str(a.commits)]
    # every commit starts with a NUL marker: git puts a blank line between a commit's header and
    # its file list, so splitting on blank lines would separate each header from its files
    log = git("log", *rng, "--format=%x00%h%x09%as%x09%an%x09%s", "--name-only").split("\x00")
    unrecorded, later = [], []
    for block in log:
        lines = [ln for ln in block.strip().split("\n") if ln]
        if not lines or "\t" not in lines[0]:
            continue
        head, files = lines[0].split("\t"), lines[1:]
        code = [f for f in files if f.startswith(CODE) and not f.startswith(IGNORE)]
        recorded = any(f in RECORD for f in files)
        if code and not recorded and head[0][:7] in RECORDED_LATER:
            later.append((head[0][:7], RECORDED_LATER[head[0][:7]]))
        elif code and not recorded:
            unrecorded.append((head, code))
    if later:
        print("record check: written up in a later commit (before the same-commit rule): "
              + ", ".join(f"{c} in {r}" for c, r in later))
    if not unrecorded:
        span = f"since {a.since}" if a.since else f"in the last {a.commits} commits"
        print(f"record check: every other application change {span} touched a record file" if later
              else f"record check: every application change {span} touched a record file")
        return 0
    print("record check: these commits changed the application but no record file. Write them up "
          "(docs/HANDOVER.md, docs/KNOWLEDGE_TRANSFER.md, PROGRESS.md, web/progress.json; see CLAUDE.md, Keep the record current):")
    for (sha, date, who, msg), code in unrecorded:
        print(f"  {sha} {date} {who}: {msg}")
        for f in code[:6]:
            print(f"      {f}")
        if len(code) > 6:
            print(f"      ... and {len(code) - 6} more")
    return 1


if __name__ == "__main__":
    sys.exit(main())
