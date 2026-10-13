from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


@pytest.fixture
def scanner(tmp_path, monkeypatch):
    path = Path(__file__).parents[1] / "scripts" / "check_staged_secrets.py"
    spec = importlib.util.spec_from_file_location("staged_scanner", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def staged(payload):
        def git(*args):
            if args == ("rev-parse", "--show-toplevel"):
                return str(tmp_path).encode()
            if args[0] == "diff":
                return b"example.txt\x00"
            if args[0] == "ls-files":
                return b"tracked"
            if args == ("show", ":example.txt"):
                return payload.encode()
            raise AssertionError("unexpected git operation")

        monkeypatch.setattr(module, "git", git)
        return module

    return tmp_path, staged


@pytest.mark.parametrize("filename", [".env", ".env.local", ".env.cloud.local", ".evn"])
def test_all_private_dotenv_credentials_are_scanned(scanner, capsys, filename):
    root, staged = scanner
    fake = "not-an-actual-credential"
    (root / filename).write_text("API_SECRET=" + fake, encoding="utf-8")
    assert staged("accidental value " + fake).main() == 1
    assert fake not in capsys.readouterr().out


def test_database_url_password_fragment_is_scanned(scanner, capsys):
    root, staged = scanner
    fake = "not-an-actual-password"
    (root / ".env.cloud.local").write_text(
        "MARKETPULSE_DATABASE_URL=postgresql://worker:" + fake + "@example.test/app",
        encoding="utf-8",
    )
    assert staged("accidental password fragment " + fake).main() == 1
    assert fake not in capsys.readouterr().out


def test_public_target_metadata_is_not_a_secret(scanner):
    root, staged = scanner
    (root / ".env.cloud.local").write_text(
        "AWS_ENDPOINT_URL_S3=https://example.test", encoding="utf-8"
    )
    assert staged("https://example.test").main() == 0
