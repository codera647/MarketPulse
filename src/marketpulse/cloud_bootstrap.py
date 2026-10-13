"""Read-only cloud setup checks; never authenticate, deploy or enable a schedule."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path

SCHEMA = "marketpulse-cloud-bootstrap/1"
REQUIRED_CI_SECRETS = (
    "VERCEL_TOKEN",
    "MARKETPULSE_DATABASE_URL",
    "APCA_API_KEY_ID",
    "APCA_API_SECRET_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
)
REQUIRED_CI_VARIABLES = (
    "VERCEL_ORG_ID",
    "VERCEL_PROJECT_ID",
    "VERCEL_CLI_VERSION",
    "AWS_ENDPOINT_URL_S3",
)


def inspect_bootstrap(root: Path, environ: Mapping[str, str]) -> dict:
    """Only key presence is inspected. This is not a credential/network check.

    Do not load .env.local: Vercel's interactive login/OIDC credential is not a
    GitHub Actions deploy credential. Operators configure CI secrets directly.
    """
    config = json.loads((root / "deploy" / "cloud.json").read_text(encoding="utf-8"))
    if config.get("schema") != SCHEMA:
        raise ValueError("unsupported bootstrap configuration schema")
    vercel = config["vercel"]
    neon = config["neon"]
    operations = config["operations"]
    if not isinstance(neon["reported_branch_limit_bytes"], int) or (
        neon["reported_branch_limit_bytes"] <= 0
    ):
        raise ValueError("invalid provider-reported storage limit")
    if operations != {
        "prediction_cutoff_timezone": "America/New_York",
        "prediction_cutoff_local": "09:00",
        "retraining_cycle": "weekly_batch",
        "cloud_data_permissions_confirmed": True,
        "schedules_enabled": False,
        "model_auto_promotion_enabled": False,
        "broker_orders_enabled": False,
    }:
        raise ValueError("bootstrap policy differs; this checker cannot authorize operations")
    link_path = root / ".vercel" / "project.json"
    if link_path.exists():
        link = json.loads(link_path.read_text(encoding="utf-8"))
        link_matches = (
            link.get("orgId") == vercel["org_id"]
            and link.get("projectId") == vercel["project_id"]
            and link.get("projectName") == vercel["project_name"]
        )
    else:
        link_matches = False
    required = REQUIRED_CI_SECRETS + REQUIRED_CI_VARIABLES
    missing = [key for key in required if not environ.get(key, "").strip()]
    expected_variables = {
        "VERCEL_ORG_ID": vercel["org_id"],
        "VERCEL_PROJECT_ID": vercel["project_id"],
        "VERCEL_CLI_VERSION": vercel["cli_version"],
    }
    mismatched = [
        key for key, expected in expected_variables.items()
        if key not in missing and environ[key] != expected
    ]
    return {
        "schema": SCHEMA,
        "status": "BLOCKED" if missing or mismatched or not link_matches else "KEYS_PRESENT",
        "linked_project_matches": link_matches,
        "required_ci_key_count": len(required),
        "present_ci_key_count": len(required) - len(missing),
        "missing_ci_key_names": missing,
        "mismatched_ci_variable_names": mismatched,
        "reported_database_limit_bytes": neon["reported_branch_limit_bytes"],
        "credentials_validated": False,
        "migration_verified": False,
        "dashboard_deployed": False,
        "schedules_enabled": False,
        "note": "Key presence only. Live credentials, schema, privacy and worker checks remain.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    arguments = parser.parse_args(argv)
    try:
        report = inspect_bootstrap(arguments.root, os.environ)
    except (OSError, ValueError, KeyError, TypeError):
        # JSON/parser exception messages can contain secret file content.
        print("Cloud bootstrap inspection failed; check configuration and project link.")
        return 2
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "KEYS_PRESENT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
