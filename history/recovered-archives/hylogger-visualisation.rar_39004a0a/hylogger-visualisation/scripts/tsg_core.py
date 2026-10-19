"""tsg_core.py — hole-agnostic TSG / HyLogger ingestion core.

All parsing logic shared by the pipeline steps lives here as parameterised
functions (raw_dir / hole_id / out_root are always arguments, never globals).
The five step scripts (parse_vnir.py, parse_tir.py, make_strips.py,
build_intervals.py, load_db.py) and the ingest_hole.py orchestrator are thin
callers of this module.

Verified format conclusions (must not regress):

  * .bip is a float32 little-endian bi-plane cube, shape (2, n_samples,
    n_bands), [plane][sample][band]: plane 0 = spectra, plane 1 = scalar
    parameters. The file size must match 2*n_samples*n_bands*4 bytes exactly.
  * Scalar columns are located by the band numbers (before the colon) of the
    .tsg [band headers] section, NOT by the .ini Param_id slot numbers.
    ini<->tsg cross-validation is by GUID (last GUID group may carry only 11
    hex digits - a dataset quirk present in both files), with exact unique
    name match as fallback. `Param_id_000` "Index" is TSG's virtual 0-based
    sample index and is generated synthetically.
  * Null sentinels: VNIR values <= -1e37 and TIR values < -1e38 are null
    (float32 min region); exported as empty cells.
  * Mineral/group names are decoded from [class N] sections, located by the
    class number stored in the band header of the Min1/Grp1 parameter (5th
    ';'-separated field; -1 = unclassified) and read via the section's
    `name =` line and `N:entry` lines - never a hard-coded class name.
  * VNIR wavelengths are found by scanning the .cal file for a uniform-step
    monotonic float32 ramp (cross-checked against [wavelength specs] when
    present); TIR wavelengths are computed linearly from [wavelength specs].
"""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from PIL import Image

# --------------------------------------------------------------------------
# constants (format-level, dataset-independent)
# --------------------------------------------------------------------------

NULL_RULE = {
    "vnir": ("<=", -1e37),  # VNIR null sentinel: value <= -1e37
    "tir": ("<", -1e38),    # TIR null sentinel:  value <  -1e38
}

BIP_PLANES = 2              # plane 0 = spectra, plane 1 = scalar parameters

# required system scalar columns (standard TSG parameter names)
REQUIRED_COLUMNS = ("Tray", "Section", "Depth (m)")
OPTIONAL_COLUMNS = ("SecDist (mm)",)

# prefixes identifying the TSA/jCLST output columns used for intervals
TSA_PREFIXES = {"min1": "Min1", "grp1": "Grp1", "wt1": "Wt1",
                "error": "Error", "nil": "NIL_Stat"}

# cross-check tolerances (float32 quantisation, verified on 05GJD001)
DEPTH_TOL = 5e-4            # bip Depth (m) vs header D, metres
SECDIST_TOL = 1e-3          # bip SecDist (mm) vs header X, mm

# strip rendering (rig-geometry constants, expressed at 1/DS scale for the
# reference ~10971x4000 px tray photo -> 1371x500; scaled to the actual size)
DS = 8                      # detection downscale factor
STRIP_WIDTH = 2048          # output strip width in px
JPEG_QUALITY = 80
REF_SMALL_W, REF_SMALL_H = 1371, 500

BRIGHT = 45.0               # "not black background"
WHITE = 200.0               # "near-white" (ruler)
ROW_DARK = 0.45             # scanline below this bright fraction = gap/dark line
RAIL_WF = 0.60              # candidate rail: near-white fraction above this
ROW_INSET = 2               # px (1/8) shaved off each row band top/bottom
COL_INSET = 1               # px (1/8) shaved off left/right core edges
FOAM_MIN_FRAC = 0.01        # row is flagged as foam above this orange fraction
GAP_NOTE_MIN = 0.05         # inter-section depth gap (m) recorded as core loss

GUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{11,12}"
)
SAMPLE_RE = re.compile(
    r"^(\d+):(\S+)\s+T=(\d+)\s+L=(\d+)\s+P=(\d+)\s+"
    r"D=([-0-9.eE+]+)\s+X=([-0-9.eE+]+)(?:\s+H=(\S+))?"
)
CLASS_HEADER_RE = re.compile(r"\[class (\d+)\]")
CLASS_ENTRY_RE = re.compile(r"(\d+):(.*)")

SENSOR_EXTS = ("tsg", "ini", "cal", "bip")


class StepError(RuntimeError):
    """A pipeline step failed one or more self-checks."""

    def __init__(self, step: str, failures: list[str]):
        self.step = step
        self.failures = list(failures)
        super().__init__(f"{step}: {len(self.failures)} failed check(s): "
                         + "; ".join(self.failures))


class Reporter:
    """Collects report lines, echoes them to stdout, saves at the end."""

    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failures: list[str] = []

    def __call__(self, text: str = "") -> None:
        self.lines.append(text)
        print(text)

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            self.failures.append(label)
        suffix = f" — {detail}" if detail else ""
        self(f"[{'PASS' if ok else 'FAIL'}] {label}{suffix}")

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")

    def failed_summary(self) -> str:
        if not self.failures:
            return "all checks passed"
        return f"{len(self.failures)} FAILED: " + "; ".join(self.failures)

    def raise_if_failed(self, step: str) -> None:
        if self.failures:
            raise StepError(step, self.failures)


# --------------------------------------------------------------------------
# raw file discovery
# --------------------------------------------------------------------------

def _sensor_paths(raw_dir: Path, base: str) -> dict[str, Path]:
    return {ext: raw_dir / f"{base}.{ext}" for ext in SENSOR_EXTS}


def discover_inputs(raw_dir: Path, hole_id: str) -> dict:
    """Locate raw inputs for one hole inside raw_dir.

    Returns {"vnir": {ext: Path}, "tir": {ext: Path} | None,
             "photos": {tray0: Path}, "photo_notes": [str]}.

    VNIR set ``<hole_id>_tsg.{tsg,ini,cal,bip}`` is mandatory (StepError if
    incomplete). TIR set ``<hole_id>_tsg_tir.*`` is optional: absent -> None;
    partially present -> StepError. Photos are found by glob
    ``<hole_id>_*.jpg``; names containing "mosaic" and non-numeric suffixes
    are excluded; the numeric suffix maps to tray = number - 1.
    """
    vnir = _sensor_paths(raw_dir, f"{hole_id}_tsg")
    missing = [p.name for p in vnir.values() if not p.is_file()]
    if missing:
        raise StepError("discover", [f"missing VNIR file(s): {missing}"])

    tir = _sensor_paths(raw_dir, f"{hole_id}_tsg_tir")
    tir_found = [ext for ext, p in tir.items() if p.is_file()]
    if not tir_found:
        tir = None
    elif len(tir_found) != len(SENSOR_EXTS):
        missing_t = [p.name for ext, p in tir.items() if not p.is_file()]
        raise StepError(
            "discover",
            [f"incomplete TIR set (found {tir_found}, missing {missing_t}); "
             "provide all four <hole_id>_tsg_tir.* files or none"],
        )

    photos: dict[int, Path] = {}
    photo_notes: list[str] = []
    photo_re = re.compile(rf"^{re.escape(hole_id)}_(\d+)\.jpe?g$", re.IGNORECASE)
    for path in sorted(raw_dir.glob(f"{hole_id}_*.jpg")):
        if "mosaic" in path.stem.lower():
            photo_notes.append(f"excluded mosaic image: {path.name}")
            continue
        m = photo_re.match(path.name)
        if not m:
            photo_notes.append(f"ignored photo with non-numeric suffix: {path.name}")
            continue
        tray0 = int(m.group(1)) - 1
        if tray0 in photos:
            photo_notes.append(
                f"duplicate photo number for tray {tray0}: {path.name} "
                f"(keeping {photos[tray0].name})")
            continue
        photos[tray0] = path

    return {"vnir": vnir, "tir": tir, "photos": photos,
            "photo_notes": photo_notes}


# --------------------------------------------------------------------------
# .tsg / .ini parsing
# --------------------------------------------------------------------------

def read_tsg_sections(path: Path) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1].strip().lower()
            sections[current] = []
        elif current is not None:
            sections[current].append(line)
    return sections


def parse_dimensions(sections: dict[str, list[str]]) -> dict[str, int]:
    dims: dict[str, int] = {}
    for line in sections.get("dimensions", []):
        if "=" in line:
            k, v = line.split("=", 1)
            try:
                dims[k.strip()] = int(v.strip())
            except ValueError:
                pass
    return dims


def parse_sample_headers(sections: dict[str, list[str]]) -> list[dict]:
    samples = []
    for line in sections.get("sample headers", []):
        if not line.strip():
            continue
        m = SAMPLE_RE.match(line)
        if not m:
            raise StepError("parse", [f"unparseable sample header: {line!r}"])
        samples.append({
            "index": int(m.group(1)),
            "name": m.group(2),
            "tray": int(m.group(3)),    # 1-based tray number (T)
            "line": int(m.group(4)),    # row within tray (L), 1-based
            "point": int(m.group(5)),   # point within row (P)
            "depth": float(m.group(6)),  # D, metres
            "x": float(m.group(7)),      # X, section distance mm
        })
    return samples


