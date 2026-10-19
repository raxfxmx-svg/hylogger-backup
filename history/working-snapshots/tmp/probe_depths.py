"""Probe: all photo sizes + sample-header depth aggregation."""
import re
from collections import defaultdict
from pathlib import Path

from PIL import Image

DATA = Path(r"C:\path\to\project\8a294cfc-68df-4f03-995b-c5fd0d47ab0")

# --- photo sizes
sizes = set()
for i in range(1, 34):
    p = DATA / f"05GJD001_{i:04d}.jpg"
    with Image.open(p) as im:
        sizes.add(im.size)
print("photo sizes:", sorted(sizes))

# --- sample headers
pat = re.compile(r"^\d+:\S+\s+T=(\d{4}) L=(\d) P=(\d+) D=([-\d.]+) X=([-\d.]+)")
groups = defaultdict(list)
in_sh = False
n_lines = 0
with open(DATA / "05GJD001_tsg.tsg", encoding="ascii", errors="replace") as f:
    for line in f:
        line = line.strip()
        if line == "[sample headers]":
            in_sh = True
            continue
        if in_sh:
            if line.startswith("["):
                break
            m = pat.match(line)
            if m:
                t, l, pp, d, x = m.groups()
                groups[(int(t), int(l))].append((float(d), float(x), int(pp)))
                n_lines += 1
print("parsed samples:", n_lines, "groups:", len(groups))
print("group size set:", sorted({len(v) for v in groups.values()}))

gmin = min(min(d for d, _, _ in v) for v in groups.values())
gmax = max(max(d for d, _, _ in v) for v in groups.values())
print(f"global depth: {gmin:.6f} .. {gmax:.6f}")

# per-section ranges, ordered by global section
rows = []
for (t, l), vals in sorted(groups.items()):
    ds = [d for d, _, _ in vals]
    xs = [x for _, x, _ in vals]
    sec = (t - 1) * 6 + l
    rows.append((sec, t, l, min(ds), max(ds), min(xs), max(xs), len(ds)))
print("first:", rows[0])
print("last:", rows[-1])

# gaps between consecutive sections
print("\ninter-section gaps > 0.05 m:")
for a, b in zip(rows, rows[1:]):
    gap = b[3] - a[4]
    if gap > 0.05:
        print(f"  sec {a[0]} (T{a[1]} L{a[2]}) to {b[4]:.6f} -> sec {b[0]} from {b[3]:.6f}: gap {gap:.6f}")

# negative overlaps (within tray, rows overlap?)
print("\noverlaps (next.from < prev.to - 0.001):")
for a, b in zip(rows, rows[1:]):
    if b[3] < a[4] - 0.001:
        print(f"  sec {a[0]} to {a[4]:.6f} -> sec {b[0]} from {b[3]:.6f}: overlap {a[4]-b[3]:.6f}")

# clamp check on section 198
last = groups[(33, 6)]
ds = sorted(d for d, _, _ in last)
print("\nsec 198 last 10 depths:", [f"{d:.6f}" for d in ds[-10:]])
print("sec 198 n at exactly 316.000:", sum(1 for d in ds if abs(d - 316.0) < 5e-7))
print("sec 198 min/max:", f"{ds[0]:.6f}", f"{ds[-1]:.6f}")

# P range per group
ps = sorted(set(p for v in groups.values() for _, _, p in v))
print("P range:", ps[0], ps[-1], "n distinct:", len(ps))
