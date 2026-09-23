"""Beacon spot shapes (PS row 9, "Target Shape: User-defined, Default: Square") at any width and
height (row 10, "5-20 x 5-20 pixels"). One function draws them, so the renderer and the
detector's size calibration always agree on what a shape looks like.

Every sprite is normalised to a peak of 1, padded by 3 px, and softened by the optics (a 0.6 px
Gaussian), except the Gaussian spot which is already smooth. A square, circle or Gaussian of
equal width and height is drawn exactly as before this module existed.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

PAD = 3
SHAPES = ("square", "circle", "gaussian", "cross", "ring", "diamond", "custom")


def parse_mask(mask: str) -> np.ndarray | None:
    """A user-defined shape: rows of 0/1 (or '.'/'#') separated by ';', or a PNG/JPG path whose
    bright pixels form the shape. Returns a float array in 0..1, or None."""
    text = (mask or "").strip()
    if not text:
        return None
    rows = [r.strip() for r in text.replace("\n", ";").split(";") if r.strip()]
    if rows and all(set(r) <= set("01.#xX ") for r in rows):
        rows = [r.replace(" ", "") for r in rows]
        wmax = max(len(r) for r in rows)
        m = np.zeros((len(rows), wmax), np.float32)
        for i, r in enumerate(rows):
            for j, ch in enumerate(r):
                m[i, j] = 1.0 if ch in "1#xX" else 0.0
        return m if m.any() else None
    p = Path(text)
    if p.is_file():
        img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if img is not None and img.size and img.max() > 0:
            return (img.astype(np.float32) / float(img.max()))
    return None


def make_sprite(shape: str, width: int, height: int | None = None, mask: str = "") -> np.ndarray:
    """The beacon's spot, peak 1, shape (height + 6, width + 6)."""
    w = max(int(width), 2)
    h = max(int(height or width), 2)
    if w == h and shape in ("square", "circle", "gaussian"):
        return _legacy(shape, w)
    nw, nh = w + 2 * PAD, h + 2 * PAD
    sp = np.zeros((nh, nw), np.float32)
    if shape == "square":
        sp[PAD:PAD + h, PAD:PAD + w] = 1.0
        sp = cv2.GaussianBlur(sp, (0, 0), 0.6)
    elif shape == "circle":
        cv2.ellipse(sp, (nw // 2, nh // 2), (max(w // 2, 1), max(h // 2, 1)), 0, 0, 360, 1.0, -1, lineType=cv2.LINE_AA)
        sp = cv2.GaussianBlur(sp, (0, 0), 0.6)
    elif shape == "gaussian":
        yy, xx = np.mgrid[0:nh, 0:nw]
        sx, sy = w / 3.0, h / 3.0
        sp = np.exp(-((xx - nw / 2 + 0.5) ** 2 / (2 * sx * sx) + (yy - nh / 2 + 0.5) ** 2 / (2 * sy * sy))).astype(np.float32)
    elif shape == "cross":
        tw = max(1, int(round(w / 3.0))); th = max(1, int(round(h / 3.0)))
        cx0 = PAD + (w - tw) // 2; cy0 = PAD + (h - th) // 2
        sp[PAD:PAD + h, cx0:cx0 + tw] = 1.0
        sp[cy0:cy0 + th, PAD:PAD + w] = 1.0
        sp = cv2.GaussianBlur(sp, (0, 0), 0.6)
    elif shape == "ring":
        t = max(1, int(round(min(w, h) / 5.0)))
        cv2.ellipse(sp, (nw // 2, nh // 2), (max(w // 2 - t // 2, 1), max(h // 2 - t // 2, 1)), 0, 0, 360, 1.0, t, lineType=cv2.LINE_AA)
        sp = cv2.GaussianBlur(sp, (0, 0), 0.6)
    elif shape == "diamond":
        cx, cy = (nw - 1) / 2.0, (nh - 1) / 2.0
        pts = np.array([[cx, cy - h / 2], [cx + w / 2, cy], [cx, cy + h / 2], [cx - w / 2, cy]], np.float32)
        cv2.fillConvexPoly(sp, np.round(pts * 16).astype(np.int32), 1.0, lineType=cv2.LINE_AA, shift=4)
        sp = cv2.GaussianBlur(sp, (0, 0), 0.6)
    else:  # custom
        m = parse_mask(mask)
        if m is None:
            sp[PAD:PAD + h, PAD:PAD + w] = 1.0
        else:
            sp[PAD:PAD + h, PAD:PAD + w] = cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA)
        sp = cv2.GaussianBlur(sp, (0, 0), 0.6)
    peak = float(sp.max())
    return sp / peak if peak > 0 else sp


def _legacy(shape: str, s: int) -> np.ndarray:
    """Square, circle and Gaussian spots of equal width and height, byte for byte as the
    renderer has always drawn them (the regression pack depends on it)."""
    n = s + 2 * PAD
    sp = np.zeros((n, n), np.float32)
    if shape == "square":
        sp[PAD:PAD + s, PAD:PAD + s] = 1.0
        sp = cv2.GaussianBlur(sp, (0, 0), 0.6)
    elif shape == "circle":
        cv2.circle(sp, (n // 2, n // 2), s // 2, 1.0, -1, lineType=cv2.LINE_AA)
        sp = cv2.GaussianBlur(sp, (0, 0), 0.6)
    else:
        yy, xx = np.mgrid[0:n, 0:n]
        sig = s / 3.0
        sp = np.exp(-((xx - n / 2 + 0.5) ** 2 + (yy - n / 2 + 0.5) ** 2) / (2 * sig * sig))
    sp /= sp.max()
    return sp
