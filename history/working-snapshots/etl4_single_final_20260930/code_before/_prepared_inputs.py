"""Read the selected preparation manifest and check its file references."""

from _db_files import inside, read, sha
from _settings import BASE_HOLES, settings, validate_hole_names

ALLOWED = BASE_HOLES


def summary_holes(summary):
    """Use the selected verification manifest as the scope and require one result for each hole ID."""
    holes = validate_hole_names(summary["active_holes"])
    records = validate_hole_names([h["hole_id"] for h in summary["holes"]])
    if set(holes) != set(records):
        raise ValueError("Prepared summary membership differs")
    return holes


def load_lock():
    lock = read(settings.reports_dir / "7_input_lock.json")
    holes = validate_hole_names(lock["holes"])
    if set(holes) != set(summary_holes(lock["summary"])):
        raise ValueError("Input scope changed")
    if set(lock["prepared_hashes"]) != set(holes) or set(lock["raw_hashes"]) != set(holes):
        raise ValueError("Input file inventories do not match selected holes")
    return lock


def prepared_holes(holes=None):
    lock = load_lock()
    summary = lock["summary"]
    selected = validate_hole_names(lock["holes"] if holes is None else holes)
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
