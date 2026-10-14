"""Read-only Actions credential verification; emit no provider bodies or secrets."""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests

from marketpulse.cloud_connections import inspect_connections

SAFE_FAILURES = (
    "cloud database target/role/TLS validation failed",
    "application database role is not restricted",
    "private storage target validation failed",
    "private artifact bucket access failed",
    "artifact bucket contains a public ACL grant",
    "Alpaca news authentication/schema check failed",
    "Alpaca bar authentication/coverage check failed",
    "Vercel project authentication failed",
    "Vercel token resolves another target",
)


def inspect(values, *, request=requests.get) -> dict:
    config = json.loads((Path.cwd() / "deploy/cloud.json").read_text(encoding="utf-8"))
    print(json.dumps({"check": "cloud_database_and_storage", "status": "CHECKING"}))
    checks = inspect_connections(values, worker_only=True)["checks"]
    print(json.dumps({"check": "cloud_database_and_storage", "status": "PASS"}))
    headers = {"APCA-API-KEY-ID": values["APCA_API_KEY_ID"],
               "APCA-API-SECRET-KEY": values["APCA_API_SECRET_KEY"]}
    # One news record only. Never log its headline/body; this verifies the actual news service.
    print(json.dumps({"check": "alpaca_news", "status": "CHECKING"}))
    response = request("https://data.alpaca.markets/v1beta1/news",
                       params={"symbols": "AAPL", "limit": 1}, headers=headers,
                       timeout=(10, 20), allow_redirects=False)
    if response.status_code != 200 or not isinstance(response.json().get("news"), list):
        raise ValueError("Alpaca news authentication/schema check failed")
    checks["alpaca_news"] = "AUTHENTICATED"
    print(json.dumps({"check": "alpaca_bars", "status": "CHECKING"}))
    response = request("https://data.alpaca.markets/v2/stocks/bars",
                       params={"symbols": "AAPL", "timeframe": "1Day", "feed": "iex",
                               "start": "2026-10-01T00:00:00Z",
                               "end": "2026-10-02T00:00:00Z", "limit": 1},
                       headers=headers, timeout=(10, 20), allow_redirects=False)
    if response.status_code != 200 or not response.json().get("bars", {}).get("AAPL"):
        raise ValueError("Alpaca bar authentication/coverage check failed")
    checks["alpaca_iex_bars"] = "AUTHENTICATED"
    target = config["vercel"]
    print(json.dumps({"check": "vercel_project", "status": "CHECKING"}))
    response = request(f"https://api.vercel.com/v9/projects/{target['project_id']}",
                       params={"teamId": target["org_id"]},
                       headers={"Authorization": f"Bearer {values['VERCEL_TOKEN']}"},
                       timeout=(10, 20), allow_redirects=False)
    if response.status_code != 200:
        raise ValueError("Vercel project authentication failed")
    project = response.json()
    if (project.get("id"), project.get("accountId"), project.get("name")) != (
        target["project_id"], target["org_id"], target["project_name"]
    ):
        raise ValueError("Vercel token resolves another target")
    checks["vercel_project"] = "AUTHENTICATED_EXACT_TARGET"
    return {"status": "PASS", "checks": checks, "writes_performed": False,
            "schedules_enabled": False}


def main():
    try:
        result = inspect(os.environ)
    except Exception as error:
        reason = (str(error) if isinstance(error, ValueError)
                  and str(error) in SAFE_FAILURES else None)
        print(json.dumps({"status": "FAIL", "error_type": type(error).__name__,
                          "safe_reason": reason,
                          "detail": "Credential check failed; private details suppressed."}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
