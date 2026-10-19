"""NVCL ETL: load data/raw/<hole_id>/ (produced by nvcl_download.py) into
data/holes/<hole_id>/hole.sqlite as NVCL side tables.

Adds (CREATE TABLE IF NOT EXISTS; INSERT OR REPLACE on reruns; never DROPs,
never touches the five legacy tables samples/intervals/trays/photos/
annotations):

    borehole_meta, nvcl_datasets, nvcl_logs, nvcl_scalar_data,
    nvcl_tray_depths, nvcl_images, etl_runs

Also adds lat/lon/operator columns to data/index.sqlite:holes (if missing)
and fills them for this hole.

Usage:
    python scripts/nvcl_etl.py <hole_id> [--out-root data]

Self-checks are written to data/holes/<hole_id>/etl-report.txt; any
inconsistency exits non-zero.

null policy: scalar CSV rows whose measurement value is the literal string
"null" are treated as missing and SKIPPED (not inserted). Skipped counts are
reported per file and in etl-report.txt.

Note: the Tray/Section lookup logs (log_id == datasets.json tray_id /
section_id) are indexed by sample number, not metres; they are loaded as-is
but excluded from the depth cross-check against the legacy samples table.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

NEW_TABLES = (
    "borehole_meta",
    "nvcl_datasets",
    "nvcl_logs",
    "nvcl_scalar_data",
    "nvcl_tray_depths",
    "nvcl_images",
    "etl_runs",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS borehole_meta (
  nvcl_id TEXT PRIMARY KEY, name TEXT, lon REAL, lat REAL, z REAL,
  boreholeLength_m REAL, elevation_m REAL,
  drillStartDate TEXT, drillEndDate TEXT, operator TEXT, driller TEXT,
  tenement TEXT, project TEXT, purpose TEXT, status TEXT,
  drillingMethod TEXT, inclinationType TEXT, identifier TEXT,
  href TEXT, description TEXT, raw_json TEXT
);
CREATE TABLE IF NOT EXISTS nvcl_datasets (
  dataset_id TEXT PRIMARY KEY, dataset_name TEXT, borehole_uri TEXT,
  tray_id TEXT, section_id TEXT, domain_id TEXT,
  created_date TEXT, modified_date TEXT
);
CREATE TABLE IF NOT EXISTS nvcl_logs (
  log_id TEXT PRIMARY KEY, dataset_id TEXT, log_name TEXT, log_type TEXT,
  algorithm_id TEXT, kind TEXT, sample_count INTEGER
);
CREATE TABLE IF NOT EXISTS nvcl_scalar_data (
  id INTEGER PRIMARY KEY, log_id TEXT, depth REAL,
  scalar_name TEXT, value_text TEXT, value_num REAL
);
CREATE TABLE IF NOT EXISTS nvcl_tray_depths (
  id INTEGER PRIMARY KEY, log_id TEXT, sample_no TEXT,
  depth_from REAL, depth_to REAL
);
CREATE TABLE IF NOT EXISTS nvcl_images (
  file TEXT PRIMARY KEY, log_id TEXT, kind TEXT, sample_no TEXT,
  depth_from REAL, depth_to REAL, nbytes INTEGER
);
CREATE TABLE IF NOT EXISTS etl_runs (
  id INTEGER PRIMARY KEY, hole_id TEXT, step TEXT,
  started_at TEXT, finished_at TEXT, status TEXT, detail TEXT
);
"""


def _f(value):
    """Safe float: empty/non-numeric -> None."""
    if value is None:
        return None
    try:
        s = str(value).strip()
        if not s:
            return None
        return float(s)
    except (TypeError, ValueError):
        return None


def _i(value):
    f = _f(value)
    return int(f) if f is not None else None


