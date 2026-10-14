"""Checksum-bound migrations on the existing review/production Neon targets."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from dotenv import dotenv_values

HOSTS = {
    "review": "ep-rough-wildflower-b703qt49.c-13.us-east-1.aws.neon.tech",
    "production": "ep-lively-wind-b70bl7t0.c-13.us-east-1.aws.neon.tech",
}


def direct_uri(value: str, target: str) -> str:
    uri = urlsplit(value)
    expected = HOSTS[target]
    if (
        uri.scheme != "postgresql" or uri.username != "marketpulse_owner"
        or not uri.password or uri.path != "/marketpulse" or uri.fragment
        or uri.port not in {None, 5432}
        or uri.hostname not in {expected, expected.replace(".c-13.", "-pooler.c-13.")}
        or parse_qs(uri.query).get("sslmode") != ["require"]
    ):
        raise ValueError("migration target/owner/TLS mismatch")
    # Application URLs remain pooled; only this migration uses the direct endpoint.
    return value.replace(uri.hostname, expected, 1)


def migrate(value: str, target: str, root: Path) -> dict:
    import psycopg

    paths = sorted(p for p in (root / "deploy/migrations").glob("*.sql")
                   if p.name > "0000_application_roles.sql")
    results = []
    with psycopg.connect(direct_uri(value, target), connect_timeout=10) as db:
        db.execute("SET LOCAL statement_timeout='30s'")
        db.execute("SELECT pg_advisory_xact_lock(491081301)")
        for path in paths:
            sql = path.read_text(encoding="utf-8")
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            exists = db.execute("SELECT to_regclass('marketpulse.schema_migrations')").fetchone()[0]
            prior = db.execute(
                "SELECT sha256 FROM marketpulse.schema_migrations WHERE name=%s", (path.name,)
            ).fetchone() if exists else None
            if prior:
                if prior[0] != checksum:
                    raise ValueError("applied migration checksum differs; add a new migration")
            else:
                db.execute(sql, prepare=False)
                db.execute(
                    "INSERT INTO marketpulse.schema_migrations(name,sha256) VALUES(%s,%s)",
                    (path.name, checksum),
                )
            results.append({"migration": path.name, "sha256": checksum,
                            "already_applied": bool(prior)})
    return {"status": "PASS", "target": target, "migrations": results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=HOSTS)
    parser.add_argument("--env-file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        values = dotenv_values(args.env_file, interpolate=False)
        report = migrate(values["MARKETPULSE_MIGRATION_DATABASE_URL"], args.target, Path.cwd())
    except Exception as error:
        print(json.dumps({"status": "FAIL", "error_type": type(error).__name__}))
        return 1
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
