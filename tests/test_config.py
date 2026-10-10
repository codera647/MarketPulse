from __future__ import annotations

import pytest
import requests

from marketpulse.alpaca import AlpacaClient, ProviderError
from marketpulse.config import load_alpaca_settings


def test_literal_dotenv_bom_and_mixed_case_endpoint(tmp_path):
    path = tmp_path / ".env"
    path.write_text('\ufeffAPCA_API_KEY_ID="local-key"\nAPCA_API_SECRET_KEY=literal$secret\n'
                    'APCA_API_EndPOINT=https://paper-api.alpaca.markets/v2\n', encoding="utf-8")
    settings = load_alpaca_settings(path, environ={})
    assert settings.secret == "literal$secret"
    assert settings.endpoint_role == "trading_endpoint_not_used"
    assert settings.data_url == "https://data.alpaca.markets"
    assert "local-key" not in repr(settings)
    assert "literal$secret" not in repr(settings.diagnostics())


def test_process_environment_overrides_file_without_mutating_environment(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text('APCA_API_KEY_ID=file\nAPCA_API_SECRET_KEY=file-secret\n', encoding="utf-8")
    monkeypatch.delenv("APCA_API_KEY_ID", raising=False)
    settings = load_alpaca_settings(path, environ={"APCA_API_KEY_ID": "process"})
    assert settings.key == "process" and settings.secret == "file-secret"
    import os
    assert "APCA_API_KEY_ID" not in os.environ


@pytest.mark.parametrize("endpoint", [
    "http://data.alpaca.markets", "https://evil.example",
    "https://data.alpaca.markets@evil.example", "https://data.alpaca.markets?token=sensitive",
    "https://data.alpaca.markets:443", "https://data.alpaca.markets/v2/stocks/bars",
])
def test_unapproved_endpoints_never_receive_keys(tmp_path, endpoint):
    with pytest.raises(ValueError) as captured:
        load_alpaca_settings(tmp_path / "missing", environ={})
    assert "sensitive" not in str(captured.value)
    with pytest.raises(ValueError) as captured:
        load_alpaca_settings(environ={"APCA_API_KEY_ID": "key", "APCA_API_SECRET_KEY": "secret",
                                     "APCA_API_ENDPOINT": endpoint})
    assert endpoint not in str(captured.value)
    with pytest.raises(ValueError):
        AlpacaClient("key", "secret", base_url=endpoint)


@pytest.mark.parametrize("text", [
    'APCA_API_KEY_ID="unterminated\n',
    'APCA_API_KEY_ID=one\napca_api_key_id=two\n',
    'APCA_API_KEY_ID=${SENSITIVE}\nAPCA_API_SECRET_KEY=secret\n',
])
def test_invalid_config_is_rejected_without_value_disclosure(tmp_path, text):
    path = tmp_path / ".env"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError) as captured:
        load_alpaca_settings(path, environ={})
    assert "unterminated" not in str(captured.value)
    assert "${SENSITIVE}" not in str(captured.value)


def test_missing_file_falls_back_to_process_only(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = load_alpaca_settings(environ={"APCA_API_KEY_ID": "key",
                                            "APCA_API_SECRET_KEY": "secret"})
    assert settings.diagnostics()["credentials_present"] is True


@pytest.mark.parametrize("status", [302, 401, 403, 429, 500])
def test_provider_errors_are_sanitized_and_redirects_disabled(status):
    class Response:
        status_code = status
        closed = False

        def close(self):
            self.closed = True

    class Session:
        response = Response()

        def mount(self, *args):
            pass

        def get(self, url, **kwargs):
            assert kwargs["allow_redirects"] is False
            return self.response

    fake = Session()
    client = AlpacaClient("sensitive-key", "sensitive-secret", session=fake)
    with pytest.raises(ProviderError) as captured:
        client.pages("alpaca_news", "/v1beta1/news", {}, "news", max_pages=1)
    assert captured.value.status_code == status
    assert "sensitive" not in str(captured.value)
    assert client.failures == [{"source": "alpaca_news", "status_code": status,
                                "reason": "http_error"}]
    assert fake.response.closed


def test_transport_exception_does_not_leak_underlying_message():
    class Session:
        def mount(self, *args):
            pass

        def get(self, *args, **kwargs):
            raise requests.ConnectionError("sensitive-credential-in-error")

    client = AlpacaClient("key", "secret", session=Session())
    with pytest.raises(ProviderError) as captured:
        client.pages("alpaca_news", "/v1beta1/news", {}, "news", max_pages=1)
    assert "sensitive" not in str(captured.value)


def test_pagination_cap_is_a_recorded_failure_not_partial_success():
    from test_extraction import FakeSession

    client = AlpacaClient("key", "secret", session=FakeSession())
    with pytest.raises(ProviderError, match="pagination_limit_exceeded"):
        client.pages("alpaca_news", "/v1beta1/news", {}, "news", max_pages=1)
    assert client.failures[-1]["reason"] == "pagination_limit_exceeded"


def test_unapproved_request_path_is_rejected_before_authentication():
    from test_extraction import FakeSession

    session = FakeSession()
    client = AlpacaClient("key", "secret", session=session)
    with pytest.raises(ValueError, match="unsupported market-data endpoint"):
        client.pages("alpaca_news", "//evil.example", {}, "news", max_pages=1)
    assert session.tokens == []


def test_stream_failure_is_sanitized_and_response_is_closed():
    class Response:
        status_code = 200
        closed = False

        def iter_content(self, **kwargs):
            raise requests.ConnectionError("sensitive-response-error")

        def close(self):
            self.closed = True

    class Session:
        response = Response()

        def mount(self, *args):
            pass

        def get(self, *args, **kwargs):
            return self.response

    session = Session()
    client = AlpacaClient("key", "secret", session=session)
    with pytest.raises(ProviderError) as captured:
        client.pages("alpaca_news", "/v1beta1/news", {}, "news", max_pages=1)
    assert "sensitive" not in str(captured.value)
    assert session.response.closed
