"""Compose the 3 to 5 minute demonstration video (optional PS deliverable) straight from the
engine: title cards, then one segment per scenario showing the scene view, the camera view,
the live specification tiles and the telemetry, and a Benchmark 2 segment on a video file.

    .venv/bin/python tools/make_demo_video.py                # docs/demo/ARGUS-demo.mp4
    .venv/bin/python tools/make_demo_video.py --seconds 20   # shorter segments

The picture is drawn with OpenCV from the same frames the application renders, so what the
video shows is what the tracker saw. No narration; captions carry the explanation.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from fsoc_tracker.engine.config import RunConfig, TargetConfig  # noqa: E402
from fsoc_tracker.engine.simulation import Simulation  # noqa: E402
from fsoc_tracker.world.renderer import World  # noqa: E402

W, H, FPS = 1280, 720, 30
INK, MUTED, ACCENT, GOOD, WARN, BG, PANEL = (241, 236, 227), (173, 161, 141), (222, 196, 82), (147, 190, 92), (76, 141, 224), (23, 17, 10), (36, 28, 17)
FONT = cv2.FONT_HERSHEY_SIMPLEX

SEGMENTS = [
    ("clear_line", "1. Clear sky, straight line", "Acquisition under 2 s, tracking error under 10 px, camera window follows the beacon."),
    ("clear_figure8", "2. Figure of 8", "The IMM estimator switches between constant velocity, acceleration and turn models."),
    ("noisy_line", "3. Salt and pepper, Gaussian and Poisson noise", "All three PS noise kinds at once (rows 21, 22). The matched filter carries the detection."),
    ("fog_circular", "4. Fog", "Contrast and brightness reduced, blur and turbulence (row 24)."),
    ("lowlight_faint", "5. Low light, faint beacon", "3 to 6 sigma per frame: weak detections are linked across frames (track-before-detect)."),
    ("platform_jitter", "6. Platform sway and camera jitter", "Rows 23 and 25. Vibration is measured from the tracker's innovation and smoothed, not chased."),
    ("full_stress", "7. Decoys, haze, noise, sway together", "The designated beacon is kept by its appearance signature among extra targets (row 8)."),
    ("hardmode_line", "8. Hard mode: the tracker sees only the camera window", "A square-spiral sweep at the 5 deg/s limit finds the beacon, then tracking is as before."),
]


def text(img, s, x, y, scale=0.55, color=INK, thick=1):
    cv2.putText(img, s, (x, y), FONT, scale, color, thick, cv2.LINE_AA)


def card(lines: list[tuple[str, float, tuple]], seconds: float, vw):
    for _ in range(int(seconds * FPS)):
        img = np.full((H, W, 3), BG, np.uint8)
        y = 250
        for s, sc, col in lines:
            text(img, s, 90, y, sc, col, 2 if sc > 0.9 else 1)
            y += int(60 * sc) + 18
        vw.write(img)


def tile(img, x, y, w, label, value, unit, ok):
    cv2.rectangle(img, (x, y), (x + w, y + 78), PANEL, -1)
    text(img, label.upper(), x + 10, y + 20, 0.38, MUTED)
    text(img, value, x + 10, y + 52, 0.8, GOOD if ok else WARN, 2)
    text(img, unit, x + 10, y + 70, 0.36, MUTED)


def segment(cfg: RunConfig, title: str, caption: str, seconds: float, vw, video_note: str | None = None):
    cfg.duration_s = seconds if not cfg.video else 0.0
    sim = Simulation(cfg, None, write_csv=False)
    acq = None; terr = []; lock = []; proc = []
    n_frames = 0
    for res in sim.steps():
        r = res.record
        if acq is None and r.locked:
            acq = r.t_sim
        if acq is not None:
            terr.append(r.tracking_err_px); lock.append(bool(r.locked))
        proc.append(r.proc_ms)
        obs = res.observed
        gray = obs if obs.ndim == 2 else cv2.cvtColor(obs, cv2.COLOR_BGR2GRAY)
        sh, sw = gray.shape
        img = np.full((H, W, 3), BG, np.uint8)
        # scene view, 560 px on the longer side
        s = 560 / max(sh, sw)
        scene = cv2.cvtColor(cv2.resize(gray, (int(sw * s), int(sh * s)), interpolation=cv2.INTER_AREA), cv2.COLOR_GRAY2BGR)
        x0, y0, w, h = res.window
        cv2.rectangle(scene, (int(x0 * s), int(y0 * s)), (int((x0 + w) * s), int((y0 + h) * s)), (222, 196, 82), 1)
        if r.true_x == r.true_x:
            cv2.circle(scene, (int(r.true_x * s), int(r.true_y * s)), 5, (76, 141, 224), 1)
        if r.est_x == r.est_x:
            ex, ey = int(r.est_x * s), int(r.est_y * s)
            cv2.line(scene, (ex - 6, ey), (ex + 6, ey), (147, 190, 92), 1); cv2.line(scene, (ex, ey - 6), (ex, ey + 6), (147, 190, 92), 1)
        img[130:130 + scene.shape[0], 40:40 + scene.shape[1]] = scene
        text(img, "SCENE  whole screen; camera window yellow, truth blue, estimate green", 40, 122, 0.42, MUTED)
        # camera view
        xa, ya = max(x0, 0), max(y0, 0); xb, yb = min(x0 + w, sw), min(y0 + h, sh)
        crop = np.zeros((h, w), np.uint8)
        if xb > xa and yb > ya:
            crop[ya - y0:yb - y0, xa - x0:xb - x0] = gray[ya:yb, xa:xb]
        lo, hi = np.percentile(crop[::4, ::4], (1, 99.8))
        if hi - lo > 8:
            crop = np.clip((crop.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)
        cam = cv2.cvtColor(cv2.resize(crop, (560, 420)), cv2.COLOR_GRAY2BGR)
        cx, cy = 280, 210
        col = (147, 190, 92) if r.locked else (76, 141, 224)
        cv2.circle(cam, (cx, cy), 26, col, 1)
        cv2.line(cam, (cx - 16, cy), (cx - 5, cy), (222, 196, 82), 1); cv2.line(cam, (cx + 5, cy), (cx + 16, cy), (222, 196, 82), 1)
        cv2.line(cam, (cx, cy - 16), (cx, cy - 5), (222, 196, 82), 1); cv2.line(cam, (cx, cy + 5), (cx, cy + 16), (222, 196, 82), 1)
        if r.det_x == r.det_x:
            dx, dy = int((r.det_x - x0) * 560 / w), int((r.det_y - y0) * 420 / h)
            cv2.rectangle(cam, (dx - 10, dy - 10), (dx + 10, dy + 10), (147, 190, 92), 1)
        img[130:550, 660:1220] = cam
        text(img, "CAMERA WINDOW  what the terminal points at; ring green when locked", 660, 122, 0.42, MUTED)
        # header and tiles
        text(img, title, 40, 46, 0.8, INK, 2)
        text(img, caption, 40, 78, 0.48, MUTED)
        fps = 1000.0 / max(np.mean(proc[-30:]), 1e-3)
        te = [v for v in terr[-300:] if v == v]
        tile(img, 40, 585, 190, "state", r.mode + (" locked" if r.locked else ""), "tracker", r.locked)
        tile(img, 240, 585, 190, "acquisition", f"{acq:.2f} s" if acq is not None else "searching", "spec 2 s or less", acq is not None and acq <= 2)
        tile(img, 440, 585, 190, "tracking error", f"{np.mean(te):.1f} px" if te else "n/a", "spec 10 px or less", bool(te) and np.mean(te) <= 10)
        lk = 100 * np.mean(lock[-300:]) if lock else None
        tile(img, 640, 585, 190, "lock retention", f"{lk:.0f} %" if lk is not None else "n/a", "spec loss under 5%", lk is not None and lk >= 95)
        tile(img, 840, 585, 190, "processing", f"{fps:.0f} FPS", "spec 20 FPS or more", fps >= 20)
        tile(img, 1040, 585, 180, "time", f"{r.t_sim:.1f} s", f"frame {r.frame}", True)
        if video_note:
            text(img, video_note, 40, 700, 0.42, ACCENT)
        vw.write(img)
        n_frames += 1
        if cfg.video and n_frames >= seconds * FPS:
            break
    return acq, (np.mean([v for v in terr if v == v]) if terr else None), (100 * np.mean(lock) if lock else None)


def make_benchmark_video(path: Path) -> None:
    cfg = RunConfig(duration_s=25.0); cfg.screen.width = cfg.screen.height = 1200
    cfg.targets = [TargetConfig(motion="figure8", radius_px=350, period_s=12, start="centre", size_px=10, intensity=230)]
    cfg.disturbance.gaussian_sigma = 8.0; cfg.disturbance.salt_pepper_frac = 0.02
    w = World(cfg)
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (1200, 1200), isColor=True)
    for _ in range(25 * 30):
        img, _ = w.render(); vw.write(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
    vw.release()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=24.0, help="length of each scenario segment")
    ap.add_argument("--out", default=str(ROOT / "docs" / "demo" / "ARGUS-demo.mp4"))
    a = ap.parse_args()
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    vw = cv2.VideoWriter(str(out), cv2.VideoWriter_fourcc(*"mp4v"), FPS, (W, H))
    if not vw.isOpened():
        raise SystemExit("cannot open the video writer")
    card([("ARGUS", 1.6, INK), ("AI-based virtual camera tracking for coarse alignment of mobile FSOC terminals", 0.7, MUTED),
          ("SIH26169  |  Department of Space, ISRO SAC", 0.6, ACCENT), ("A simulated scene, a moving laser beacon, disturbances, and a tracker that steers", 0.55, MUTED),
          ("a rate-limited virtual pan-tilt camera to keep the beacon centred.", 0.55, MUTED)], 6, vw)
    card([("What the video shows", 1.2, INK), ("Eight scenarios from the problem statement, then Benchmark 2 (video input).", 0.6, MUTED),
          ("Left: the whole scene with the camera window. Right: the camera window itself.", 0.6, MUTED),
          ("Bottom: the live specification tiles, green when the PS value is met.", 0.6, MUTED),
          ("Every run also writes a per-frame CSV and a PDF performance report.", 0.6, MUTED)], 6, vw)
    results = []
    for name, title, caption in SEGMENTS:
        cfg = RunConfig.load(ROOT / "configs" / "scenarios" / f"{name}.yaml")
        acq, err, lk = segment(cfg, title, caption, a.seconds, vw)
        results.append((title, acq, err, lk)); print(f"{name}: acq {acq} err {err} lock {lk}")
    with tempfile.TemporaryDirectory() as td:
        vpath = Path(td) / "benchmark2.mp4"
        make_benchmark_video(vpath)
        cfg = RunConfig(video=str(vpath), duration_s=0)
        acq, err, lk = segment(cfg, "9. Benchmark 2: a video file replaces the simulator", "The PTZ camera is bypassed; the frames are the scene. Size and frame rate are read from the file.", a.seconds, vw,
                               video_note="No ground truth in a video: the report carries the detection centroids per frame for comparison with the evaluators' values.")
        results.append(("9. Benchmark 2 (video)", acq, err, lk)); print(f"video: acq {acq} err {err} lock {lk}")
    lines = [("Results of this recording", 1.1, INK)]
    for title, acq, err, lk in results:
        lines.append((f"{title[:52]:52s}  acq {acq:.2f} s   lock {lk:.0f} %" if acq is not None and lk is not None else f"{title[:52]:52s}  not acquired", 0.5, GOOD if acq is not None else WARN))
    lines.append(("Report, per-frame CSV and summary are written for every run. Desktop builds: Windows, Linux, macOS.", 0.5, MUTED))
    card(lines, 8, vw)
    vw.release()
    print(f"wrote {out} ({out.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