def _s(value):
    if value is None:
        return None
    return str(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Runner:
    """Records one etl_runs row per step."""

    def __init__(self, conn: sqlite3.Connection, hole_id: str):
        self.conn = conn
        self.hole_id = hole_id

    def run(self, step: str, fn):
        started = _now()
        t0 = time.perf_counter()
        try:
            detail = fn() or ""
            status = "ok"
        except Exception as exc:
            status = "error"
            detail = f"{type(exc).__name__}: {exc}"
            self.conn.execute(
                "INSERT INTO etl_runs (hole_id, step, started_at, finished_at,"
                " status, detail) VALUES (?,?,?,?,?,?)",
                (self.hole_id, step, started, _now(), status, detail),
            )
            self.conn.commit()
            raise
        detail = f"{detail} ({time.perf_counter() - t0:.1f}s)"
        self.conn.execute(
            "INSERT INTO etl_runs (hole_id, step, started_at, finished_at,"
            " status, detail) VALUES (?,?,?,?,?,?)",
            (self.hole_id, step, started, _now(), status, detail),
        )
        self.conn.commit()
        return detail


def load_borehole_meta(conn, raw_dir: Path) -> str:
    text = (raw_dir / "borehole.json").read_text(encoding="utf-8")
    d = json.loads(text)
    conn.execute(
        "INSERT OR REPLACE INTO borehole_meta (nvcl_id, name, lon, lat, z,"
        " boreholeLength_m, elevation_m, drillStartDate, drillEndDate,"
        " operator, driller, tenement, project, purpose, status,"
        " drillingMethod, inclinationType, identifier, href, description,"
        " raw_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            _s(d.get("nvcl_id")), _s(d.get("name")), _f(d.get("x")),
            _f(d.get("y")), _f(d.get("z")), _f(d.get("boreholeLength_m")),
            _f(d.get("elevation_m")), _s(d.get("drillStartDate")),
            _s(d.get("drillEndDate")), _s(d.get("operator")),
            _s(d.get("driller")), _s(d.get("tenement")), _s(d.get("project")),
            _s(d.get("purpose")), _s(d.get("status")),
            _s(d.get("drillingMethod")), _s(d.get("inclinationType")),
            _s(d.get("identifier")), _s(d.get("href")), _s(d.get("description")),
            text,
        ),
    )
    return f"1 row, lon={_f(d.get('x'))} lat={_f(d.get('y'))}"


def load_datasets(conn, raw_dir: Path) -> str:
    rows = json.loads((raw_dir / "datasets.json").read_text(encoding="utf-8"))
    conn.executemany(
        "INSERT OR REPLACE INTO nvcl_datasets (dataset_id, dataset_name,"
        " borehole_uri, tray_id, section_id, domain_id, created_date,"
        " modified_date) VALUES (?,?,?,?,?,?,?,?)",
        [
            (
                _s(d.get("dataset_id")), _s(d.get("dataset_name")),
                _s(d.get("borehole_uri")), _s(d.get("tray_id")),
                _s(d.get("section_id")), _s(d.get("domain_id")),
                _s(d.get("created_date")), _s(d.get("modified_date")),
            )
            for d in rows
        ],
    )
    return f"{len(rows)} rows"


