"""Probe fraction-bright profiles near edges."""
from pathlib import Path

import numpy as np
from PIL import Image

DATA = Path(r"C:\path\to\project\8a294cfc-68df-4f03-995b-c5fd0d47ab0")

for tray in ["0001", "0008", "0033"]:
    p = DATA / f"05GJD001_{tray}.jpg"
    im = Image.open(p).convert("L")
    small = im.resize((im.width // 8, im.height // 8), Image.BILINEAR)
    g = np.asarray(small, dtype=np.float32)
    h, w = g.shape
    print(f"=== {tray} 1/8 size {w}x{h}")

    bright_mask = g > 45.0

    # row fraction-bright over full width (rough), find 6 row bands first
    rowfrac = bright_mask[:, 60:1300].mean(axis=1)
    # print profile compressed: every 5px
    prof = ",".join(f"{v:.2f}" for v in rowfrac[::5])
    print("rowfrac[::5]:", prof)

    thr = 0.5
    runs = []
    i = 0
    above = rowfrac > thr
    while i < h:
        if above[i]:
            j = i
            while j < h and above[j]:
                j += 1
            runs.append((i, j - 1))
            i = j
        else:
            i += 1
    print("row runs @0.5:", runs)
