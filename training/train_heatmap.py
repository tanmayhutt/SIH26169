"""Train the Tier 2 beacon heat-map detector on frames from our own simulator.

The simulator draws the picture and knows where the beacon is, so labels are exact and
free. We render 128 x 128 patches around the beacon under randomised disturbances (and
some patches with no beacon), and train a small fully convolutional network to output a
heat map at half resolution (64 x 64) with a Gaussian bump on the beacon.

    .venv/bin/python training/train_heatmap.py --samples 6000 --epochs 8
    -> models/beacon_heatmap.onnx  (a few hundred kB, CPU inference in a few ms)
"""
from __future__ import annotations

import argparse
import math
import time
from pathlib import Path

import numpy as np

from fsoc_tracker.engine.config import DisturbanceConfig, RunConfig, TargetConfig, apply_atmosphere_preset
from fsoc_tracker.world.renderer import World

PATCH, OUT = 128, 64


def random_cfg(rng: np.random.Generator) -> RunConfig:
    cfg = RunConfig(seed=int(rng.integers(0, 10 ** 6)))
    cfg.screen.width = cfg.screen.height = 512          # small scene: fast rendering
    cfg.screen.background = str(rng.choice(["starfield", "terrain", "gradient", "flat"]))
    cfg.screen.background_level = int(rng.integers(4, 60))
    cfg.targets = [TargetConfig(shape=str(rng.choice(["square", "circle", "gaussian"])), size_px=int(rng.integers(5, 21)),
                                intensity=int(rng.integers(70, 236)), motion="static", start="random")]
    for _ in range(int(rng.integers(0, 3))):     # decoys
        cfg.targets.append(TargetConfig(shape=str(rng.choice(["square", "circle", "gaussian"])), size_px=int(rng.integers(4, 18)),
                                        intensity=int(rng.integers(60, 230)), motion="static", start="random"))
    d = DisturbanceConfig(atmosphere=str(rng.choice(["clear", "haze", "fog", "rain", "lowlight"])),
                          salt_pepper_frac=float(rng.choice([0, 0, 0.02, 0.05, 0.10])),
                          gaussian_sigma=float(rng.uniform(0, 20)), poisson=bool(rng.random() < 0.5),
                          jitter_px=0.0, platform_motion="none")
    apply_atmosphere_preset(d)
    d.contrast *= float(rng.uniform(0.7, 1.1))
    d.brightness += float(rng.uniform(-15, 15))
    d.blur_sigma += float(rng.uniform(0, 1.0))
    cfg.disturbance = d
    return cfg


