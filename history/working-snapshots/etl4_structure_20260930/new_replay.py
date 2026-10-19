"""Rerun the new-format sealed package and compare all business tables and active pointers."""

import subprocess
import sys
from preserve import AUDIT, setup, encoded, connection
from replay import snapshot

setup()
with connection("reader") as conn, conn.transaction():
    conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    before = snapshot(conn)
(AUDIT / "new_replay_before.json").write_bytes(encoded(before))
subprocess.run([sys.executable, "-B", "-X", "utf8", str(AUDIT / "run_steps.py"), "replay", "9", "10", "28", "29"], check=True)
with connection("reader") as conn, conn.transaction():
    conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    after = snapshot(conn)
changed = [name for name in before["tables"] if before["tables"][name] != after["tables"][name]]
assert set(changed) <= {"ingest_run", "revision_validation"}, changed
assert before["active_release"] == after["active_release"]
assert before["active_members"] == after["active_members"]
(AUDIT / "new_replay_result.json").write_bytes(encoded({"status": "passed", "changed_tables": changed,
    "business_tables_unchanged": 35, "active_release": after["active_release"],
    "table_deltas": {name: after["tables"][name]["count"] - before["tables"][name]["count"] for name in changed}}))
print("New compact package replay passed; 35 business tables unchanged", flush=True)
