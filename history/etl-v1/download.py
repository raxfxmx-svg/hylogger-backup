#!/usr/bin/env python
"""Download all available data for one borehole from the NVCL online service.

Usage:
    python download.py <nvcl_id> [--provider wa] [--out data] [--cache data/.cache]

Output directory <out>/raw/<nvcl_id>/:
    borehole.json            All borehole WFS fields
    datasets.json            Dataset list
    logs_scalar.json / logs_image.json / logs_spectral.json / logs_profilometer.json
    scalars/<log_id>_<safe_name>.csv
    spectral/<log_id>_<safe_name>.f32
    profilometer/<log_id>_<safe_name>.jsonl (when provided)
    images/... / mosaics/...
    tray_depths.json
    *_manifest.json
    download-report.txt      Inventory and validation

Idempotent: skip completed files and resume large downloads. Record step failures and continue;
Return a nonzero exit code if any step fails.
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from nvcl_kit.reader import NVCLReader
from nvcl_kit.param_builder import param_builder


def _patch_nvcl_cache():
    """Fix the cache bug in nvcl-kit 1.3.3 svc_interface._get_response_str:
    Writing text responses in wb mode raises TypeError; cached reads also omit decoding.
    Patch: encode cache writes and decode cache reads."""
    import hashlib
    import urllib.parse

    import requests
    from requests.adapters import HTTPAdapter
    from requests.exceptions import HTTPError
    from urllib3.util.retry import Retry

    from nvcl_kit import svc_interface

    def _get_response_str(self, url, params={}, binary=False):
        response_str = b"" if binary else ""
        fileCachePath = None
        if self.CACHE_PATH is not None:
            enc_params = None
            if params != {}:
                enc_params = urllib.parse.urlencode(params).encode("ascii")
            fileCachePath = self.CACHE_PATH + urllib.parse.quote(
                f"{url}?{enc_params.decode('utf-8')}", "") + ".txt"
            if len(fileCachePath) > 256:
                param = hashlib.sha1(enc_params).hexdigest()
                fileCachePath = self.CACHE_PATH + urllib.parse.quote(
                    f"{url}?{param}", "") + ".txt"
            if os.path.exists(fileCachePath):
                with open(fileCachePath, "rb") as cacheFile:
                    data = cacheFile.read()
                svc_interface.LOGGER.debug(f"read cache:{fileCachePath}")
                return data if binary else data.decode("utf-8", errors="replace")

        try:
            with requests.Session() as s:
                retries = Retry(total=self.RETRIES,
                                backoff_factor=self.BACKOFF_FACTOR,
                                status_forcelist=svc_interface.HTTP_RETRY_CODES,
                                allowed_methods=["GET"])
                s.mount("https://", HTTPAdapter(max_retries=retries))
                s.mount("http://", HTTPAdapter(max_retries=retries))
                svc_interface.LOGGER.debug(f"Sending {url=} {params=}")
                response = s.get(url, params=params, timeout=120)
                response_str = response.content if binary else response.text
        except (HTTPError, requests.RequestException) as e:
            svc_interface.LOGGER.error(f"HTTP Error with {url}: {e}")
            return b"" if binary else ""

        if response.status_code != 200:
            svc_interface.LOGGER.error(
                f"HTTP Error with {url}: HTTP Status Code {response.status_code}: {response.reason}")
            return b"" if binary else ""

        if self.CACHE_PATH is not None and not os.path.exists(fileCachePath):
            with open(fileCachePath, "wb") as cacheFile:
                cacheFile.write(response_str if binary else response_str.encode("utf-8"))
            svc_interface.LOGGER.debug(f"write cache:{fileCachePath}")
        return response_str

    svc_interface._ServiceInterface._get_response_str = _get_response_str


_patch_nvcl_cache()

CALL_TIMEOUT = 120  # Seconds; the nvcl-kit TIMEOUT setting is ineffective here.
SCALAR_LOG_TYPES = {"1", "2", "5", "6"}
SPECTRAL_CHUNK_SAMPLES = 512
PROFILOMETER_CHUNK_SAMPLES = 512

# Reserve extra workers so stalled calls do not block later calls.
EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=8)

FAILURES = []  # List of (step, detail) pairs
WARNINGS = []  # Nonfatal issues, such as optional data unavailable from the server


def call(desc, fn, timeout=CALL_TIMEOUT):
    """Run fn() with an outer timeout and return (ok, value_or_error)."""
    future = EXECUTOR.submit(fn)
    try:
        return True, future.result(timeout=timeout)
    except concurrent.futures.TimeoutError:
        return False, f"timeout after {timeout}s"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def fail(step, detail):
    FAILURES.append((step, detail))
    print(f"  FAIL {step}: {detail}")


def warn(step, detail):
    WARNINGS.append((step, detail))
    print(f"  WARN {step}: {detail}")


def jsonable(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    raise TypeError(f"not JSON-serializable: {type(obj).__name__}")


def ns_to_dict(ns):
    return {k: v for k, v in vars(ns).items()}


def write_json_if_missing(path, obj):
    if path.exists() and path.stat().st_size > 0:
        print(f"  skip (exists): {path.name}")
        return "skipped"
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=jsonable) + "\n",
        encoding="utf-8",
    )
    return "written"


def write_json(path, obj):
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, default=jsonable) + "\n",
        encoding="utf-8",
    )


def sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_name(name):
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name)).strip("_")
    return s or "log"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def download_spectral_data(reader, spectral_logs, out_dir):
    """Download every spectral log containing samples.

    NVCL returns headerless sample-major little-endian float32. Request chunks and write
    to .part files, resuming at complete sample boundaries. Final size must match the log
    metadata sample_count * band_count * 4 exactly.
    """
    spectral_dir = out_dir / "spectral"
    spectral_dir.mkdir(parents=True, exist_ok=True)
    manifest = []

    for log in spectral_logs:
        log_id = str(log.get("log_id") or "")
        sample_count = int(log.get("sample_count") or 0)
        wavelengths = log.get("wavelengths") or []
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
            fail(f"spectral {log_id or '?'}", "sample_count > 0 but wavelengths are missing")
            continue

        filename = f"{log_id}_{safe_name(log.get('log_name', 'spectral'))}.f32"
        path = spectral_dir / filename
        part = spectral_dir / f"{filename}.part"
        row_bytes = band_count * 4
        expected_bytes = sample_count * row_bytes
        entry["file"] = f"spectral/{filename}"

        if path.exists() and path.stat().st_size == expected_bytes:
            print(f"  skip (complete): {entry['file']}")
        else:
            resume_bytes = part.stat().st_size if part.exists() else 0
            if resume_bytes > expected_bytes or resume_bytes % row_bytes:
                warn(f"spectral {log_id}", "discarding invalid partial file")
                part.unlink(missing_ok=True)
                resume_bytes = 0
            start = resume_bytes // row_bytes
            mode = "ab" if start else "wb"
            print(
                f"spectral {log.get('log_name')} ({log_id}): "
                f"samples={sample_count} bands={band_count} resume={start}"
            )
            completed = True
            with part.open(mode) as fh:
                while start < sample_count:
                    end = min(start + SPECTRAL_CHUNK_SAMPLES, sample_count) - 1
                    ok, res = call(
                        f"spectral {log_id}#{start}-{end}",
                        lambda lid=log_id, a=start, b=end: reader.get_spectrallog_datasets(
                            lid, start_sample_no=str(a), end_sample_no=str(b)
                        ),
                    )
                    expected_chunk = (end - start + 1) * row_bytes
                    if not ok or not isinstance(res, (bytes, bytearray)):
                        fail(f"spectral {log_id}#{start}-{end}", res)
                        completed = False
                        break
                    if len(res) != expected_chunk:
                        fail(
                            f"spectral {log_id}#{start}-{end}",
                            f"expected {expected_chunk} bytes, got {len(res)}",
                        )
                        completed = False
                        break
                    fh.write(res)
                    fh.flush()
                    start = end + 1
            if completed and part.stat().st_size == expected_bytes:
                os.replace(part, path)

        if path.exists() and path.stat().st_size == expected_bytes:
            entry["status"] = "complete"
            entry["nbytes"] = expected_bytes
            entry["sha256"] = sha256_file(path)
        else:
            entry["status"] = "partial"
            entry["nbytes"] = part.stat().st_size if part.exists() else 0

    write_json(out_dir / "spectral_manifest.json", manifest)
    complete = sum(x["status"] == "complete" for x in manifest)
    print(f"spectral data: complete={complete} metadata_only={sum(x['status'] == 'metadata_only' for x in manifest)}")
    return manifest


def _count_jsonl(path):
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as fh:
        return sum(1 for line in fh if line.strip())


def download_profilometer_data(reader, profilometer_logs, out_dir):
    """Download profilometer data as JSON Lines; mark unavailable when no server endpoint exists."""
    prof_dir = out_dir / "profilometer"
    prof_dir.mkdir(parents=True, exist_ok=True)
    manifest = []

    for log in profilometer_logs:
        log_id = str(log.get("log_id") or "")
        sample_count = int(log.get("sample_count") or 0)
        filename = f"{log_id}_{safe_name(log.get('log_name', 'profilometer'))}.jsonl"
        path = prof_dir / filename
        part = prof_dir / f"{filename}.part"
        entry = {
            "log_id": log_id,
            "log_name": log.get("log_name"),
            "sample_count": sample_count,
            "floats_per_sample": int(float(log.get("floats_per_sample") or 0)),
            "file": f"profilometer/{filename}",
            "records": 0,
            "nbytes": 0,
            "sha256": None,
            "status": "metadata_only",
        }
        manifest.append(entry)
        if sample_count <= 0:
            continue

        if path.exists() and _count_jsonl(path) == sample_count:
            print(f"  skip (complete): {entry['file']}")
        else:
            start = _count_jsonl(part)
            if start > sample_count:
                warn(f"profilometer {log_id}", "discarding invalid partial file")
                part.unlink(missing_ok=True)
                start = 0
            mode = "a" if start else "w"
            completed = True
            unavailable = False
            with part.open(mode, encoding="utf-8", newline="\n") as fh:
                while start < sample_count:
                    end = min(start + PROFILOMETER_CHUNK_SAMPLES, sample_count) - 1
                    ok, res = call(
                        f"profilometer {log_id}#{start}-{end}",
                        lambda lid=log_id, a=start, b=end: reader.get_profilometer_datasets(
                            lid, start_sample_no=str(a), end_sample_no=str(b)
                        ),
                    )
                    if not ok:
                        fail(f"profilometer {log_id}#{start}-{end}", res)
                        completed = False
                        break
                    if not res:
                        if start == 0:
                            warn(
                                f"profilometer {log_id}",
                                "provider returned no data (endpoint unavailable)",
                            )
                            unavailable = True
                        else:
                            fail(f"profilometer {log_id}#{start}-{end}", "empty response")
                        completed = False
                        break
                    rows = [ns_to_dict(x) for x in res]
                    for row in rows:
                        fh.write(json.dumps(row, ensure_ascii=False, default=jsonable) + "\n")
                    fh.flush()
                    start += len(rows)
                    if len(rows) != end - (start - len(rows)) + 1:
                        fail(
                            f"profilometer {log_id}",
                            f"expected chunk through sample {end}, got {len(rows)} records",
                        )
                        completed = False
                        break
            if unavailable:
                part.unlink(missing_ok=True)
                entry["status"] = "unavailable"
            elif completed and _count_jsonl(part) == sample_count:
                os.replace(part, path)

        if path.exists() and _count_jsonl(path) == sample_count:
            entry["status"] = "complete"
            entry["records"] = sample_count
            entry["nbytes"] = path.stat().st_size
            entry["sha256"] = sha256_file(path)
        elif entry["status"] != "unavailable":
            entry["status"] = "partial"
            entry["records"] = _count_jsonl(part)
            entry["nbytes"] = part.stat().st_size if part.exists() else 0

    write_json(out_dir / "profilometer_manifest.json", manifest)
    print(
        "profilometer data: "
        f"complete={sum(x['status'] == 'complete' for x in manifest)} "
        f"unavailable={sum(x['status'] == 'unavailable' for x in manifest)}"
    )
    return manifest


def _is_jpeg(data):
    return isinstance(data, (bytes, bytearray)) and len(data) > 3 and data[:2] == b"\xff\xd8"


def download_remaining_images(reader, datasets, tray_logs, depths_all, out_dir):
    """Save accessible image-log content and create unambiguous import manifests.

    The main workflow downloads Tray Thumbnail through the legacy endpoint. This function adds full trays,
    per-sample imagery, and mosaics. If getImage is unavailable, probe
    once and mark the entire log unavailable, avoiding thousands of repeated 404 responses.
    """
    images_dir = out_dir / "images"
    files = []
    log_manifest = []
    dataset_depths = {}

    for ds_id, lg in tray_logs:
        log_id = str(lg.get("log_id") or "")
        entries = depths_all.get(log_id, [])
        by_no = {
            str(e.get("sample_no")): (_f_json(e.get("start_value")), _f_json(e.get("end_value")))
            for e in entries
        }
        dataset_depths[ds_id] = by_no

    multi_thumb = len(tray_logs) > 1
    for ds_id, lg in tray_logs:
        log_id = str(lg.get("log_id") or "")
        depths = depths_all.get(log_id, [])
        for e in depths:
            sno = str(e.get("sample_no"))
            stem = f"tray_{sno}" if not multi_thumb else f"tray_{safe_name(log_id)}_{sno}"
            path = images_dir / f"{stem}.jpg"
            if path.exists() and path.stat().st_size > 0:
                files.append(
                    {
                        "file": path.relative_to(out_dir).as_posix(),
                        "log_id": log_id,
                        "dataset_id": ds_id,
                        "kind": "tray_thumbnail",
                        "sample_no": sno,
                        "depth_from": _f_json(e.get("start_value")),
                        "depth_to": _f_json(e.get("end_value")),
                        "nbytes": path.stat().st_size,
                    }
                )

    all_logs = []
    for ds in datasets:
        ds_id = str(ds.get("dataset_id") or ds.get("DatasetID") or "")
        if not ds_id:
            continue
        ok, res = call(f"all image logs {ds_id}", lambda d=ds_id: reader.get_all_imglogs(d))
        if not ok:
            fail(f"all image logs {ds_id}", res)
            continue
        for obj in res:
            item = ns_to_dict(obj)
            item["dataset_id"] = ds_id
            all_logs.append(item)
    write_json(out_dir / "image_logs_by_dataset.json", all_logs)

    for log in all_logs:
        ds_id = str(log.get("dataset_id") or "")
        log_id = str(log.get("log_id") or "")
        name = str(log.get("log_name") or "")
        sample_count = int(float(log.get("sample_count") or 0))
        summary = {
            "dataset_id": ds_id,
            "log_id": log_id,
            "log_name": name,
            "sample_count": sample_count,
            "downloaded": 0,
            "status": "metadata_only",
        }
        log_manifest.append(summary)

        if name == "Tray Thumbnail Images":
            summary["downloaded"] = sum(x["log_id"] == log_id for x in files)
            summary["status"] = "complete" if summary["downloaded"] == sample_count else "partial"
            continue

        if name == "Mosaic":
            mosaic_dir = out_dir / "mosaics"
            mosaic_dir.mkdir(parents=True, exist_ok=True)
            html_path = mosaic_dir / f"{log_id}_{safe_name(name)}.html"
            if not html_path.exists() or html_path.stat().st_size == 0:
                ok, res = call(
                    f"mosaic {log_id}",
                    lambda lid=log_id, n=sample_count: reader.get_mosaic_image(
                        lid, width=1, startsampleno=0, endsampleno=max(0, n - 1)
                    ),
                )
                if ok and isinstance(res, str) and res.strip():
                    html_path.write_text(res, encoding="utf-8")
                elif ok and isinstance(res, (bytes, bytearray)) and res:
                    html_path.write_bytes(bytes(res))
                else:
                    warn(f"mosaic {log_id}", "provider returned no mosaic content")
            if html_path.exists() and html_path.stat().st_size > 0:
                files.append(
                    {
                        "file": html_path.relative_to(out_dir).as_posix(),
                        "log_id": log_id,
                        "dataset_id": ds_id,
                        "kind": "mosaic",
                        "sample_no": None,
                        "depth_from": None,
                        "depth_to": None,
                        "nbytes": html_path.stat().st_size,
                    }
                )
                summary["downloaded"] = 1
                summary["status"] = "complete"
            else:
                summary["status"] = "unavailable"
            continue

        if name not in {"Tray Images", "Imagery"}:
            warn(f"image log {log_id}", f"unknown image log type: {name}")
            summary["status"] = "unknown_type"
            continue

        kind = "tray_image" if name == "Tray Images" else "imagery"
        target_dir = images_dir / kind / safe_name(log_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        if kind == "tray_image" and dataset_depths.get(ds_id):
            sample_nos = list(dataset_depths[ds_id])
        else:
            sample_nos = [str(i) for i in range(sample_count)]

        unavailable = False
        for sno in sample_nos:
            path = target_dir / f"sample_{sno}.jpg"
            if path.exists() and path.stat().st_size > 0:
                data_ok = True
            else:
                ok, res = call(
                    f"image {log_id}#{sno}",
                    lambda lid=log_id, s=sno, d=ds_id: reader.get_image(
                        lid, s, dataset_id=d, uncorrected=True
                    ),
                )
                data_ok = ok and _is_jpeg(res)
                if data_ok:
                    path.write_bytes(bytes(res))
                else:
                    if summary["downloaded"] == 0:
                        warn(
                            f"image log {log_id}",
                            "provider getImage endpoint unavailable; remaining samples skipped",
                        )
                        unavailable = True
                    else:
                        fail(f"image {log_id}#{sno}", res if not ok else "invalid/empty JPEG")
                    break
            if data_ok:
                depth_from, depth_to = dataset_depths.get(ds_id, {}).get(sno, (None, None))
                files.append(
                    {
                        "file": path.relative_to(out_dir).as_posix(),
                        "log_id": log_id,
                        "dataset_id": ds_id,
                        "kind": kind,
                        "sample_no": sno,
                        "depth_from": depth_from,
                        "depth_to": depth_to,
                        "nbytes": path.stat().st_size,
                    }
                )
                summary["downloaded"] += 1

        if unavailable:
            summary["status"] = "unavailable"
        elif summary["downloaded"] == len(sample_nos):
            summary["status"] = "complete"
        else:
            summary["status"] = "partial"

    manifest = {"logs": log_manifest, "files": files}
    write_json(out_dir / "images_manifest.json", manifest)
    print(
        f"all image assets: files={len(files)} "
        f"unavailable_logs={sum(x['status'] == 'unavailable' for x in log_manifest)}"
    )
    return manifest


def _f_json(value):
    try:
        return float(value) if value is not None and str(value).strip() else None
    except (TypeError, ValueError):
        return None


def main():
    ap = argparse.ArgumentParser(description='Download NVCL borehole data')
    ap.add_argument("nvcl_id", help='NVCL borehole ID, for example 05GJD001')
    ap.add_argument("--provider", default="wa", help='NVCL provider (default: wa)')
    ap.add_argument("--out", default="data", help='Output data root (default: data)')
    ap.add_argument("--cache", default="data/.cache", help='HTTP cache directory (default: data/.cache)')
    args = ap.parse_args()

    nvcl_id = args.nvcl_id
    out_dir = Path(args.out) / "raw" / nvcl_id
    scalars_dir = out_dir / "scalars"
    images_dir = out_dir / "images"
    for d in (out_dir, scalars_dir, images_dir):
        d.mkdir(parents=True, exist_ok=True)
    cache_path = Path(args.cache)
    cache_path.mkdir(parents=True, exist_ok=True)

    print(f"NVCL download: hole={nvcl_id} provider={args.provider} out={out_dir}")

    # --- Reader initialization ------------------------------------------------------
    # nvcl-kit concatenates CACHE_PATH and filename, so the path needs a trailing separator.
    param_obj = param_builder(args.provider, cache_path=str(cache_path) + os.sep)
    if param_obj is None:
        print(f"ERROR: param_builder failed, provider='{args.provider}'")
        return 2
    ok, reader = call("init NVCLReader", lambda: NVCLReader(param_obj))
    if not ok:
        fail("init NVCLReader", reader)
        return finish(out_dir, nvcl_id, args)
    if getattr(reader, "wfs_error", False):
        print('WARNING: reader reported wfs_error; the borehole list may be incomplete.')

    # --- borehole.json ------------------------------------------------------
    bh_path = out_dir / "borehole.json"
    if bh_path.exists() and bh_path.stat().st_size > 0:
        print("skip (exists): borehole.json")
    else:
        feats = []
        ok, res = call("filter_feat_list", lambda: reader.filter_feat_list(name=nvcl_id))
        if ok and res:
            feats = res
        else:
            # Fallback: scan all features for the matching nvcl_id.
            ok2, all_feats = call("get_feature_list", reader.get_feature_list)
            if ok2:
                feats = [f for f in all_feats if getattr(f, "nvcl_id", None) == nvcl_id]
            else:
                fail("get_feature_list", all_feats)
        if feats:
            write_json_if_missing(bh_path, ns_to_dict(feats[0]))
            print(f"borehole.json: matched nvcl_id={getattr(feats[0], 'nvcl_id', '?')}")
        else:
            fail("borehole.json", f"No WFS feature found for '{nvcl_id}'")

    # --- datasets.json ------------------------------------------------------
    ds_path = out_dir / "datasets.json"
    datasets = []
    if ds_path.exists() and ds_path.stat().st_size > 0:
        print("skip (exists): datasets.json")
        datasets = read_json(ds_path)
    else:
        ok, res = call("get_dataset_list", lambda: reader.get_dataset_list(nvcl_id))
        if ok:
            datasets = [ns_to_dict(d) for d in res]
            write_json_if_missing(ds_path, datasets)
        else:
            fail("datasets.json", res)
    print(f"datasets: {len(datasets)}")

    # --- Four log categories ------------------------------------------------------
    log_specs = [
        ("logs_scalar.json", lambda: reader.get_logs_data(nvcl_id)),
        ("logs_image.json", lambda: reader.get_imagelog_data(nvcl_id)),
        ("logs_spectral.json", lambda: reader.get_spectrallog_data(nvcl_id)),
        ("logs_profilometer.json", lambda: reader.get_profilometer_data(nvcl_id)),
    ]
    log_lists = {}
    for fname, fn in log_specs:
        path = out_dir / fname
        if path.exists() and path.stat().st_size > 0:
            print(f"skip (exists): {fname}")
            log_lists[fname] = read_json(path)
            continue
        ok, res = call(fname, fn)
        if ok:
            data = [ns_to_dict(x) for x in res]
            write_json_if_missing(path, data)
            log_lists[fname] = data
            print(f"{fname}: {len(data)}  records")
        else:
            fail(fname, res)

    scalar_logs = log_lists.get("logs_scalar.json", [])
    spectral_logs = log_lists.get("logs_spectral.json", [])
    profilometer_logs = log_lists.get("logs_profilometer.json", [])

    # --- scalar CSV ---------------------------------------------------------
    csv_ok = csv_fail = 0
    for log in scalar_logs:
        if log.get("log_type") not in SCALAR_LOG_TYPES or not log.get("algorithm_id"):
            continue
        log_id = log["log_id"]
        csv_path = scalars_dir / f"{log_id}_{safe_name(log.get('log_name', 'log'))}.csv"
        if csv_path.exists() and csv_path.stat().st_size > 0:
            csv_ok += 1
            continue
        ok, res = call(f"scalar {log_id}", lambda lid=log_id: reader.get_scalar_data([lid]))
        if ok and isinstance(res, str) and res.strip():
            csv_path.write_text(res, encoding="utf-8")
            csv_ok += 1
        else:
            csv_fail += 1
            fail(f"scalar csv {log_id}", res if not ok else "empty response")
    print(f"scalar CSV: ok={csv_ok} failed={csv_fail}")

    # --- Spectral / profilometer payloads ----------------------------------
    # Spectral endpoints return sample-major little-endian float32; save profiles as JSONL.
    # Some providers, including the current WA service, publish only profile metadata.
    # Record unavailable in manifests/reports; never mark missing server data as downloaded.
    download_spectral_data(reader, spectral_logs, out_dir)
    download_profilometer_data(reader, profilometer_logs, out_dir)

    # --- Tray images -----------------------------------------------------------
    # Collect tray-thumbnail logs for each dataset.
    tray_logs = []  # (dataset_id, log dict)
    for ds in datasets:
        ds_id = ds.get("dataset_id") or ds.get("DatasetID") or ""
        if not ds_id:
            continue
        ok, res = call(f"tray_thumb_imglogs {ds_id}", lambda d=ds_id: reader.get_tray_thumb_imglogs(d))
        if ok:
            for lg in res:
                tray_logs.append((ds_id, ns_to_dict(lg)))
        else:
            fail(f"tray_thumb_imglogs {ds_id}", res)
    print(f"Tray-thumbnail log: {len(tray_logs)}")

    # Tray depth list for each log
    depths_all = {}
    td_path = out_dir / "tray_depths.json"
    if td_path.exists() and td_path.stat().st_size > 0:
        print("skip (exists): tray_depths.json")
        depths_all = read_json(td_path)
    else:
        for ds_id, lg in tray_logs:
            log_id = lg["log_id"]
            ok, res = call(f"tray_depths {log_id}", lambda lid=log_id: reader.get_tray_depths(lid))
            if ok:
                depths_all[log_id] = [ns_to_dict(t) for t in res]
            else:
                fail(f"tray_depths {log_id}", res)
        write_json_if_missing(td_path, depths_all)
        print(f"tray_depths.json: total  {sum(len(v) for v in depths_all.values())}  trays")

    img_ok = img_fail = 0
    multi = len(tray_logs) > 1
    for ds_id, lg in tray_logs:
        log_id = lg["log_id"]
        depths = depths_all.get(log_id, [])
        sample_nos = [str(d["sample_no"]) for d in depths]
        if not sample_nos:
            n = int(lg.get("sample_count") or 0)
            sample_nos = [str(i) for i in range(n)]
        for sno in sample_nos:
            stem = f"tray_{sno}" if not multi else f"tray_{safe_name(log_id)}_{sno}"
            img_path = images_dir / f"{stem}.jpg"
            if img_path.exists() and img_path.stat().st_size > 0:
                img_ok += 1
                continue
            # WA getImage.html returns 404; use the legacy thumbnail endpoint directly.
            ok, res = call(
                f"tray_thumb {log_id}#{sno}",
                lambda lid=log_id, s=sno: reader.get_tray_thumb_jpg(lid, s),
            )
            if ok and isinstance(res, (bytes, bytearray)) and len(res) > 0:
                img_path.write_bytes(bytes(res))
                img_ok += 1
            else:
                img_fail += 1
                fail(f"image {log_id}#{sno}", res if not ok else "empty response")
    print(f"Tray images: ok={img_ok} failed={img_fail}")

    # Add all image logs: full trays, per-sample imagery, and mosaics. If the provider
    # has no corresponding endpoint, mark it unavailable and retain metadata and accessible thumbnails.
    download_remaining_images(reader, datasets, tray_logs, depths_all, out_dir)

    return finish(out_dir, nvcl_id, args)


def finish(out_dir, nvcl_id, args):
    """Validate downloads, write download-report.txt, and return an exit code."""
    lines = []
    lines.append("NVCL download report")
    lines.append(f"hole_id      : {nvcl_id}")
    lines.append(f"provider     : {args.provider}")
    lines.append(f"output dir   : {out_dir}")
    lines.append(f"generated at : {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    lines.append("JSON files:")
    for path in sorted(out_dir.glob("*.json")):
        try:
            data = read_json(path)
            n = len(data) if isinstance(data, (list, dict)) else 1
            lines.append(f"  {path.name:<24} {n} records, {path.stat().st_size} bytes")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"  {path.name:<24} UNREADABLE: {exc}")
            fail("report json check", f"{path.name}: {exc}")
    lines.append("")

    csvs = sorted((out_dir / "scalars").glob("*.csv"))
    lines.append(f"scalar CSVs: {len(csvs)} files")
    bad_csv = 0
    for p in csvs:
        try:
            n_rows = sum(1 for _ in p.open("r", encoding="utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001
            n_rows = -1
            bad_csv += 1
            fail("report csv check", f"{p.name}: {exc}")
        lines.append(f"  {p.name}: {n_rows} lines, {p.stat().st_size} bytes")
    lines.append("")

    jpgs = sorted((out_dir / "images").rglob("*.jpg"))
    lines.append(f"image assets: {len(jpgs)} JPG files")
    bad_jpg = 0
    try:
        from PIL import Image
        for p in jpgs:
            try:
                with Image.open(p) as im:
                    im.verify()
                lines.append(f"  {p.name}: OK, {p.stat().st_size} bytes")
            except Exception as exc:  # noqa: BLE001
                bad_jpg += 1
                fail("report jpg check", f"{p.name}: {exc}")
                lines.append(f"  {p.name}: INVALID ({exc})")
    except ImportError:
        lines.append('  (PIL unavailable; image validation skipped)')
    lines.append("")

    lines.append(f"summary: {len(csvs)} scalar CSVs ({bad_csv} bad), "
                 f"{len(jpgs)} JPGs ({bad_jpg} bad)")
    for manifest_name in (
        "spectral_manifest.json",
        "profilometer_manifest.json",
        "images_manifest.json",
    ):
        path = out_dir / manifest_name
        lines.append(
            f"  {manifest_name}: "
            f"{'OK' if path.exists() and path.stat().st_size > 0 else 'MISSING'}"
        )
    if WARNINGS:
        lines.append(f"warnings ({len(WARNINGS)}):")
        for step, detail in WARNINGS:
            lines.append(f"  - {step}: {detail}")
    else:
        lines.append("warnings: none")
    if FAILURES:
        lines.append(f"failures ({len(FAILURES)}):")
        for step, detail in FAILURES:
            lines.append(f"  - {step}: {detail}")
    else:
        lines.append("failures: none")

    report = "\n".join(lines) + "\n"
    (out_dir / "download-report.txt").write_text(report, encoding="utf-8")
    print(report)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
