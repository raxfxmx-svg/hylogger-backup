"""HyLogger visualisation backend.

FastAPI app serving hole metadata, mineral intervals, core-strip images and
on-demand spectra read from the raw TSG .bip files.

Layout expected under data/ (relative to this package's parent directory,
i.e. the hylogger-visualisation/ root):

    data/index.sqlite                       table holes(hole_id, depth_from,
                                            depth_to, n_trays, sensors,
                                            raw_dir)
    data/holes/<hole_id>/hole.sqlite        tables trays(...), strips(...),
                                            intervals(...), annotations(...)
    data/holes/<hole_id>/strips/            tray_XXXX_sec_S.jpg + strips.json
    data/holes/<hole_id>/fixture/           vnir-wavelengths.csv,
                                            tir-wavelengths.csv

Raw spectra live in holes.raw_dir as little-endian float32 BIP files with two
planes, shape (2, n_samples, n_bands), plane-major order:
    vnir -> <raw_dir>/<hole_id>_tsg.bip      (n_bands = len(vnir-wavelengths))
    tir  -> <raw_dir>/<hole_id>_tsg_tir.bip  (n_bands = len(tir-wavelengths))
Plane 0 holds the spectrum values; values < -1e37 are nulls.
"""

from __future__ import annotations

import csv
import json
import mmap
import re
import sqlite3
import struct
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
INDEX_DB = DATA_DIR / "index.sqlite"
WEB_DIR = BASE_DIR / "web"

SENSORS = ("vnir", "tir")
INTERVAL_STATUSES = ("confirmed", "doubtful")

_HOLE_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_STRIP_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+\.jpe?g$", re.IGNORECASE)

NULL_THRESHOLD = -1e37

app = FastAPI(title="HyLogger Visualisation")


# ---------------------------------------------------------------------------
# helpers


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _connect_ro(db_path: Path):
    """Close the connection when a read-only query context exits.

    SQLite's connection context manager controls transactions but does not close
    the connection. Explicit closing prevents database file locks on Windows.
    """
    return closing(_connect(db_path))


def _check_hole_id(hole_id: str) -> str:
    if not _HOLE_ID_RE.match(hole_id):
        raise HTTPException(status_code=422, detail=f"invalid hole_id: {hole_id!r}")
    return hole_id


def _hole_dir(hole_id: str) -> Path:
    return DATA_DIR / "holes" / hole_id


def _hole_db_path(hole_id: str) -> Path:
    return _hole_dir(hole_id) / "hole.sqlite"


