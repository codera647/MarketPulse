from __future__ import annotations

import json
from pathlib import Path

import pytest

from marketpulse.cloud_bootstrap import (
    REQUIRED_CI_SECRETS,
    REQUIRED_CI_VARIABLES,
    inspect_bootstrap,
    main,
)


@pytest.fixture
def linked(tmp_path):
    config = json.loads(
        (Path(__file__).parents[1] / "deploy" / "cloud.json").read_text(encoding="utf-8")
    )
    (tmp_path / "deploy").mkdir()
    (tmp_path / "deploy" / "cloud.json").write_text(json.dumps(config), encoding="utf-8")
    (tmp_path / ".vercel").mkdir()
    (tmp_path / ".vercel" / "project.json").write_text(json.dumps({
        "orgId": config["vercel"]["org_id"],
        "projectId": config["vercel"]["project_id"],
        "projectName": config["vercel"]["project_name"],
    }), encoding="utf-8")
    return tmp_path, config


def configured(config):
    result = dict.fromkeys(REQUIRED_CI_SECRETS + REQUIRED_CI_VARIABLES, "private-test-value")
    result.update({
        "VERCEL_ORG_ID": config["vercel"]["org_id"],
        "VERCEL_PROJECT_ID": config["vercel"]["project_id"],
        "VERCEL_CLI_VERSION": config["vercel"]["cli_version"],
    })
    return result


def test_empty_environment_blocks_without_exposing_values(linked):
    root, _ = linked
    report = inspect_bootstrap(root, {})
    assert report["status"] == "BLOCKED"
    assert report["linked_project_matches"] is True
    assert report["present_ci_key_count"] == 0
    assert report["reported_database_limit_bytes"] == 512 * 1024 * 1024


def test_keys_present_does_not_claim_deployment_or_credential_validity(linked):
    root, config = linked
    report = inspect_bootstrap(root, configured(config))
    assert report["status"] == "KEYS_PRESENT"
    assert report["credentials_validated"] is False
    assert report["dashboard_deployed"] is False
    assert report["schedules_enabled"] is False
    assert "private-test-value" not in json.dumps(report)


@pytest.mark.parametrize("key", REQUIRED_CI_SECRETS + REQUIRED_CI_VARIABLES)
def test_each_missing_key_blocks(linked, key):
    root, config = linked
    values = configured(config)
    values[key] = "  "
    report = inspect_bootstrap(root, values)
    assert report["status"] == "BLOCKED"
    assert report["missing_ci_key_names"] == [key]


def test_wrong_project_blocks_even_with_all_keys(linked):
    root, config = linked
    values = configured(config)
    values["VERCEL_PROJECT_ID"] = "an-unrelated-project"
    report = inspect_bootstrap(root, values)
    assert report["status"] == "BLOCKED"
    assert report["mismatched_ci_variable_names"] == ["VERCEL_PROJECT_ID"]


def test_missing_local_link_blocks(linked):
    root, config = linked
    (root / ".vercel" / "project.json").unlink()
    assert inspect_bootstrap(root, configured(config))["status"] == "BLOCKED"


def test_policy_cannot_enable_training_or_orders(linked):
    root, config = linked
    config["operations"]["schedules_enabled"] = True
    (root / "deploy" / "cloud.json").write_text(json.dumps(config), encoding="utf-8")
    with pytest.raises(ValueError, match="cannot authorize"):
        inspect_bootstrap(root, configured(config))


def test_malformed_config_does_not_leak_content(linked, capsys):
    root, _ = linked
    (root / "deploy" / "cloud.json").write_text("private-test-value", encoding="utf-8")
    assert main(["--root", str(root)]) == 2
    assert "private-test-value" not in capsys.readouterr().out