def parse_band_headers(sections: dict[str, list[str]]) -> dict[int, dict]:
    """band number -> {name, guid, class_no} from [band headers].

    Numbering may be sparse. The 5th ';'-separated field is the class number
    that decodes classified scalar parameters (-1 = unclassified).
    """
    bands: dict[int, dict] = {}
    for line in sections.get("band headers", []):
        if not line.strip():
            continue
        m = re.match(r"(\d+):([^;]*)(;.*)?$", line)
        if not m:
            raise StepError("parse", [f"unparseable band header: {line!r}"])
        g = GUID_RE.search(line)
        fields = (m.group(3) or "").split(";")[1:]  # fields after the name
        class_no = None
        if len(fields) >= 4:
            try:
                class_no = int(fields[3])
            except ValueError:
                class_no = None
        bands[int(m.group(1))] = {
            "name": m.group(2),
            "guid": g.group(0).lower() if g else None,
            "class_no": class_no,
        }
    return bands


def parse_ini_params(path: Path) -> list[dict]:
    """Param_id catalogue; .ini may use CR-only line endings."""
    raw = path.read_bytes().decode("utf-8", errors="replace")
    params = []
    for line in re.split(r"\r\n|\r|\n", raw):
        if not line.startswith("Param_id_"):
            continue
        _slot, sep, rest = line.partition("=")
        if not sep:
            continue
        parts = rest.split(";")
        if len(parts) < 3:
            continue
        params.append({"ini_id": parts[0].strip(), "name": parts[1],
                       "guid": parts[2].strip().lower()})
    return params


def resolve_param_columns(params: list[dict], bands: dict[int, dict],
                          rep: Reporter) -> list[dict]:
    """Map each ini parameter to its plane-1 column (tsg band number).

    Primary key is the GUID; parameters whose GUIDs differ between the two
    files (or are absent) fall back to exact, unique name matching.
    """
    by_guid = {b["guid"]: num for num, b in bands.items() if b["guid"]}
    by_name: dict[str, list[int]] = {}
    for num, b in bands.items():
        by_name.setdefault(b["name"], []).append(num)

    resolved = []
    name_dupes = set()
    seen = set()
    misses = []
    name_mismatches = []
    fallbacks = []
    for p in params:
        if p["name"] in seen:
            name_dupes.add(p["name"])
        seen.add(p["name"])
        if p["name"].lower() == "index" and p["guid"] == "index":
            resolved.append({**p, "band": None, "method": "synthetic"})
            continue
        if p["guid"] in by_guid:
            num = by_guid[p["guid"]]
            method = "guid"
            if bands[num]["name"] != p["name"]:
                name_mismatches.append((p["name"], num, bands[num]["name"]))
        else:
            candidates = by_name.get(p["name"], [])
            if len(candidates) != 1:
                misses.append((p["name"], p["guid"], candidates))
                continue
            num = candidates[0]
            method = "name-fallback"
            fallbacks.append(p["name"])
        resolved.append({**p, "band": num, "method": method})

    rep.check("ini<->tsg parameter resolution (GUID, name fallback)",
              not misses,
              f"{len(resolved)} resolved; misses={misses}" if misses else
              f"{len(resolved)} resolved "
              f"({sum(1 for r in resolved if r['method'] == 'guid')} by GUID, "
              f"name fallback for {fallbacks})")
    rep.check("ini vs tsg parameter names consistent",
              not name_mismatches, f"mismatches={name_mismatches}")
    rep.check("parameter names unique", not name_dupes,
              f"dupes={sorted(name_dupes)}")
    return resolved


def parse_classes(tsg_path: Path) -> dict[int, dict]:
    """Parse all [class N] sections: {N: {name, max, entries{idx: name}}}."""
    classes: dict[int, dict] = {}
    class_no = None
    name = None
    maxn = None
    entries: dict[int, str] = {}

    def commit():
        nonlocal class_no, name, maxn, entries
        if class_no is not None and name:
            classes[class_no] = {"name": name, "max": maxn, "entries": entries}
        class_no, name, maxn, entries = None, None, None, {}

    with open(tsg_path, "r", errors="replace") as fh:
        for raw in fh:
            line = raw.strip()
            if line.startswith("["):
                commit()
                m = CLASS_HEADER_RE.fullmatch(line)
                if m:
                    class_no = int(m.group(1))
                continue
            if class_no is None or not line:
                continue
            key, sep, val = line.partition("=")
            if sep and key.strip() == "name":
                name = val.strip()
            elif sep and key.strip() == "max":
                try:
                    maxn = int(val.strip())
                except ValueError:
                    maxn = None
            else:
                m = CLASS_ENTRY_RE.match(line)
                if m:
                    entries[int(m.group(1))] = m.group(2).strip()
    commit()
    return classes


# --------------------------------------------------------------------------
# .bip cube
# --------------------------------------------------------------------------

def read_bip_cube(bip_path: Path, n_samples: int, n_bands: int,
                  rep: Reporter) -> tuple[np.ndarray, np.ndarray]:
    """Read the float32 bi-plane cube; byte-exact size validation."""
    expected_bytes = BIP_PLANES * n_samples * n_bands * 4
    actual_bytes = bip_path.stat().st_size
    rep.check(
        f".bip byte-exact for ({BIP_PLANES}, {n_samples}, {n_bands}) float32",
        actual_bytes == expected_bytes,
        f"file={actual_bytes} bytes, expected={expected_bytes}",
    )
    if actual_bytes != expected_bytes:
        raise StepError("parse", [rep.failures[-1]])
    cube = np.fromfile(bip_path, dtype="<f4").reshape(
        BIP_PLANES, n_samples, n_bands)
    rep.check("no NaN anywhere in the cube", not bool(np.isnan(cube).any()))
    return cube[0], cube[1]


# --------------------------------------------------------------------------
# wavelengths
# --------------------------------------------------------------------------

def wavelength_specs(sections: dict[str, list[str]]):
    """[wavelength specs] -> (start_nm, end_nm, unit) or None."""
    for line in sections.get("wavelength specs", []):
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 3:
            try:
                return float(parts[0]), float(parts[1]), parts[2]
            except ValueError:
                return None
    return None


def _uniform_runs(mask: np.ndarray, min_len: int):
    """Yield (start, length) runs of True in mask with length >= min_len."""
    i, n = 0, mask.size
    while i < n:
        if mask[i]:
            j = i
            while j < n and mask[j]:
                j += 1
            if j - i >= min_len:
                yield i, j - i
            i = j
        else:
            i += 1


def locate_vnir_wavelengths(cal_path: Path, n_bands: int, spec,
                            rep: Reporter) -> np.ndarray:
    """Scan .cal for a uniform-step monotonic float32 ramp of n_bands values.

    When [wavelength specs] is available, the ramp must match its start/end.
    Otherwise any uniform increasing run of the right length qualifies.
    """
    arr = np.fromfile(cal_path, dtype="<f4")
    diffs = np.diff(arr)
    if spec is not None:
        start, end, _unit = spec
        step = (end - start) / (n_bands - 1)
        tol = max(0.025 * abs(step), 1e-4)
        mask = np.abs(diffs - step) < tol
    else:
        step = None
        close = np.abs(diffs[1:] - diffs[:-1]) <= np.maximum(
            1e-6, 1e-4 * np.abs(diffs[:-1]))
        mask = np.concatenate(([False], close)) & (diffs > 0)

    candidates = []
    for i, run_len in _uniform_runs(mask, n_bands - 1):
        window = arr[i:i + n_bands]
        if window.size < n_bands:
            continue
        wd = np.diff(window.astype(np.float64))
        if not (wd > 0).all():
            continue
        if spec is not None:
            end_tol = max(0.25 * abs(step), 1e-3)
            if abs(float(window[0]) - start) > end_tol:
                continue
            if abs(float(window[-1]) - end) > end_tol:
                continue
        elif wd.min() != wd.max() and (wd.max() - wd.min()) > 1e-3 * wd.mean():
            continue
        candidates.append(window)

    rep.check("wavelength ramp located in .cal by scanning",
              len(candidates) > 0,
              f"{len(candidates)} candidate window(s)" +
              (f" matching [wavelength specs] {start}->{end} nm"
               if spec is not None else " (no [wavelength specs] to match)"))
    if not candidates:
        raise StepError("parse", rep.failures[-1:])
    wavelengths = candidates[0]
    n_identical = sum(1 for w in candidates if np.array_equal(w, wavelengths))
    wd = np.diff(wavelengths.astype(np.float64))
    rep.check("wavelength ramp monotonic increasing, uniform step",
              bool((wd > 0).all() and wd.min() == wd.max()),
              f"n={len(wavelengths)}, first={float(wavelengths[0]):.4f}, "
              f"last={float(wavelengths[-1]):.4f}, step {wd.min():.6f}.."
              f"{wd.max():.6f}; {n_identical}/{len(candidates)} identical "
              "windows (one per tray)")
    return wavelengths


