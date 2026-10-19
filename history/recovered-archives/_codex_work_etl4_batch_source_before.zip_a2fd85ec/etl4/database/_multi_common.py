"""Read the explicit source scope and prepared results for multiple datasets."""

import importlib.util
from _db_common import CODE, ETL
from _db_files import inside, read, sha
from _settings import settings

MULTI_HOLES = ("12CADD001", "14KDD001", "15EIS001")


PROCESSING = CODE.parent / "processing"
SERVICE = "https://geossdi.dmp.wa.gov.au/NVCLDataServices/"


def require(ok, message):
    if not ok:
        raise ValueError(message)


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def raw_metadata(hole):
    require(hole in MULTI_HOLES, "Hole outside approved multi-dataset scope")
    from processing._etl_common import METADATA

    return {n: read(ETL / hole / n) for n in METADATA}


def audit():
    return read(settings.multi_work_dir / "31_source_audit.json")


def prepared():
    summary = read(settings.multi_work_dir / "32_prepared.json")
    require(summary["status"] == "passed", "Dataset preparation incomplete")
    result = []
    for u in summary["datasets"]:
        folder = inside(ETL, ETL / u["prepared_directory"])
        for rel, checksum in u["prepared_hashes"].items():
            require(sha(folder / rel) == checksum, f"Prepared artifact changed: {rel}")
        result.append(
            {
                "prepared_hashes": u["prepared_hashes"],
                "summary": u,
                "folder": folder,
                "metadata": read(folder / "3_normalized_metadata.json"),
                "alignment": read(folder / "4_alignment_report.json"),
                "storage": read(folder / "5_storage_report.json"),
            }
        )
    return result
