"""Check whitefrac (fraction >200) around row boundaries."""
from pathlib import Path

import numpy as np
from PIL import Image

DATA = Path(r"C:\path\to\project\8a294cfc-68df-4f03-995b-c5fd0d47ab0")

for tray, y0, y1 in [("0008", 305, 335), ("0001", 30, 50), ("0001", 445, 470),
                     ("0033", 385, 405)]:
    im = Image.open(DATA / f"05GJD001_{tray}.jpg").convert("L")
    small = im.resize((im.width // 8, im.height // 8), Image.BILINEAR)
    g = np.asarray(small, dtype=np.float32)
    rowfrac = (g[:, 60:1300] > 45.0).mean(axis=1)
    whitefrac = (g[:, 60:1300] > 200.0).mean(axis=1)
    print(f"=== {tray} y={y0}..{y1}")
    for y in range(y0, y1):
        print(f"  {y:3d} rf={rowfrac[y]:.3f} wf={whitefrac[y]:.3f}")
