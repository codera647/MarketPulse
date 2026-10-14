from __future__ import annotations

from fastapi.testclient import TestClient

from web import index


def test_dashboard_projection_and_no_store_headers(monkeypatch):
    result = {"research": {"live": False}, "forward": None, "jobs": []}
    monkeypatch.setattr(index, "read_dashboard", lambda period: result)
    response = TestClient(index.app).get("/api/dashboard?period=2025%20development")
    assert response.status_code == 200
    assert response.json() == result
    assert response.headers["cache-control"] == "private, no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_invalid_period_never_queries_database(monkeypatch):
    def forbidden(period):
        raise AssertionError("invalid request must not query")
    monkeypatch.setattr(index, "read_dashboard", forbidden)
    assert TestClient(index.app).get("/api/dashboard?period=other").status_code == 400


def test_driver_errors_are_redacted(monkeypatch, caplog):
    def fail(period):
        raise ValueError("private-test-password")
    monkeypatch.setattr(index, "read_dashboard", fail)
    response = TestClient(index.app).get("/api/dashboard")
    assert response.status_code == 503
    assert "private-test-password" not in response.text + caplog.text


def test_only_static_whitelist_is_served():
    client = TestClient(index.app)
    assert client.get("/").status_code == 200
    assert client.get("/assets/app.css").status_code == 200
    assert client.get("/assets/app.js").status_code == 200
    assert client.get("/assets/.env").status_code == 404
    assert client.get("/.env.cloud.local").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.post("/api/dashboard").status_code == 405


def test_dashboard_refuses_worker_url(monkeypatch):
    import pytest
    monkeypatch.setenv("MARKETPULSE_DASHBOARD_DATABASE_URL", "postgresql://marketpulse_worker:"
                       "test@ep-lively-wind-b70bl7t0-pooler.c-13.us-east-1.aws.neon.tech/"
                       "marketpulse?sslmode=require")
    with pytest.raises(ValueError, match="restricted"):
        index.connection()
