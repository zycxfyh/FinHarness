"""Small Alpaca paper API client used by local scripts.

The client is intentionally paper-first. Live trading should get a separate
adapter with explicit review, not a flag flip on this module.
"""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[2]
LOCAL_ENV = ROOT / ".env.alpaca"
PAPER_BASE_URL = "https://paper-api.alpaca.markets"
DATA_BASE_URL = "https://data.alpaca.markets"


class AlpacaConfigError(RuntimeError):
    """Raised when local Alpaca credentials or options are missing."""


def load_local_env() -> None:
    """Load ignored local Alpaca env vars without echoing secret values."""
    if not LOCAL_ENV.exists():
        return

    for raw_line in LOCAL_ENV.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def paper_headers() -> dict[str, str]:
    load_local_env()
    api_key = os.environ.get("ALPACA_API_KEY_ID")
    secret_key = os.environ.get("ALPACA_API_SECRET_KEY")
    if not api_key or not secret_key:
        raise AlpacaConfigError("Missing ALPACA_API_KEY_ID or ALPACA_API_SECRET_KEY")

    return {
        "APCA-API-KEY-ID": api_key,
        "APCA-API-SECRET-KEY": secret_key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def query_path(path: str, params: dict[str, Any]) -> str:
    clean = {key: value for key, value in params.items() if value is not None}
    if not clean:
        return path
    return f"{path}?{urlencode(clean, doseq=True)}"


@dataclass(frozen=True)
class AlpacaPaperClient:
    trading_base_url: str = PAPER_BASE_URL
    data_base_url: str = DATA_BASE_URL
    timeout: int = 20

    def request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        data_api: bool = False,
    ) -> dict[str, Any] | list[Any]:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        base_url = self.data_base_url if data_api else self.trading_base_url
        req = urllib.request.Request(
            f"{base_url}{path}",
            data=data,
            headers=paper_headers(),
            method=method,
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else {}

    def get(self, path: str, *, data_api: bool = False) -> dict[str, Any] | list[Any]:
        return self.request("GET", path, data_api=data_api)

    def post(self, path: str, body: dict[str, Any]) -> dict[str, Any] | list[Any]:
        return self.request("POST", path, body=body)

    def patch(self, path: str, body: dict[str, Any]) -> dict[str, Any] | list[Any]:
        return self.request("PATCH", path, body=body)

    def delete(self, path: str) -> dict[str, Any] | list[Any]:
        return self.request("DELETE", path)


def paper_experiment_config() -> dict[str, Any]:
    """Return broad paper-account settings for experimentation."""
    return {
        "suspend_trade": False,
        "no_shorting": False,
        "fractional_trading": True,
        "max_margin_multiplier": "4",
        "max_options_trading_level": 3,
        "disable_overnight_trading": False,
        "trade_confirm_email": "all",
        "dtbp_check": "both",
        "pdt_check": "both",
    }


def summarize_account(account: dict[str, Any]) -> dict[str, Any]:
    return {
        "account_id": account.get("id"),
        "status": account.get("status"),
        "currency": account.get("currency"),
        "cash": account.get("cash"),
        "portfolio_value": account.get("portfolio_value"),
        "buying_power": account.get("buying_power"),
        "options_approved_level": account.get("options_approved_level"),
        "options_trading_level": account.get("options_trading_level"),
        "pattern_day_trader": account.get("pattern_day_trader"),
        "trading_blocked": account.get("trading_blocked"),
        "transfers_blocked": account.get("transfers_blocked"),
        "account_blocked": account.get("account_blocked"),
    }
