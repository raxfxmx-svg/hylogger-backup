"""Inspect rowfrac profile around tray 0008 rows 3-5."""
from pathlib import Path

import numpy as np
from PIL import Image

DATA = Path(r"C:\path\to\project\8a294cfc-68df-4f03-995b-c5fd0d47ab0")

im = Image.open(DATA / "05GJD001_0008.jpg").convert("L")
small = im.resize((im.width // 8, im.height // 8), Image.BILINEAR)
g = np.asarray(small, dtype=np.float32)
bright = g > 45.0
rowfrac = bright[:, 60:1300].mean(axis=1)

for y in range(225, 345):
    bar = "#" * int(rowfrac[y] * 40)
    print(f"{y:3d} {rowfrac[y]:.3f} {bar}")
