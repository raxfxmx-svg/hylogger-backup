"""Probe column fraction-bright profile within core row bands."""
from pathlib import Path

import numpy as np
from PIL import Image

DATA = Path(r"C:\path\to\project\8a294cfc-68df-4f03-995b-c5fd0d47ab0")

# row bands from previous probe (top,bottom) inclusive, rough
BANDS = {
    "0001": [(40, 96), (103, 168), (174, 241), (243, 313), (316, 385), (387, 457)],
    "0008": [(38, 95), (110, 167), (181, 240), (245, 312), (327, 384), (398, 456)],
    "0033": [(32, 98), (102, 167), (181, 239), (245, 312), (322, 391), (394, 451)],
}

for tray, bands in BANDS.items():
    im = Image.open(DATA / f"05GJD001_{tray}.jpg").convert("L")
    small = im.resize((im.width // 8, im.height // 8), Image.BILINEAR)
    g = np.asarray(small, dtype=np.float32)
    mask = np.zeros(g.shape[0], dtype=bool)
    for t, b in bands:
        mask[t:b + 1] = True
    sub = g[mask, :]
    colfrac = (sub > 45.0).mean(axis=0)
    print(f"=== {tray}")
    print("left  x=30..110:", ",".join(f"{v:.2f}" for v in colfrac[30:111:4]))
    print("right x=1290..1370:", ",".join(f"{v:.2f}" for v in colfrac[1290:1371:2]))
    # also exact first/last col above 0.5
    above = np.where(colfrac > 0.5)[0]
    print("first>0.5:", above[0], "last>0.5:", above[-1])
