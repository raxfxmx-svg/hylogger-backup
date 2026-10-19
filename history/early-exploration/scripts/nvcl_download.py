#!/usr/bin/env python
"""Download a borehole's data from the NVCL online service.

Usage:
    python scripts/nvcl_download.py <nvcl_id> [--provider wa] [--out-root data] [--cache data/.nvcl_cache]

Outputs land in <out-root>/raw/<nvcl_id>/:
    borehole.json            WFS feature fields for the hole
    datasets.json            dataset list
    logs_scalar.json         scalar logs
    logs_image.json          image logs
    logs_spectral.json       spectral logs
    logs_profilometer.json   profilometer logs
    scalars/<log_id>_<name>.csv
    images/tray_<sample_no>.jpg
    tray_depths.json
    download-report.txt

Idempotent: existing non-empty files are skipped. Per-step failures are
recorded in the report; the exit code is non-zero if anything failed.
"""

import argparse
import concurrent.futures
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
    """Fix nvcl-kit 1.3.3's broken HTTP cache in svc_interface._get_response_str:
    text responses are written in 'wb' mode (TypeError) and cached reads return
    bytes instead of str. Patch: encode on write, decode on read for text calls.
    """
    import hashlib
    import os
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
                response = s.get(url, params=params)
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

CALL_TIMEOUT = 120  # seconds; nvcl_kit's own TIMEOUT is not enforced
SCALAR_LOG_TYPES = {"1", "2", "5", "6"}

# One executor with spare workers so a hung call never blocks later ones.
EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=8)

FAILURES = []  # list of (step, detail) strings


def call(desc, fn, timeout=CALL_TIMEOUT):
    """Run fn() with an outer timeout. Returns (ok, value_or_error)."""
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


def safe_name(name):
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", str(name)).strip("_")
    return s or "log"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser(description="Download NVCL borehole data")
    ap.add_argument("nvcl_id", help="NVCL hole identifier, e.g. 05GJD001")
    ap.add_argument("--provider", default="wa", help="NVCL provider (default: wa)")
    ap.add_argument("--out-root", default="data", help="output data root (default: data)")
    ap.add_argument("--cache", default="data/.nvcl_cache", help="HTTP cache dir")
    args = ap.parse_args()

    nvcl_id = args.nvcl_id
    out_dir = Path(args.out_root) / "raw" / nvcl_id
    scalars_dir = out_dir / "scalars"
    images_dir = out_dir / "images"
    for d in (out_dir, scalars_dir, images_dir):
        d.mkdir(parents=True, exist_ok=True)
    cache_path = Path(args.cache)
    cache_path.mkdir(parents=True, exist_ok=True)

    print(f"NVCL download: hole={nvcl_id} provider={args.provider} out={out_dir}")

    # --- reader setup -------------------------------------------------------
    # nvcl-kit concatenates CACHE_PATH + filename, so it needs a trailing sep
    param_obj = param_builder(args.provider, cache_path=str(cache_path) + os.sep)
    if param_obj is None:
        print(f"ERROR: param_builder failed for provider '{args.provider}'")
        return 2
    ok, reader = call("init NVCLReader", lambda: NVCLReader(param_obj))
    if not ok:
        fail("init NVCLReader", reader)
        return finish(out_dir, nvcl_id, args, reader=None)
    if getattr(reader, "wfs_error", False):
        print("WARNING: reader reports wfs_error (borehole list may be incomplete)")

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
            # fall back: scan the full feature list for a matching nvcl_id
            ok2, all_feats = call("get_feature_list", reader.get_feature_list)
            if ok2:
                feats = [f for f in all_feats if getattr(f, "nvcl_id", None) == nvcl_id]
            else:
                fail("get_feature_list", all_feats)
        if feats:
            write_json_if_missing(bh_path, ns_to_dict(feats[0]))
            print(f"borehole.json: matched feature nvcl_id={getattr(feats[0], 'nvcl_id', '?')}")
        else:
            fail("borehole.json", f"no WFS feature found for '{nvcl_id}'")

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

    # --- log lists ----------------------------------------------------------
    log_specs = [
        ("logs_scalar.json", lambda: reader.get_logs_data(nvcl_id)),
        ("logs_image.json", lambda: reader.get_imagelog_data(nvcl_id)),
        ("logs_spectral.json", lambda: reader.get_spectrallog_data(nvcl_id)),
        ("logs_profilometer.json", lambda: reader.get_profilometer_data(nvcl_id)),
    ]
    scalar_logs = []
    for fname, fn in log_specs:
        path = out_dir / fname
        if path.exists() and path.stat().st_size > 0:
            print(f"skip (exists): {fname}")
            if fname == "logs_scalar.json":
                scalar_logs = read_json(path)
            continue
        ok, res = call(fname, fn)
        if ok:
            data = [ns_to_dict(x) for x in res]
            write_json_if_missing(path, data)
            if fname == "logs_scalar.json":
                scalar_logs = data
            print(f"{fname}: {len(data)} records")
        else:
            fail(fname, res)

    # --- scalar CSVs --------------------------------------------------------
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
    print(f"scalar CSVs: ok={csv_ok} failed={csv_fail}")

    # --- tray images --------------------------------------------------------
    # collect tray thumbnail logs per dataset
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
    print(f"tray thumbnail logs: {len(tray_logs)}")

    # tray depths per log
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
        print(f"tray_depths.json: {sum(len(v) for v in depths_all.values())} trays")

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
            ok, res = call(
                f"image {log_id}#{sno}",
                lambda lid=log_id, s=sno, d=ds_id: reader.get_image(lid, s, dataset_id=d),
            )
            if not (ok and isinstance(res, (bytes, bytearray)) and len(res) > 0):
                # Some providers (e.g. WA) do not implement getImage.html (HTTP 404);
                # fall back to the legacy Display_Tray_Thumb.html thumbnail service.
                ok2, res2 = call(
                    f"tray_thumb {log_id}#{sno}",
                    lambda lid=log_id, s=sno: reader.get_tray_thumb_jpg(lid, s),
                )
                if ok2 and isinstance(res2, (bytes, bytearray)) and len(res2) > 0:
                    ok, res = True, res2
            if ok and isinstance(res, (bytes, bytearray)) and len(res) > 0:
                img_path.write_bytes(bytes(res))
                img_ok += 1
            else:
                img_fail += 1
                fail(f"image {log_id}#{sno}", res if not ok else "empty response")
    print(f"tray images: ok={img_ok} failed={img_fail}")

    return finish(out_dir, nvcl_id, args, reader=reader)


def finish(out_dir, nvcl_id, args, reader):
    """Self-check and write download-report.txt; return exit code."""
    lines = []
    lines.append(f"NVCL download report")
    lines.append(f"hole_id      : {nvcl_id}")
    lines.append(f"provider     : {args.provider}")
    lines.append(f"output dir   : {out_dir}")
    lines.append(f"generated at : {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")

    # JSON record counts
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

    # scalar CSV check
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

    # JPG check via PIL
    jpgs = sorted((out_dir / "images").glob("*.jpg"))
    lines.append(f"tray images: {len(jpgs)} files")
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
        lines.append("  (PIL not available; skipped image validation)")
    lines.append("")

    lines.append(f"summary: {len(csvs)} scalar CSVs ({bad_csv} bad), "
                 f"{len(jpgs)} JPGs ({bad_jpg} bad)")
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
