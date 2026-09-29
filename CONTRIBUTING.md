# Contributing

1. Install: `python -m venv .venv`, activate it, `pip install -e ".[dev,web]"`.
2. Before changing the tracker, detector or controller, run the regression batch and keep it:
   `fsoc-tracker batch -s configs/scenarios/*.yaml --seeds 0-2 --duration 15 --out results/before`.
3. Make the change. Keep modules documented (a docstring at the top of every module) and the two
   front ends in step through `fsoc_tracker/ui_shared.py`.
4. Verify: `python -m pytest`, `python tools/ps_audit.py`, `python webapp/smoke.py`, and the batch
   again, compared with `python tools/compare_batches.py results/before results/after`. No run may
   be worse. A change that only helps one video or scenario does not go in.
5. Commit with your own git identity and the message convention ("updated project"). Do not commit
   `results/`, `context.md` or any document, PDF or presentation: the repository is the codebase.
6. Write the change up in the team's records folder (`../SIH169-records`, see `CLAUDE.md`), which is
   shared privately by the team.
