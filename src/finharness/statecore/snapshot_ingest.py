"""Portfolio snapshot ingestion for broker-read evidence."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from finharness.capital_import_contract import (
    CapitalImportContractError,
    ImportFinding,
    build_time_semantics,
    completeness_status,
    currency_code,
    exact_decimal,
)
from finharness.statecore.identities import (
    account_identity,
    instrument_identity,
    unresolved_instrument_finding,
)
from finharness.statecore.models import (
    Account,
    AccountIdentity,
    IdentityAlias,
    InstrumentIdentity,
    Position,
    Snapshot,
)
from finharness.statecore.receipt_index import _display_path, receipt_index_record_from_path
from finharness.statecore.store import StateCoreStoreError, upsert_records


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in value)


def _string(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _decimal_or_none(value: Any, *, field: str) -> Decimal | None:
    if value is None or value == "":
        return None
    return exact_decimal(value, field=field, record_type="position")


def _first_decimal(field: str, *values: Any) -> Decimal | None:
    for value in values:
        number = _decimal_or_none(value, field=field)
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


def _market_value(position: dict[str, Any]) -> Decimal | None:
    value = _first_decimal(
        "market_value",
        position.get("market_value"),
        position.get("market_value_usd"),
        position.get("asset_value"),
    )
    if value is not None:
        return value
    quantity = _first_decimal("quantity", position.get("qty"), position.get("quantity"))
    price = _first_decimal(
        "market_price",
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
    provider_namespace: str,
) -> tuple[
    list[Position],
    list[InstrumentIdentity],
    list[IdentityAlias],
    list[dict[str, Any]],
    list[ImportFinding],
]:
    records: list[Position] = []
    identities: dict[str, InstrumentIdentity] = {}
    aliases: dict[str, IdentityAlias] = {}
    normalized: list[dict[str, Any]] = []
    findings: list[ImportFinding] = []
    for index, raw in enumerate(positions):
        symbol = _string(raw.get("symbol") or raw.get("asset_symbol")).upper()
        currency = currency_code(
            raw.get("currency"), record_type="position", record_number=index + 1
        )
        quantity = _first_decimal("quantity", raw.get("qty"), raw.get("quantity"))
        market_value = _market_value(raw)
        if not symbol or quantity is None or market_value is None:
            findings.append(
                ImportFinding(
                    "omitted_incomplete_position",
                    "partial",
                    "position omitted because symbol, quantity, or market value is missing",
                    record_type="position",
                    record_number=index + 1,
                )
            )
            continue
        cost_basis = _first_decimal("cost_basis", raw.get("cost_basis"))
        instrument_type = _string(raw.get("instrument_type") or raw.get("asset_class"))
        instrument_venue = _string(raw.get("instrument_venue") or raw.get("exchange"))
        instrument_id: str | None = None
        if instrument_type and instrument_venue:
            identity, alias = instrument_identity(
                symbol=symbol,
                instrument_type=instrument_type,
                venue=instrument_venue,
                quote_currency=currency,
                provider_namespace=provider_namespace,
                source_refs=[source_ref],
            )
            identities.setdefault(identity.instrument_id, identity)
            aliases.setdefault(alias.alias_id, alias)
            instrument_id = identity.instrument_id
        else:
            finding = unresolved_instrument_finding(
                record_id=f"position:{index + 1}",
                missing_fields=(
                    "instrument_type" if not instrument_type else "",
                    "instrument_venue" if not instrument_venue else "",
                ),
            )
            findings.append(
                ImportFinding(
                    finding.code,
                    finding.severity,
                    finding.message,
                    record_type="position",
                    record_number=index + 1,
                    field=finding.field,
                )
            )
        normalized.append(
            {
                "symbol": symbol,
                "instrument_id": instrument_id,
                "quantity": str(quantity),
                "market_value": str(market_value),
                "cost_basis": str(cost_basis) if cost_basis is not None else None,
                "currency": currency,
                "cost_basis_disclosed": cost_basis is not None,
            }
        )
        records.append(
            Position(
                position_id=_safe_id(f"pos_{snapshot_id}_{index}_{symbol}"),
                snapshot_id=snapshot_id,
                account_id=account_id,
                instrument_id=instrument_id,
                symbol=symbol,
                quantity=quantity,
                market_value=market_value,
                cost_basis=cost_basis,
                as_of_utc=as_of_utc,
                source_refs=[source_ref],
            )
        )
    return records, list(identities.values()), list(aliases.values()), normalized, findings


def _time_contract(
    payload: dict[str, Any], positions: list[dict[str, Any]]
) -> tuple[dict[str, str | None], list[ImportFinding]]:
    needs_legacy = not payload.get("effective_at_utc") or not payload.get("observed_at_utc")
    legacy = _created_at(payload) if needs_legacy else None
    effective = str(payload.get("effective_at_utc") or legacy)
    observed = str(payload.get("observed_at_utc") or legacy)
    valued_values = {
        str(position.get("valued_at_utc")).strip()
        for position in positions
        if position.get("valued_at_utc")
    }
    if payload.get("valued_at_utc"):
        valued_values.add(str(payload["valued_at_utc"]).strip())
    if len(valued_values) > 1:
        raise StateCoreStoreError(
            "broker snapshot contains mixed valued_at_utc values; current-state import denied"
        )
    if not valued_values and legacy is None:
        legacy = _created_at(payload)
    valued = next(iter(valued_values), legacy)
    findings: list[ImportFinding] = []
    explicit_base_clocks = all(
        payload.get(field) for field in ("effective_at_utc", "observed_at_utc")
    )
    if not explicit_base_clocks or not valued_values:
        findings.append(
            ImportFinding(
                "legacy_time_projection",
                "partial",
                "explicit broker clocks were projected from a legacy receipt timestamp",
            )
        )
    try:
        semantics, time_findings = build_time_semantics(
            effective_at=effective,
            observed_at=observed,
            valued_at=valued,
            ingested_at=datetime.now(UTC),
        )
    except CapitalImportContractError as exc:
        raise StateCoreStoreError(str(exc)) from exc
    findings.extend(time_findings)
    return semantics.as_dict(), findings


def _portfolio_records_with_identities(
    payload: dict[str, Any],
    *,
    source_ref: str,
    snapshot_id: str | None = None,
) -> tuple[
    Account,
    AccountIdentity,
    list[IdentityAlias],
    Snapshot,
    list[InstrumentIdentity],
    list[Position],
]:
    """Normalize a broker-read payload into state-core records.

    This is state ingestion only. It never infers positions from orders or
    execution plans, and it leaves cost basis empty unless the source disclosed
    it directly.
    """
    if not isinstance(payload, dict):
        raise StateCoreStoreError("portfolio snapshot input must be a JSON object")
    account_payload = _account_payload(payload)
    positions_payload = _positions_payload(payload)
    try:
        time_semantics, findings = _time_contract(payload, positions_payload)
    except CapitalImportContractError as exc:
        raise StateCoreStoreError(str(exc)) from exc
    as_of_utc = str(time_semantics["observed_at_utc"])
    source_native_account_id = _account_id(payload, account_payload)
    provider_namespace = f"broker:{_venue(payload)}"
    account_identity_record, account_alias = account_identity(
        source_namespace=provider_namespace,
        source_native_id=source_native_account_id,
        source_refs=[source_ref],
    )
    account_id = account_identity_record.canonical_account_id
    resolved_snapshot_id = _safe_id(
        snapshot_id or f"snap_portfolio_{payload.get('receipt_id') or Path(source_ref).stem}"
    )
    try:
        (
            position_records,
            instrument_identities,
            instrument_aliases,
            normalized_positions,
            position_findings,
        ) = _position_records(
            positions=positions_payload,
            snapshot_id=resolved_snapshot_id,
            account_id=account_id,
            source_ref=source_ref,
            as_of_utc=as_of_utc,
            provider_namespace=provider_namespace,
        )
    except CapitalImportContractError as exc:
        raise StateCoreStoreError(str(exc)) from exc
    findings.extend(position_findings)
    account = Account(
        account_id=account_id,
        canonical_account_id=account_id,
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
            "omitted_position_count": len(position_findings),
            "positions_source_disclosed": bool(positions_payload),
            "coverage_mode": "full",
            "completeness_status": completeness_status(findings),
            "time_semantics": time_semantics,
            "findings": [finding.as_dict() for finding in findings],
            "not_claimed": [
                "Not execution authorization.",
                "Not investment advice.",
                "Cost basis is omitted unless directly disclosed by the source.",
            ],
            "execution_allowed": False,
        },
        source_refs=[source_ref],
    )
    return (
        account,
        account_identity_record,
        [account_alias, *instrument_aliases],
        snapshot,
        instrument_identities,
        position_records,
    )


def portfolio_records_from_broker_payload(
    payload: dict[str, Any],
    *,
    source_ref: str,
    snapshot_id: str | None = None,
) -> tuple[Account, Snapshot, list[Position]]:
    """Compatibility projection; identity records are persisted by ingest helpers."""
    account, _account_identity, _aliases, snapshot, _instruments, positions = (
        _portfolio_records_with_identities(payload, source_ref=source_ref, snapshot_id=snapshot_id)
    )
    return account, snapshot, positions


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
    account, account_id, aliases, snapshot, instruments, positions = (
        _portfolio_records_with_identities(
            payload,
            source_ref=source_ref,
        )
    )
    upsert_records(
        [account_id, *instruments, *aliases, account, snapshot, *positions], engine=engine
    )
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
    account, account_id, aliases, snapshot, instruments, positions = (
        _portfolio_records_with_identities(
            payload,
            source_ref=source_ref,
        )
    )
    upsert_records(
        [receipt_index, account_id, *instruments, *aliases, account, snapshot, *positions],
        engine=engine,
    )
    return snapshot
