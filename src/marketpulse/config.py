"""Local, literal configuration; credentials never become public diagnostics."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from urllib.parse import urlsplit

from dotenv.parser import parse_stream

DATA_URL = "https://data.alpaca.markets"
TRADING_HOSTS = {"api.alpaca.markets", "paper-api.alpaca.markets"}


def validate_data_url(value: str) -> str:
    # Never send the user's credentials to an arbitrary host or a redirect.
    if value.strip().rstrip("/") != DATA_URL:
        raise ValueError("APCA_API_DATA_URL must be https://data.alpaca.markets")
    return DATA_URL


@dataclass(frozen=True)
class AlpacaSettings:
    key: str = field(repr=False)
    secret: str = field(repr=False)
    data_url: str = DATA_URL
    endpoint_role: str = "default_data_endpoint"

    def diagnostics(self) -> dict:
        return {"credentials_present": True, "data_url": self.data_url,
                "endpoint_role": self.endpoint_role}


def load_alpaca_settings(
    env_file: Path | None = None, *, environ: dict[str, str] | None = None
) -> AlpacaSettings:
    """Read only the explicit file (or cwd/.env); process values win, no interpolation."""
    path = env_file if env_file is not None else Path(".env")
    values: dict[str, str | None] = {}
    if path.exists():
        if not path.is_file() or path.stat().st_size > 65536:
            raise ValueError("environment file must be a regular file under 64 KiB")
        text = path.read_text(encoding="utf-8-sig")
        for binding in parse_stream(StringIO(text)):
            if binding.error:
                raise ValueError(f"invalid environment-file syntax on line {binding.original.line}")
            if binding.key is not None:
                name = binding.key.upper()
                if name in values:
                    raise ValueError("duplicate environment-file variable")
                values[name] = binding.value
    elif env_file is not None:
        raise ValueError("explicit environment file was not found")
    values.update({key.upper(): value for key, value in
                   (os.environ if environ is None else environ).items()})
    key = values.get("APCA_API_KEY_ID")
    secret = values.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        raise ValueError(
            "set APCA_API_KEY_ID and APCA_API_SECRET_KEY in .env or process environment"
        )
    if any(character.isspace() for character in key + secret) or "${" in key + secret:
        raise ValueError("Alpaca credentials must be literal values without whitespace")
    endpoint = values.get("APCA_API_ENDPOINT") or values.get("APCA_API_BASE_URL")
    data_url = values.get("APCA_API_DATA_URL")
    role = "default_data_endpoint"
    if endpoint:
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.query
                or parsed.fragment or parsed.netloc != parsed.hostname):
            raise ValueError("Alpaca endpoint must be an approved HTTPS origin without credentials")
        if parsed.hostname in TRADING_HOSTS and parsed.path.rstrip("/") in {"", "/v2"}:
            role = "trading_endpoint_not_used"
        elif endpoint.rstrip("/") == DATA_URL:
            role = "configured_data_endpoint"
            data_url = data_url or endpoint
        else:
            raise ValueError("unsupported Alpaca endpoint; arbitrary hosts are not allowed")
    return AlpacaSettings(key, secret, validate_data_url(data_url or DATA_URL), role)