def load_logs(conn, raw_dir: Path) -> str:
    datasets = json.loads((raw_dir / "datasets.json").read_text(encoding="utf-8"))
    default_ds = datasets[0]["dataset_id"] if len(datasets) == 1 else None
    rows = []
    for kind, fname in (
        ("scalar", "logs_scalar.json"),
        ("image", "logs_image.json"),
        ("spectral", "logs_spectral.json"),
        ("profilometer", "logs_profilometer.json"),
    ):
        path = raw_dir / fname
        if not path.exists():
            continue
        for d in json.loads(path.read_text(encoding="utf-8")):
            rows.append(
                (
                    _s(d.get("log_id")),
                    _s(d.get("dataset_id")) or default_ds,
                    _s(d.get("log_name")),
                    _s(d.get("log_type")),
                    _s(d.get("algorithm_id")),
                    kind,
                    _i(d.get("sample_count")),
                )
            )
    conn.executemany(
        "INSERT OR REPLACE INTO nvcl_logs (log_id, dataset_id, log_name,"
        " log_type, algorithm_id, kind, sample_count) VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    return f"{len(rows)} rows"


def load_scalar_data(conn, raw_dir: Path) -> str:
    scalar_logs = json.loads((raw_dir / "logs_scalar.json").read_text(encoding="utf-8"))
    log_ids = {d["log_id"] for d in scalar_logs}
    csv_files = sorted((raw_dir / "scalars").glob("*.csv"))

    inserted = 0
    skipped_null = 0
    unmatched = []
    # batch tuples are (depth, log_id, scalar_name, value_text, value_num)
    insert_sql = (
        "INSERT INTO nvcl_scalar_data (depth, log_id, scalar_name, value_text,"
        " value_num) VALUES (?,?,?,?,?)"
    )
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA journal_mode = MEMORY")
    for path in csv_files:
        stem = path.stem
        log_id = next(
            (lid for lid in log_ids if stem.startswith(lid + "_") or stem == lid),
            None,
        )
        if log_id is None:
            unmatched.append(path.name)
            continue
        batch = []
        with path.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.reader(fh)
            header = next(reader)
            scalar_name = header[2] if len(header) > 2 else ""
            for row in reader:
                if len(row) < 3:
                    continue
                value_text = row[2]
                if value_text == "null":
                    skipped_null += 1
                    continue
                value_num = _f(value_text)
                batch.append((_f(row[0]), log_id, scalar_name, value_text, value_num))
                if len(batch) >= 50000:
                    conn.executemany(insert_sql, batch)
                    inserted += len(batch)
                    batch = []
        if batch:
            conn.executemany(insert_sql, batch)
            inserted += len(batch)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_nvcl_scalar_data_log_depth"
        " ON nvcl_scalar_data (log_id, depth)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_nvcl_scalar_data_name"
        " ON nvcl_scalar_data (scalar_name)"
    )
    detail = (
        f"{inserted} rows inserted from {len(csv_files)} csv files,"
        f" {skipped_null} null rows skipped"
    )
    if unmatched:
        detail += f"; UNMATCHED FILES: {unmatched}"
    return detail


def load_tray_depths(conn, raw_dir: Path) -> str:
    data = json.loads((raw_dir / "tray_depths.json").read_text(encoding="utf-8"))
    rows = []
    for log_id, entries in data.items():
        for e in entries:
            rows.append(
                (
                    _s(log_id),
                    _s(e.get("sample_no")),
                    _f(e.get("start_value")),
                    _f(e.get("end_value")),
                )
            )
    conn.executemany(
        "INSERT INTO nvcl_tray_depths (log_id, sample_no, depth_from, depth_to)"
        " VALUES (?,?,?,?)",
        rows,
    )
    return f"{len(rows)} rows from {len(data)} log(s)"


