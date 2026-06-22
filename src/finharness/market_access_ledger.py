"""Shared aggregate market-access limit ledger.

The ledger is a pre-trade brake, not an execution authority. It accumulates
authorized order consumption by daily window so many small requests cannot slip
past a per-order cap. Evaluation is read-only; recording consumption is a
separate post-authorization state change with a receipt.
"""

from __future__ import annotations

import json
import math
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from finharness.market_data import ROOT, display_path, sha256_text

MARKET_ACCESS_LEDGER_ENV_VAR = "FINHARNESS_MARKET_ACCESS_LEDGER_PATH"
MARKET_ACCESS_RECEIPT_ROOT_ENV_VAR = "FINHARNESS_MARKET_ACCESS_RECEIPT_ROOT"
DEFAULT_MARKET_ACCESS_LEDGER_PATH = (
    ROOT / "data" / "state" / "market-access-ledger" / "ledger.json"
)
DEFAULT_MARKET_ACCESS_RECEIPT_ROOT = ROOT / "data" / "receipts" / "market-access-ledger"


class MarketAccessLedgerError(RuntimeError):
    """Raised when the market-access ledger cannot be safely updated."""


class MarketAccessKey(BaseModel):
    """Aggregation key for a market-access window."""

    model_config = ConfigDict(frozen=True)

    environment: Literal["paper", "live"]
    venue: str
    operator: str
    account: str
    symbol: str


class MarketAccessLimit(BaseModel):
    """Human-owned aggregate ceiling for one key/window."""

    model_config = ConfigDict(frozen=True)

    window: Literal["daily"] = "daily"
    max_window_notional: float = Field(gt=0)
    max_window_order_count: int = Field(gt=0)


class LedgerEntry(BaseModel):
    """One post-authorization consumption entry."""

    model_config = ConfigDict(frozen=True)

    entry_id: str
    window_id: str
    key: MarketAccessKey
    notional: float
    created_at_utc: str
    source_ref: str | None = None


class MarketAccessDecision(BaseModel):
    """Read-only aggregate limit decision.

    ``allowed_within_limit`` only means the request fits the remaining aggregate
    ceiling. It is not an order permission and never authorizes execution.
    """

    model_config = ConfigDict(frozen=True)

    allowed_within_limit: bool
    window_id: str
    used_notional: float
    remaining_notional_after: float
    used_order_count: int
    remaining_orders_after: int
    blocking_reasons: list[str] = Field(default_factory=list)
    configured_ceiling: float | None = None
    effective_ceiling: float | None = None
    ceiling_provenance: dict[str, Any] | None = None
    ignored_ceiling_changes: list[str] = Field(default_factory=list)
    request_limit: float | None = None
    enforced_cap: float | None = None
    request_limit_clamped_to_ceiling: bool = False
    cap_invariant_holds: bool = True
    execution_allowed: Literal[False] = False


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _coerce_now(now: datetime | str | None = None) -> datetime:
    if now is None:
        return datetime.now(UTC)
    if isinstance(now, datetime):
        return now.astimezone(UTC) if now.tzinfo else now.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(now)
    return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def window_id(now: datetime | str | None = None) -> str:
    """Return the UTC daily window id for ``now``."""
    return _coerce_now(now).date().isoformat()


def market_access_ledger_path(path: str | Path | None = None) -> Path:
    if path is not None:
        target = Path(path)
        return target if target.suffix else target / "ledger.json"
    env_path = os.environ.get(MARKET_ACCESS_LEDGER_ENV_VAR)
    if env_path:
        return Path(env_path)
    return DEFAULT_MARKET_ACCESS_LEDGER_PATH