def make_dataset(n: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    X = np.zeros((n, 1, PATCH, PATCH), np.float32)
    Y = np.zeros((n, 1, OUT, OUT), np.float32)
    i = 0
    t0 = time.time()
    while i < n:
        cfg = random_cfg(rng)
        world = World(cfg)
        for _ in range(4):
            img, truth = world.render()
            tx, ty = truth.beacons[0]
            has = rng.random() > 0.15
            if has:
                cx = tx + rng.uniform(-PATCH * 0.38, PATCH * 0.38)
                cy = ty + rng.uniform(-PATCH * 0.38, PATCH * 0.38)
            else:
                cx, cy = rng.uniform(PATCH, 512 - PATCH), rng.uniform(PATCH, 512 - PATCH)
                if math.hypot(cx - tx, cy - ty) < PATCH * 0.7:
                    continue
            xa, ya = int(cx - PATCH / 2), int(cy - PATCH / 2)
            xa = min(max(xa, 0), 512 - PATCH); ya = min(max(ya, 0), 512 - PATCH)
            crop = img[ya:ya + PATCH, xa:xa + PATCH].astype(np.float32) / 255.0
            crop = (crop - crop.mean()) / (crop.std() + 1e-3)
            X[i, 0] = crop
            if has:
                hx, hy = (tx - xa) / 2.0, (ty - ya) / 2.0
                yy, xx = np.mgrid[0:OUT, 0:OUT]
                sig = max(cfg.targets[0].size_px / 4.0, 1.0)
                Y[i, 0] = np.exp(-((xx + 0.5 - hx) ** 2 + (yy + 0.5 - hy) ** 2) / (2 * sig * sig))
            i += 1
            if i >= n:
                break
        if i % 500 == 0:
            print(f"  {i}/{n} samples  {time.time() - t0:.0f}s")
    return X, Y


def build_model():
    import torch.nn as nn

    def block(i, o):
        return nn.Sequential(nn.Conv2d(i, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(inplace=True),
                             nn.Conv2d(o, o, 3, padding=1), nn.BatchNorm2d(o), nn.ReLU(inplace=True))

    class Net(nn.Module):
        def __init__(self):
            super().__init__()
            self.e1 = block(1, 16)           # 128
            self.e2 = block(16, 32)          # 64
            self.e3 = block(32, 48)          # 32
            self.pool = nn.MaxPool2d(2)
            self.up = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False)
            self.d2 = block(48 + 32, 32)     # 64
            self.head = nn.Conv2d(32, 1, 1)

        def forward(self, x):
            e1 = self.e1(x)
            e2 = self.e2(self.pool(e1))
            e3 = self.e3(self.pool(e2))
            d2 = self.d2(__import__("torch").cat([self.up(e3), e2], 1))
            return self.head(d2)

    return Net()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=6000)
    ap.add_argument("--epochs", type=int, default=8)
    ap.add_argument("--out", default="models/beacon_heatmap.onnx")
    a = ap.parse_args()
    import torch
    import torch.nn.functional as F
    torch.manual_seed(0)
    print("generating dataset from the simulator")
    X, Y = make_dataset(a.samples)
    Xv, Yv = make_dataset(max(a.samples // 10, 200), seed=123)
    X, Y, Xv, Yv = map(torch.from_numpy, (X, Y, Xv, Yv))
    net = build_model()
    n_params = sum(p.numel() for p in net.parameters())
    print(f"model parameters: {n_params:,}")
    opt = torch.optim.AdamW(net.parameters(), lr=2e-3, weight_decay=1e-4)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=3e-3, total_steps=a.epochs * math.ceil(len(X) / 64))
    pos_w = torch.tensor(8.0)
    for ep in range(a.epochs):
        net.train()
        perm = torch.randperm(len(X))
        tot = 0.0
        for k in range(0, len(X), 64):
            idx = perm[k:k + 64]
            xb, yb = X[idx], Y[idx]
            # augment: random flips and 90 degree rotations
            if torch.rand(1) < 0.5:
                xb, yb = xb.flip(-1), yb.flip(-1)
            if torch.rand(1) < 0.5:
                xb, yb = xb.flip(-2), yb.flip(-2)
            out = net(xb)
            loss = F.binary_cross_entropy_with_logits(out, yb, pos_weight=pos_w)
            opt.zero_grad(); loss.backward(); opt.step(); sched.step()
            tot += loss.item() * len(idx)
        net.eval()
        with torch.no_grad():
            vo = net(Xv)
            vl = F.binary_cross_entropy_with_logits(vo, Yv, pos_weight=pos_w).item()
            # localisation error on positives
            has = Yv.flatten(1).max(1).values > 0.5
            pr = vo[has].flatten(1).argmax(1); gt = Yv[has].flatten(1).argmax(1)
            dy = (pr // OUT - gt // OUT).float(); dx = (pr % OUT - gt % OUT).float()
            loc = (dx ** 2 + dy ** 2).sqrt().mean().item() * 2   # in patch px
        print(f"epoch {ep + 1}/{a.epochs}  train {tot / len(X):.4f}  val {vl:.4f}  val loc err {loc:.2f} px")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    torch.save(net.state_dict(), str(Path(a.out).with_suffix(".pt")))   # for fine-tuning on video later
    dummy = torch.zeros(1, 1, PATCH, PATCH)
    torch.onnx.export(net, dummy, a.out, input_names=["patch"], output_names=["heat"], opset_version=17, dynamo=False)
    print(f"exported {a.out}  ({Path(a.out).stat().st_size / 1024:.0f} kB)")


if __name__ == "__main__":
    main()