def load_images(conn, raw_dir: Path) -> str:
    images_dir = raw_dir / "images"
    tray_depths = json.loads((raw_dir / "tray_depths.json").read_text(encoding="utf-8"))
    # depth lookup: sample_no -> (depth_from, depth_to), plus the log_id that
    # owns the tray-depth mapping (an image log, e.g. "Tray Thumbnail Images")
    depth_log_id = next(iter(tray_depths), None)
    depth_by_no = {}
    if depth_log_id is not None:
        for e in tray_depths[depth_log_id]:
            depth_by_no[str(e["sample_no"])] = (
                _f(e["start_value"]),
                _f(e["end_value"]),
            )
    files = sorted(images_dir.glob("*.jpg"))
    rows = []
    for p in files:
        rel = f"images/{p.name}"
        sample_no = None
        if p.stem.startswith("tray_"):
            sample_no = p.stem[len("tray_"):]
        depth_from, depth_to = depth_by_no.get(sample_no, (None, None))
        rows.append(
            (rel, depth_log_id, "tray_thumbnail", sample_no, depth_from,
             depth_to, p.stat().st_size)
        )
    conn.executemany(
        "INSERT OR REPLACE INTO nvcl_images (file, log_id, kind, sample_no,"
        " depth_from, depth_to, nbytes) VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    return f"{len(rows)} rows"


def update_index(index_db: Path, hole_id: str, meta: dict) -> str:
    """Add lat/lon/operator columns to index.sqlite:holes and fill them."""
    if not index_db.exists():
        return "index.sqlite not found, skipped"
    conn = sqlite3.connect(str(index_db))
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(holes)")}
        added = []
        for col, decl in (("lat", "REAL"), ("lon", "REAL"), ("operator", "TEXT")):
            if col not in cols:
                conn.execute(f"ALTER TABLE holes ADD COLUMN {col} {decl}")
                added.append(col)
        cur = conn.execute(
            "UPDATE holes SET lat = ?, lon = ?, operator = ? WHERE hole_id = ?",
            (meta["lat"], meta["lon"], meta["operator"], hole_id),
        )
        conn.commit()
        return f"columns added: {added or 'none'}; rows updated: {cur.rowcount}"
    finally:
        conn.close()


def self_check(conn, raw_dir: Path, hole_dir: Path, hole_id: str) -> list[str]:
    """Return list of failure messages (empty = all consistent)."""
    fails = []
    lines = []

    def check(label, db_count, src_count):
        ok = db_count == src_count
        lines.append(f"  {label}: db={db_count} src={src_count} {'OK' if ok else 'MISMATCH'}")
        if not ok:
            fails.append(f"{label}: db={db_count} != src={src_count}")

    # nvcl_datasets vs datasets.json
    src = len(json.loads((raw_dir / "datasets.json").read_text(encoding="utf-8")))
    check("nvcl_datasets", conn.execute("SELECT COUNT(*) FROM nvcl_datasets").fetchone()[0], src)

    # nvcl_logs vs 4 json files
    src = 0
    for fname in ("logs_scalar.json", "logs_image.json", "logs_spectral.json", "logs_profilometer.json"):
        p = raw_dir / fname
        if p.exists():
            src += len(json.loads(p.read_text(encoding="utf-8")))
    check("nvcl_logs", conn.execute("SELECT COUNT(*) FROM nvcl_logs").fetchone()[0], src)

    # nvcl_scalar_data: rows are inserted, null rows skipped (not exact match)
    scalar_rows = conn.execute("SELECT COUNT(*) FROM nvcl_scalar_data").fetchone()[0]
    csv_files = list((raw_dir / "scalars").glob("*.csv"))
    lines.append(f"  nvcl_scalar_data: db={scalar_rows} rows from {len(csv_files)} csv files (null rows skipped)")
    depth_range = conn.execute("SELECT MIN(depth), MAX(depth) FROM nvcl_scalar_data").fetchone()
    lines.append(f"  nvcl_scalar_data depth range (all logs): {depth_range[0]} .. {depth_range[1]}")
    # The Tray/Section lookup logs (log_id == datasets tray_id/section_id) are
    # indexed by sample number (0..n_samples), not metres; exclude them from
    # the depth cross-check against the legacy samples table.
    lookup_ids = {
        r[0] for r in conn.execute(
            "SELECT tray_id FROM nvcl_datasets WHERE tray_id IS NOT NULL"
            " UNION SELECT section_id FROM nvcl_datasets WHERE section_id IS NOT NULL"
        )
    }
    depth_range_m = None
    if lookup_ids:
        placeholders = ",".join("?" * len(lookup_ids))
        depth_range_m = conn.execute(
            f"SELECT MIN(depth), MAX(depth) FROM nvcl_scalar_data"
            f" WHERE log_id NOT IN ({placeholders})",
            tuple(lookup_ids),
        ).fetchone()
        lines.append(
            f"  nvcl_scalar_data depth range (metre-based logs,"
            f" excluding {len(lookup_ids)} tray/section lookup log(s)):"
            f" {depth_range_m[0]} .. {depth_range_m[1]}"
        )
    legacy_tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "samples" in legacy_tables:
        s = conn.execute("SELECT MIN(depth), MAX(depth) FROM samples").fetchone()
        lines.append(f"  samples depth range: {s[0]} .. {s[1]}")
        check_range = depth_range_m if depth_range_m is not None else depth_range
        if check_range[0] is None or check_range[0] < s[0] - 1 or check_range[1] > s[1] + 1:
            fails.append(f"scalar depth {check_range} outside samples range {s}")
            lines.append("  depth cross-check: MISMATCH")
        else:
            lines.append("  depth cross-check: OK (scalar range within samples range)")

    # nvcl_tray_depths vs tray_depths.json
    src = sum(len(v) for v in json.loads((raw_dir / "tray_depths.json").read_text(encoding="utf-8")).values())
    check("nvcl_tray_depths", conn.execute("SELECT COUNT(*) FROM nvcl_tray_depths").fetchone()[0], src)

    # nvcl_images vs images/*.jpg
    src = len(list((raw_dir / "images").glob("*.jpg")))
    check("nvcl_images", conn.execute("SELECT COUNT(*) FROM nvcl_images").fetchone()[0], src)

    # borehole_meta single non-empty row
    n = conn.execute("SELECT COUNT(*) FROM borehole_meta").fetchone()[0]
    row = conn.execute("SELECT nvcl_id, name, lon, lat FROM borehole_meta LIMIT 1").fetchone()
    ok = n == 1 and row is not None and all(v is not None for v in row)
    lines.append(f"  borehole_meta: {n} row(s), key fields {'non-empty' if ok else 'EMPTY/MISSING'}")
    if not ok:
        fails.append("borehole_meta not exactly one non-empty row")

    # unmatched scalar csv files (filename not matching any log_id) = mismatch
    matched_logs = conn.execute(
        "SELECT COUNT(DISTINCT log_id) FROM nvcl_scalar_data"
    ).fetchone()[0]
    lines.append(f"  distinct log_ids with scalar data: {matched_logs}")

    report = ["ETL self-check report", f"hole_id: {hole_id}", f"time: {_now()}", ""] + lines
    report_path = hole_dir / "etl-report.txt"
    report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report))
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description="ETL NVCL raw downloads into hole.sqlite")
    ap.add_argument("hole_id", help="NVCL hole identifier, e.g. 05GJD001")
    ap.add_argument("--out-root", default="data", help="output data root (default: data)")
    args = ap.parse_args()

    out_root = Path(args.out_root)
    raw_dir = out_root / "raw" / args.hole_id
    hole_dir = out_root / "holes" / args.hole_id
    if not raw_dir.is_dir():
        print(f"ERROR: raw dir not found: {raw_dir} (run nvcl_download.py first)")
        return 2
    hole_dir.mkdir(parents=True, exist_ok=True)
    db_path = hole_dir / "hole.sqlite"

    t0 = time.perf_counter()
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.executescript(SCHEMA)
        conn.commit()
        # idempotent reruns: replace per-key rows, rebuild set-based tables
        conn.execute("DELETE FROM nvcl_scalar_data")
        conn.execute("DELETE FROM nvcl_tray_depths")
        conn.commit()

        runner = Runner(conn, args.hole_id)
        runner.run("borehole_meta", lambda: load_borehole_meta(conn, raw_dir))
        runner.run("nvcl_datasets", lambda: load_datasets(conn, raw_dir))
        runner.run("nvcl_logs", lambda: load_logs(conn, raw_dir))
        runner.run("nvcl_scalar_data", lambda: load_scalar_data(conn, raw_dir))
        runner.run("nvcl_tray_depths", lambda: load_tray_depths(conn, raw_dir))
        runner.run("nvcl_images", lambda: load_images(conn, raw_dir))
        conn.commit()

        meta = conn.execute(
            "SELECT lon, lat, operator FROM borehole_meta WHERE nvcl_id = ?",
            (args.hole_id,),
        ).fetchone()
        meta_d = {"lon": meta[0], "lat": meta[1], "operator": meta[2]} if meta else {}
        idx_detail = update_index(out_root / "index.sqlite", args.hole_id, meta_d)
        runner.run("index.sqlite", lambda: idx_detail)

        fails = self_check(conn, raw_dir, hole_dir, args.hole_id)
    finally:
        conn.close()

    elapsed = time.perf_counter() - t0
    print(f"\nETL finished in {elapsed:.1f}s -> {db_path}")
    if fails:
        print(f"SELF-CHECK FAILED ({len(fails)}): " + "; ".join(fails))
        return 1
    print("SELF-CHECK OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
