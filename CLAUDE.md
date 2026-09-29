# ARGUS (SIH26169) rules for agents

These rules apply to every contributor and every AI agent working in this repository. The
repository holds the codebase only. The team's record (handover, knowledge transfer, progress,
compliance, testing guide, demo script), the deliverables (user manual, technical report and its
LaTeX source, the presentation) and the shared chat history live in the team's records folder,
kept beside this repository as `../SIH169-records` on each teammate's machine and shared privately
by the team, never through this repository. Read `../SIH169-records/record/HANDOVER.md` and
`../SIH169-records/record/KNOWLEDGE_TRANSFER.md` before changing anything; if the folder is missing,
ask the project owner for it.

## The problem statement is the only source of truth

- The problem statement (ISRO SAC, SIH26169; `26169.pdf` in the records folder) defines what the
  system must do. Every design choice, default value and readiness claim is justified from it:
  rows 1 to 25 of its parameter table, the eight "shall" functions, the deliverables and the
  evaluation stages.
- Never tune the tracker, detector or controller to a video or scenario any of us feeds it. Such a
  file may reveal a defect; a change goes in only if it is a general defect inside the PS scope,
  and only after it is proven on the scenario pack with no run worse than before
  (`fsoc-tracker batch -s configs/scenarios/*.yaml --seeds 0-2 --duration 15`, compare with the
  previous batch using `tools/compare_batches.py`). If a file is simply harder than the PS
  describes, report that; do not adapt.
- Readiness means the evaluators' scenarios (Benchmark 1) and their 30 fps videos covering a
  complete screen with noise and a moving beacon (Benchmark 2).
- Do not read or borrow from other SIH26169 team repositories. They are competitors.

## Honesty in numbers

- Report measured values only. A physical limit (for example the random per-frame vibration at
  the PS maximum) is documented as a limit, with the measurement, never tuned away or hidden.
- When a metric can mislead, add the clarifying metric beside it (tracked rate beside lock
  retention) rather than changing the definition.

## Deliverable shape

- The standalone desktop executable is the mandatory deliverable and must work offline with no
  account. The web app, the progress site and any cloud or AI service are additions and must
  never become dependencies of the desktop application.
- Every run writes one folder `results/FSOC_<sim|video>_<name>_seed<N>_<date-time>/` with the
  label prefixed to `_report.pdf`, `_frames.csv`, `_summary.json`, `_scenario.yaml`.
  `fsoc_tracker/engine/naming.py` owns that scheme.
- The desktop app and the web page are one interface: panel fields, tiles, texts and summaries
  live in `fsoc_tracker/ui_shared.py`. Never change one front end alone.

## Keep the record current, in the records folder

Every change another person would need to know about is written up in the records folder in the
same session as the change: `record/HANDOVER.md` (how it works now, why, the history paragraph),
`record/KNOWLEDGE_TRANSFER.md` (the step it changes, the timeline, ideas tried and dropped, measured
results and limits), `record/PROGRESS.md` and `site/progress.json`, `record/COMPLIANCE.md` when a PS
item is affected, the manual and the report (`sources/`, built into `deliverables/` by
`tools/build_pdfs.py`) when the user
sees the change or a number changes. Record decisions and their reasons and measured numbers in
plain language. Run `python tools/ps_audit.py` after engine changes.

The shared chat history is `../SIH169-records/record/CHAT_LOG.md`. Run
`python ../SIH169-records/tools/chat_history.py sync` at the start of every task, before every
commit and when the session ends; it appends this machine's Claude Code sessions about this
repository. Never edit that file by hand and never put clock times in it. Exact strings that must
not appear go in `../SIH169-records/.chat_redact`, one per line.

## Repository hygiene

- Commit as your own configured git identity. Never pass a `user.email` or `user.name` override
  and do not add co-author trailers.
- Commit messages follow the repository convention (short, generic: "updated project").
- Never commit `context.md`, `results/`, or anything from the records folder (documents, PDFs,
  presentations, chat logs, screenshots). The repository is the codebase.
- After an engine change: run `python -m pytest`, the regression batch compared with
  `tools/compare_batches.py` (no run worse), `python webapp/smoke.py`; rebuild the archives
  (Windows and Linux through `.github/workflows/build.yml`, run by hand; the two macOS ones with
  `bash tools/build_macos.sh` on an Apple silicon Mac); redeploy with `bash webapp/deploy.sh`,
  which also publishes the progress site and the documents from the records folder when present.
