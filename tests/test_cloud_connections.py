from __future__ import annotations

import pytest

from marketpulse.cloud_connections import DATABASE_HOST, database_uri, main


def uri(role="marketpulse_reader", host=DATABASE_HOST):
    return f"postgresql://{role}:not-a-real-password@{host}/marketpulse?sslmode=require"


def test_expected_restricted_database_target():
    assert database_uri(uri(), "marketpulse_reader") == uri()


@pytest.mark.parametrize("value", [
    uri(role="marketpulse_owner"),
    uri(host="an-unrelated-project.neon.tech"),
    uri().replace("sslmode=require", "sslmode=disable"),
    uri().replace("/marketpulse?", "/neondb?"),
    uri().replace("not-a-real-password", ""),
    uri() + "&sslmode=disable",
    uri() + "#not-an-allowed-fragment",
])
def test_wrong_privileged_or_insecure_target_is_rejected(value):
    with pytest.raises(ValueError, match="target/role/TLS"):
        database_uri(value, "marketpulse_reader")


def test_driver_errors_never_print_secret_values(monkeypatch, capsys, tmp_path):
    def fail(values):
        raise ValueError("private-test-value")

    monkeypatch.setattr("marketpulse.cloud_connections.inspect_connections", fail)
    assert main(["--env-file", str(tmp_path / "absent")]) == 1
    assert "private-test-value" not in capsys.readouterr().out
