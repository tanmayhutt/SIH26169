# ARGUS (SIH26169) rules for agents

These rules apply to every contributor and every AI agent working in this repository. Start with
`docs/HANDOVER.md`: it holds the full project context (design reasons, tried-and-rejected ideas,
verification and release steps), and `docs/KNOWLEDGE_TRANSFER.md` explains the problem statement
and the solution completely. On the project owner's machine the workspace rules in
`/Users/tanmay/Developer/CLAUDE.md` and the local `context.md` also apply.

## The problem statement is the only source of truth

- `26169.pdf` in the project root (ISRO SAC, SIH26169) defines what the system must do. Every
  design choice, default value and readiness claim is justified from it: rows 1 to 25 of its
  parameter table, the eight "shall" functions, the deliverables and the evaluation stages.
- Never tune the tracker, detector or controller to a video or scenario any of us feeds it. Such a
  file may reveal a defect; a change goes in only if it is a general defect inside the PS scope,
  and only after it is proven on the 16-scenario pack with no run worse than before
  (`fsoc-tracker batch -s configs/scenarios/*.yaml --seeds 0-2 --duration 15`, compare with the
  previous batch). If a file is simply harder than the PS describes, report that; do not adapt.
- Readiness means: the evaluators' scenarios (Benchmark 1) and their 30 fps videos covering a
  complete screen with noise and a moving beacon (Benchmark 2). Evaluate against those, not
  against one test file.
- Do not read or borrow from other SIH26169 team repositories. They are competitors; reason from
  the PDF alone.

## Honesty in numbers

- Report measured values only. A limit that is physical (for example the random per-frame
  vibration at the PS maximum) is documented as a limit, with the measurement, never tuned away
  or hidden.
- When a metric can mislead, add the clarifying metric beside it (tracked rate beside lock
  retention) rather than changing the definition.

## Deliverable shape

- The standalone desktop executable is the mandatory deliverable and must work offline with no
  account. The web app, the progress site and any cloud or AI service are additions and must
  never become dependencies of the desktop application.
- Every run writes one folder `results/FSOC_<sim|video>_<name>_seed<N>_<date-time>/` with the
  label prefixed to `_report.pdf`, `_frames.csv`, `_summary.json`, `_scenario.yaml`. Keep that
  scheme; `fsoc_tracker/engine/naming.py` owns it.

## Repository hygiene

- Commit as your own configured git identity. Never pass a `user.email` or `user.name` override
  (on the owner's machine that identity is tanmayhutt) and do not add co-author trailers.
- Commit messages follow the repository convention (short, generic: "updated project").
- Never commit `context.md` or `results/`.
- The desktop app and the web page are one interface: panel fields, tiles, texts and summaries
  live in `fsoc_tracker/ui_shared.py`. Never change one front end alone.
- After an engine change: run `python -m pytest`, the regression batch compared with
  `tools/compare_batches.py` (no run worse), `python webapp/smoke.py`; rebuild the four archives
  through `.github/workflows/build.yml`, publish them with `bash webapp/publish_builds.sh`, and
  redeploy with `bash webapp/deploy.sh`. Update `web/progress.json`, `PROGRESS.md`,
  `COMPLIANCE.md`, `docs/HANDOVER.md` and the PDFs (`docs/build_pdfs.py`) so they say what the
  code does.
