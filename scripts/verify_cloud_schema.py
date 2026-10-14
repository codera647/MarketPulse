"""Rollback-only integration tests on the existing Neon schema-review branch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import psycopg
from dotenv import dotenv_values

from marketpulse.cloud_migrate import direct_uri


def verify(uri):
    checks = 0
    with psycopg.connect(direct_uri(uri, "review"), connect_timeout=10) as db:
        try:
            with db.transaction(force_rollback=True):
                for view in ("dashboard_research", "dashboard_forward", "dashboard_jobs"):
                    assert db.execute("SELECT has_table_privilege('marketpulse_reader',%s,"
                                      "'SELECT')", (f"marketpulse.{view}",)).fetchone() == (True,)
                    checks += 1
                for table in ("jobs", "objects", "projections", "schema_migrations"):
                    assert db.execute("SELECT has_table_privilege('marketpulse_reader',%s,"
                                      "'SELECT')", (f"marketpulse.{table}",)).fetchone() == (False,)
                    checks += 1
        finally:
            db.rollback()
        with db.transaction(force_rollback=True):
            for statement in (
                "SELECT has_schema_privilege('marketpulse_worker','marketpulse','CREATE')",
                "SELECT has_table_privilege('marketpulse_worker','marketpulse.jobs','DELETE')",
                "SELECT has_column_privilege('marketpulse_worker',"
                "'marketpulse.projections','kind','UPDATE')",
                "SELECT has_column_privilege('marketpulse_worker',"
                "'marketpulse.jobs','owner','UPDATE')",
            ):
                assert db.execute(statement).fetchone() == (False,)
                checks += 1
            db.execute(
                "INSERT INTO marketpulse.jobs(job_key,kind,status,owner,lease_until) "
                "VALUES('rollback-only-integration','bootstrap','RUNNING',gen_random_uuid(),now())"
            )
            checks += 1
            with db.transaction(force_rollback=True):
                try:
                    db.execute("UPDATE marketpulse.jobs SET status='COMPLETE' "
                               "WHERE job_key='rollback-only-integration'")
                except psycopg.errors.CheckViolation:
                    checks += 1
                else:
                    raise AssertionError("completion without checkpoints was accepted")
    return {"status": "PASS", "target": "review", "checks": checks,
            "test_rows_retained": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env.cloud-review.local"))
    args = parser.parse_args()
    try:
        values = dotenv_values(args.env_file, interpolate=False)
        result = verify(values["MARKETPULSE_MIGRATION_DATABASE_URL"])
    except Exception as error:
        print(json.dumps({"status": "FAIL", "error_type": type(error).__name__}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
