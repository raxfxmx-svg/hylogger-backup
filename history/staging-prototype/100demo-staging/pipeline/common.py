from __future__ import annotations

import csv
import hashlib
import json
import os
import struct
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
except ImportError as exc:  # pragma: no cover - command-line setup path
    raise SystemExit(
        "Missing ETL3 dependency. Run: python -m pip install -r requirements.txt"
    ) from exc


SCHEMA_VERSION = "etl3.processed.v2"
RELEASE_ID_PREFIX = "etl3-v2"
ROW_GROUP_SIZE = 4096


class ETLError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while block := handle.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def raw_tree_summary(raw_dir: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    total = 0
    for path in sorted(item for item in raw_dir.rglob("*") if item.is_file()):
        relative = path.relative_to(raw_dir).as_posix()
        file_hash = sha256_file(path)
        size = path.stat().st_size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(file_hash.encode("ascii"))
        digest.update(b"\n")
        count += 1
        total += size
    return {"file_count": count, "nbytes": total, "tree_sha256": digest.hexdigest()}


def write_parquet(path: Path, table: pa.Table) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        table,
        path,
        compression="zstd",
        use_dictionary=True,
        row_group_size=ROW_GROUP_SIZE,
        write_statistics=True,
    )


def table_from_rows(rows: list[dict[str, Any]]) -> pa.Table:
    if not rows:
        raise ETLError("Cannot infer a Parquet schema from an empty row collection")
    return pa.Table.from_pylist(rows)


def relative_key(path: Path, release_root: Path) -> str:
    return path.relative_to(release_root).as_posix()


def resolved_storage_path(release_root: Path, key: str) -> Path:
    candidate = (release_root / key).resolve()
    try:
        candidate.relative_to(release_root.resolve())
    except ValueError as exc:
        raise ETLError(f"Storage key escapes release root: {key}") from exc
    return candidate


def validate_declared_file(
    raw_dir: Path, item: dict[str, Any], label: str
) -> Path | None:
    status = str(item.get("status") or "")
    key = item.get("file")
    if status != "complete":
        return None
    if not key:
        raise ETLError(f"{label}: complete item has no file")
    path = (raw_dir / str(key)).resolve()
    try:
        path.relative_to(raw_dir.resolve())
    except ValueError as exc:
        raise ETLError(f"{label}: raw path escapes package: {key}") from exc
    if not path.is_file():
        raise ETLError(f"{label}: missing file: {key}")
    expected_size = item.get("nbytes")
    if expected_size is not None and int(expected_size) != path.stat().st_size:
        raise ETLError(
            f"{label}: byte count mismatch for {key}: "
            f"{path.stat().st_size} != {expected_size}"
        )
    expected_hash = item.get("sha256")
    if expected_hash and sha256_file(path) != str(expected_hash):
        raise ETLError(f"{label}: SHA-256 mismatch for {key}")
    return path


def read_scalar_csv(path: Path) -> tuple[list[str], list[tuple[str, str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ETLError(f"Empty scalar CSV: {path}") from exc
        if len(header) != 3:
            raise ETLError(f"Expected three scalar columns in {path}, got {len(header)}")
        rows: list[tuple[str, str, str]] = []
        for line_number, row in enumerate(reader, start=2):
            if len(row) != 3:
                raise ETLError(
                    f"{path.name}:{line_number}: expected 3 fields, got {len(row)}"
                )
            rows.append((row[0], row[1], row[2]))
    return header, rows


def values_digest(values: Iterable[str]) -> str:
    digest = hashlib.sha256()
    for value in values:
        raw = value.encode("utf-8")
        digest.update(struct.pack("<Q", len(raw)))
        digest.update(raw)
    return digest.hexdigest()


def numeric_parseable(values: Iterable[str]) -> bool | None:
    seen = False
    for value in values:
        if value == "":
            continue
        seen = True
        try:
            float(value)
        except ValueError:
            return False
    return True if seen else None


def source_log_map(raw_dir: Path, filename: str) -> dict[str, dict[str, Any]]:
    path = raw_dir / filename
    if not path.is_file():
        return {}
    return {str(item.get("log_id") or ""): item for item in read_json(path)}