def _get_hole_row(hole_id: str) -> sqlite3.Row:
    """Fetch the hole row from index.sqlite or raise 404."""
    _check_hole_id(hole_id)
    if not INDEX_DB.exists():
        raise HTTPException(status_code=404, detail="index database not found")
    with _connect_ro(INDEX_DB) as conn:
        row = conn.execute(
            "SELECT * FROM holes WHERE hole_id = ?", (hole_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"unknown hole: {hole_id}")
    return row


def _parse_sensors(raw) -> list[str]:
    """sensors column: JSON array or comma-separated string."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        return [str(s) for s in raw]
    text = str(raw).strip()
    if text.startswith("["):
        try:
            return [str(s) for s in json.loads(text)]
        except json.JSONDecodeError:
            pass
    return [s.strip() for s in text.split(",") if s.strip()]


def _check_sensor(sensor: str) -> str:
    if sensor not in SENSORS:
        raise HTTPException(
            status_code=422, detail=f"invalid sensor {sensor!r}; expected one of {SENSORS}"
        )
    return sensor


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
        is not None
    )


def _interval_row_to_dict(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "depth_from": row["depth_from"],
        "depth_to": row["depth_to"],
        "mineral": row["mineral"],
        "grp": row["grp"],
        "wt1_avg": row["wt1_avg"],
        "error_avg": row["error_avg"],
        "nil_avg": row["nil_avg"],
        "status": row["status"],
        "flags": row["flags"],
        "n_samples": row["n_samples"],
    }


def _load_wavelengths(hole_id: str, sensor: str) -> list[float]:
    path = _hole_dir(hole_id) / "fixture" / f"{sensor}-wavelengths.csv"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"wavelength file not found: {path.name}")
    wavelengths: list[float] = []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        header = next(reader, None)
        for row in reader:
            if not row:
                continue
            # column "wavelength_nm" if present, else the last numeric column
            value = None
            if header and "wavelength_nm" in header:
                idx = header.index("wavelength_nm")
                if idx < len(row):
                    value = row[idx]
            if value is None:
                value = row[-1]
            try:
                wavelengths.append(float(value))
            except ValueError:
                continue
    return wavelengths


def _bip_path(hole_id: str, sensor: str, raw_dir: str) -> Path:
    name = f"{hole_id}_tsg_tir.bip" if sensor == "tir" else f"{hole_id}_tsg.bip"
    path = Path(raw_dir) / name
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"raw bip file not found: {name}")
    return path


# ---------------------------------------------------------------------------
# routes


@app.get("/api/holes")
def list_holes() -> list[dict]:
    if not INDEX_DB.exists():
        return []
    with _connect_ro(INDEX_DB) as conn:
        rows = conn.execute(
            "SELECT hole_id, depth_from, depth_to, n_trays, sensors FROM holes"
            " ORDER BY hole_id"
        ).fetchall()
    return [
        {
            "hole_id": r["hole_id"],
            "depth_from": r["depth_from"],
            "depth_to": r["depth_to"],
            "n_trays": r["n_trays"],
            "sensors": _parse_sensors(r["sensors"]),
        }
        for r in rows
    ]


@app.get("/api/holes/{hole_id}/meta")
def hole_meta(hole_id: str) -> dict:
    hole = _get_hole_row(hole_id)
    db_path = _hole_db_path(hole_id)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"hole database not found for {hole_id}")

    strips_json = _hole_dir(hole_id) / "strips" / "strips.json"

    trays: dict[int, dict] = {}
    with _connect_ro(db_path) as conn:
        for r in conn.execute(
            "SELECT tray, tray_label, depth_from, depth_to FROM trays ORDER BY tray"
        ):
            trays[r["tray"]] = {
                "tray": r["tray"],
                "tray_label": r["tray_label"],
                "depth_from": r["depth_from"],
                "depth_to": r["depth_to"],
                "sections": [],
            }
        if _table_exists(conn, "strips"):
            strip_rows = conn.execute(
                "SELECT tray, section, row, depth_from, depth_to, strip, note"
                " FROM strips ORDER BY tray, section"
            ).fetchall()
            for r in strip_rows:
                tray = trays.get(r["tray"])
                if tray is None:
                    continue
                tray["sections"].append(
                    {
                        "section": r["section"],
                        "row": r["row"],
                        "depth_from": r["depth_from"],
                        "depth_to": r["depth_to"],
                        "strip": r["strip"],
                        "note": r["note"] if r["note"] is not None else "",
                    }
                )

    # fall back to strips.json for sections not present in hole.sqlite
    # (decide which trays need the fallback once, up front: checking
    #  tray["sections"] per entry would skip all but the first entry of a tray)
    if strips_json.exists():
        needs_fallback = {t["tray"] for t in trays.values() if not t["sections"]}
    else:
        needs_fallback = set()
    if needs_fallback:
        entries = json.loads(strips_json.read_text(encoding="utf-8"))
        for e in entries:
            tray = trays.get(e["tray"])
            if tray is None or e["tray"] not in needs_fallback:
                continue
            tray["sections"].append(
                {
                    "section": e["section"],
                    "row": e.get("row"),
                    "depth_from": e["depth_from"],
                    "depth_to": e["depth_to"],
                    "strip": e.get("file") or e.get("strip"),
                    "note": e.get("note", ""),
                }
            )

    return {
        "hole_id": hole["hole_id"],
        "depth_from": hole["depth_from"],
        "depth_to": hole["depth_to"],
        "sensors": _parse_sensors(hole["sensors"]),
        "trays": list(trays.values()),
    }


@app.get("/api/holes/{hole_id}/intervals")
def hole_intervals(
    hole_id: str, sensor: str = Query(..., description="vnir or tir")
) -> list[dict]:
    _check_sensor(sensor)
    _get_hole_row(hole_id)
    db_path = _hole_db_path(hole_id)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"hole database not found for {hole_id}")
    with _connect_ro(db_path) as conn:
        rows = conn.execute(
            "SELECT id, depth_from, depth_to, mineral, grp, wt1_avg, error_avg,"
            " nil_avg, status, flags, n_samples FROM intervals"
            " WHERE sensor = ? ORDER BY depth_from, id",
            (sensor,),
        ).fetchall()
    return [_interval_row_to_dict(r) for r in rows]


@app.get("/api/holes/{hole_id}/strip/{filename}")
def hole_strip(hole_id: str, filename: str) -> FileResponse:
    _get_hole_row(hole_id)
    if ".." in filename or not _STRIP_NAME_RE.match(filename):
        raise HTTPException(status_code=422, detail=f"invalid strip filename: {filename!r}")
    strips_dir = (_hole_dir(hole_id) / "strips").resolve()
    path = (strips_dir / filename).resolve()
    if path.parent != strips_dir:
        raise HTTPException(status_code=422, detail="strip path escapes strips directory")
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"strip not found: {filename}")
    return FileResponse(str(path), media_type="image/jpeg")


@app.get("/api/holes/{hole_id}/spectrum")
def hole_spectrum(hole_id: str, sensor: str = Query("vnir"), sample: int = Query(...)) -> dict:
    _check_sensor(sensor)
    hole = _get_hole_row(hole_id)
    wavelengths = _load_wavelengths(hole_id, sensor)
    n_bands = len(wavelengths)
    bip = _bip_path(hole_id, sensor, hole["raw_dir"])

    row_bytes = n_bands * 4  # float32
    plane_bytes = bip.stat().st_size // 2
    n_samples = plane_bytes // row_bytes
    if sample < 0 or sample >= n_samples:
        raise HTTPException(
            status_code=422,
            detail=f"sample {sample} out of range [0, {n_samples - 1}]",
        )

    with bip.open("rb") as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        try:
            offset = sample * row_bytes  # plane 0 first
            values = struct.unpack_from(f"<{n_bands}f", mm, offset)
        finally:
            mm.close()

    return {
        "wavelengths_nm": wavelengths,
        "values": [None if v < NULL_THRESHOLD else v for v in values],
    }


class StatusUpdate(BaseModel):
    status: str
    note: str | None = None


@app.post("/api/holes/{hole_id}/intervals/{interval_id}/status")
def update_interval_status(hole_id: str, interval_id: int, body: StatusUpdate) -> dict:
    if body.status not in INTERVAL_STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"invalid status {body.status!r}; expected one of {INTERVAL_STATUSES}",
        )
    _get_hole_row(hole_id)
    db_path = _hole_db_path(hole_id)
    if not db_path.exists():
        raise HTTPException(status_code=404, detail=f"hole database not found for {hole_id}")

    conn = _connect(db_path)
    try:
        conn.isolation_level = None  # manual transaction control
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id, depth_from, depth_to, mineral, grp, wt1_avg, error_avg,"
            " nil_avg, status, flags, n_samples FROM intervals WHERE id = ?",
            (interval_id,),
        ).fetchone()
        if row is None:
            conn.execute("ROLLBACK")
            raise HTTPException(
                status_code=404, detail=f"unknown interval: {interval_id}"
            )
        old_status = row["status"]
        ts = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "UPDATE intervals SET status = ? WHERE id = ?", (body.status, interval_id)
        )
        conn.execute(
            "INSERT INTO annotations (interval_id, old_status, new_status, ts, note)"
            " VALUES (?, ?, ?, ?, ?)",
            (interval_id, old_status, body.status, ts, body.note),
        )
        conn.execute("COMMIT")
    except HTTPException:
        raise
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()

    updated = dict(_interval_row_to_dict(row))
    updated["status"] = body.status
    return updated


# ---------------------------------------------------------------------------
# NVCL endpoints (tables are created by the nvcl-kit ETL pipeline; they may
# not exist yet for holes that have not been processed)


def _nvcl_not_found(hole_id: str) -> HTTPException:
    return HTTPException(
        status_code=404, detail=f"hole {hole_id} has no NVCL data"
    )


def _nvcl_db_path(hole_id: str) -> Path:
    _get_hole_row(hole_id)
    db_path = _hole_db_path(hole_id)
    if not db_path.exists():
        raise _nvcl_not_found(hole_id)
    return db_path


@app.get("/api/holes/{hole_id}/nvcl/meta")
def nvcl_meta(hole_id: str) -> dict:
    db_path = _nvcl_db_path(hole_id)
    with _connect_ro(db_path) as conn:
        if not _table_exists(conn, "borehole_meta"):
            raise _nvcl_not_found(hole_id)
        row = conn.execute("SELECT * FROM borehole_meta LIMIT 1").fetchone()
    if row is None:
        raise _nvcl_not_found(hole_id)
    return dict(row)


@app.get("/api/holes/{hole_id}/nvcl/logs")
def nvcl_logs(hole_id: str) -> dict:
    db_path = _nvcl_db_path(hole_id)
    with _connect_ro(db_path) as conn:
        if not (
            _table_exists(conn, "nvcl_datasets") and _table_exists(conn, "nvcl_logs")
        ):
            raise _nvcl_not_found(hole_id)
        datasets = [
            dict(r)
            for r in conn.execute(
                "SELECT dataset_id, dataset_name, borehole_uri, tray_id,"
                " section_id, domain_id, created_date, modified_date"
                " FROM nvcl_datasets ORDER BY dataset_id"
            )
        ]
        logs = [
            dict(r)
            for r in conn.execute(
                "SELECT log_id, dataset_id, log_name, log_type, algorithm_id,"
                " kind, sample_count FROM nvcl_logs ORDER BY log_id"
            )
        ]
    return {"datasets": datasets, "logs": logs}


@app.get("/api/holes/{hole_id}/nvcl/scalars")
def nvcl_scalars(
    hole_id: str,
    log_id: str = Query(..., description="nvcl_logs.log_id"),
    depth_from: float | None = Query(None, description="inclusive lower depth bound"),
    depth_to: float | None = Query(None, description="inclusive upper depth bound"),
    limit: int = Query(5000, ge=1, le=50000),
) -> list[dict]:
    db_path = _nvcl_db_path(hole_id)
    sql = (
        "SELECT id, log_id, depth, scalar_name, value_text, value_num"
        " FROM nvcl_scalar_data WHERE log_id = ?"
    )
    params: list = [log_id]
    if depth_from is not None:
        sql += " AND depth >= ?"
        params.append(depth_from)
    if depth_to is not None:
        sql += " AND depth <= ?"
        params.append(depth_to)
    sql += " ORDER BY depth, id LIMIT ?"
    params.append(limit)
    with _connect_ro(db_path) as conn:
        if not _table_exists(conn, "nvcl_scalar_data"):
            raise _nvcl_not_found(hole_id)
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# static frontend (mounted last so /api routes win); web/ may not exist yet
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