def market_access_receipt_root(path: str | Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    env_path = os.environ.get(MARKET_ACCESS_RECEIPT_ROOT_ENV_VAR)
    if env_path:
        return Path(env_path)
    return DEFAULT_MARKET_ACCESS_RECEIPT_ROOT


def load_market_access_ledger(path: str | Path | None = None) -> list[LedgerEntry]:
    """Load persisted ledger entries.

    A corrupt ledger raises instead of returning a clean slate; callers that
    cannot read state should fail closed before mutation.
    """
    target = market_access_ledger_path(path)
    if not target.exists():
        return []
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
        rows = payload.get("entries", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError("market-access ledger must contain a list of entries")
        return [LedgerEntry.model_validate(item) for item in rows]
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise MarketAccessLedgerError(f"market-access ledger unreadable: {exc}") from exc


def save_market_access_ledger(
    ledger: list[LedgerEntry],
    path: str | Path | None = None,
) -> Path:
    target = market_access_ledger_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    payload = {
        "schema_version": "finharness.market_access_ledger.v1",
        "updated_at_utc": _now_utc(),
        "entries": [entry.model_dump(mode="json") for entry in ledger],
    }
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    tmp.replace(target)
    return target


def usage_in_window(
    ledger: list[LedgerEntry],
    key: MarketAccessKey,
    window: str,
) -> tuple[float, int]:
    matching = [entry for entry in ledger if entry.key == key and entry.window_id == window]
    return sum(entry.notional for entry in matching), len(matching)


def _bounded_notional(notional: float | int | None) -> float | None:
    if notional is None:
        return None
    try:
        value = float(notional)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    return value


def evaluate_market_access(
    *,
    key: MarketAccessKey,
    notional: float | int | None,
    limit: MarketAccessLimit | None,
    ledger: list[LedgerEntry],
    now: datetime | str | None = None,
    limit_evidence: dict[str, Any] | None = None,
) -> MarketAccessDecision:
    """Read-only aggregate market-access check."""
    current_window = window_id(now)
    used_notional, used_count = usage_in_window(ledger, key, current_window)
    bounded = _bounded_notional(notional)
    blocking: list[str] = []

    if bounded is None:
        blocking.append("notional could not be bounded; refusing fail-closed")
    if limit is None:
        blocking.append("no pre-set aggregate limit configured; refusing fail-closed")

    if limit is None:
        remaining_notional_after = 0.0
        remaining_orders_after = 0
    else:
        candidate_notional = bounded or 0.0
        remaining_notional_after = (
            limit.max_window_notional - used_notional - candidate_notional
        )
        remaining_orders_after = limit.max_window_order_count - used_count - 1
        if bounded is not None and remaining_notional_after < 0:
            blocking.append(
                "aggregate window notional "
                f"{used_notional + bounded:.4f} exceeds remaining "
                f"{limit.max_window_notional - used_notional:.4f}"
            )
        if used_count + 1 > limit.max_window_order_count:
            blocking.append("aggregate window order count exceeded")

    return MarketAccessDecision(
        allowed_within_limit=not blocking,
        window_id=current_window,
        used_notional=used_notional,
        remaining_notional_after=max(0.0, remaining_notional_after),
        used_order_count=used_count,
        remaining_orders_after=max(0, remaining_orders_after),
        blocking_reasons=blocking,
        configured_ceiling=(
            limit_evidence.get("configured_ceiling") if limit_evidence else None
        ),
        effective_ceiling=(
            limit_evidence.get("effective_ceiling") if limit_evidence else None
        ),
        ceiling_provenance=(
            limit_evidence.get("provenance") if limit_evidence else None
        ),
        ignored_ceiling_changes=(
            list(limit_evidence.get("ignored", [])) if limit_evidence else []
        ),
        request_limit=limit_evidence.get("request_limit") if limit_evidence else None,
        enforced_cap=limit_evidence.get("enforced_cap") if limit_evidence else None,
        request_limit_clamped_to_ceiling=bool(
            limit_evidence.get("request_limit_clamped_to_ceiling", False)
        )
        if limit_evidence
        else False,
        cap_invariant_holds=bool(
            limit_evidence.get("cap_invariant_holds", True)
        )
        if limit_evidence
        else True,
    )


def record_consumption(
    *,
    key: MarketAccessKey,
    notional: float | int,
    ledger: list[LedgerEntry] | None = None,
    now: datetime | str | None = None,
    limit: MarketAccessLimit | None = None,
    limit_evidence: dict[str, Any] | None = None,
    source_ref: str | None = None,
    state_root: str | Path | None = None,
    receipt_root: str | Path | None = None,
) -> LedgerEntry:
    """Append one post-authorization consumption entry and write a receipt."""
    bounded = _bounded_notional(notional)
    if bounded is None:
        raise MarketAccessLedgerError("cannot record unbounded market-access notional")
    state_path = market_access_ledger_path(state_root)
    entries = list(ledger) if ledger is not None else load_market_access_ledger(state_path)
    created_at = _coerce_now(now)
    entry = LedgerEntry(
        entry_id=f"mktacc_{created_at.strftime('%Y%m%dT%H%M%SZ')}_{uuid4().hex[:8]}",
        window_id=window_id(created_at),
        key=key,
        notional=bounded,
        created_at_utc=created_at.isoformat(),
        source_ref=source_ref,
    )
    updated = [*entries, entry]
    ledger_path = save_market_access_ledger(updated, state_path)
    used_notional, used_count = usage_in_window(updated, key, entry.window_id)
    remaining_notional = (
        max(0.0, limit.max_window_notional - used_notional) if limit is not None else None
    )
    remaining_orders = (
        max(0, limit.max_window_order_count - used_count) if limit is not None else None
    )
    receipt_id = f"receipt_{entry.entry_id}"
    payload: dict[str, Any] = {
        "receipt_id": receipt_id,
        "kind": "market_access_consumption",
        "created_at_utc": _now_utc(),
        "entry": entry.model_dump(mode="json"),
        "ledger_ref": display_path(ledger_path),
        "window_usage_after": {
            "used_notional": used_notional,
            "used_order_count": used_count,
            "remaining_notional": remaining_notional,
            "remaining_orders": remaining_orders,
        },
        "limit": limit.model_dump(mode="json") if limit is not None else None,
        "limit_evidence": limit_evidence,
        "not_claimed": [
            "Not execution authorization.",
            "Not legal or regulatory compliance certification.",
            "Not investment advice.",
        ],
        "execution_allowed": False,
    }
    payload["content_hash"] = sha256_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    )
    receipts = market_access_receipt_root(receipt_root)
    receipts.mkdir(parents=True, exist_ok=True)
    (receipts / f"{receipt_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )
    return entry
