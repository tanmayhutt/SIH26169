# ARGUS against a simple baseline

Measured by `tools/compare_trackers.py` on 2026-09-24 (Darwin arm64): every scenario in `configs/scenarios`, seeds 0-2, 15 s runs, the same simulator, gimbal limits and metrics for both. The baseline (`fsoc_tracker/control/baseline.py`) takes the brightest spot and steers toward it with proportional control; it has no matched filter, confirmation, prediction, gating, identity, faint path or search. Means over the seeds; `n/a` means no seed acquired, so there is no error to average. "PS pass" counts the runs that meet every PS performance limit (rows 16 to 20). Every scenario is listed, including any where the baseline does as well.

| Scenario | Acquisition (s) ARGUS / baseline | Tracking error (px) | Centroiding error (px) | Lock (%) | PS pass |
|---|---|---|---|---|---|
| beacon_shapes | 0.67 / n/a | 2.94 / n/a | 0.05 / 1.29 | 100.00 / 0.00 | 3/3 / 0/3 |
| clear_circular | 1.03 / 0.37 | 2.21 / 39.99 | 0.01 / 0.05 | 100.00 / 0.46 | 3/3 / 0/3 |
| clear_figure8 | 1.03 / 0.97 | 3.09 / 37.78 | 0.01 / 0.05 | 100.00 / 26.94 | 3/3 / 0/3 |
| clear_line | 0.93 / 1.28 | 2.99 / 29.47 | 0.01 / 0.05 | 100.00 / 52.92 | 3/3 / 0/3 |
| clear_random | 0.90 / 1.03 | 5.71 / 27.15 | 0.01 / 0.05 | 100.00 / 63.17 | 3/3 / 0/3 |
| decoys_identical | 0.62 / 6.82 | 3.41 / 190.56 | 0.03 / 555.87 | 100.00 / 1.64 | 3/3 / 0/3 |
| fast_circular | 0.69 / n/a | 4.87 / n/a | 0.01 / 0.05 | 100.00 / 0.00 | 3/3 / 0/3 |
| fog_circular | 1.02 / 0.43 | 2.64 / 33.25 | 0.08 / 0.09 | 100.00 / 0.76 | 3/3 / 0/3 |
| full_stress | 0.63 / 3.86 | 10.80 / 66.02 | 0.18 / 2.47 | 99.40 / 4.88 | 0/3 / 0/3 |
| hardmode_line | 6.31 / 12.50 | 2.98 / 19.29 | 0.01 / 0.13 | 100.00 / 33.33 | 0/3 / 0/3 |
| lowlight_faint | 1.48 / n/a | 2.84 / n/a | 1.54 / n/a | 96.97 / 0.00 | 3/3 / 0/3 |
| lowlight_figure8 | 1.28 / 0.96 | 3.36 / 38.80 | 0.14 / 0.30 | 100.00 / 23.55 | 3/3 / 0/3 |
| noisy_line | 0.89 / 1.00 | 3.00 / 29.42 | 0.19 / 0.26 | 100.00 / 56.84 | 3/3 / 0/3 |
| platform_jitter | 0.73 / 1.24 | 19.20 / 56.18 | 0.02 / 0.05 | 99.61 / 18.41 | 0/3 / 0/3 |
| platform_max | 0.88 / 1.11 | 22.21 / 79.50 | 0.07 / 0.04 | 96.38 / 11.92 | 0/3 / 0/3 |
| platform_max_10degs | 0.89 / 1.11 | 23.05 / 79.50 | 0.07 / 0.04 | 93.78 / 11.92 | 0/3 / 0/3 |

Runs meeting every PS limit: ARGUS 33 of 48, baseline 0 of 48.

PS limits used: acquisition_time_s <= 2, tracking_err_mean_px <= 10, target_loss_pct < 5, reacq_time_max_s <= 1, fps_mean >= 20.
