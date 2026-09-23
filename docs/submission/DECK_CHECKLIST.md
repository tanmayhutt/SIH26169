# Presentation checklist

`LAKSHYA_SIH2026_26169.pdf` in this folder is the current submission deck. Corrections were made
directly in the PDF, so the source presentation file may not have them. Before exporting a new
version, make sure the deck still says all of this. Every number comes from `docs/KNOWLEDGE_TRANSFER.md`
Part D; never round a limit away.

| Slide | Must say |
|---|---|
| 1 | Team ID (still to fill in) |
| 2 | OBSERVE: the tracker watches the whole 2000 x 2000 px (12.5 degree) scene because the PS asks it to "observe the environment"; hard mode limits it to the camera window |
| 4 | Engine: one config field per PS row, all 25 rows |
| 5 | Benchmark 2 screenshot taken mid-run (TRACK locked), not "video ready"; caption says our measured centre is logged every frame (`det_x`, `det_y`) for comparison with the evaluators' values |
| 5 | Stress caption: 57 FPS is with live drawing; the 14.3 px error is the injected shake |
| 5 | Repo link marked "private; access on request"; demo video link filled in (currently the site downloads page, login needed) |
| 6 | Faint beacon acquisition 1.3 to 5.5 s (one seed in ten took 5.5 s) |
| 6 | A hard mode row: 3 to 12 s, 7 to 12 px, 100 %, "By design" |
| 8 | Reference [18]: the technical report has 12 pages |
| 8 | Coverage (25 of 25 rows, 8 of 8 "shall", 5 of 5 deliverables), performance log fields, metric definitions (lock, tracking error, centroiding error), known limits |
