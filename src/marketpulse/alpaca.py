from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from marketpulse.clock import utc_iso
from marketpulse.config import validate_data_url

BASE_URL = "https://data.alpaca.markets"
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class ProviderError(RuntimeError):
    """Sanitized provider failure; never includes headers, response body, or query tokens."""

    def __init__(self, source: str, status_code: int | None, reason: str):
        self.source = source
        self.status_code = status_code
        self.reason = reason
        super().__init__(f"{source}: {reason}; HTTP status={status_code}")


@dataclass(frozen=True)
class CapturedPage:
    source: str
    endpoint: str
    params: dict[str, Any]
    received_at: str
    request_id: str | None
    payload: dict[str, Any]
    base_url: str = BASE_URL


class AlpacaClient:
    def __init__(
        self,
        key: str,
        secret: str,
        *,
        timeout: float = 15,
        session: requests.Session | None = None,
        clock: Callable[[], datetime] | None = None,
        base_url: str = BASE_URL,
    ):
        if not key or not secret:
            raise ValueError("Alpaca market-data credentials are required")
        self.timeout = timeout
        self.base_url = validate_data_url(base_url)
        self.failures: list[dict] = []
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
        if endpoint not in {"/v1beta1/news", "/v2/stocks/bars"}:
            raise ValueError("unsupported market-data endpoint")
        result: list[CapturedPage] = []
        token: str | None = None
        seen_tokens: set[str] = set()
        for _ in range(max_pages):
            request_params = dict(params)
            if token is not None:
                request_params["page_token"] = token
            try:
                response = self.session.get(
                    self.base_url + endpoint,
                    params=request_params,
                    headers=self.headers,
                    timeout=self.timeout,
                    stream=True,
                    allow_redirects=False,
                )
            except requests.RequestException as error:
                failure = ProviderError(source, None, type(error).__name__)
                self.failures.append({"source": source, "status_code": None,
                                      "reason": failure.reason})
                raise failure from None
            try:
                if not 200 <= response.status_code < 300:
                    self.failures.append({"source": source, "status_code": response.status_code,
                                          "reason": "http_error"})
                    raise ProviderError(source, response.status_code, "http_error")
                body = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise ValueError("provider page exceeds size limit")
                payload = json.loads(body)
                request_id = response.headers.get("X-Request-ID")
            except requests.RequestException as error:
                self.failures.append({"source": source, "status_code": None,
                                      "reason": type(error).__name__})
                raise ProviderError(source, None, type(error).__name__) from None
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
                    base_url=self.base_url,
                )
            )
            token = payload.get("next_page_token")
            if not token:
                return result
            if not isinstance(token, str) or token in seen_tokens:
                raise ValueError("invalid or repeated provider page token")
            seen_tokens.add(token)
        self.failures.append({"source": source, "status_code": None,
                              "reason": "pagination_limit_exceeded"})
        raise ProviderError(source, None, "pagination_limit_exceeded")
