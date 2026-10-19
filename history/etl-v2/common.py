"""Small shared ETL2 utilities without business rules."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable


HOLE_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]+")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_hole_id(value: str) -> str:
    hole_id = value.strip()
    if not hole_id or HOLE_ID_PATTERN.fullmatch(hole_id) is None:
        raise ValueError(
            f"invalid hole id {value!r}; only letters, digits, '.', '_' and '-' are allowed"
        )
    return hole_id


def json_default(value: object):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".tmp")
    with part.open("wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(part, path)


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path: Path, value: object) -> None:
    atomic_write_text(
        path,
        json.dumps(value, ensure_ascii=False, indent=2, default=json_default) + "\n",
    )


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(value: object, fallback: str = "item") -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "")).strip("_")
    return text or fallback


def as_dict(value: object) -> dict:
    if isinstance(value, dict):
        return dict(value)
    return {key: val for key, val in vars(value).items()}


def load_hole_ids(positional: Iterable[str], holes_file: str | None) -> list[str]:
    """Read borehole IDs from a one-column text file or CSV containing hole_id/nvcl_id."""
    values = [str(item) for item in positional]
    if holes_file:
        path = Path(holes_file)
        if not path.is_file():
            raise FileNotFoundError(f"hole list does not exist: {path}")
        text = path.read_text(encoding="utf-8-sig")
        lines = [line for line in text.splitlines() if line.strip()]
        if lines:
            header = [cell.strip().lower() for cell in next(csv.reader([lines[0]]))]
            key = next((item for item in ("hole_id", "nvcl_id") if item in header), None)
            if key:
                for row in csv.DictReader(lines):
                    if row.get(key):
                        values.append(row[key])
            else:
                for row in csv.reader(lines):
                    values.extend(cell for cell in row if cell.strip())

    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        hole_id = validate_hole_id(value)
        if hole_id not in seen:
            seen.add(hole_id)
            result.append(hole_id)
    if not result:
        raise ValueError("no hole ids supplied")
    return result


def raw_fingerprint(raw_dir: Path) -> str:
    """Create a fast, stable raw-package fingerprint to skip unchanged boreholes."""
    package = raw_dir / "package_manifest.json"
    if package.is_file():
        try:
            value = read_json(package).get("content_fingerprint")
            if value:
                return str(value)
        except (OSError, ValueError, TypeError):
            pass

    digest = hashlib.sha256()
    metadata_names = (
        "borehole.json",
        "datasets.json",
        "logs_scalar.json",
        "logs_spectral.json",
        "logs_profilometer.json",
        "tray_depths.json",
        "spectral_manifest.json",
        "profilometer_manifest.json",
        "images_manifest.json",
    )
    for name in metadata_names:
        path = raw_dir / name
        digest.update(name.encode("utf-8"))
        if path.is_file():
            digest.update(path.read_bytes())
    for folder in ("scalars", "spectral", "profilometer", "images", "mosaics"):
        root = raw_dir / folder
        if not root.is_dir():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            stat = path.stat()
            digest.update(path.relative_to(raw_dir).as_posix().encode("utf-8"))
            digest.update(str(stat.st_size).encode("ascii"))
            digest.update(str(stat.st_mtime_ns).encode("ascii"))
    return digest.hexdigest()
