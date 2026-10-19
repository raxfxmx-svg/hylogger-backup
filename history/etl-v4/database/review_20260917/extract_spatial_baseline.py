"""Offline evidence extraction only; never connects to PostgreSQL or AWS."""
from pathlib import Path
import hashlib
import json
import re
import struct
import subprocess

OUT = Path(__file__).resolve().parent
DB = OUT.parent
ETL = DB.parent
PG_RESTORE = Path(r"C:\Program Files\PostgreSQL\17\bin\pg_restore.exe")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def restore_text(dump, *args):
    proc = subprocess.run([str(PG_RESTORE), "--file=-", *args, str(dump)],
                          capture_output=True, check=True)
    return proc.stdout.decode("utf-8").replace("\r\n", "\n")


def parse_copy(text):
    tables, current, columns = {}, None, None
    for line in text.splitlines():
        if line.startswith("COPY core."):
            match = re.fullmatch(r"COPY core\.([a-z_]+) \((.+)\) FROM stdin;", line)
            if not match:
                raise ValueError("Unexpected COPY header")
            current, fields = match.groups()
            columns = fields.split(", ")
            tables[current] = []
        elif current and line == r"\.":
            current = None
        elif current:
            values = line.split("\t")
            if len(values) != len(columns):
                raise ValueError("COPY column count mismatch")
            # Fields consumed below are UUIDs, numbers, plain identifiers and EWKB;
            # complex escaped text and JSON are deliberately not interpreted.
            tables[current].append(dict(zip(columns, [None if v == r"\N" else v for v in values])))
    return tables


def decode_point(hex_string):
    if hex_string is None:
        return None
    data = bytes.fromhex(hex_string)
    order = "<" if data[0] == 1 else ">"
    type_code, srid, x, y = struct.unpack(order + "IIdd", data[1:])
    if type_code != 0x20000001 or len(data) != 25:
        raise ValueError("Expected 2D Point EWKB with SRID")
    # Canonical little-endian encoding for exact SQL comparison on any host.
    canonical = struct.pack("<BIIdd", 1, type_code, srid, x, y).hex()
    return {"dump_ewkb_hex": hex_string.lower(), "ndr_ewkb_hex": canonical,
            "srid": srid, "x_longitude": x, "y_latitude": y, "dimensions": 2}


def main():
    pointer = json.loads((DB / "reports/latest_database_backup.json").read_text(encoding="utf-8"))
    dump = DB / pointer["backup_relative_path"]
    actual_hash = digest(dump)
    if actual_hash != pointer["backup_sha256"]:
        raise ValueError("Selected dump hash differs from backup pointer")
    schema = restore_text(dump, "--schema-only", "--schema=core", "--no-owner", "--no-acl")
    (OUT / "dump_core_schema.sql").write_text(schema, encoding="utf-8")
    names = ("borehole", "borehole_revision", "dataset_revision", "release_dataset")
    text = restore_text(dump, "--data-only", "--schema=core", *("--table=" + t for t in names))
    tables = parse_copy(text)
    holes = {r["id"]: r for r in tables["borehole"]}
    revisions = {r["id"]: r for r in tables["dataset_revision"]}
    all_collar_rows = []
    for row in tables["borehole_revision"]:
        all_collar_rows.append({"borehole_revision_id": row["id"],
                               "borehole_id": row["borehole_id"],
                               "hole_id": holes[row["borehole_id"]]["source_hole_id"],
                               "coordinate_basis": row["coordinate_basis"],
                               "horizontal_crs": row["horizontal_crs"],
                               "geometry": decode_point(row["collar_geom"])})
    by_id = {r["borehole_revision_id"]: r for r in all_collar_rows}
    current = []
    for member in tables["release_dataset"]:
        if member["release_id"] != pointer["release_id"]:
            continue
        revision = revisions[member["dataset_revision_id"]]
        collar = by_id[revision["borehole_revision_id"]]
        source_path = ETL / collar["hole_id"] / "borehole.json"
        source = json.loads(source_path.read_text(encoding="utf-8"))
        geom = collar["geometry"]
        current.append({**collar, "dataset_id": member["dataset_id"],
                        "dataset_revision_id": member["dataset_revision_id"],
                        "source_file": source_path.relative_to(ETL).as_posix(),
                        "source_file_sha256": digest(source_path),
                        "source_x": source["x"], "source_y": source["y"],
                        "dump_xy_exactly_match_source": geom is not None and
                        geom["x_longitude"] == source["x"] and geom["y_latitude"] == source["y"]})
    current.sort(key=lambda r: r["hole_id"])
    catalog_path = DB / "reports/schema_catalog.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    evidence = {"scope": "Offline extraction; no live restore or AWS query performed",
                "release_id": pointer["release_id"],
                "dump_relative_to_database": pointer["backup_relative_path"],
                "dump_sha256": actual_hash,
                "dump_core_schema_sha256": digest(OUT / "dump_core_schema.sql"),
                "schema_catalog_sha256": digest(catalog_path),
                "migration_sha256": {p.name: digest(p) for p in sorted((DB / "migrations").glob("*.sql"))},
                "geometry_columns": [r for r in catalog["columns"] if "geometry" in r["data_type"] or "geography" in r["data_type"]],
                "all_borehole_revision_geometries": sorted(all_collar_rows, key=lambda r: r["borehole_revision_id"]),
                "current_release_source_comparison": current}
    (OUT / "spatial_baseline.json").write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"all_collar_rows": len(all_collar_rows), "current_release": current}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
