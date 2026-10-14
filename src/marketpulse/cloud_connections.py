"""Bounded credential checks for new private cloud resources, without writes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from dotenv import dotenv_values

STORAGE_HOST = "br-cool-fire-b7c9ge4z.storage.c-13.us-east-1.aws.neon.tech"
DATABASE_HOST = "ep-lively-wind-b70bl7t0-pooler.c-13.us-east-1.aws.neon.tech"


def database_uri(value: str, role: str) -> str:
    """Reject accidental connections to other apps and privileged role URLs."""
    uri = urlsplit(value)
    if (
        uri.scheme != "postgresql"
        or uri.hostname != DATABASE_HOST
        or uri.username != role
        or not uri.password
        or uri.path != "/marketpulse"
        or uri.port not in {None, 5432}
        or uri.fragment
        or parse_qs(uri.query).get("sslmode") != ["require"]
    ):
        raise ValueError("cloud database target/role/TLS validation failed")
    return value


def s3_client(values):
    import boto3
    from botocore.config import Config

    uri = urlsplit(values["AWS_ENDPOINT_URL_S3"])
    if (
        uri.scheme != "https" or uri.hostname != STORAGE_HOST or uri.username
        or uri.password or uri.query or uri.fragment or uri.path not in {"", "/"}
        or uri.port not in {None, 443}
    ):
        raise ValueError("private storage target validation failed")
    return boto3.client(
        "s3", endpoint_url=values["AWS_ENDPOINT_URL_S3"], region_name="us-east-1",
        aws_access_key_id=values["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=values["AWS_SECRET_ACCESS_KEY"],
        config=Config(
            signature_version="s3v4", s3={"addressing_style": "path"},
            connect_timeout=10, read_timeout=20,
            retries={"total_max_attempts": 2, "mode": "standard"},
        ),
    )


def inspect_connections(values, *, worker_only=False) -> dict:
    import psycopg

    results = {}
    roles = (
        ("MARKETPULSE_DATABASE_URL", "marketpulse_worker"),
        ("MARKETPULSE_DASHBOARD_DATABASE_URL", "marketpulse_reader"),
    )
    for key, role in roles[:1] if worker_only else roles:
        uri = database_uri(values[key], role)
        with psycopg.connect(uri, connect_timeout=10, autocommit=True) as db:
            record = db.execute(
                "SELECT current_database(), current_user, rolcreatedb, rolcreaterole, "
                "rolbypassrls, rolsuper, "
                "EXISTS(SELECT 1 FROM pg_auth_members WHERE member=pg_roles.oid) "
                "FROM pg_roles WHERE rolname=current_user"
            ).fetchone()
            if record != ("marketpulse", role, False, False, False, False, False):
                raise ValueError("application database role is not restricted")
            if role == "marketpulse_reader" and (
                db.execute("SHOW default_transaction_read_only").fetchone() != ("on",)
            ):
                raise ValueError("dashboard connection is not read-only by default")
        results[role] = "CONNECTED_RESTRICTED"
    storage = s3_client(values)
    # Reads only. No sample/model/raw data is uploaded by this check.
    response = storage.head_bucket(Bucket="research-artifacts")
    if response["ResponseMetadata"]["HTTPStatusCode"] != 200:
        raise ValueError("private artifact bucket access failed")
    acl = storage.get_bucket_acl(Bucket="research-artifacts")
    if any("URI" in item.get("Grantee", {}) for item in acl.get("Grants", [])):
        raise ValueError("artifact bucket contains a public ACL grant")
    results["private_artifact_bucket"] = "ACCESS_VERIFIED"
    return {"status": "PASS", "checks": results, "app_schema_checked": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=Path(".env.cloud.local"))
    arguments = parser.parse_args(argv)
    try:
        values = dotenv_values(arguments.env_file, interpolate=False)
        report = inspect_connections(values)
    except Exception as error:
        # Drivers and SDKs may include credentials, query text or response bodies.
        print(json.dumps({"status": "FAIL", "error_type": type(error).__name__,
                          "detail": "Cloud access check failed; secret details suppressed."}))
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
