## What changes and why

<!-- One or two sentences. Link the PS row or document section this relates to. -->

## Checks

- [ ] `python -m pytest` passes
- [ ] Perception, estimation or control changed: regression batch compared with `tools/compare_batches.py`, no run worse (paste the last line)
- [ ] Interface changed: made in `fsoc_tracker/ui_shared.py` so desktop and web stay the same; screenshots checked
- [ ] `python webapp/smoke.py` passes
- [ ] Records updated where affected: `web/progress.json`, `PROGRESS.md`, `COMPLIANCE.md`, `docs/HANDOVER.md`, `docs/KNOWLEDGE_TRANSFER.md`, PDFs
- [ ] Not tuned to a single test video; no competitor code; no secrets committed