def wavelengths_from_specs(spec, n_bands: int, rep: Reporter) -> np.ndarray:
    """TIR: wavelengths computed linearly from [wavelength specs]."""
    if spec is None:
        rep.check("[wavelength specs] present", False,
                  "required to compute wavelengths linearly")
        raise StepError("parse", rep.failures[-1:])
    start, end, unit = spec
    rep.check("wavelength specs unit is nm", unit == "nm", unit)
    step = (end - start) / (n_bands - 1)
    rep.check("wavelength grid computed linearly from [wavelength specs]",
              step > 0, f"start={start}, end={end}, step={step}")
    return start + step * np.arange(n_bands)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def fmt_f32(value: float) -> str:
    """Shortest string that round-trips to the same float32 bits."""
    return np.format_float_positional(np.float32(value), unique=True, trim="-")


def null_mask(sensor: str, arr: np.ndarray) -> np.ndarray:
    op, thr = NULL_RULE[sensor]
    return arr <= thr if op == "<=" else arr < thr


def sensor_order(names) -> list[str]:
    """Canonical sensor ordering: vnir first, then tir, then alphabetical."""
    rank = {"vnir": 0, "tir": 1}
    return sorted(names, key=lambda s: (rank.get(s, 2), s))


def _choose_min1_column(candidates: list[str], tsg_path: Path,
                        rep: Reporter | None) -> str:
    """Pick one Min1 column among several TSA scalar sets (sTSAS/sTSAV/uTSAS…).

    Data-driven disambiguation, no hard-coded set names:
      1. resolve each candidate's band -> [class N] (band header 5th field);
      2. prefer columns decoded by a *system* class (name starts with "S_",
         not the user "U_" classes);
      3. if several remain, walk the [sclrsets] entries in file order and
         take the first entry whose digit string (e.g. 705 from
         "S_SWIR_TSA705") matches exactly one candidate's class name;
      4. otherwise fail loudly, listing every candidate and its class.
    """
    sections = read_tsg_sections(tsg_path)
    bands = parse_band_headers(sections)
    classes = parse_classes(tsg_path)
    col_by_name = {c["name"]: c["band"]
                   for c in resolve_param_columns(
                       parse_ini_params(tsg_path.with_suffix(".ini")),
                       bands, Reporter())}

    decoded = []  # (column, class_no, class_name)
    for cand in candidates:
        band = col_by_name.get(cand)
        class_no = bands[band]["class_no"] if band in bands else None
        if class_no is None or class_no < 0 or class_no not in classes:
            continue  # not a decodable classified parameter
        decoded.append((cand, class_no, classes[class_no]["name"]))
    if not decoded:
        raise StepError(
            "columns",
            [f"none of the Min1 candidates {candidates} resolves to a "
             f"[class N] section via its band header"])
    usable = decoded

    system = [d for d in usable if d[2].startswith("S_")]
    if system:
        usable = system
    if len(usable) == 1:
        chosen = usable[0][0]
    else:
        chosen = None
        sclrsets = [line.split(",", 1)[1].strip()
                    for line in sections.get("sclrsets", []) if "," in line]
        for entry in sclrsets:
            digits = "".join(ch for ch in entry if ch.isdigit())
            if not digits:
                continue
            hits = [d for d in usable if digits in d[2]]
            if len(hits) == 1:
                chosen = hits[0][0]
                break
        if chosen is None:
            raise StepError(
                "columns",
                [f"cannot choose between Min1 candidates "
                 f"{[(c, n) for c, _k, n in usable]} "
                 f"(sclrsets={sclrsets}); pick the intended TSA scalar set "
                 f"manually"])
    if rep is not None:
        cls = next(n for c, _k, n in decoded if c == chosen)
        rep.check(f"Min1 column chosen among {len(candidates)} TSA scalar "
                  f"sets", True, f"'{chosen}' (class '{cls}'); candidates: "
                  f"{[(c, n) for c, _k, n in decoded]}")
    return chosen


def find_tsa_columns(csv_path: Path, tsg_path: Path | None = None,
                     rep: Reporter | None = None) -> dict[str, str]:
    """Locate the Min1/Grp1/Wt1/Error/NIL_Stat column set of one TSA run.

    With several TSA scalar sets in the file (e.g. Min1 sTSAS / Min1 sTSAV /
    Min1 uTSAS) the Min1 column is chosen via _choose_min1_column (requires
    tsg_path); the other four columns follow the same name suffix.
    """
    header = pd.read_csv(csv_path, nrows=0).columns.tolist()
    min1_cands = [c for c in header if c.startswith("Min1")]
    if not min1_cands:
        raise StepError("columns",
                        [f"no 'Min1*' column in {csv_path.name}"])
    if len(min1_cands) == 1:
        chosen = min1_cands[0]
    else:
        if tsg_path is None:
            raise StepError(
                "columns",
                [f"ambiguous Min1 columns in {csv_path.name}: {min1_cands}; "
                 "the raw .tsg is required to choose the TSA scalar set"])
        chosen = _choose_min1_column(min1_cands, tsg_path, rep)
    suffix = chosen[len("Min1"):]
    found: dict[str, str] = {}
    missing = []
    for key, prefix in TSA_PREFIXES.items():
        name = prefix + suffix
        if name in header:
            found[key] = name
        else:
            missing.append(name)
    if missing:
        raise StepError(
            "columns",
            [f"TSA set '{suffix.strip()}' incomplete in {csv_path.name}: "
             f"missing columns {missing}"])
    return found


def class_for_column(bands: dict[int, dict], classes: dict[int, dict],
                     band: int | None, col_label: str,
                     rep: Reporter) -> dict:
    """Resolve the [class N] section decoding a classified scalar column.

    The class number comes from the band header (5th field); the class
    section is then read by its own `name =` line and entries.
    """
    if band is None or band not in bands:
        raise StepError("classes", [f"{col_label}: band column not resolved"])
    class_no = bands[band]["class_no"]
    if class_no is None or class_no < 0 or class_no not in classes:
        raise StepError(
            "classes",
            [f"{col_label}: band {band} carries no usable class number "
             f"({class_no}); available classes: "
             f"{[(n, c['name']) for n, c in sorted(classes.items())]}"])
    cls = classes[class_no]
    rep.check(f"{col_label}: decoded by [class {class_no}] "
              f"'{cls['name']}' (located via band header class number)",
              len(cls["entries"]) > 0, f"{len(cls['entries'])} entries")
    return cls


# --------------------------------------------------------------------------
# step 1/2: parse one sensor (VNIR or TIR)
# --------------------------------------------------------------------------

