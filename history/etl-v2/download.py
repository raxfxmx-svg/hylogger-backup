#!/usr/bin/env python
"""Download the NVCL original package in bulk.

Write `` data/raw/<hole_id >`` independently for each borehole. Use ``. part``` breakpoints for all large files.
Documents; The failure of a drilling hole will not pollute other drilling holes, nor will it delete the old files that have been successful.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import csv
import hashlib
import json
import os
import re
import shutil
import sys
import threading
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

from common import (
    as_dict,
    atomic_write_bytes as _write_bytes,
    atomic_write_json as _write_json,
    atomic_write_text as _write_text,
    json_default,
    read_json,
    safe_name,
    sha256_file,
    utc_now,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


HERE = Path(__file__).resolve().parent
SCALAR_LOG_TYPES = {"1", "2", "5", "6"}
SPECTRAL_CHUNK_SAMPLES = 512
PROFILOMETER_CHUNK_SAMPLES = 512
CONTROL = None
WRITE_LOCK = threading.RLock()


class DownloadPaused(RuntimeError):
    """Leave completed files and sample-aligned breakpoints for the next run."""


class DownloadControl:
    def __init__(self, roots, min_free_bytes=0, stop_file=None):
        self.roots = list(roots)
        self.min_free_bytes = min_free_bytes
        self.stop_file = stop_file
        self.stopped = threading.Event()
        self.reason = ""
        self.lock = threading.Lock()

    def pause(self, reason):
        with self.lock:
            if not self.stopped.is_set():
                self.reason = reason
                self.stopped.set()
                print(f"PAUSED: {reason}", flush=True)
        raise DownloadPaused(self.reason)

    def check(self, additional_bytes=0):
        if self.stopped.is_set():
            raise DownloadPaused(self.reason)
        if self.stop_file is not None and self.stop_file.exists():
            self.pause(f"Stop requested by {self.stop_file}")
        if self.min_free_bytes:
            checked = set()
            for root in self.roots:
                path = Path(root)
                while not path.exists():
                    path = path.parent
                volume = path.resolve().anchor.casefold()
                if volume in checked:
                    continue
                checked.add(volume)
                free = shutil.disk_usage(path).free
                if free < self.min_free_bytes + additional_bytes:
                    self.pause(
                        f"{volume} free {free / 1024**3:.2f} GiB; "
                        f"reserve {self.min_free_bytes / 1024**3:.2f} GiB"
                    )


def check_run(additional_bytes=0):
    if CONTROL is not None:
        CONTROL.check(additional_bytes)


def atomic_write_bytes(path, data):
    # Serialize writes and check the reserve immediately before allocating space.
    with WRITE_LOCK:
        check_run(len(data))
        _write_bytes(path, data)


def atomic_write_text(path, text):
    atomic_write_bytes(path, text.encode("utf-8"))


def atomic_write_json(path, value):
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2, default=json_default) + "\n")


def local_hole_name(hole_id):
    """Encode filesystem-reserved characters without changing the source identity."""
    if not hole_id or any(ord(c) < 32 for c in hole_id):
        raise ValueError(f"Invalid source hole id: {hole_id!r}")
    name = quote(hole_id, safe=" ._-")
    if name.endswith((".", " ")):
        name = name.rstrip(". ") + "".join(f"%{ord(c):02X}" for c in name[len(name.rstrip('. ')):])
    if re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", name):
        name = f"%{ord(name[0]):02X}" + name[1:]
    if len(name) > 180:
        raise ValueError(f"Source hole id is too long for a local directory: {hole_id!r}")
    return name


def load_download_hole_ids(positional, holes_file):
    values = list(positional)
    if holes_file:
        lines = [line for line in Path(holes_file).read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        if lines:
            header = next(csv.reader([lines[0]]))
            key = next((item for item in ("hole_id", "nvcl_id") if item in header), None)
            if key:
                values.extend(row[key] for row in csv.DictReader(lines) if row.get(key))
            else:
                values.extend(cell for row in csv.reader(lines) for cell in row if cell.strip())
    result = list(dict.fromkeys(str(value).strip() for value in values))
    if not result:
        raise ValueError("No hole ids supplied")
    names = [local_hole_name(hole).casefold() for hole in result]
    if len(names) != len(set(names)):
        raise ValueError("Hole ids collide on the Windows filesystem")
    return result


@contextmanager
def output_lock(out_root):
    """An OS lock prevents two runs from appending to the same breakpoints."""
    path = out_root / ".download.lock"
    with path.open("a+b") as handle:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError(f"Another downloader holds {path}") from exc
            try:
                yield
            finally:
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def patch_nvcl_cache() -> None:
    import urllib.parse

    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    from nvcl_kit import svc_interface

    if getattr(svc_interface._ServiceInterface, "_etl2_cache_patch", False):
        return

    def get_response(self, url, params=None, binary=False):
        check_run()
        params = params or {}
        cache_file = None
        if self.CACHE_PATH is not None:
            encoded = urllib.parse.urlencode(params).encode("ascii")
            cache_key = f"{url}?{encoded.decode('ascii')}"
            quoted = urllib.parse.quote(cache_key, "")
            if len(quoted) > 220:
                quoted = urllib.parse.quote(url, "") + "_" + hashlib.sha1(encoded).hexdigest()
            cache_file = Path(self.CACHE_PATH) / f"{quoted}.txt"
            if cache_file.is_file():
                data = cache_file.read_bytes()
                return data if binary else data.decode("utf-8", errors="replace")

        retry = Retry(
            total=int(getattr(self, "RETRIES", 3)),
            connect=int(getattr(self, "RETRIES", 3)),
            read=int(getattr(self, "RETRIES", 3)),
            backoff_factor=float(getattr(self, "BACKOFF_FACTOR", 0.5)),
            status_forcelist=getattr(svc_interface, "HTTP_RETRY_CODES", [429, 500, 502, 503, 504]),
            allowed_methods=["GET"],
        )
        with requests.Session() as session:
            adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
            response = session.get(url, params=params, timeout=(20, 120))
            if response.status_code != 200:
                return b"" if binary else ""
            data = response.content if binary else response.text

        if cache_file is not None and not cache_file.exists():
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(
                cache_file,
                bytes(data) if binary else str(data).encode("utf-8"),
            )
        return data

    svc_interface._ServiceInterface._get_response_str = get_response
    svc_interface._ServiceInterface._etl2_cache_patch = True


@dataclass
class HoleResult:
    hole_id: str
    status: str
    raw_dir: str
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class HoleDownloader:
    def __init__(
        self,
        hole_id: str,
        provider: str,
        out_root: Path,
        cache_root: Path,
    ) -> None:
        self.hole_id = hole_id
        self.provider = provider
        self.out_root = out_root
        self.local_name = local_hole_name(hole_id)
        self.raw_dir = out_root / "raw" / self.local_name
        self.cache_dir = cache_root / provider / self.local_name
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.reader = None
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def log(self, message: str) -> None:
        print(f"[{self.hole_id}] {message}", flush=True)

    def warn(self, step: str, detail: object) -> None:
        message = f"{step}: {detail}"
        self.warnings.append(message)
        self.log(f"WARN {message}")

    def fail(self, step: str, detail: object) -> None:
        message = f"{step}: {detail}"
        self.errors.append(message)
        self.log(f"FAIL {message}")

    def call(self, step: str, function, *, optional: bool = False):
        check_run()
        try:
            value = function()
            check_run()
            return value
        except DownloadPaused:
            raise
        except Exception as exc:  # noqa: BLE001 - per-hole failure isolation
            check_run()
            detail = f"{type(exc).__name__}: {exc}"
            if optional:
                self.warn(step, detail)
            else:
                self.fail(step, detail)
            return None

    def cached_json(self, filename: str, getter, *, required: bool = True):
        path = self.raw_dir / filename
        if path.is_file() and path.stat().st_size:
            try:
                return read_json(path)
            except (OSError, ValueError, TypeError) as exc:
                self.warn(filename, f"invalid cache will be refreshed: {exc}")
        value = self.call(filename, getter, optional=not required)
        if value is None:
            return [] if filename != "borehole.json" else {}
        atomic_write_json(path, value)
        return value

    def init_reader(self) -> bool:
        patch_nvcl_cache()
        from nvcl_kit.param_builder import param_builder
        from nvcl_kit.reader import NVCLReader

        params = param_builder(self.provider, cache_path=str(self.cache_dir) + os.sep)
        if params is None:
            self.fail("reader", f"unknown provider {self.provider!r}")
            return False
        self.reader = self.call("reader", lambda: NVCLReader(params))
        return self.reader is not None

    def download_metadata(self):
        assert self.reader is not None

        def borehole_getter():
            matches = [
                item for item in (self.reader.get_feature_list() or [])
                if str(getattr(item, "nvcl_id", "")).strip() == self.hole_id
            ]
            if not matches:
                raise ValueError("hole not found in provider WFS")
            return as_dict(matches[0])

        borehole = self.cached_json("borehole.json", borehole_getter)
        datasets = self.cached_json(
            "datasets.json",
            lambda: [as_dict(item) for item in self.reader.get_dataset_list(self.hole_id)],
        )
        getters = {
            "logs_scalar.json": self.reader.get_logs_data,
            "logs_image.json": self.reader.get_imagelog_data,
            "logs_spectral.json": self.reader.get_spectrallog_data,
            "logs_profilometer.json": self.reader.get_profilometer_data,
        }
        logs = {}
        for filename, method in getters.items():
            logs[filename] = self.cached_json(
                filename,
                lambda fn=method: [as_dict(item) for item in fn(self.hole_id)],
            )
        return borehole, datasets, logs

    @staticmethod
    def valid_scalar(path: Path) -> bool:
        if not path.is_file() or path.stat().st_size < 10:
            return False
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as handle:
                header = handle.readline().strip()
                first = handle.readline().strip()
            return header.count(",") >= 2 and bool(first)
        except (OSError, UnicodeError):
            return False

    def download_scalars(self, logs: list[dict]) -> list[dict]:
        assert self.reader is not None
        target = self.raw_dir / "scalars"
        target.mkdir(parents=True, exist_ok=True)
        manifest = []
        for log in logs:
            log_id = str(log.get("log_id") or "")
            if str(log.get("log_type") or "") not in SCALAR_LOG_TYPES or not log_id:
                continue
            filename = f"{log_id}_{safe_name(log.get('log_name'), 'measurement')}.csv"
            path = target / filename
            status = "complete"
            if not self.valid_scalar(path):
                response = self.call(
                    f"scalar {log.get('log_name') or log_id}",
                    lambda lid=log_id: self.reader.get_scalar_data([lid]),
                )
                if isinstance(response, str) and response.strip():
                    atomic_write_text(path, response)
                if not self.valid_scalar(path):
                    status = "failed"
                    self.fail("scalar", f"empty or invalid response for {log_id}")
            manifest.append(
                {
                    "log_id": log_id,
                    "log_name": log.get("log_name"),
                    "file": f"scalars/{filename}",
                    "status": status,
                    "nbytes": path.stat().st_size if path.is_file() else 0,
                    "sha256": sha256_file(path) if status == "complete" else None,
                }
            )
        atomic_write_json(self.raw_dir / "scalar_manifest.json", manifest)
        self.log(f"scalar files complete={sum(x['status'] == 'complete' for x in manifest)}")
        return manifest

    def download_spectra(self, logs: list[dict]) -> list[dict]:
        assert self.reader is not None
        target = self.raw_dir / "spectral"
        target.mkdir(parents=True, exist_ok=True)
        manifest = []
        for log in logs:
            log_id = str(log.get("log_id") or "")
            sample_count = int(float(log.get("sample_count") or 0))
            wavelengths = list(log.get("wavelengths") or [])
            band_count = len(wavelengths)
            entry = {
                "log_id": log_id,
                "log_name": log.get("log_name"),
                "sample_count": sample_count,
                "band_count": band_count,
                "dtype": "float32",
                "byte_order": "little",
                "file": None,
                "nbytes": 0,
                "sha256": None,
                "status": "metadata_only",
            }
            manifest.append(entry)
            if sample_count <= 0:
                continue
            if not log_id or band_count <= 0:
                entry["status"] = "failed"
                self.fail("spectrum", f"missing log id or wavelength axis: {log}")
                continue

            filename = f"{log_id}_{safe_name(log.get('log_name'), 'spectrum')}.f32"
            path = target / filename
            part = target / f"{filename}.part"
            row_bytes = band_count * 4
            expected = sample_count * row_bytes
            entry["file"] = f"spectral/{filename}"
            if not path.is_file() or path.stat().st_size != expected:
                resume = part.stat().st_size if part.is_file() else 0
                if resume > expected or resume % row_bytes:
                    part.unlink(missing_ok=True)
                    resume = 0
                start = resume // row_bytes
                self.log(f"spectrum {log_id}: resume sample {start}/{sample_count}")
                mode = "ab" if start else "wb"
                with part.open(mode) as handle:
                    while start < sample_count:
                        end = min(sample_count, start + SPECTRAL_CHUNK_SAMPLES) - 1
                        data = self.call(
                            f"spectrum {log.get('log_name')} {start}-{end}",
                            lambda lid=log_id, first=start, last=end: self.reader.get_spectrallog_datasets(
                                lid,
                                start_sample_no=str(first),
                                end_sample_no=str(last),
                            ),
                        )
                        expected_chunk = (end - start + 1) * row_bytes
                        if not isinstance(data, (bytes, bytearray)) or len(data) != expected_chunk:
                            self.fail(
                                "spectrum",
                                f"{log_id} expected {expected_chunk} bytes for {start}-{end}",
                            )
                            break
                        with WRITE_LOCK:
                            check_run(len(data))
                            handle.write(data)
                            handle.flush()
                        start = end + 1
                if part.is_file() and part.stat().st_size == expected:
                    os.replace(part, path)

            if path.is_file() and path.stat().st_size == expected:
                entry.update(
                    status="complete",
                    nbytes=expected,
                    sha256=sha256_file(path),
                )
            else:
                entry.update(
                    status="partial",
                    nbytes=part.stat().st_size if part.is_file() else 0,
                )
        atomic_write_json(self.raw_dir / "spectral_manifest.json", manifest)
        self.log(f"spectral logs complete={sum(x['status'] == 'complete' for x in manifest)}")
        return manifest

    @staticmethod
    def jsonl_count(path: Path) -> int:
        if not path.is_file():
            return 0
        with path.open("r", encoding="utf-8") as handle:
            return sum(1 for line in handle if line.strip())

    def download_profilometer(self, logs: list[dict]) -> list[dict]:
        assert self.reader is not None
        target = self.raw_dir / "profilometer"
        target.mkdir(parents=True, exist_ok=True)
        manifest = []
        for log in logs:
            log_id = str(log.get("log_id") or "")
            sample_count = int(float(log.get("sample_count") or 0))
            filename = f"{log_id}_{safe_name(log.get('log_name'), 'profile')}.jsonl"
            path = target / filename
            part = target / f"{filename}.part"
            entry = {
                "log_id": log_id,
                "log_name": log.get("log_name"),
                "sample_count": sample_count,
                "channel_count": int(float(log.get("floats_per_sample") or 0)),
                "file": f"profilometer/{filename}",
                "records": 0,
                "nbytes": 0,
                "sha256": None,
                "status": "metadata_only",
            }
            manifest.append(entry)
            if sample_count <= 0:
                continue
            if self.jsonl_count(path) != sample_count:
                start = self.jsonl_count(part)
                if start > sample_count:
                    part.unlink(missing_ok=True)
                    start = 0
                self.log(f"profilometer {log_id}: resume sample {start}/{sample_count}")
                unavailable = False
                with part.open("a" if start else "w", encoding="utf-8", newline="\n") as handle:
                    while start < sample_count:
                        end = min(sample_count, start + PROFILOMETER_CHUNK_SAMPLES) - 1
                        rows = self.call(
                            f"profilometer {log.get('log_name')} {start}-{end}",
                            lambda lid=log_id, first=start, last=end: self.reader.get_profilometer_datasets(
                                lid,
                                start_sample_no=str(first),
                                end_sample_no=str(last),
                            ),
                            optional=True,
                        )
                        if not rows:
                            if start == 0:
                                unavailable = True
                                self.warn("profilometer", f"provider returned no data for {log_id}")
                            break
                        converted = [as_dict(item) for item in rows]
                        chunk = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in converted)
                        with WRITE_LOCK:
                            check_run(len(chunk.encode("utf-8")))
                            handle.write(chunk)
                            handle.flush()
                        start += len(converted)
                        if start <= end:
                            self.fail("profilometer", f"short response for {log_id}")
                            break
                if unavailable:
                    part.unlink(missing_ok=True)
                    entry["status"] = "unavailable"
                elif self.jsonl_count(part) == sample_count:
                    os.replace(part, path)

            if self.jsonl_count(path) == sample_count:
                entry.update(
                    status="complete",
                    records=sample_count,
                    nbytes=path.stat().st_size,
                    sha256=sha256_file(path),
                )
            elif entry["status"] != "unavailable":
                entry.update(
                    status="partial",
                    records=self.jsonl_count(part),
                    nbytes=part.stat().st_size if part.is_file() else 0,
                )
        atomic_write_json(self.raw_dir / "profilometer_manifest.json", manifest)
        return manifest

    @staticmethod
    def is_jpeg(value: object) -> bool:
        return isinstance(value, (bytes, bytearray)) and len(value) > 3 and value[:2] == b"\xff\xd8"

    def download_images(self, datasets: list[dict]) -> dict:
        assert self.reader is not None
        images_dir = self.raw_dir / "images"
        images_dir.mkdir(parents=True, exist_ok=True)
        depth_map: dict[str, list[dict]] = {}
        tray_logs: list[tuple[str, dict]] = []
        all_logs: list[dict] = []

        for dataset in datasets:
            dataset_id = str(dataset.get("dataset_id") or dataset.get("DatasetID") or "")
            if not dataset_id:
                continue
            logs = self.call(
                f"tray image logs {dataset_id}",
                lambda did=dataset_id: self.reader.get_tray_thumb_imglogs(did),
                optional=True,
            ) or []
            tray_logs.extend((dataset_id, as_dict(log)) for log in logs)
            image_logs = self.call(
                f"all image logs {dataset_id}",
                lambda did=dataset_id: self.reader.get_all_imglogs(did),
                optional=True,
            ) or []
            for log in image_logs:
                value = as_dict(log)
                value["dataset_id"] = dataset_id
                all_logs.append(value)

        for _, log in tray_logs:
            log_id = str(log.get("log_id") or "")
            rows = self.call(
                f"tray depths {log_id}",
                lambda lid=log_id: self.reader.get_tray_depths(lid),
                optional=True,
            ) or []
            depth_map[log_id] = [as_dict(item) for item in rows]
        atomic_write_json(self.raw_dir / "tray_depths.json", depth_map)
        atomic_write_json(self.raw_dir / "image_logs_by_dataset.json", all_logs)

        files: list[dict] = []
        log_status: list[dict] = []
        for dataset_id, log in tray_logs:
            log_id = str(log.get("log_id") or "")
            for item in depth_map.get(log_id, []):
                sample_no = str(item.get("sample_no") or "0")
                filename = f"tray_{safe_name(log_id)}_{safe_name(sample_no)}.jpg"
                path = images_dir / filename
                if not self.is_jpeg(path.read_bytes() if path.is_file() else None):
                    data = self.call(
                        f"tray thumbnail {sample_no}",
                        lambda lid=log_id, no=sample_no: self.reader.get_tray_thumb_jpg(lid, no),
                        optional=True,
                    )
                    if self.is_jpeg(data):
                        atomic_write_bytes(path, bytes(data))
                if path.is_file() and self.is_jpeg(path.read_bytes()):
                    files.append(
                        {
                            "file": f"images/{filename}",
                            "dataset_id": dataset_id,
                            "log_id": log_id,
                            "log_name": log.get("log_name") or "Tray Thumbnail Images",
                            "kind": "tray_thumbnail",
                            "sample_no": sample_no,
                            "depth_from": _float_or_none(item.get("start_value")),
                            "depth_to": _float_or_none(item.get("end_value")),
                            "nbytes": path.stat().st_size,
                            "sha256": sha256_file(path),
                        }
                    )

        for log in all_logs:
            dataset_id = str(log.get("dataset_id") or "")
            log_id = str(log.get("log_id") or "")
            name = str(log.get("log_name") or "")
            sample_count = int(float(log.get("sample_count") or 0))
            summary = {
                "dataset_id": dataset_id,
                "log_id": log_id,
                "log_name": name,
                "sample_count": sample_count,
                "downloaded": 0,
                "status": "metadata_only",
            }
            log_status.append(summary)

            if name == "Tray Thumbnail Images":
                summary["downloaded"] = sum(
                    item["log_id"] == log_id and item["kind"] == "tray_thumbnail"
                    for item in files
                )
                summary["status"] = (
                    "complete" if summary["downloaded"] == sample_count else "partial"
                )
                continue
            if name == "Mosaic":
                target = self.raw_dir / "mosaics"
                target.mkdir(parents=True, exist_ok=True)
                filename = f"{log_id}_{safe_name(name)}.html"
                path = target / filename
                if not path.is_file() or not path.stat().st_size:
                    data = self.call(
                        f"mosaic {log_id}",
                        lambda lid=log_id, count=sample_count: self.reader.get_mosaic_image(
                            lid,
                            width=1,
                            startsampleno=0,
                            endsampleno=max(0, count - 1),
                        ),
                        optional=True,
                    )
                    if isinstance(data, str) and data.strip():
                        atomic_write_text(path, data)
                    elif isinstance(data, (bytes, bytearray)) and data:
                        atomic_write_bytes(path, bytes(data))
                if path.is_file() and path.stat().st_size:
                    files.append(
                        {
                            "file": f"mosaics/{filename}",
                            "dataset_id": dataset_id,
                            "log_id": log_id,
                            "log_name": name,
                            "kind": "mosaic",
                            "sample_no": None,
                            "depth_from": None,
                            "depth_to": None,
                            "nbytes": path.stat().st_size,
                            "sha256": sha256_file(path),
                        }
                    )
                    summary.update(status="complete", downloaded=1)
                else:
                    summary["status"] = "unavailable"
                continue

            if name not in {"Tray Images", "Imagery"}:
                summary["status"] = "unknown_type"
                self.warn("image", f"unknown image log {name!r}")
                continue

            summary["skip_reason"] = "thumbnail_only_policy"
            self.log(f"{name}: metadata retained; payload download disabled")

        manifest = {"logs": log_status, "files": files}
        atomic_write_json(self.raw_dir / "images_manifest.json", manifest)
        self.log(f"image assets complete files={len(files)}")
        return manifest

    def content_fingerprint(self) -> str:
        digest = hashlib.sha256()
        for path in sorted(item for item in self.raw_dir.rglob("*") if item.is_file()):
            if path.name in {"package_manifest.json", "download-report.txt"}:
                continue
            if path.name.endswith((".part", ".tmp")):
                continue
            relative = path.relative_to(self.raw_dir).as_posix()
            digest.update(relative.encode("utf-8"))
            digest.update(str(path.stat().st_size).encode("ascii"))
            if path.suffix.lower() in {".json", ".csv"} or path.stat().st_size < 2_000_000:
                digest.update(sha256_file(path).encode("ascii"))
        return digest.hexdigest()

    def run(self) -> HoleResult:
        started = utc_now()
        check_run()
        self.log("download started")
        atomic_write_json(self.raw_dir / "source_identity.json", {
            "hole_id": self.hole_id, "local_directory": self.local_name,
            "provider": self.provider, "encoding": "percent-encoding of filesystem-reserved characters",
        })
        if not self.init_reader():
            return self.finish(started)
        _, datasets, logs = self.download_metadata()
        if not datasets:
            self.fail("datasets", "No datasets returned; package is incomplete")
            return self.finish(started)
        self.download_scalars(logs.get("logs_scalar.json", []))
        self.download_spectra(logs.get("logs_spectral.json", []))
        self.download_profilometer(logs.get("logs_profilometer.json", []))
        self.download_images(datasets)
        return self.finish(started)

    def finish(self, started: str) -> HoleResult:
        status = "failed" if self.errors else ("complete_with_warnings" if self.warnings else "complete")
        manifest = {
            "schema_version": 1,
            "local_directory": self.local_name,
            "image_policy": "tray thumbnails; Tray Images and Imagery payloads excluded",
            "hole_id": self.hole_id,
            "provider": self.provider,
            "status": status,
            "started_at": started,
            "finished_at": utc_now(),
            "content_fingerprint": self.content_fingerprint(),
            "warnings": self.warnings,
            "errors": self.errors,
        }
        atomic_write_json(self.raw_dir / "package_manifest.json", manifest)
        report = [
            f"hole_id: {self.hole_id}",
            f"provider: {self.provider}",
            f"status: {status}",
            f"warnings: {len(self.warnings)}",
            *[f"  WARN {item}" for item in self.warnings],
            f"errors: {len(self.errors)}",
            *[f"  ERROR {item}" for item in self.errors],
        ]
        atomic_write_text(self.raw_dir / "download-report.txt", "\n".join(report) + "\n")
        self.log(f"download {status}")
        return HoleResult(
            hole_id=self.hole_id,
            status=status,
            raw_dir=str(self.raw_dir),
            warnings=list(self.warnings),
            errors=list(self.errors),
        )


def _float_or_none(value: object):
    try:
        return float(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def download_one(hole_id: str, provider: str, out_root: Path, cache_root: Path) -> HoleResult:
    raw_dir = out_root / "raw" / local_hole_name(hole_id)
    try:
        check_run()
        return HoleDownloader(hole_id, provider, out_root, cache_root).run()
    except DownloadPaused as exc:
        return HoleResult(hole_id, "paused", str(raw_dir), warnings=[str(exc)])
    except Exception as exc:  # noqa: BLE001 - per-hole failure isolation
        raw_dir.mkdir(parents=True, exist_ok=True)
        detail = f"{type(exc).__name__}: {exc}"
        _write_text(raw_dir / "download-crash.txt", traceback.format_exc())
        print(f"[{hole_id}] CRASH {detail}", flush=True)
        return HoleResult(hole_id, "failed", str(raw_dir), errors=[detail])


def run_batch(holes, args, out_root, cache_root):
    results: list[HoleResult] = []
    started = utc_now()

    def snapshot(final=False):
        ordered = sorted(results, key=lambda item: holes.index(item.hole_id))
        summary = {
            "started_at": started,
            "generated_at": utc_now(),
            "status": "running" if not final else (
                "paused" if any(x.status == "paused" for x in results) else
                "finished_with_failures" if any(x.status == "failed" for x in results) else "finished"
            ),
            "pid": os.getpid(),
            "workers": args.workers,
            "requested": len(holes),
            "processed": len(results),
            "complete": sum(item.status == "complete" for item in results),
            "complete_with_warnings": sum(item.status == "complete_with_warnings" for item in results),
            "failed": sum(item.status == "failed" for item in results),
            "paused": sum(item.status == "paused" for item in results),
            "pause_reason": CONTROL.reason if CONTROL else None,
            "image_policy": "Tray Images and Imagery: metadata only",
            "holes": [vars(item) for item in ordered],
        }
        # Small status reports remain writable after the data-space guard pauses.
        if args.progress_file:
            _write_json(Path(args.progress_file), summary)
        return summary

    snapshot()
    print(f"Batch: {len(holes)} holes; workers={args.workers}; reserve={args.min_free_gib} GiB", flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(download_one, hole, args.provider, out_root, cache_root): hole
            for hole in holes
        }
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            snapshot()

    summary = snapshot(final=True)
    _write_json(out_root / "download-batch-summary.json", summary)
    print(json.dumps({key: value for key, value in summary.items() if key != "holes"}, ensure_ascii=False, indent=2))
    return 2 if summary["paused"] else 1 if summary["failed"] else 0


def main() -> int:
    global CONTROL
    parser = argparse.ArgumentParser(description='Batch-download raw NVCL packages, retaining metadata only for full-resolution images')
    parser.add_argument("hole_ids", nargs="*", help='One or more source borehole IDs')
    parser.add_argument("--holes-file", help='Borehole ID text file or CSV with hole_id/nvcl_id column')
    parser.add_argument("--provider", default="wa", help='NVCL provider (default: wa)')
    parser.add_argument("--out", default=str(HERE / "data"), help='Data root')
    parser.add_argument("--cache", help='Cache root (default: <out>/.cache)')
    parser.add_argument("--workers", type=int, default=1, help='Number of concurrent borehole downloads')
    parser.add_argument("--min-free-gib", type=float, default=30, help='Free-space reserve for raw packages and cache, GiB (default: 30)')
    parser.add_argument("--progress-file", help='Update status JSON after each borehole and when the batch exits')
    parser.add_argument("--stop-file", help='Pause safely when this file appears, retaining downloaded data')
    args = parser.parse_args()
    try:
        holes = load_download_hole_ids(args.hole_ids, args.holes_file)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between 1 and 8")
    if not 0 <= args.min_free_gib < float("inf"):
        parser.error("--min-free-gib must be finite and non-negative")
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.provider):
        parser.error("Invalid provider")

    out_root = Path(args.out).resolve()
    cache_root = Path(args.cache).resolve() if args.cache else out_root / ".cache"
    CONTROL = DownloadControl(
        [out_root, cache_root], int(args.min_free_gib * 1024**3),
        Path(args.stop_file).resolve() if args.stop_file else None,
    )
    out_root.mkdir(parents=True, exist_ok=True)
    with output_lock(out_root):
        return run_batch(holes, args, out_root, cache_root)


if __name__ == "__main__":
    raise SystemExit(main())
