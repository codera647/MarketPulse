from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from marketpulse.clock import utc_iso

BASE_URL = "https://data.alpaca.markets"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


@dataclass(frozen=True)
class CapturedPage:
    source: str
    endpoint: str
    params: dict[str, Any]
    received_at: str
    request_id: str | None
    payload: dict[str, Any]


class AlpacaClient:
    def __init__(
        self,
        key: str,
        secret: str,
        *,
        timeout: float = 15,
        session: requests.Session | None = None,
        clock: Callable[[], datetime] | None = None,
    ):
        if not key or not secret:
            raise ValueError("Alpaca market-data credentials are required")
        self.timeout = timeout
        self.session = session or requests.Session()
        retry = Retry(
            total=2,
            backoff_factor=0.5,
            backoff_max=2,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET",),
            respect_retry_after_header=False,
        )
        self.session.mount("https://", HTTPAdapter(max_retries=retry))
        self.headers = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def pages(
        self,
        source: str,
        endpoint: str,
        params: dict[str, Any],
        item_key: str,
        *,
        max_pages: int,
    ) -> list[CapturedPage]:
        if max_pages < 1:
            raise ValueError("max_pages must be positive")
        result: list[CapturedPage] = []
        token: str | None = None
        seen_tokens: set[str] = set()
        for _ in range(max_pages):
            request_params = dict(params)
            if token is not None:
                request_params["page_token"] = token
            response = self.session.get(
                BASE_URL + endpoint,
                params=request_params,
                headers=self.headers,
                timeout=self.timeout,
                stream=True,
            )
            try:
                response.raise_for_status()
                body = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise ValueError("provider page exceeds size limit")
                payload = json.loads(body)
                request_id = response.headers.get("X-Request-ID")
            finally:
                response.close()
            if not isinstance(payload, dict) or item_key not in payload:
                raise ValueError(f"provider response missing {item_key}")
            items = payload[item_key]
            if item_key == "news" and not isinstance(items, list):
                raise ValueError("malformed news page")
            if item_key == "bars" and not isinstance(items, dict):
                raise ValueError("malformed bars page")
            result.append(
                CapturedPage(
                    source=source,
                    endpoint=endpoint,
                    params=request_params,
                    received_at=utc_iso(self.clock()),
                    request_id=request_id,
                    payload=payload,
                )
            )
            token = payload.get("next_page_token")
            if not token:
                return result
            if not isinstance(token, str) or token in seen_tokens:
                raise ValueError("invalid or repeated provider page token")
            seen_tokens.add(token)
        raise ValueError(f"pagination exceeded {max_pages} pages; result is incomplete")
