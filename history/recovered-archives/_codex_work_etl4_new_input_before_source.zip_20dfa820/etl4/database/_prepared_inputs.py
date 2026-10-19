"""Read the selected preparation manifest and check its file references."""

from _db_files import inside, read, sha
from _settings import BASE_HOLES, settings

ALLOWED = BASE_HOLES


def load_lock():
    lock = read(settings.reports_dir / "7_input_lock.json")
    if not lock["holes"] or not set(lock["holes"]) <= set(ALLOWED):
        raise ValueError("Input scope changed")
    return lock


def prepared_holes(holes=None):
    lock = load_lock()
    summary = lock["summary"]
    selected = holes or lock["holes"]
    if not set(selected) <= set(ALLOWED):
        raise ValueError("Hole outside approved scope")
    if not set(selected) <= set(lock["holes"]):
        raise ValueError("Selected holes are absent from this input manifest")
    result = []
    for h in summary["holes"]:
        if h["hole_id"] not in selected:
            continue
        folder = inside(settings.prepared_dir, settings.prepared_dir / h["directory"])
        for relative, expected in lock["prepared_hashes"][h["hole_id"]].items():
            if sha(inside(folder, folder / relative)) != expected:
                raise ValueError(f'Prepared input changed: {h["hole_id"]}/{relative}')
        result.append(
            {
                "prepared_hashes": lock["prepared_hashes"][h["hole_id"]],
                "summary": h,
                "folder": folder,
                "metadata": read(folder / "3_normalized_metadata.json"),
                "alignment": read(folder / "4_alignment_report.json"),
                "storage": read(folder / "5_storage_report.json"),
            }
        )
    return result
