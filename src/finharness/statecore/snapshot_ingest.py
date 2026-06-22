"""Portfolio snapshot ingestion for broker-read evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from finharness.statecore.models import Account, Position, Snapshot
from finharness.statecore.receipt_index import _display_path, receipt_index_record_from_path
from finharness.statecore.store import StateCoreStoreError, upsert_records


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in value)


def _string(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_float(*values: Any) -> float | None:
    for value in values:
        number = _float_or_none(value)
        if number is not None:
            return number
    return None


def _account_payload(payload: dict[str, Any]) -> dict[str, Any]:
    account = payload.get("account")
    if isinstance(account, dict):
        return dict(account)
    summary_keys = {
        "account_id",
        "status",
        "currency",
        "cash",
        "portfolio_value",
        "buying_power",
        "trading_blocked",
        "transfers_blocked",
        "account_blocked",
    }
    if any(key in payload for key in summary_keys):
        return {key: payload.get(key) for key in summary_keys if key in payload}
    pre_trade = payload.get("pre_trade")
    if isinstance(pre_trade, dict):
        return dict(pre_trade)
    return {}


def _positions_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    positions = payload.get("positions")
    if isinstance(positions, list):
        return [item for item in positions if isinstance(item, dict)]
    account = payload.get("account")
    if isinstance(account, dict) and isinstance(account.get("positions"), list):
        return [item for item in account["positions"] if isinstance(item, dict)]
    return []


def _created_at(payload: dict[str, Any]) -> str:
    for key in ("as_of_utc", "created_at_utc", "timestamp_utc", "generated_at"):
        value = payload.get(key)
        if value:
            return str(value)
    snapshot = payload.get("snapshot")
    if isinstance(snapshot, dict) and snapshot.get("as_of_utc"):
        return str(snapshot["as_of_utc"])
    raise StateCoreStoreError("portfolio snapshot input lacks as-of timestamp")


def _account_id(payload: dict[str, Any], account: dict[str, Any]) -> str:
    value = (
        account.get("account_id")
        or account.get("id")
        or payload.get("account_id")
        or payload.get("account_ref")
    )
    if value:
        return _safe_id(str(value))
    broker = _string(payload.get("broker"), "manual")
    environment = _string(payload.get("environment"), "read")
    return _safe_id(f"{broker}_{environment}_account")


def _venue(payload: dict[str, Any]) -> str:
    broker = _string(payload.get("broker"), "manual")
    environment = _string(payload.get("environment"), "read")
    return f"{broker}-{environment}"


def _market_value(position: dict[str, Any]) -> float | None:
    value = _first_float(
        position.get("market_value"),
        position.get("market_value_usd"),
        position.get("asset_value"),
    )
    if value is not None:
        return value
    quantity = _first_float(position.get("qty"), position.get("quantity"))
    price = _first_float(
        position.get("current_price"),
        position.get("market_price"),
        position.get("last_price"),
    )
    if quantity is None or price is None:
        return None
    return quantity * price


def _position_records(
    *,
    positions: list[dict[str, Any]],
    snapshot_id: str,
    account_id: str,
    source_ref: str,
    as_of_utc: str,
) -> tuple[list[Position], list[dict[str, Any]], int]:
    records: list[Position] = []
    normalized: list[dict[str, Any]] = []
    omitted = 0
    for index, raw in enumerate(positions):
        symbol = _string(raw.get("symbol") or raw.get("asset_symbol")).upper()
        quantity = _first_float(raw.get("qty"), raw.get("quantity"))
        market_value = _market_value(raw)
        if not symbol or quantity is None or market_value is None:
            omitted += 1
            continue
        cost_basis = _first_float(raw.get("cost_basis"))
        normalized.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "market_value": market_value,
                "cost_basis": cost_basis,
                "cost_basis_disclosed": cost_basis is not None,
            }
        )
        records.append(
            Position(
                position_id=_safe_id(f"pos_{snapshot_id}_{index}_{symbol}"),
                snapshot_id=snapshot_id,
                account_id=account_id,
                symbol=symbol,
                quantity=quantity,
                market_value=market_value,
                cost_basis=cost_basis,
                as_of_utc=as_of_utc,
                source_refs=[source_ref],
            )
        )
    return records, normalized, omitted


def portfolio_records_from_broker_payload(
    payload: dict[str, Any],
    *,
    source_ref: str,
    snapshot_id: str | None = None,
) -> tuple[Account, Snapshot, list[Position]]:
    """Normalize a broker-read payload into state-core records.

    This is state ingestion only. It never infers positions from orders or
    execution plans, and it leaves cost basis empty unless the source disclosed
    it directly.
    """
    if not isinstance(payload, dict):
        raise StateCoreStoreError("portfolio snapshot input must be a JSON object")
    as_of_utc = _created_at(payload)
    account_payload = _account_payload(payload)
    positions_payload = _positions_payload(payload)
    account_id = _account_id(payload, account_payload)
    resolved_snapshot_id = _safe_id(
        snapshot_id
        or f"snap_portfolio_{payload.get('receipt_id') or Path(source_ref).stem}"
    )
    position_records, normalized_positions, omitted_positions = _position_records(
        positions=positions_payload,
        snapshot_id=resolved_snapshot_id,
        account_id=account_id,
        source_ref=source_ref,
        as_of_utc=as_of_utc,
    )
    account = Account(
        account_id=account_id,
        kind="broker" if payload.get("broker") else "manual",
        venue=_venue(payload),
        display_name=_string(
            account_payload.get("display_name")
            or account_payload.get("name")
            or account_payload.get("status"),
            account_id,
        ),
        as_of_utc=as_of_utc,
        source_refs=[source_ref],
    )
    snapshot = Snapshot(
        snapshot_id=resolved_snapshot_id,
        kind="portfolio",
        as_of_utc=as_of_utc,
        payload={
            "source": "broker_read",
            "account": account_payload,
            "position_count": len(normalized_positions),
            "positions": normalized_positions,
            "omitted_position_count": omitted_positions,
            "positions_source_disclosed": bool(positions_payload),
            "not_claimed": [
                "Not execution authorization.",
                "Not investment advice.",
                "Cost basis is omitted unless directly disclosed by the source.",
            ],
            "execution_allowed": False,
        },
        source_refs=[source_ref],
    )
    return account, snapshot, position_records


def load_portfolio_payload_from_receipt(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StateCoreStoreError(f"portfolio receipt unreadable: {target}: {exc}") from exc
    if not isinstance(payload, dict):
        raise StateCoreStoreError(f"portfolio receipt must contain a JSON object: {target}")
    return payload


def ingest_portfolio_snapshot_from_payload(
    payload: dict[str, Any],
    *,
    source_ref: str,
    engine: Engine,
) -> Snapshot:
    account, snapshot, positions = portfolio_records_from_broker_payload(
        payload,
        source_ref=source_ref,
    )
    upsert_records([account, snapshot, *positions], engine=engine)
    return snapshot


def ingest_portfolio_snapshot_from_receipt(
    path: str | Path,
    *,
    engine: Engine,
) -> Snapshot:
    target = Path(path)
    source_ref = _display_path(target)
    payload = load_portfolio_payload_from_receipt(target)
    receipt_index = receipt_index_record_from_path(target, receipt_root=target.parent)
    account, snapshot, positions = portfolio_records_from_broker_payload(
        payload,
        source_ref=source_ref,
    )
    upsert_records([receipt_index, account, snapshot, *positions], engine=engine)
    return snapshot
