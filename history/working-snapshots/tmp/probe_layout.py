"""Probe photo layout: brightness profiles at 1/8 scale on a few trays."""
from pathlib import Path

import numpy as np
from PIL import Image

DATA = Path(r"C:\path\to\project\8a294cfc-68df-4f03-995b-c5fd0d47ab0")

for tray in ["0001", "0008", "0033"]:
    p = DATA / f"05GJD001_{tray}.jpg"
    im = Image.open(p)
    print(tray, "size:", im.size)
    small = im.convert("L").resize((im.width // 8, im.height // 8), Image.BILINEAR)
    g = np.asarray(small, dtype=np.float32)
    h, w = g.shape

    # Column profile: median over vertical middle band (10%..90%)
    band = g[int(h * 0.1):int(h * 0.9), :]
    colmed = np.median(band, axis=0)
    thr_c = 60.0
    bright = colmed > thr_c
    # find runs
    runs = []
    i = 0
    while i < w:
        if bright[i]:
            j = i
            while j < w and bright[j]:
                j += 1
            runs.append((i, j - 1, j - i))
            i = j
        else:
            i += 1
    runs.sort(key=lambda r: -r[2])
    print("  top col runs (start,end,len):", runs[:5])

    x0, x1 = runs[0][0], runs[0][1]
    # Row profile within core x-range
    rowmean = g[:, x0:x1 + 1].mean(axis=1)
    print("  row profile min/max:", rowmean.min(), rowmean.max())
    thr_r = rowmean.min() + 0.45 * (rowmean.max() - rowmean.min())
    brightr = rowmean > thr_r
    rruns = []
    i = 0
    while i < h:
        if brightr[i]:
            j = i
            while j < h and brightr[j]:
                j += 1
            rruns.append((i, j - 1, j - i))
            i = j
        else:
            i += 1
    print("  thr_r=%.1f row runs:" % thr_r, rruns)
