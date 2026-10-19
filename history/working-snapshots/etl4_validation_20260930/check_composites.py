"""Check read-only display-composition validation within a rolled-back test-database transaction."""

import json
from pathlib import Path
import sys

AUDIT = Path(__file__).resolve().parent
ETL = AUDIT.parents[1] / "etl4"
sys.path[:0] = [str(ETL / "database"), str(ETL)]
from _settings import settings
from _db_common import connection
from _multi_db import install_composites, verify_composites

selection = json.loads((AUDIT / "selection.json").read_text(encoding="utf-8"))
settings.work_dir = Path(selection["work_dir"])
settings.dbname = selection["database"]
assert settings.dbname == "etl4_validation_check_20260930"
checks = []
with connection() as conn:
    assert conn.execute("SELECT current_database() n").fetchone()["n"] == settings.dbname
    release = str(conn.execute("SELECT release_id FROM core.active_release WHERE singleton").fetchone()["release_id"])
    before = conn.execute("SELECT count(*) n FROM core.borehole_composite").fetchone()["n"]
    assert before == 0, 'This case requires a new test database without display compositions'
    with conn.transaction(force_rollback=True):
        groups = install_composites(conn, release, {})
        assert len(groups) == 1
        assert verify_composites(conn, release, {}) == groups
        checks.append('Complete composition passed')
        composite_id = groups[0]["composite"]["id"]
        conn.execute("DELETE FROM core.borehole_composite_part WHERE composite_id=%s", (composite_id,))
        try:
            verify_composites(conn, release, {})
        except ValueError as error:
            assert "parts differ" in str(error)
            checks.append('Missing interval rejected')
        else:
            raise AssertionError('Validation did not reject the missing interval')
        assert conn.execute("SELECT count(*) n FROM core.borehole_composite_part WHERE composite_id=%s", (composite_id,)).fetchone()["n"] == 0
        conn.execute("DELETE FROM core.borehole_composite WHERE id=%s", (composite_id,))
        try:
            verify_composites(conn, release, {})
        except ValueError as error:
            assert "Missing composite" in str(error)
            checks.append('Missing composition rejected without creating a replacement')
        else:
            raise AssertionError('Validation did not reject the missing composition')
        assert conn.execute("SELECT count(*) n FROM core.borehole_composite").fetchone()["n"] == 0
    assert conn.execute("SELECT count(*) n FROM core.borehole_composite").fetchone()["n"] == before
    assert conn.execute("SELECT count(*) n FROM core.borehole_composite_part").fetchone()["n"] == 0
result = {"status": "passed", "database": settings.dbname, "checks": checks, "forced_rollback": True}
(AUDIT / "composite_checks.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(result, ensure_ascii=False))
