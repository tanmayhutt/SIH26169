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


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--commits", type=int, default=40)
    ap.add_argument("--since", default=None, help="date, e.g. 2026-09-20 (overrides --commits)")
    a = ap.parse_args(argv)
    rng = ["--since", a.since] if a.since else ["-n", str(a.commits)]
    log = git("log", *rng, "--format=%h%x09%as%x09%an%x09%s", "--name-only").strip("\n").split("\n\n")
    unrecorded = []
    for block in log:
        lines = [ln for ln in block.strip().split("\n") if ln]
        if not lines or "\t" not in lines[0]:
            continue
        head, files = lines[0].split("\t"), lines[1:]
        code = [f for f in files if f.startswith(CODE) and not f.startswith(IGNORE)]
        recorded = any(f in RECORD for f in files)
        if code and not recorded:
            unrecorded.append((head, code))
    if not unrecorded:
        span = f"since {a.since}" if a.since else f"in the last {a.commits} commits"
        print(f"record check: every application change {span} touched a record file")
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
