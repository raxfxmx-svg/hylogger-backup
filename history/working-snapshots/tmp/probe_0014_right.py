"""Investigate tray 0014 right edge."""
from pathlib import Path

import numpy as np
from PIL import Image

DATA = Path(r"C:\path\to\project\8a294cfc-68df-4f03-995b-c5fd0d47ab0")

im = Image.open(DATA / "05GJD001_0014.jpg").convert("RGB")
fw, fh = im.size
small = im.resize((fw // 8, fh // 8), Image.BILINEAR)
rgb8 = np.asarray(small, dtype=np.uint8)
gray = rgb8.astype(np.float32).mean(axis=2)

# row bands as detected
bands = [(34, 108), (112, 179), (185, 238), (244, 314), (330, 381), (388, 455)]
rowmask = np.zeros(gray.shape[0], dtype=bool)
for t, b in bands:
    rowmask[t:b + 1] = True
sub = gray[rowmask, :]
colfrac = (sub > 45.0).mean(axis=0)
white = (sub > 200.0).mean(axis=0)

print("x     :", "".join(f"{x % 100:5d}"[-1] for x in range(1280, 1371, 2)))
print("colfrac:")
for x in range(1280, 1371, 2):
    print(f"  {x} cf={colfrac[x]:.2f} wf={white[x]:.2f}")

# save a zoomed crop of the right edge at 1/2 scale for viewing
crop = im.crop((1260 * 8, 0, 1371 * 8, fh))
crop = crop.resize((crop.width // 4, crop.height // 4), Image.BILINEAR)
crop.save(r"_codex_work\tmp\probe_0014_right.png")
print("saved probe_0014_right.png", crop.size)
