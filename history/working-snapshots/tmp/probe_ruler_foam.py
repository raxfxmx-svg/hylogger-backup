"""Probe ruler continuity metric + left edge detail + foam colour."""
from pathlib import Path

import numpy as np
from PIL import Image

DATA = Path(r"C:\path\to\project\8a294cfc-68df-4f03-995b-c5fd0d47ab0")

BANDS = {
    "0001": [(40, 96), (103, 168), (174, 241), (243, 313), (316, 385), (387, 457)],
    "0008": [(38, 95), (110, 167), (181, 240), (245, 312), (327, 384), (398, 456)],
    "0033": [(32, 98), (102, 167), (181, 239), (245, 312), (322, 391), (394, 451)],
}

for tray, bands in BANDS.items():
    im = Image.open(DATA / f"05GJD001_{tray}.jpg").convert("L")
    small = im.resize((im.width // 8, im.height // 8), Image.BILINEAR)
    g = np.asarray(small, dtype=np.float32)
    ytop, ybot = bands[0][0], bands[-1][1]
    full = g[ytop:ybot + 1, :]
    # continuity: fraction of bright pixels over the FULL vertical extent (incl. gaps)
    cont = (full > 45.0).mean(axis=0)
    print(f"=== {tray}")
    print("cont x=1300..1362:", ",".join(f"{v:.2f}" for v in cont[1300:1363:2]))
    # near-white fraction within rows
    mask = np.zeros(g.shape[0], dtype=bool)
    for t, b in bands:
        mask[t:b + 1] = True
    sub = g[mask, :]
    white = (sub > 200.0).mean(axis=0)
    print("white x=1300..1362:", ",".join(f"{v:.2f}" for v in white[1300:1363:2]))
    colfrac = (sub > 45.0).mean(axis=0)
    print("left colfrac x=38..72:", ",".join(f"{v:.2f}" for v in colfrac[38:73]))

# foam colour: tray 0008 row 6 right end, at 1/8: band (398,456), x ~ 1150-1300
im8 = Image.open(DATA / "05GJD001_0008.jpg").convert("RGB")
s8 = im8.resize((im8.width // 8, im8.height // 8), Image.BILINEAR)
a8 = np.asarray(s8, dtype=np.int32)
reg = a8[410:450, 1150:1290, :]
r, gg, b = reg[..., 0], reg[..., 1], reg[..., 2]
foam = (r > 150) & (gg > 80) & (gg < 200) & (b < 140) & (r - b > 60)
print("=== 0008 row6 foam-region: shape", reg.shape, "foam frac", foam.mean())
fr, fg, fb = r[foam], gg[foam], b[foam]
print("foam RGB mean:", fr.mean(), fg.mean(), fb.mean())
print("foam RGB p05/p95 R:", np.percentile(fr, 5), np.percentile(fr, 95))
# whole-row foam fraction per row band of 0008
for i, (t, b_) in enumerate(BANDS["0008"], 1):
    reg = a8[t:b_ + 1, 46:1330, :]
    r, gg, b = reg[..., 0], reg[..., 1], reg[..., 2]
    foam = (r > 150) & (gg > 80) & (gg < 200) & (b < 140) & (r - b > 60)
    print(f"0008 row{i} foam frac: {foam.mean():.4f}")
