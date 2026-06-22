"""Versioned restricted-symbol checks for the risk gate."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from finharness.market_data import ROOT, display_path
from finharness.okx_symbols import normalize_usdt_symbol

RESTRICTED_SYMBOLS_ENV_VAR = "FINHARNESS_RESTRICTED_SYMBOLS_PATH"
DEFAULT_RESTRICTED_SYMBOLS_PATH = ROOT / "data" / "security" / "restricted-symbols.json"
RESTRICTED_SYMBOLS_SCHEMA_VERSION = "finharness.restricted_symbols.v1"

TradabilityStatus = Literal["tradable", "not_tradable", "unknown", "not_applicable"]
TradabilityProvider = Literal["not_applicable", "alpaca", "okx", "manual"]


class RestrictedSymbolsError(RuntimeError):
    """Raised when the restricted-symbol list cannot be trusted."""


class RestrictedSymbolEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    symbol: str
    reason: str
    added_utc: str

    @field_validator("symbol", "reason", "added_utc")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("restricted-symbol entries require non-empty text")
        return value.strip()


class RestrictedSymbolList(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: str = RESTRICTED_SYMBOLS_SCHEMA_VERSION
    restricted_list_version: str
    updated_at_utc: str
    entries: list[RestrictedSymbolEntry] = Field(default_factory=list)
    non_claims: list[str] = Field(
        default_factory=lambda: [
            "Restricted-symbol list is a local safety brake.",
            "Restricted-symbol list is not regulatory compliance certification.",
            "Restricted-symbol list is not execution authorization.",
        ]
    )


class RestrictedSymbolDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    normalized_symbol: str
    restricted: bool
    restricted_list_version: str | None
    restricted_list_ref: str | None
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)


class TradabilityDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    normalized_symbol: str
    provider: TradabilityProvider
    status: TradabilityStatus
    allowed: bool
    reason: str
    source_ref: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


def normalize_symbol(symbol: str) -> str:
    return normalize_usdt_symbol(symbol).strip().upper()


def restricted_symbols_path(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    env_path = os.environ.get(RESTRICTED_SYMBOLS_ENV_VAR)
    if env_path:
        return Path(env_path)
    return DEFAULT_RESTRICTED_SYMBOLS_PATH


def load_restricted_symbol_list(path: str | Path | None = None) -> RestrictedSymbolList:
    target = restricted_symbols_path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RestrictedSymbolsError(
            f"restricted-symbol list unreadable: {target}: {exc}"
        ) from exc
    try:
        return RestrictedSymbolList.model_validate(payload)
    except ValueError as exc:
        raise RestrictedSymbolsError(
            f"restricted-symbol list invalid: {target}: {exc}"
        ) from exc


def is_restricted(
    symbol: str,
    *,
    restricted_list: RestrictedSymbolList | None = None,
    restricted_list_path: str | Path | None = None,
) -> RestrictedSymbolDecision:
    target = restricted_symbols_path(restricted_list_path)
    normalized = normalize_symbol(symbol)
    try:
        active_list = restricted_list or load_restricted_symbol_list(target)
    except RestrictedSymbolsError as exc:
        return RestrictedSymbolDecision(
            symbol=symbol,
            normalized_symbol=normalized,
            restricted=True,
            restricted_list_version=None,
            restricted_list_ref=display_path(target),
            reason=f"{exc}; refusing fail-closed",
            evidence_refs=[display_path(target)],
        )
    entry = next(
        (
            item
            for item in active_list.entries
            if normalize_symbol(item.symbol) == normalized
        ),
        None,
    )
    if entry is None:
        return RestrictedSymbolDecision(
            symbol=symbol,
            normalized_symbol=normalized,
            restricted=False,
            restricted_list_version=active_list.restricted_list_version,
            restricted_list_ref=display_path(target),
            reason="symbol not present in restricted list",
            evidence_refs=[
                display_path(target),
                f"restricted_list_version:{active_list.restricted_list_version}",
            ],
        )
    return RestrictedSymbolDecision(
        symbol=symbol,
        normalized_symbol=normalized,
        restricted=True,
        restricted_list_version=active_list.restricted_list_version,
        restricted_list_ref=display_path(target),
        reason=entry.reason,
        evidence_refs=[
            display_path(target),
            f"restricted_list_version:{active_list.restricted_list_version}",
            f"restricted_symbol:{normalized}",
        ],
    )


def _asset_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    asset = payload.get("asset")
    if isinstance(asset, dict):
        records.append(asset)
    assets = payload.get("assets")
    if isinstance(assets, list):
        records.extend(item for item in assets if isinstance(item, dict))
    account = payload.get("account")
    if isinstance(account, dict) and isinstance(account.get("assets"), list):
        records.extend(item for item in account["assets"] if isinstance(item, dict))
    return records


def _load_receipt_payload(path: str | Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def tradability_for_symbol(
    symbol: str,
    *,
    provider: TradabilityProvider = "not_applicable",
    receipt_ref: str | Path | None = None,
    manual_tradability: dict[str, bool] | None = None,
) -> TradabilityDecision:
    normalized = normalize_symbol(symbol)
    if provider in {"not_applicable", "okx"}:
        return TradabilityDecision(
            symbol=symbol,
            normalized_symbol=normalized,
            provider=provider,
            status="not_applicable",
            allowed=True,
            reason=f"provider tradability is not applicable for {provider}",
            source_ref=str(receipt_ref) if receipt_ref else None,
            evidence_refs=[f"tradability:{provider}:not_applicable"],
        )

    if provider == "manual":
        if manual_tradability is None:
            return TradabilityDecision(
                symbol=symbol,
                normalized_symbol=normalized,
                provider=provider,
                status="unknown",
                allowed=False,
                reason="manual provider tradability evidence is missing",
                evidence_refs=["tradability:manual:unknown"],
            )
        value = manual_tradability.get(normalized)
        if value is None:
            value = manual_tradability.get(symbol.upper())
        status: TradabilityStatus = "tradable" if value else "not_tradable"
        return TradabilityDecision(
            symbol=symbol,
            normalized_symbol=normalized,
            provider=provider,
            status=status,
            allowed=bool(value),
            reason=f"manual provider tradability is {status}",
            evidence_refs=[f"tradability:manual:{status}"],
        )

    if receipt_ref is None:
        return TradabilityDecision(
            symbol=symbol,
            normalized_symbol=normalized,
            provider=provider,
            status="unknown",
            allowed=False,
            reason=f"{provider} tradability receipt is missing",
            evidence_refs=[f"tradability:{provider}:unknown"],
        )
    payload = _load_receipt_payload(receipt_ref)
    if payload is None:
        return TradabilityDecision(
            symbol=symbol,
            normalized_symbol=normalized,
            provider=provider,
            status="unknown",
            allowed=False,
            reason=f"{provider} tradability receipt is unreadable",
            source_ref=str(receipt_ref),
            evidence_refs=[str(receipt_ref), f"tradability:{provider}:unknown"],
        )
    for asset in _asset_records(payload):
        asset_symbol = str(asset.get("symbol") or asset.get("asset_symbol") or "")
        if normalize_symbol(asset_symbol) != normalized:
            continue
        if asset.get("tradable") is True:
            return TradabilityDecision(
                symbol=symbol,
                normalized_symbol=normalized,
                provider=provider,
                status="tradable",
                allowed=True,
                reason=f"{provider} receipt marks asset tradable",
                source_ref=str(receipt_ref),
                evidence_refs=[str(receipt_ref), f"tradability:{provider}:tradable"],
            )
        if asset.get("tradable") is False:
            return TradabilityDecision(
                symbol=symbol,
                normalized_symbol=normalized,
                provider=provider,
                status="not_tradable",
                allowed=False,
                reason=f"{provider} receipt marks asset not tradable",
                source_ref=str(receipt_ref),
                evidence_refs=[
                    str(receipt_ref),
                    f"tradability:{provider}:not_tradable",
                ],
            )
    return TradabilityDecision(
        symbol=symbol,
        normalized_symbol=normalized,
        provider=provider,
        status="unknown",
        allowed=False,
        reason=f"{provider} receipt lacks tradability for {normalized}",
        source_ref=str(receipt_ref),
        evidence_refs=[str(receipt_ref), f"tradability:{provider}:unknown"],
    )
