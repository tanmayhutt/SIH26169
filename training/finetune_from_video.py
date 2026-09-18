"""Fine-tune the beacon detector on a video you provide (self-training).

There is no ground truth in a video, so the tracker itself supplies the labels: frames where
it was in TRACK with a high-confidence classical detection are taken as correct, and 128 x
128 patches are cut around those positions (with random offsets so the beacon is not always
centred) plus background patches far from the beacon as negatives. The network is then
trained on a mix of these real patches and freshly simulated ones, so it learns the look of
your beacon and background without forgetting the simulator.

    .venv/bin/python training/finetune_from_video.py path/to/video.mp4 [--epochs 6] [--out models/beacon_heatmap.onnx]

Starts from models/beacon_heatmap.pt if present (saved by train_heatmap.py), otherwise from
scratch. Writes the ONNX model the application loads, and the .pt next to it.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np

from fsoc_tracker.engine.config import RunConfig
from fsoc_tracker.engine.simulation import Simulation
from training.train_heatmap import OUT, PATCH, build_model, make_dataset


def patches_from_video(path: str, max_samples: int = 4000, min_conf: float = 0.9, seed: int = 0):
    rng = np.random.default_rng(seed)
    cfg = RunConfig(video=path, duration_s=0)
    cfg.tracker.detector = "classical"          # labels must come from the classical path only
    sim = Simulation(cfg, None, write_csv=False)
    X, Y = [], []
    for res in sim.steps():
        tr = res.track
        if tr.mode.value != "TRACK" or tr.detection is None or tr.confidence < min_conf or tr.tier != "classical":
            continue
        img = res.observed
        H, W = img.shape
        bx, by = tr.detection
        for _ in range(2):                     # two positive crops per usable frame
            cx = bx + rng.uniform(-PATCH * 0.38, PATCH * 0.38)
            cy = by + rng.uniform(-PATCH * 0.38, PATCH * 0.38)
            xa = int(min(max(cx - PATCH / 2, 0), W - PATCH)); ya = int(min(max(cy - PATCH / 2, 0), H - PATCH))
            crop = img[ya:ya + PATCH, xa:xa + PATCH].astype(np.float32) / 255.0
            crop = (crop - crop.mean()) / (crop.std() + 1e-3)
            hx, hy = (bx - xa) / 2.0, (by - ya) / 2.0
            yy, xx = np.mgrid[0:OUT, 0:OUT]
            sig = max(tr.sigma / 2.0, 1.0)
            heat = np.exp(-((xx + 0.5 - hx) ** 2 + (yy + 0.5 - hy) ** 2) / (2 * sig * sig))
            X.append(crop[None]); Y.append(heat[None].astype(np.float32))
        # one negative crop far from the beacon
        for _ in range(8):
            cx, cy = rng.uniform(PATCH / 2, W - PATCH / 2), rng.uniform(PATCH / 2, H - PATCH / 2)
            if math.hypot(cx - bx, cy - by) > PATCH:
                xa, ya = int(cx - PATCH / 2), int(cy - PATCH / 2)
                crop = img[ya:ya + PATCH, xa:xa + PATCH].astype(np.float32) / 255.0
                crop = (crop - crop.mean()) / (crop.std() + 1e-3)
                X.append(crop[None]); Y.append(np.zeros((1, OUT, OUT), np.float32))
                break
        if len(X) >= max_samples:
            break
    print(f"video patches: {len(X)} (from frames the tracker was confident about)")
    return np.array(X, np.float32), np.array(Y, np.float32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--epochs", type=int, default=6)
    ap.add_argument("--sim-samples", type=int, default=3000, help="simulated patches mixed in so the model does not forget")
    ap.add_argument("--out", default="models/beacon_heatmap.onnx")
    ap.add_argument("--init", default="models/beacon_heatmap.pt")
    a = ap.parse_args()
    import torch
    import torch.nn.functional as F
    torch.manual_seed(0)
    Xv, Yv = patches_from_video(a.video)
    if len(Xv) < 50:
        raise SystemExit("too few confident frames in this video to learn from; run it in the app first and check the tracker locks")
    Xs, Ys = make_dataset(a.sim_samples, seed=7)
    X = torch.from_numpy(np.concatenate([Xv, Xs])); Y = torch.from_numpy(np.concatenate([Yv, Ys]))
    net = build_model()
    if Path(a.init).exists():
        net.load_state_dict(torch.load(a.init, map_location="cpu")); print(f"initialised from {a.init}")
    else:
        print("no saved weights found; training from scratch")
    opt = torch.optim.AdamW(net.parameters(), lr=1e-3, weight_decay=1e-4)
    pos_w = torch.tensor(8.0)
    for ep in range(a.epochs):
        net.train(); perm = torch.randperm(len(X)); tot = 0.0
        for k in range(0, len(X), 64):
            idx = perm[k:k + 64]; xb, yb = X[idx], Y[idx]
            if torch.rand(1) < 0.5:
                xb, yb = xb.flip(-1), yb.flip(-1)
            loss = F.binary_cross_entropy_with_logits(net(xb), yb, pos_weight=pos_w)
            opt.zero_grad(); loss.backward(); opt.step(); tot += loss.item() * len(idx)
        print(f"epoch {ep + 1}/{a.epochs}  loss {tot / len(X):.4f}")
    net.eval()
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    torch.save(net.state_dict(), str(Path(a.out).with_suffix(".pt")))
    torch.onnx.export(net, torch.zeros(1, 1, PATCH, PATCH), a.out, input_names=["patch"], output_names=["heat"], opset_version=17, dynamo=False)
    print(f"exported {a.out}")


if __name__ == "__main__":
    main()