def parse_sensor(sensor: str, paths: dict[str, Path],
                 fixture_dir: Path) -> dict:
    """Parse one TSG sensor set into fixture CSVs + self-check report.

    Writes {sensor}-scalars.csv, {sensor}-wavelengths.csv and
    {sensor}-parse-report.txt into fixture_dir. Raises StepError when any
    self-check fails. Returns a stats dict.
    """
    rep = Reporter()
    rep(f"{sensor.upper()} parse report")
    rep(f"raw base  : {paths['tsg'].with_suffix('')}")
    rep(f"output dir: {fixture_dir}")
    rep("")

    for ext in SENSOR_EXTS:
        rep.check(f"input exists: {paths[ext].name}", paths[ext].is_file(),
                  f"{paths[ext].stat().st_size} bytes"
                  if paths[ext].is_file() else "")

    # ---------------- .tsg / .ini ----------------
    sections = read_tsg_sections(paths["tsg"])
    rep("tsg sections: " + ", ".join(f"[{s}]" for s in sections))
    dims = parse_dimensions(sections)
    n_samples = dims.get("samples", -1)
    n_bands = dims.get("bands", -1)
    rep.check("[dimensions] samples/bands present",
              n_samples > 0 and n_bands > 0,
              f"samples={n_samples}, bands={n_bands}")

    samples = parse_sample_headers(sections)
    rep.check("[sample headers] count == [dimensions] samples",
              len(samples) == n_samples, f"{len(samples)} header lines")
    rep.check("sample indices sequential 0..N-1",
              [s["index"] for s in samples] == list(range(len(samples))))

    hdr_t = np.array([s["tray"] for s in samples])
    hdr_l = np.array([s["line"] for s in samples])
    hdr_d = np.array([s["depth"] for s in samples])
    hdr_x = np.array([s["x"] for s in samples])

    trays_sorted = sorted(int(t) for t in np.unique(hdr_t))
    rows_per_tray = int(hdr_l.max()) if len(hdr_l) else 0
    n_trays = len(trays_sorted)
    rep.check("tray numbers contiguous from 1",
              trays_sorted == list(range(1, n_trays + 1)),
              f"{n_trays} trays, T={trays_sorted[0] if trays_sorted else '-'}.."
              f"{trays_sorted[-1] if trays_sorted else '-'}")
    rep.check("row numbers contiguous 1..L within every tray",
              all(sorted(np.unique(hdr_l[hdr_t == t]).tolist())
                  == list(range(1, rows_per_tray + 1)) for t in trays_sorted),
              f"{rows_per_tray} rows per tray")
    per_tray = [int((hdr_t == t).sum()) for t in trays_sorted]
    per_section = sorted({int(((hdr_t == t) & (hdr_l == l)).sum())
                          for t in trays_sorted
                          for l in range(1, rows_per_tray + 1)})
    rep(f"dataset shape (data-derived): {n_trays} trays x {rows_per_tray} rows"
        f" = {n_trays * rows_per_tray} sections; samples per tray "
        f"{sorted(set(per_tray))}, per section {per_section}")
    rep(f"header depth range {hdr_d.min():.6f} .. {hdr_d.max():.6f} m")

    bands = parse_band_headers(sections)
    rep(f"[band headers]: {len(bands)} entries, numbering "
        f"{min(bands)}..{max(bands)}"
        + (" (sparse)" if len(bands) != max(bands) - min(bands) + 1 else ""))

    ini_params = parse_ini_params(paths["ini"])
    rep.check("ini Param_id catalogue non-empty", len(ini_params) > 1,
              f"{len(ini_params)} entries")
    columns = resolve_param_columns(ini_params, bands, rep)
    col_by_name = {c["name"]: c["band"] for c in columns}

    for req in REQUIRED_COLUMNS:
        rep.check(f"required system column '{req}' present",
                  col_by_name.get(req) is not None)
    for opt in OPTIONAL_COLUMNS:
        if col_by_name.get(opt) is None:
            rep(f"note: optional column '{opt}' not present")

    rep.raise_if_failed("parse")

    # ---------------- .bip ----------------
    spectra, scalars = read_bip_cube(paths["bip"], n_samples, n_bands, rep)
    nm = null_mask(sensor, scalars)
    n_null_cells = int(nm.sum())
    rep(f"null cells in scalar plane (sentinel, rule {NULL_RULE[sensor][0]}"
        f" {NULL_RULE[sensor][1]}): {n_null_cells}")
    all_null = [(b, bands[b]["name"]) for b in sorted(bands)
                if b < n_bands and nm[:, b].all()]
    if all_null:
        rep(f"scalar bands entirely empty (all sentinel): {all_null}")

    # scalar cross-checks against sample headers
    depth_bip = scalars[:, col_by_name["Depth (m)"]].astype(np.float64)
    tray_bip = scalars[:, col_by_name["Tray"]]
    section_bip = scalars[:, col_by_name["Section"]]
    rep.check("bip Tray (0-based) == T-1",
              bool((tray_bip.astype(int) == hdr_t - 1).all()),
              f"range {tray_bip.min():.0f}..{tray_bip.max():.0f}")
    rep.check("bip Section == (T-1)*rows + L",
              bool((section_bip.astype(int)
                    == (hdr_t - 1) * rows_per_tray + hdr_l).all()),
              f"range {section_bip.min():.0f}..{section_bip.max():.0f}")
    rep.check("bip Depth (m) matches header D at float32 precision",
              float(np.abs(depth_bip - hdr_d).max()) < DEPTH_TOL,
              f"max |diff|={np.abs(depth_bip - hdr_d).max():.3e} m")
    if col_by_name.get("SecDist (mm)") is not None:
        secdist_bip = scalars[:, col_by_name["SecDist (mm)"]].astype(np.float64)
        rep.check("bip SecDist (mm) matches header X at float32 precision",
                  float(np.abs(secdist_bip - hdr_x).max()) < SECDIST_TOL,
                  f"max |diff|={np.abs(secdist_bip - hdr_x).max():.3e} mm")

    mono_ok = True
    worst = 0.0
    for t in np.unique(hdr_t):
        dd = np.diff(depth_bip[hdr_t == t])
        if dd.size:
            worst = min(worst, float(dd.min()))
            if (dd < 0).any():
                mono_ok = False
    rep.check("depth non-decreasing within every tray", mono_ok,
              f"worst within-tray step={worst:.6f} m")

    spec_vals = spectra[~null_mask(sensor, spectra)]
    rep(f"spectra value range (non-null): {float(spec_vals.min()):.6f} .. "
        f"{float(spec_vals.max()):.6f}; "
        f"null spectral values={int(null_mask(sensor, spectra).sum())}")

    # ---------------- wavelengths ----------------
    spec = wavelength_specs(sections)
    if sensor == "vnir":
        wavelengths = locate_vnir_wavelengths(paths["cal"], n_bands, spec, rep)
    else:
        rep("note: the TIR .cal holds per-tray radiometric calibration records "
            "(binary, no wavelength table); wavelengths come from "
            "[wavelength specs].")
        wavelengths = wavelengths_from_specs(spec, n_bands, rep)

    rep.raise_if_failed("parse")

    # ---------------- write CSVs ----------------
    fixture_dir.mkdir(parents=True, exist_ok=True)
    if not any(c["band"] is None and c["name"] == "Index" for c in columns):
        columns = [{"name": "Index", "band": None, "method": "synthetic"}] + columns
        rep("note: no 'Index' parameter in ini catalogue; "
            "synthetic 0-based Index column prepended")

    scalars_csv = fixture_dir / f"{sensor}-scalars.csv"
    index_col = np.arange(n_samples, dtype=np.float32)
    col_data = [index_col if c["band"] is None else scalars[:, c["band"]]
                for c in columns]
    with open(scalars_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([c["name"] for c in columns])
        for i in range(n_samples):
            row = []
            for c, values in zip(columns, col_data):
                v = values[i]
                if c["band"] is not None and null_mask(sensor, np.float32(v)):
                    row.append("")
                else:
                    row.append(fmt_f32(v))
            writer.writerow(row)
    null_counts = {c["name"]: int(null_mask(sensor, scalars[:, c["band"]]).sum())
                   for c in columns if c["band"] is not None
                   and null_mask(sensor, scalars[:, c["band"]]).any()}
    rep(f"wrote {scalars_csv}")
    rep(f"columns with nulls (sentinel -> empty): {null_counts or 'none'}")

    wl_csv = fixture_dir / f"{sensor}-wavelengths.csv"
    # historical convention: VNIR wavelength bands are 1-based, TIR 0-based
    band_start = 1 if sensor == "vnir" else 0
    with open(wl_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["band", "wavelength_nm"])
        for b, w in enumerate(wavelengths, start=band_start):
            writer.writerow([b, fmt_f32(w)])
    rep(f"wrote {wl_csv}")

    # read-back verification
    with open(scalars_csv, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)
        n_rows = sum(1 for _ in reader)
    rep.check(f"{sensor}-scalars.csv shape",
              n_rows == n_samples and len(header) == len(columns),
              f"{n_rows} data rows x {len(header)} columns")
    with open(wl_csv, newline="", encoding="utf-8") as fh:
        reader = csv.reader(fh)
        next(reader)
        n_rows = sum(1 for _ in reader)
    rep.check(f"{sensor}-wavelengths.csv rows", n_rows == n_bands,
              f"{n_rows} rows")

    rep("")
    if rep.failures:
        rep(f"RESULT: {len(rep.failures)} FAILED CHECKS: {rep.failures}")
    else:
        rep("RESULT: all checks passed")
    rep.save(fixture_dir / f"{sensor}-parse-report.txt")
    print(f"report written to {fixture_dir / f'{sensor}-parse-report.txt'}")
    rep.raise_if_failed("parse")

    return {
        "sensor": sensor,
        "n_samples": n_samples,
        "n_bands": n_bands,
        "n_trays": n_trays,
        "rows_per_tray": rows_per_tray,
        "n_sections": n_trays * rows_per_tray,
        "depth_min": float(hdr_d.min()),
        "depth_max": float(hdr_d.max()),
        "wl_first": float(wavelengths[0]),
        "wl_last": float(wavelengths[-1]),
        "scalars_csv": str(scalars_csv),
        "wavelengths_csv": str(wl_csv),
    }


# --------------------------------------------------------------------------
# step 3: core strip images
# --------------------------------------------------------------------------

def parse_section_depths(tsg_path: Path) -> dict[tuple[int, int], tuple]:
    """{(tray T, row L): (dmin, dmax, n_samples)} from [sample headers]."""
    sections = read_tsg_sections(tsg_path)
    groups: dict[tuple[int, int], list[float]] = {}
    for s in parse_sample_headers(sections):
        groups.setdefault((s["tray"], s["line"]), []).append(s["depth"])
    return {k: (min(v), max(v), len(v)) for k, v in groups.items()}


def _runs_above(profile: np.ndarray, thr: float):
    runs, i, n = [], 0, len(profile)
    while i < n:
        if profile[i] > thr:
            j = i
            while j < n and profile[j] > thr:
                j += 1
            runs.append((i, j - 1))
            i = j
        else:
            i += 1
    return runs


def detect_geometry(gray: np.ndarray, rows_per_tray: int, warn: list[str]):
    """Detect core rows/columns on the 1/DS grayscale image.

    Returns (x_left, x_right, [(top, bottom) x rows_per_tray], ruler_start).
    Horizontal geometry constants are given for the reference width
    REF_SMALL_W and scaled to the actual image width.
    """
    h, w = gray.shape
    sxr = w / REF_SMALL_W
    syr = h / REF_SMALL_H
    bright = gray > BRIGHT

    x_in0, x_in1 = round(60 * sxr), round(1300 * sxr)
    rowfrac = bright[:, x_in0:x_in1].mean(axis=1)
    railfrac = (gray > WHITE)[:, x_in0:x_in1].mean(axis=1)

    # specular divider rails: scanlines whose near-white fraction is an
    # isolated local maximum (flanked by non-white transition scanlines).
    is_rail = np.zeros(h, dtype=bool)
    for y in range(h):
        if railfrac[y] <= RAIL_WF:
            continue
        win = railfrac[max(0, y - 6):y + 7]
        if railfrac[y] < win.max():
            continue
        left = railfrac[max(0, y - 8):max(0, y - 3)]
        right = railfrac[y + 4:y + 9]
        if len(left) and len(right) and (left < 0.2).all() \
                and (right < 0.2).all():
            is_rail[y] = True

    # core vertical extent: first/last scanline >0.5 sustained over most of
    # the surrounding window (rejects thin bright rails and tick marks).
    sustain_n = max(1, round(25 * syr))
    sustain_min = max(1, round(20 * syr))
    sustain = np.convolve(rowfrac > 0.5, np.ones(sustain_n, dtype=int),
                          mode="same")
    solid = np.where(sustain >= sustain_min)[0]
    if len(solid) == 0:
        raise StepError("strips", ["no solid core rows found"])
    y_top, y_bot = int(solid[0]), int(solid[-1])

    # inter-row gaps: local minima around the expected regular-lattice
    # positions (rows_per_tray derived from the TSG sample headers).
    pitch = (y_bot - y_top + 1) / rows_per_tray
    smooth = np.convolve(rowfrac, np.ones(3) / 3, mode="same")
    gap_half = max(2, round(14 * syr))
    margin = max(2, round(20 * syr))
    gap_seeds = []
    for k in range(1, rows_per_tray):
        exp = y_top + pitch * k
        lo = int(round(exp - gap_half))
        hi = int(round(exp + gap_half))
        lo = max(lo, gap_seeds[-1] + margin if gap_seeds else y_top + margin)
        hi = min(hi, y_bot - margin)
        gap_seeds.append(int(lo + np.argmin(smooth[lo:hi + 1])))

    # row bands: from each band centre walk outward until a dark scanline or
    # an isolated specular divider rail; clamped at neighbouring gap seeds.
    edge = max(1, round(12 * syr))
    min_row_h = max(2, round(40 * syr))
    bands = []
    for k in range(rows_per_tray):
        g_lo = gap_seeds[k - 1] if k > 0 else max(y_top - edge, 0)
        g_hi = (gap_seeds[k] if k < rows_per_tray - 1
                else min(y_bot + edge, h - 1))
        centre = (g_lo + g_hi) // 2
        top = centre
        while (top > g_lo and rowfrac[top - 1] >= ROW_DARK
               and not is_rail[top - 1]):
            top -= 1
        bot = centre
        while (bot < g_hi and rowfrac[bot + 1] >= ROW_DARK
               and not is_rail[bot + 1]):
            bot += 1
        if bot - top + 1 < min_row_h:
            warn.append(f"row {k + 1}: dark/empty row? lattice fallback used")
            top, bot = g_lo + 3, g_hi - 3
        bands.append((top + ROW_INSET, bot - ROW_INSET))

    # horizontal: profiles restricted to the detected row bands
    rowmask = np.zeros(h, dtype=bool)
    for t, b in bands:
        rowmask[t:b + 1] = True
    sub = gray[rowmask, :]
    colfrac = (sub > BRIGHT).mean(axis=0)
    white = (sub > WHITE).mean(axis=0)

    # left edge: anchor on the solid core wall, extend left over markers.
    xsolid = None
    for x in range(round(30 * sxr), round(200 * sxr)):
        if colfrac[x] > 0.85 and colfrac[x:x + 8].min() > 0.6:
            xsolid = x
            break
    if xsolid is None:
        raise StepError("strips", ["left core edge not found"])
    x_left = xsolid
    while x_left > max(xsolid - round(8 * sxr), round(40 * sxr)) \
            and colfrac[x_left - 1] > 0.3:
        x_left -= 1
    x_left += COL_INSET

    # right edge: the white ruler is a sustained blown-out-white strip; the
    # core channel ends left of it. Strict thresholds so that empty tray
    # channel (pale plastic) does not trigger detection.
    ruler_start = None
    for x in range(round(1290 * sxr), min(round(1368 * sxr), w - 6)):
        if white[x] > 0.8 and white[x:x + 6].min() > 0.7:
            ruler_start = x
            break
    if ruler_start is None:
        warn.append("ruler not found by whiteness; using fallback")
        ruler_start = int(np.where(colfrac > 0.5)[0][-1]) - round(18 * sxr)
    x_right = ruler_start - 1
    for _ in range(15):
        if white[x_right] > 0.4:
            x_right -= 1
        elif white[x_right] < 0.05 and colfrac[x_right] < 0.65:
            x_right -= 1
        else:
            break
    x_right -= COL_INSET

    return x_left, x_right, bands, ruler_start


def foam_fraction(rgb: np.ndarray, top: int, bot: int, x0: int, x1: int) -> float:
    reg = rgb[top:bot + 1, x0:x1 + 1, :].astype(np.int32)
    r, g, b = reg[..., 0], reg[..., 1], reg[..., 2]
    foam = (r > 150) & (g > 80) & (g < 200) & (b < 140) & (r - b > 60)
    return float(foam.mean())


def make_strips(tsg_path: Path, photos: dict[int, Path], hole_id: str,
                out_dir: Path) -> list[dict]:
    """Crop core-row strip JPEGs from tray photos + write strips.json/report.

    photos: {0-based tray: image path}. Trays without a photo are skipped
    with a note in the report. Returns the strips.json records.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    rep = Reporter()
    rep(f"{hole_id} core strip rebuild")
    rep("=" * 72)
    rep(f"depths from : {tsg_path}")
    rep(f"output dir  : {out_dir}")
    rep(f"detection at 1/{DS} scale, strip width {STRIP_WIDTH} px, "
        f"JPEG q{JPEG_QUALITY}")
    rep("")

    depths = parse_section_depths(tsg_path)
    n_samples = sum(v[2] for v in depths.values())
    rows_per_tray = max(l for _t, l in depths)
    tray_numbers = sorted({t for t, _l in depths})
    g_min = min(v[0] for v in depths.values())
    g_max = max(v[1] for v in depths.values())
    size_set = sorted({v[2] for v in depths.values()})
    rep("TSG [sample headers] summary (data-derived)")
    rep(f"  samples parsed      : {n_samples}")
    rep(f"  (tray,row) sections : {len(depths)}")
    rep(f"  trays               : {len(tray_numbers)} "
        f"(T={tray_numbers[0]}..{tray_numbers[-1]})")
    rep(f"  rows per tray       : {rows_per_tray}")
    rep(f"  samples per section : {size_set}")
    rep(f"  global depth range  : {g_min:.6f} .. {g_max:.6f} m")
    rep("")

    # per-section table ordered by global section number
    sections = []
    for (t, l), (dmin, dmax, n) in sorted(depths.items()):
        sections.append(((t - 1) * rows_per_tray + l, t, l, dmin, dmax, n))
    sections.sort()

    # inter-section gap / overlap scan (data-driven anomaly notes)
    gap_notes: dict[int, str] = {}
    rep(f"inter-section depth discontinuities (> {GAP_NOTE_MIN} m):")
    n_gaps = 0
    for a, b in zip(sections, sections[1:]):
        gap = b[3] - a[4]
        if gap > GAP_NOTE_MIN:
            n_gaps += 1
            rep(f"  section {a[0]} (tray {a[1]:04d} row {a[2]}) ends "
                f"{a[4]:.3f} m -> section {b[0]} starts {b[3]:.3f} m: "
                f"gap {gap:.3f} m (core loss, recorded as-is)")
            gap_notes[b[0]] = (
                f"{gap:.3f} m core-loss gap above this section "
                f"(between sections {a[0]} and {b[0]}, per TSG depths)")
        elif gap < -0.001:
            rep(f"  WARNING overlap: section {a[0]} ends {a[4]:.3f} m, "
                f"section {b[0]} starts {b[3]:.3f} m")
    if n_gaps == 0:
        rep("  none")
    clamp_notes: dict[int, str] = {}
    last = sections[-1]
    if abs(last[3] - last[4]) < 0.001:
        clamp_notes[last[0]] = (
            f"depth clamped at {last[3]:.3f} m in source TSG (whole section)")
        rep(f"  section {last[0]} depth clamped at {last[3]:.3f} m "
            f"(min {last[3]:.6f}, max {last[4]:.6f}) - recorded as-is")
    rep("")

    rep("per-tray geometry (scaled detection px) and foam scan:")
    records: list[dict] = []
    n_files = 0
    file_sizes = []
    foam_rows = []
    all_warnings = []

    for t in tray_numbers:
        photo_path = photos.get(t - 1)
        if photo_path is None:
            all_warnings.append(
                f"tray {t:04d}: no photo ({hole_id}_{t:04d}.jpg), skipped")
            rep(f"  {t:04d} -- no photo, skipped")
            continue
        warn: list[str] = []
        with Image.open(photo_path) as im:
            im = im.convert("RGB")
            fw, fh = im.size
            small = im.resize((fw // DS, fh // DS), Image.Resampling.BILINEAR)
            rgb8 = np.asarray(small, dtype=np.uint8)
            gray8 = rgb8.astype(np.float32).mean(axis=2)

            sxr = (fw // DS) / REF_SMALL_W
            syr = (fh // DS) / REF_SMALL_H
            x0, x1, bands, ruler = detect_geometry(gray8, rows_per_tray, warn)

            # sanity checks against rig geometry (scaled to this photo size)
            if not (round(40 * sxr) <= x0 <= round(55 * sxr)):
                warn.append(f"x_left {x0} outside expected "
                            f"{round(40 * sxr)}..{round(55 * sxr)}")
            if not (round(1320 * sxr) <= x1 <= round(1345 * sxr)):
                warn.append(f"x_right {x1} outside expected "
                            f"{round(1320 * sxr)}..{round(1345 * sxr)}")
            if len(bands) != rows_per_tray:
                warn.append(f"{len(bands)} row bands instead of "
                            f"{rows_per_tray}")
            for k, (bt, bb) in enumerate(bands, 1):
                if not (round(40 * syr) <= bb - bt + 1 <= round(75 * syr)):
                    warn.append(f"row {k} height {bb - bt + 1} outside "
                                f"{round(40 * syr)}..{round(75 * syr)}")

            sx, sy = fw / (fw // DS), fh / (fh // DS)
            foam_flags = []
            for l in range(1, rows_per_tray + 1):
                if (t, l) not in depths:
                    warn.append(f"row {l}: no samples in TSG, skipped")
                    continue
                bt, bb = bands[l - 1]
                f_frac = foam_fraction(rgb8, bt, bb, x0, x1)
                is_foam = f_frac > FOAM_MIN_FRAC
                if is_foam:
                    foam_flags.append(f"L{l}:{f_frac * 100:.1f}%")
                    foam_rows.append((t, l, f_frac))

                box = (int(round(x0 * sx)), int(round(bt * sy)),
                       int(round((x1 + 1) * sx)), int(round((bb + 1) * sy)))
                strip = im.crop(box)
                out_h = max(1, round(strip.height * STRIP_WIDTH / strip.width))
                strip = strip.resize((STRIP_WIDTH, out_h),
                                     Image.Resampling.LANCZOS)
                fname = f"tray_{t:04d}_sec_{l}.jpg"
                strip.save(out_dir / fname, "JPEG", quality=JPEG_QUALITY)
                n_files += 1
                file_sizes.append((out_dir / fname).stat().st_size)

                sec = (t - 1) * rows_per_tray + l
                dmin, dmax, n = depths[(t, l)]
                notes = []
                if is_foam:
                    notes.append(f"orange foam filler present "
                                 f"(~{f_frac * 100:.1f}% of strip area)")
                if sec in gap_notes:
                    notes.append(gap_notes[sec])
                if sec in clamp_notes:
                    notes.append(clamp_notes[sec])
                records.append({
                    "tray": t - 1,
                    "tray_label": f"{t:04d}",
                    "section": sec,
                    "row": l,
                    "depth_from": round(dmin, 3),
                    "depth_to": round(dmax, 3),
                    "file": fname,
                    "note": "; ".join(notes),
                })

        band_desc = " ".join(f"{bt}-{bb}({bb - bt + 1})" for bt, bb in bands)
        rep(f"  {t:04d} {fw}x{fh:<5} {x0:>4} {x1:>4} {ruler:>5} "
            f"{band_desc:52} {','.join(foam_flags) or '-':10} "
            f"{'; '.join(warn) or 'ok'}")
        all_warnings.extend(f"tray {t:04d}: {w}" for w in warn)

    records.sort(key=lambda r: r["section"])
    with open(out_dir / "strips.json", "w", encoding="utf-8") as fh:
        json.dump(records, fh, indent=2, ensure_ascii=False)
        fh.write("\n")

    rep("")
    rep("foam rows (orange filler, fraction of strip area):")
    if foam_rows:
        for t, l, f_frac in foam_rows:
            sec = (t - 1) * rows_per_tray + l
            rep(f"  tray {t:04d} row {l} (section {sec}): "
                f"{f_frac * 100:.1f}%")
    else:
        rep("  none")
    rep("")
    rep("output summary:")
    rep(f"  strip files written : {n_files} "
        f"({len(tray_numbers)} trays x {rows_per_tray} rows = "
        f"{len(tray_numbers) * rows_per_tray} sections in TSG; "
        f"{len(photos)} photos available)")
    if file_sizes:
        rep(f"  JPEG size bytes     : min {min(file_sizes)}, "
            f"max {max(file_sizes)}, total {sum(file_sizes)}")
    rep(f"  strips.json records : {len(records)}")
    rep("")
    if all_warnings:
        rep(f"WARNINGS ({len(all_warnings)}):")
        for w in all_warnings:
            rep(f"  {w}")
    else:
        rep("all geometry sanity checks passed")

    rep.save(out_dir / "strips-report.txt")
    print(f"report written to {out_dir / 'strips-report.txt'}")
    return records


# --------------------------------------------------------------------------
# step 4: mineral intervals
# --------------------------------------------------------------------------

def _nanmean_or_none(arr):
    if np.isnan(arr).all():
        return None
    return float(np.nanmean(arr))


def _round6(v):
    return None if v is None else round(v, 6)


def build_intervals(fixture_dir: Path, tsg_paths: dict[str, Path],
                    hole_id: str, wt1_min: dict, error_max: dict,
                    nil_max: dict) -> dict:
    """Run-length compress Min1 into mineral intervals for each sensor.

    tsg_paths: {sensor: path to that sensor's .tsg} (class decoding).
    Thresholds are passed in (kept as script-top constants in
    build_intervals.py). Writes intervals.json + intervals-report.txt.
    """
    rep = Reporter()
    sensors = sensor_order(tsg_paths)
    rep(f"Mineral interval rebuild - hole {hole_id}")
    rep(f"fixture dir : {fixture_dir}")
    rep(f"sensors     : {sensors}")
    rep(f"thresholds  : WT1_MIN={wt1_min} ERROR_MAX={error_max} "
        f"NIL_MAX={nil_max}")
    rep("")

    payload = {
        "hole_id": hole_id,
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "thresholds": {"wt1_min": wt1_min, "error_max": error_max,
                       "nil_max": nil_max},
        "classes": {},
        "sensors": {},
    }
    summary: dict[str, dict] = {}

    for sensor in sensors:
        csv_path = fixture_dir / f"{sensor}-scalars.csv"
        if not csv_path.is_file():
            raise StepError("intervals", [f"missing {csv_path}; run the "
                                          f"{sensor} parse step first"])
        cols = find_tsa_columns(csv_path, tsg_paths[sensor], rep)
        df = pd.read_csv(
            csv_path,
            usecols=["Depth (m)", "Tray", cols["min1"], cols["grp1"],
                     cols["wt1"], cols["error"], cols["nil"]],
        )

        sections = read_tsg_sections(tsg_paths[sensor])
        bands = parse_band_headers(sections)
        classes = parse_classes(tsg_paths[sensor])
        col_by_name = {c["name"]: c["band"]
                       for c in resolve_param_columns(
                           parse_ini_params(tsg_paths[sensor].with_suffix(".ini")),
                           bands, rep)}
        minerals = class_for_column(
            bands, classes, col_by_name.get(cols["min1"]),
            cols["min1"], rep)
        groups = class_for_column(
            bands, classes, col_by_name.get(cols["grp1"]),
            cols["grp1"], rep)

        depth = df["Depth (m)"].to_numpy(np.float64)
        tray = df["Tray"].to_numpy(np.float64)
        min1 = df[cols["min1"]].to_numpy(np.float64)
        grp1 = df[cols["grp1"]].to_numpy(np.float64)
        wt1 = df[cols["wt1"]].to_numpy(np.float64)
        error = df[cols["error"]].to_numpy(np.float64)
        nil = df[cols["nil"]].to_numpy(np.float64)

        # run-length encoding; NaN (empty Min1) -> -1 sentinel so consecutive
        # unassigned samples merge into a single run
        unassigned = np.isnan(min1)
        key = np.where(unassigned, -1.0, min1)
        change = np.empty(len(key), dtype=bool)
        change[0] = True
        change[1:] = key[1:] != key[:-1]
        starts = np.flatnonzero(change)
        ends = np.append(starts[1:], len(key))

        intervals = []
        for seq, (s, e) in enumerate(zip(starts, ends), start=1):
            wt_avg = _nanmean_or_none(wt1[s:e])
            err_avg = _nanmean_or_none(error[s:e])
            nil_avg = _nanmean_or_none(nil[s:e])
            if unassigned[s]:
                mineral_index = mineral = grp_index = grp = None
                status, flags = "doubtful", "unassigned"
            else:
                mineral_index = int(min1[s])
                mineral = minerals["entries"].get(mineral_index)
                grp_index = None if np.isnan(grp1[s]) else int(grp1[s])
                grp = groups["entries"].get(grp_index) \
                    if grp_index is not None else None
                doubtful = (
                    (wt_avg is not None and wt_avg < wt1_min[sensor])
                    or (err_avg is not None and err_avg > error_max[sensor])
                    or (nil_avg is not None and nil_avg > nil_max[sensor])
                )
                status, flags = ("doubtful" if doubtful else "confirmed"), None
            intervals.append({
                "seq": seq,
                "depth_from": _round6(float(depth[s])),
                "depth_to": _round6(float(depth[e - 1])),
                "tray_from": int(tray[s]),
                "tray_to": int(tray[e - 1]),
                "n_samples": int(e - s),
                "mineral_index": mineral_index,
                "mineral": mineral,
                "grp_index": grp_index,
                "grp": grp,
                "wt1_avg": _round6(wt_avg),
                "error_avg": _round6(err_avg),
                "nil_avg": _round6(nil_avg),
                "status": status,
                "flags": flags,
            })

        total = len(intervals)
        n_unassigned = sum(1 for iv in intervals if iv["flags"] == "unassigned")
        n_confirmed = sum(1 for iv in intervals if iv["status"] == "confirmed")
        n_doubtful = total - n_confirmed
        n_samples_sum = sum(iv["n_samples"] for iv in intervals)
        rep.check(f"{sensor}: interval n_samples tiles all samples",
                  n_samples_sum == len(df),
                  f"sum(n_samples)={n_samples_sum}, csv rows={len(df)}")
        rep.check(f"{sensor}: unassigned runs flagged doubtful/unassigned",
                  all(iv["status"] == "doubtful" and iv["flags"] == "unassigned"
                      for iv in intervals if iv["mineral"] is None))
        rep(f"{sensor}: {total} intervals ({n_unassigned} unassigned), "
            f"confirmed/doubtful {n_confirmed}/{n_doubtful}, depth "
            f"{depth.min():.3f}..{depth.max():.3f} m over "
            f"{pd.Series(tray.astype(int)).nunique()} trays")

        payload["classes"][sensor] = {
            "minerals": {str(k): v for k, v
                         in sorted(minerals["entries"].items())},
            "groups": {str(k): v for k, v
                       in sorted(groups["entries"].items())},
            "mineral_class": minerals["name"],
            "group_class": groups["name"],
            "columns": cols,
        }
        payload["sensors"][sensor] = intervals
        summary[sensor] = {
            "total": total, "unassigned": n_unassigned,
            "confirmed": n_confirmed, "doubtful": n_doubtful,
            "depth_min": float(depth.min()), "depth_max": float(depth.max()),
            "n_trays": int(pd.Series(tray.astype(int)).nunique()),
        }

    out_json = fixture_dir / "intervals.json"
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
    rep("")
    rep(f"wrote {out_json} ({out_json.stat().st_size} bytes)")

    rep("")
    if rep.failures:
        rep(f"RESULT: {len(rep.failures)} FAILED CHECKS: {rep.failures}")
    else:
        rep("RESULT: all checks passed")
    rep.save(fixture_dir / "intervals-report.txt")
    print(f"report written to {fixture_dir / 'intervals-report.txt'}")
    rep.raise_if_failed("intervals")
    return {"payload": payload, "summary": summary}


# --------------------------------------------------------------------------
# step 5: SQLite load
# --------------------------------------------------------------------------

HOLE_SCHEMA = """
CREATE TABLE samples (
    id INTEGER PRIMARY KEY,
    sensor TEXT NOT NULL,
    sample_index INTEGER NOT NULL,
    tray INTEGER NOT NULL,
    section INTEGER NOT NULL,
    depth REAL NOT NULL,
    secdist_mm REAL,
    min1_index INTEGER,
    min1_name TEXT,
    grp1_index INTEGER,
    grp1_name TEXT,
    wt1 REAL,
    error REAL,
    nil_stat REAL
);
CREATE TABLE intervals (
    id INTEGER PRIMARY KEY,
    sensor TEXT NOT NULL,
    seq INTEGER NOT NULL,
    depth_from REAL NOT NULL,
    depth_to REAL NOT NULL,
    tray_from INTEGER NOT NULL,
    tray_to INTEGER NOT NULL,
    n_samples INTEGER NOT NULL,
    mineral_index INTEGER,
    mineral TEXT,
    grp_index INTEGER,
    grp TEXT,
    wt1_avg REAL,
    error_avg REAL,
    nil_avg REAL,
    status TEXT NOT NULL,
    flags TEXT
);
CREATE TABLE trays (
    tray INTEGER PRIMARY KEY,
    tray_label TEXT NOT NULL,
    depth_from REAL NOT NULL,
    depth_to REAL NOT NULL,
    n_samples INTEGER NOT NULL,
    photo_file TEXT
);
CREATE TABLE photos (
    file TEXT PRIMARY KEY,
    tray INTEGER NOT NULL
);
CREATE TABLE annotations (
    id INTEGER PRIMARY KEY,
    interval_id INTEGER NOT NULL REFERENCES intervals(id),
    old_status TEXT,
    new_status TEXT,
    ts TEXT,
    note TEXT
);
CREATE INDEX idx_samples_sensor_depth ON samples(sensor, depth);
CREATE INDEX idx_intervals_sensor_depth ON intervals(sensor, depth_from, depth_to);
"""

INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS holes (
    hole_id TEXT PRIMARY KEY,
    depth_from REAL NOT NULL,
    depth_to REAL NOT NULL,
    n_trays INTEGER NOT NULL,
    n_samples INTEGER NOT NULL,
    sensors TEXT NOT NULL,
    raw_dir TEXT NOT NULL,
    ingested_at TEXT NOT NULL
);
"""


def _iornan(v):
    return None if pd.isna(v) else int(v)


def _fornan(v):
    return None if pd.isna(v) else float(v)


def _load_samples(conn, sensor, csv_path, cols, minerals, groups, rep):
    """Insert one samples row per CSV row; return (n_rows, tray_stats).

    Columns are addressed by name (CSV column order follows the ini
    catalogue and must not be relied upon).
    """
    header = pd.read_csv(csv_path, nrows=0).columns.tolist()
    has_index = "Index" in header
    has_secdist = "SecDist (mm)" in header
    wanted = (["Index"] if has_index else []) + [
        "Tray", "Section", "Depth (m)"]
    if has_secdist:
        wanted.append("SecDist (mm)")
    wanted += [cols["min1"], cols["grp1"], cols["wt1"], cols["error"],
               cols["nil"]]
    df = pd.read_csv(csv_path, usecols=lambda c: c in wanted)
    df = df[wanted]  # enforce a known column order by name

    rows = []
    for i, r in enumerate(df.itertuples(index=False)):
        vals = list(r)
        if has_index:
            sample_index = int(round(float(vals.pop(0))))
        else:
            sample_index = i
        tray, section, depth = vals[0], vals[1], vals[2]
        if has_secdist:
            secdist = vals[3]
            min1, grp1, wt1, error, nil = vals[4:9]
        else:
            secdist = np.nan
            min1, grp1, wt1, error, nil = vals[3:8]
        min1_i = _iornan(min1)
        grp1_i = _iornan(grp1)
        rows.append((
            sensor, sample_index, int(tray), int(section), float(depth),
            _fornan(secdist), min1_i,
            minerals.get(min1_i) if min1_i is not None else None,
            grp1_i,
            groups.get(grp1_i) if grp1_i is not None else None,
            _fornan(wt1), _fornan(error), _fornan(nil),
        ))
    conn.executemany(
        "INSERT INTO samples (sensor, sample_index, tray, section, depth,"
        " secdist_mm, min1_index, min1_name, grp1_index, grp1_name,"
        " wt1, error, nil_stat) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    tray_stats = (
        df.assign(tray=df["Tray"].astype(int))
        .groupby("tray")["Depth (m)"]
        .agg(["min", "max", "count"])
    )
    return len(rows), tray_stats


def load_hole_db(hole_id: str, raw_dir: Path, photos: dict[int, Path],
                 fixture_dir: Path, hole_db: Path, index_db: Path) -> dict:
    """(Re)build hole.sqlite from fixture products and upsert index.sqlite.

    WARNING: the hole database is rebuilt from scratch - any rows in the
    annotations table (manual review state) are discarded. Back up
    hole.sqlite first if it contains review records.

    photos: {0-based tray: path} discovered in raw_dir; the trays table rule
    is tray+1 -> four-digit photo name; missing files leave photo_file NULL
    and are reported as warnings.
    """
    rep = Reporter()
    rep("")
    rep("=" * 78)
    rep(f"Database load - hole {hole_id}")
    rep(f"hole db  : {hole_db}")
    rep(f"index db : {index_db}")

    payload = json.loads(
        (fixture_dir / "intervals.json").read_text(encoding="utf-8"))
    sensors = sensor_order(payload["sensors"])
    class_maps = {
        sensor: (
            {int(k): v for k, v in payload["classes"][sensor]["minerals"].items()},
            {int(k): v for k, v in payload["classes"][sensor]["groups"].items()},
        )
        for sensor in sensors
    }
    ingested_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    hole_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(hole_db)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        for table in ("annotations", "photos", "trays", "intervals", "samples"):
            conn.execute(f"DROP TABLE IF EXISTS {table}")
        conn.executescript(HOLE_SCHEMA)

        tray_stats_by_sensor = {}
        n_rows_by_sensor = {}
        for sensor in sensors:
            csv_path = fixture_dir / f"{sensor}-scalars.csv"
            # the TSA column set chosen during interval building is recorded
            # in intervals.json; fall back to re-derivation for older files
            cols = payload["classes"][sensor].get("columns") \
                or find_tsa_columns(csv_path)
            minerals, groups = class_maps[sensor]
            n_rows, tray_stats = _load_samples(
                conn, sensor, csv_path, cols, minerals, groups, rep)
            tray_stats_by_sensor[sensor] = tray_stats
            n_rows_by_sensor[sensor] = n_rows
            rep.check(f"samples: {sensor} rows inserted", n_rows > 0,
                      f"{n_rows}")

        ref = sensors[0]
        for other in sensors[1:]:
            same = tray_stats_by_sensor[ref].equals(tray_stats_by_sensor[other])
            rep.check(f"samples: {ref}/{other} tray geometry identical", same,
                      "per-tray depth min/max/count equal" if same else "MISMATCH")

        for sensor, intervals in payload["sensors"].items():
            conn.executemany(
                "INSERT INTO intervals (sensor, seq, depth_from, depth_to,"
                " tray_from, tray_to, n_samples, mineral_index, mineral,"
                " grp_index, grp, wt1_avg, error_avg, nil_avg, status, flags)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [(sensor, iv["seq"], iv["depth_from"], iv["depth_to"],
                  iv["tray_from"], iv["tray_to"], iv["n_samples"],
                  iv["mineral_index"], iv["mineral"], iv["grp_index"],
                  iv["grp"], iv["wt1_avg"], iv["error_avg"], iv["nil_avg"],
                  iv["status"], iv["flags"]) for iv in intervals],
            )

        # trays from the first sensor's sample geometry; photo rule
        # tray+1 -> four-digit name; missing photo -> NULL + warning
        tray_stats = tray_stats_by_sensor[ref]
        tray_rows = []
        photo_rows = []
        missing_photos = []
        for tray, row in tray_stats.iterrows():
            label = f"{tray + 1:04d}"
            photo_path = photos.get(int(tray))
            if photo_path is None:
                photo_name = None
                missing_photos.append(f"{hole_id}_{label}.jpg")
            else:
                photo_name = photo_path.name
                photo_rows.append((photo_name, int(tray)))
            tray_rows.append((int(tray), label,
                              round(float(row["min"]), 6),
                              round(float(row["max"]), 6),
                              int(row["count"]), photo_name))
        conn.executemany(
            "INSERT INTO trays (tray, tray_label, depth_from, depth_to,"
            " n_samples, photo_file) VALUES (?,?,?,?,?,?)", tray_rows)
        conn.executemany("INSERT INTO photos (file, tray) VALUES (?,?)",
                         photo_rows)
        rep(f"trays: {len(tray_rows)} rows; photos catalogued: "
            f"{len(photo_rows)} (rule tray+1 -> 4-digit file name)")
        if missing_photos:
            rep(f"WARNING: {len(missing_photos)} tray photo(s) missing in raw "
                f"dir; photo_file left NULL for: {missing_photos}")

        # ---------------- verification queries ----------------
        q = conn.execute
        for sensor in sensors:
            (n,) = q("SELECT COUNT(*) FROM samples WHERE sensor=?",
                     (sensor,)).fetchone()
            rep.check(f"db samples[{sensor}] count matches csv rows",
                      n == n_rows_by_sensor[sensor], f"{n}")
            total, conf, doubt, unassigned = q(
                "SELECT COUNT(*), SUM(status='confirmed'),"
                " SUM(status='doubtful'), SUM(flags='unassigned')"
                " FROM intervals WHERE sensor=?", (sensor,)).fetchone()
            expected = payload["sensors"][sensor]
            rep.check(
                f"db intervals[{sensor}] total/unassigned/confirmed/doubtful",
                total == len(expected)
                and unassigned == sum(1 for iv in expected
                                      if iv["flags"] == "unassigned")
                and conf == sum(1 for iv in expected
                                if iv["status"] == "confirmed")
                and doubt == sum(1 for iv in expected
                                 if iv["status"] == "doubtful"),
                f"{total}/{unassigned}/{conf}/{doubt}")
            (null_flags,) = q(
                "SELECT COUNT(*) FROM intervals WHERE sensor=?"
                " AND mineral IS NULL AND (status!='doubtful'"
                " OR flags!='unassigned')", (sensor,)).fetchone()
            rep.check(f"db intervals[{sensor}] mineral=NULL rows flagged "
                      "correctly", null_flags == 0, f"{null_flags} misflagged")
        dmin, dmax = q("SELECT MIN(depth), MAX(depth) FROM samples").fetchone()
        rep(f"db samples depth {dmin:.6f}..{dmax:.6f} m")
        (n_trays,) = q("SELECT COUNT(*) FROM trays").fetchone()
        (n_photos,) = q("SELECT COUNT(*) FROM photos").fetchone()
        (n_ann,) = q("SELECT COUNT(*) FROM annotations").fetchone()
        rep(f"db trays={n_trays}, photos={n_photos}, annotations={n_ann}")
        (integrity,) = q("PRAGMA integrity_check").fetchone()
        rep.check("PRAGMA integrity_check", integrity == "ok", integrity)

        depth_from = float(tray_stats["min"].min())
        depth_to = float(tray_stats["max"].max())
        n_trays = len(tray_rows)
        n_samples = n_rows_by_sensor[ref]
        conn.commit()
    finally:
        conn.close()

    # ---------------- index.sqlite upsert ----------------
    index_db.parent.mkdir(parents=True, exist_ok=True)
    iconn = sqlite3.connect(index_db)
    try:
        iconn.executescript(INDEX_SCHEMA)
        iconn.execute(
            "INSERT INTO holes (hole_id, depth_from, depth_to, n_trays,"
            " n_samples, sensors, raw_dir, ingested_at)"
            " VALUES (?,?,?,?,?,?,?,?)"
            " ON CONFLICT(hole_id) DO UPDATE SET"
            " depth_from=excluded.depth_from, depth_to=excluded.depth_to,"
            " n_trays=excluded.n_trays, n_samples=excluded.n_samples,"
            " sensors=excluded.sensors, raw_dir=excluded.raw_dir,"
            " ingested_at=excluded.ingested_at",
            (hole_id, round(depth_from, 6), round(depth_to, 6), n_trays,
             n_samples, json.dumps(sensors), str(raw_dir.resolve()),
             ingested_at),
        )
        iconn.commit()
        row = iconn.execute(
            "SELECT hole_id, depth_from, depth_to, n_trays, n_samples,"
            " sensors, raw_dir FROM holes WHERE hole_id=?",
            (hole_id,)).fetchone()
        rep.check(
            "index.sqlite holes upsert",
            row is not None and row[3] == n_trays and row[4] == n_samples
            and json.loads(row[5]) == sensors
            and row[6] == str(raw_dir.resolve()),
            f"row={row}")
    finally:
        iconn.close()

    # ---------------- hole.json export ----------------
    hole_json = {
        "hole_id": hole_id,
        "depth_from": round(depth_from, 6),
        "depth_to": round(depth_to, 6),
        "n_trays": n_trays,
        "n_samples": n_samples,
        "sensors": sensors,
        "trays": [
            {"tray": t, "tray_label": label, "depth_from": df_,
             "depth_to": dt, "n_samples": n, "photo_file": photo}
            for t, label, df_, dt, n, photo in tray_rows
        ],
        "intervals": {
            sensor: {
                "total": len(payload["sensors"][sensor]),
                "unassigned": sum(1 for iv in payload["sensors"][sensor]
                                  if iv["flags"] == "unassigned"),
                "confirmed": sum(1 for iv in payload["sensors"][sensor]
                                 if iv["status"] == "confirmed"),
                "doubtful": sum(1 for iv in payload["sensors"][sensor]
                                if iv["status"] == "doubtful"),
            }
            for sensor in sensors
        },
        "database": str(hole_db),
        "raw_dir": str(raw_dir.resolve()),
        "ingested_at": ingested_at,
    }
    hole_json_path = fixture_dir / "hole.json"
    hole_json_path.write_text(
        json.dumps(hole_json, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8")
    rep(f"wrote {hole_json_path}")

    rep("")
    if rep.failures:
        rep(f"RESULT: {len(rep.failures)} FAILED CHECKS: {rep.failures}")
    else:
        rep("RESULT: all checks passed")
    with open(fixture_dir / "intervals-report.txt", "a",
              encoding="utf-8") as fh:
        fh.write("\n".join(rep.lines) + "\n")
    print(f"appended to {fixture_dir / 'intervals-report.txt'}")
    rep.raise_if_failed("load_db")

    return {
        "depth_from": depth_from, "depth_to": depth_to,
        "n_trays": n_trays, "n_samples": n_samples, "sensors": sensors,
        "n_photos": len(photo_rows), "missing_photos": missing_photos,
    }
