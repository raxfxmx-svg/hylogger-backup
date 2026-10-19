"""Compare manifests, crops and web reads before and after refactoring using existing data read-only."""

from collections import Counter
import importlib
import importlib.util
from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

AUDIT = Path(__file__).resolve().parent
ETL = AUDIT.parents[1] / "etl4"
sys.path[:0] = [str(ETL / "database"), str(ETL)]
from _db_files import read, write, encoded
from _settings import settings
from _media_common import stage
from _media_manifest import pack_document, unpack_document
from _db_common import connection
from _media_import import media_identity
import _media_reader as current_reader


def baseline(name):
    spec = importlib.util.spec_from_file_location("baseline_" + name, AUDIT / "baseline_code" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CountConnection:
    def __init__(self, conn):
        self.conn = conn
        self.count = 0
        self.log_rows = 0

    def execute(self, query, parameters=None):
        self.count += 1
        cursor = self.conn.execute(query, parameters)
        if "SELECT l.*,b.status AS binding_status" in str(query):
            self.log_rows += cursor.rowcount
        return cursor


result = {}
settings.work_dir = ETL / "refactor_work"
settings.dbname = "etl4_refactor_check"
sizes = []
for number in range(20, 28):
    path = settings.multi_media_dir / f"{number}.json"
    document = read(path)
    packed = pack_document(document)
    assert unpack_document(packed) == document
    sizes.append({"step": number, "before_bytes": path.stat().st_size, "after_bytes": len(encoded(packed))})
    print("Manifest roundtrip", number, sizes[-1], flush=True)
result["multi_manifest_roundtrips"] = sizes
units = stage(20, settings.multi_media_dir)["datasets"]
arrays = stage(22, settings.multi_media_dir)["arrays"]
document = stage(27, settings.multi_media_dir)
restored = unpack_document(pack_document(document))
for unit in units:
    selected = [a for a in arrays if a["dataset_id"] == unit["dataset_id"]]
    old = [r for r in document["rows"] if r["dataset_id"] == unit["dataset_id"]]
    new = [r for r in restored["rows"] if r["dataset_id"] == unit["dataset_id"]]
    assert media_identity(unit, selected, old) == media_identity(unit, selected, new)
result["identical_multi_dataset_identities"] = len(units)
del document, restored, packed

import _media_common as mc
old_multi = baseline("33_prepare_multi_dataset_media")
new_multi = importlib.import_module("33_prepare_multi_dataset_media")
old_frames, old_rows, old_templates = old_multi.detect_rows(units, mc)
new_frames, new_rows, new_templates = new_multi.detect_rows(units, mc)
assert (old_frames, old_rows, old_templates) == (new_frames, new_rows, new_templates)
assert old_multi.bind_rows(old_rows, units, mc) == new_multi.bind_rows(new_rows, units, mc)
result["multi_image_algorithms"] = {"frames": len(new_frames), "rows": len(new_rows), "identical": True}
print("Multi image algorithms", result["multi_image_algorithms"], flush=True)

settings.work_dir = ETL / "new_input_check/random_09THD028"
source = stage(26)
old_crop = baseline("27_build_image_row_assets")
new_crop = importlib.import_module("27_build_image_row_assets")
with tempfile.TemporaryDirectory(dir=AUDIT, prefix="crop_compare_") as temporary:
    folder = Path(temporary)
    captured = []
    with patch.object(old_crop, "stage", return_value=source), patch.object(old_crop, "save_stage", side_effect=lambda n, v, **kw: captured.append(v)), patch.object(old_crop, "decode", wraps=old_crop.decode) as old_decodes:
        start = time.perf_counter()
        old_crop.main(folder / "old")
        old_seconds = time.perf_counter() - start
    with patch.object(new_crop, "decode", wraps=new_crop.decode) as new_decodes:
        start = time.perf_counter()
        new_rows = new_crop.build_crops(source["rows"], folder / "new")
        new_seconds = time.perf_counter() - start
    assert captured[0]["rows"] == new_rows
    for row in new_rows:
        assert (folder / "old" / row["crop_work_path"]).read_bytes() == (folder / "new" / row["crop_work_path"]).read_bytes()
    result["crop_comparison"] = {"rows": len(new_rows), "identical_files": True,
        "old_source_decodes": old_decodes.call_count - len(new_rows), "new_source_decodes": new_decodes.call_count - len(new_rows),
        "old_seconds": old_seconds, "new_seconds": new_seconds}
print("Crop comparison", result["crop_comparison"], flush=True)

old_reader = baseline("_media_reader")
readings = []
with connection("reader") as conn, conn.transaction():
    conn.execute("SET TRANSACTION READ ONLY")
    release = conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()["release_id"]
    members = conn.execute("""SELECT rd.*,a.id axis_id,a.sample_count,b.source_hole_id FROM core.release_dataset rd
        JOIN core.sample_axis a ON a.dataset_revision_id=rd.dataset_revision_id
        JOIN core.dataset d ON d.id=rd.dataset_id JOIN core.borehole b ON b.id=d.borehole_id
        WHERE rd.release_id=%s ORDER BY b.source_hole_id,rd.dataset_id""", (release,)).fetchall()
    for member in members:
        logs = conn.execute("SELECT id,log_kind,availability_status FROM core.scan_log WHERE dataset_revision_id=%s AND log_kind IN ('scalar','spectral','profile') ORDER BY log_kind,id", (member["dataset_revision_id"],)).fetchall()
        selected = []
        for kind in ("scalar", "spectral", "profile"):
            selected += [str(l["id"]) for l in logs if l["log_kind"] == kind and l["availability_status"] == "payload_present"][:2]
        selected += [str(l["id"]) for l in logs if l["availability_status"] != "payload_present"][:1]
        cases = [(0, selected), (member["sample_count"] // 2, selected), (member["sample_count"]-1, selected)]
        if member["source_hole_id"] == "09THD028": cases += [(0, []), (0, None), (0, selected + selected)]
        for sample, ids in cases:
            before, after = CountConnection(conn), CountConnection(conn)
            args = (release, member["dataset_id"], member["axis_id"], sample, ids)
            old = old_reader.read_sample(before, *args)
            new = current_reader.read_sample(after, *args)
            assert encoded(old) == encoded(new), (member["source_hole_id"], sample, ids)
            readings.append({"hole": member["source_hole_id"], "dataset": member["dataset_id"], "sample": sample,
                "result_count": len(new["results"]), "before_sql": before.count, "after_sql": after.count,
                "before_catalog_rows": before.log_rows, "after_catalog_rows": after.log_rows,
                "statuses": dict(Counter(r["status"] for r in new["results"]))})
        for ids in (["not-a-uuid"], [str(members[-1]["dataset_revision_id"]) ]):
            for reader in (old_reader, current_reader):
                try: reader.read_sample(conn, release, member["dataset_id"], member["axis_id"], 0, ids)
                except ValueError: pass
                else: raise AssertionError("Unknown/foreign log accepted")
    result["reader_comparisons"] = readings
    result["release"] = release
result["status"] = "passed"
(AUDIT / "comparisons.json").write_bytes(encoded(result))
print("All comparisons passed; reader selections:", len(readings), flush=True)
