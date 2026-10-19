"""Generate cleanup candidates for three work directories after receiving both actual receipts; never delete files."""
import importlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
ETL = ROOT / "etl4"
sys.path[:0] = [str(ETL / "database"), str(ETL)]
from _batch_files import write_json

cleanup = importlib.import_module("41_cleanup_batch")
EXPORTS = ETL / "single_final_check_20260930/database/exports"
EXPORT = EXPORTS / "8039f5a6c2c5711141bb201eaa1fb96636924d23c48faddd66edb782253519cd"
reports = []
files = {}
for name in ("refactor_work", "new_input_check", "structure_input_20260930"):
    result = cleanup.cleanup_batch(EXPORT, EXPORTS, ETL / name, apply=False)
    write_json(HERE / ("cleanup_preview_" + name + ".json"), result)
    reports.append({"work_root": str(ETL / name), "status": result["status"],
                    "candidate_count": len(result["candidates"]), "candidate_bytes": result["candidate_bytes"],
                    "kept_count": len(result["kept"]), "blockers": result["blockers"], "deleted_count": len(result["deleted"])})
    for row in result["candidates"]:
        files[row["path"]] = row
blocked = any(row["status"] != "preview" or row["blockers"] for row in reports)
index = {"status": "blocked" if blocked else "preview", "reports": reports, "candidates": len(files),
         "candidate_bytes": sum(row["byte_size"] for row in files.values()), "deleted_count": 0,
         "blocker_count": sum(len(row["blockers"]) for row in reports),
         "raw_included": False, "requires_user_review_before_cleanup": True,
         "reference_scope": str(EXPORTS), "legacy_local_references_checked": False}
write_json(HERE / "cleanup_preview_index.json", index)
(HERE / "cleanup_file_list.txt").write_text("bytes\tpath\n" + "".join(
    f"{row['byte_size']}\t{row['path']}\n" for row in sorted(files.values(), key=lambda item: item["path"])), encoding="utf-8-sig")
summary = ['# Cleanup Preview After the Twelve-Hole Delivery', "", 'This run listed candidates and deleted zero files. Raw data, acceptance evidence, reports, exports, databases and backups remain.', "",
           'Summary: blocked; the candidate list must not be used for deletion.' if blocked else 'The preview is complete; the candidate list still requires review and is not approval to delete.', "",
           '| Workspace | Status | Blockers | Candidate files | Bytes |', "|---|---|---:|---:|---:|"]
summary.extend(f"| `{Path(row['work_root']).name}` | {row['status']} | {len(row['blockers'])} | {row['candidate_count']:,} | {row['candidate_bytes']:,} |" for row in reports)
if blocked:
    summary.extend(["", 'Blockers: ', ""])
    for row in reports:
        if row["blockers"]:
            summary.extend(f"- `{Path(row['work_root']).name}`：{reason}" for reason in row["blockers"])
        elif row["status"] != "preview":
            summary.append(f"- `{Path(row['work_root']).name}`: report status is  {row['status']}, normal preview did not complete.")
summary.extend(["", f"Listed total:  {len(files):,}  candidate files, {index['candidate_bytes']:,}  bytes ({index['candidate_bytes']/1024**3:.3f}  GiB); this is not confirmed reclaimable space.", "",
    'See [cleanup_file_list.txt](cleanup_file_list.txt) for the complete list. Per-workspace JSON previews retain SHA256, file identity, retention reasons and blockers.',
    "", f"Reference checks cover only new-format batches registered under `{EXPORTS}`. Checks exclude legacy database asset_location records, older media releases and unregistered preparation directories, so protection of all legacy local references is not established.",
    "", 'This run only listed candidates. Before deletion, decide which old local references must remain valid and register other retained batches. Stop concurrent processing and export during cleanup.',
    "", 'Deleting these outputs would make dependent local database file reads unavailable. Delivered cloud objects remain.'])
(HERE / "CLEANUP_PREVIEW.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
print(json.dumps(index, ensure_ascii=False), flush=True)
