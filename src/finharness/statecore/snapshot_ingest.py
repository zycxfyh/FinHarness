"""Portfolio snapshot normalization and manifested broker-read ingestion."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import Engine

from finharness.artifact_store import ArtifactStore, LocalArtifactStore
from finharness.capital_import_contract import (
    CapitalImportContractError,
    ImportFinding,
    build_time_semantics,
    completeness_status,
    currency_code,
    exact_decimal,
)
from finharness.capital_import_valuation import (
    assess_positions,
    merge_valuation_findings,
)
from finharness.import_provenance import persist_source_evidence, prepare_import
from finharness.position_valuation import ValuationEvidence, assess_position_valuation
from finharness.project_paths import ROOT
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
    ReceiptIndex,
    Snapshot,
)
from finharness.statecore.receipt_index import _display_path
from finharness.statecore.store import (
    StateCoreRecord,
    StateCoreStoreError,
    materialize_import_batch,
)

BROKER_READ_SOURCE_KIND = "broker_read"
BROKER_READ_MATERIALIZED_SOURCE = "broker_read_import"
BROKER_READ_ADAPTER_VERSION = "finharness.broker_read_receipt.v1"
DEFAULT_BROKER_IMPORT_RECEIPT_ROOT = (
    ROOT / "data" / "receipts" / "capital-imports" / "broker-read"
)
BROKER_IMPORT_NON_CLAIMS = (
    "Read-only broker receipt import.",
    "Not investment advice.",
    "Not execution authorization.",
)


@dataclass(frozen=True)
class BrokerReadImportResult:
    batch_id: str
    manifest_id: str
    snapshot_id: str
    receipt_id: str
    receipt_ref: str
    source_artifact_id: str
    upstream_receipt_id: str | None
    account_count: int
    position_count: int
    record_counts: dict[str, int]
    findings: list[dict[str, Any]]
    as_of_utc: str
    completeness_status: str
    execution_allowed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in value)


def _broker_import_version(source_ref: str, source_sha256: str) -> str:
    identity = f"{source_ref}\x00{source_sha256}".encode()
    return hashlib.sha256(identity).hexdigest()[:24]


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
    payload_valued_at_utc: str | None,
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
        if not symbol or quantity is None:
            findings.append(
                ImportFinding(
                    "omitted_incomplete_position",
                    "partial",
                    "position omitted because symbol or quantity is missing",
                    record_type="position",
                    record_number=index + 1,
                )
            )
            continue
        cost_basis = _first_decimal("cost_basis", raw.get("cost_basis"))
        unit_price = _first_decimal(
            "unit_price",
            raw.get("unit_price"),
            raw.get("current_price"),
            raw.get("market_price"),
            raw.get("last_price"),
        )
        valued_at_utc = _string(raw.get("valued_at_utc") or payload_valued_at_utc) or None
        price_currency = _string(raw.get("price_currency") or raw.get("currency")).upper() or None
        valuation_currency = (
            _string(raw.get("valuation_currency") or raw.get("currency")).upper() or None
        )
        price_source_ref = _string(raw.get("price_source_ref")) or (
            source_ref if unit_price is not None else None
        )
        fx_rate = _first_decimal("fx_rate", raw.get("fx_rate"))
        fx_as_of_utc = _string(raw.get("fx_as_of_utc")) or None
        fx_source_ref = _string(raw.get("fx_source_ref")) or None
        position_id = _safe_id(f"pos_{snapshot_id}_{index}_{symbol}")
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
        evidence = ValuationEvidence(
            quantity=quantity,
            market_value=market_value,
            valuation_currency=valuation_currency,
            unit_price=unit_price,
            price_currency=price_currency,
            valued_at_utc=valued_at_utc,
            price_source_ref=price_source_ref,
            fx_rate=fx_rate,
            fx_as_of_utc=fx_as_of_utc,
            fx_source_ref=fx_source_ref,
        )
        provisional = assess_position_valuation(
            evidence,
            record_id=position_id,
            record_number=index + 1,
            evaluated_at_utc=as_of_utc,
            check_freshness=False,
            allow_unknown_legacy=False,
        )
        valuation_status = provisional.status.value
        normalized.append(
            {
                "symbol": symbol,
                "instrument_id": instrument_id,
                "quantity": str(quantity),
                "market_value": str(market_value) if market_value is not None else None,
                "cost_basis": str(cost_basis) if cost_basis is not None else None,
                "currency": currency,
                "valuation_currency": valuation_currency,
                "unit_price": str(unit_price) if unit_price is not None else None,
                "price_currency": price_currency,
                "valued_at_utc": valued_at_utc,
                "price_source_ref": price_source_ref,
                "fx_rate": str(fx_rate) if fx_rate is not None else None,
                "fx_as_of_utc": fx_as_of_utc,
                "fx_source_ref": fx_source_ref,
                "valuation_status": valuation_status,
                "cost_basis_disclosed": cost_basis is not None,
            }
        )
        records.append(
            Position(
                position_id=position_id,
                snapshot_id=snapshot_id,
                account_id=account_id,
                instrument_id=instrument_id,
                symbol=symbol,
                quantity=quantity,
                market_value=market_value,
                cost_basis=cost_basis,
                valuation_currency=valuation_currency,
                unit_price=unit_price,
                price_currency=price_currency,
                valued_at_utc=valued_at_utc,
                price_source_ref=price_source_ref,
                fx_rate=fx_rate,
                fx_as_of_utc=fx_as_of_utc,
                fx_source_ref=fx_source_ref,
                valuation_status=valuation_status,
                as_of_utc=as_of_utc,
                source_refs=[source_ref],
            )
        )
    return records, list(identities.values()), list(aliases.values()), normalized, findings


def _time_contract(
    payload: dict[str, Any],
    positions: list[dict[str, Any]],
    *,
    ingested_at_utc: str | None = None,
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
            ingested_at=ingested_at_utc or datetime.now(UTC),
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
    ingested_at_utc: str | None = None,
) -> tuple[
    Account,
    AccountIdentity,
    list[IdentityAlias],
    Snapshot,
    list[InstrumentIdentity],
    list[Position],
]:
    """Normalize broker-read evidence without persisting it."""
    if not isinstance(payload, dict):
        raise StateCoreStoreError("portfolio snapshot input must be a JSON object")
    account_payload = _account_payload(payload)
    positions_payload = _positions_payload(payload)
    try:
        time_semantics, findings = _time_contract(
            payload,
            positions_payload,
            ingested_at_utc=ingested_at_utc,
        )
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
            payload_valued_at_utc=(
                str(payload["valued_at_utc"]).strip() if payload.get("valued_at_utc") else None
            ),
        )
    except CapitalImportContractError as exc:
        raise StateCoreStoreError(str(exc)) from exc
    findings.extend(position_findings)
    # Canonical assessment over the final position set before any freeze.
    assessments = assess_positions(position_records, evaluated_at_utc=as_of_utc)
    # Replace with copies carrying derived status (avoid mutating SQLModel
    # instances in-place which triggers ObjectDereferencedError).
    status_map = {}
    for position, assessment in zip(position_records, assessments, strict=True):
        p = Position(**position.model_dump())
        p.valuation_status = assessment.status.value
        status_map[position.position_id] = p
    position_records = [status_map[p.position_id] for p in position_records]
    findings = merge_valuation_findings(findings, assessments)
    # Keep normalized payload status aligned with assessed Position rows.
    status_by_id = {
        position.position_id: position.valuation_status for position in position_records
    }
    for index, position in enumerate(position_records):
        if index < len(normalized_positions):
            normalized_positions[index]["valuation_status"] = status_by_id[position.position_id]
    record_counts = {"account": 1, "position": len(position_records)}
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
            "source": BROKER_READ_MATERIALIZED_SOURCE,
            "adapter_version": BROKER_READ_ADAPTER_VERSION,
            "account": account_payload,
            "record_counts": record_counts,
            "position_count": len(normalized_positions),
            "positions": normalized_positions,
            "omitted_position_count": sum(
                1 for finding in findings if finding.code == "omitted_incomplete_position"
            ),
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
    """Pure compatibility projection; this function never writes State Core."""
    account, _account_identity, _aliases, snapshot, _instruments, positions = (
        _portfolio_records_with_identities(payload, source_ref=source_ref, snapshot_id=snapshot_id)
    )
    return account, snapshot, positions


def _payload_from_exact_bytes(target: Path, source_content: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(source_content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StateCoreStoreError(f"portfolio receipt unreadable: {target}: {exc}") from exc
    if not isinstance(payload, dict):
        raise StateCoreStoreError(f"portfolio receipt must contain a JSON object: {target}")
    return payload


def load_portfolio_payload_from_receipt(path: str | Path) -> dict[str, Any]:
    target = Path(path)
    try:
        source_content = target.read_bytes()
    except OSError as exc:
        raise StateCoreStoreError(f"portfolio receipt unreadable: {target}: {exc}") from exc
    return _payload_from_exact_bytes(target, source_content)


def _set_lineage_refs(records: list[StateCoreRecord], refs: list[str]) -> None:
    for record in records:
        if hasattr(record, "source_refs"):
            record.source_refs = list(refs)


def _ingest_broker_read_receipt_with_snapshot(
    path: str | Path,
    *,
    engine: Engine,
    receipt_root: str | Path | None = None,
    artifact_store: ArtifactStore | None = None,
    snapshot_id: str | None = None,
) -> tuple[BrokerReadImportResult, Snapshot]:
    target = Path(path)
    try:
        source_content = target.read_bytes()
    except OSError as exc:
        raise StateCoreStoreError(f"portfolio receipt unreadable: {target}: {exc}") from exc
    source_sha256 = hashlib.sha256(source_content).hexdigest()
    payload = _payload_from_exact_bytes(target, source_content)
    source_ref = _display_path(target)
    active_receipt_root = (
        Path(receipt_root)
        if receipt_root is not None
        else target.parent / "capital-import"
    )
    active_artifact_store = artifact_store or LocalArtifactStore(
        active_receipt_root / "artifact-store"
    )
    source_descriptor = persist_source_evidence(
        source_kind=BROKER_READ_SOURCE_KIND,
        source_content=source_content,
        source_sha256=source_sha256,
        artifact_store=active_artifact_store,
        created_at_utc=datetime.now(UTC).isoformat(),
    )
    version_fragment = _broker_import_version(source_ref, source_sha256)
    expected_snapshot_id = f"snap_broker_read_{version_fragment}"
    if snapshot_id is not None and snapshot_id != expected_snapshot_id:
        raise StateCoreStoreError(
            "broker recovery snapshot_id does not match exact source identity"
        )
    active_snapshot_id = expected_snapshot_id
    import_receipt_id = f"receipt_broker_read_import_{version_fragment}"
    import_receipt_path = active_receipt_root / f"{import_receipt_id}.json"
    import_receipt_ref = _display_path(import_receipt_path)
    (
        account,
        account_identity_record,
        aliases,
        snapshot,
        instrument_identities,
        positions,
    ) = _portfolio_records_with_identities(
        payload,
        source_ref=source_ref,
        snapshot_id=active_snapshot_id,
        ingested_at_utc=source_descriptor.created_at_utc,
    )
    record_counts = dict(snapshot.payload["record_counts"])
    receipt_payload = {
        "receipt_id": import_receipt_id,
        "kind": BROKER_READ_SOURCE_KIND,
        "adapter_version": BROKER_READ_ADAPTER_VERSION,
        "source_ref": source_ref,
        "source_sha256": source_sha256,
        "upstream_receipt_id": (
            str(payload["receipt_id"]) if payload.get("receipt_id") is not None else None
        ),
        "upstream_kind": str(payload.get("kind") or BROKER_READ_SOURCE_KIND),
        "snapshot_id": active_snapshot_id,
        "record_counts": record_counts,
        "non_claims": list(BROKER_IMPORT_NON_CLAIMS),
        "execution_allowed": False,
    }
    prepared = prepare_import(
        source_kind=BROKER_READ_SOURCE_KIND,
        source_id=source_ref,
        source_content=source_content,
        source_sha256=source_sha256,
        adapter_version=BROKER_READ_ADAPTER_VERSION,
        coverage_mode="full",
        record_counts=record_counts,
        snapshot_id=active_snapshot_id,
        receipt_id=import_receipt_id,
        receipt_root=active_receipt_root,
        receipt_ref=import_receipt_ref,
        artifact_store=active_artifact_store,
        receipt_payload=receipt_payload,
        created_at_utc=source_descriptor.created_at_utc,
        completeness_status=str(snapshot.payload["completeness_status"]),
        time_semantics=dict(snapshot.payload["time_semantics"]),
        findings=list(snapshot.payload["findings"]),
        covered_domains=["position"],
        corporate_action_status="unsupported_gap" if positions else "not_applicable",
    )
    lineage_refs = [import_receipt_ref, source_ref]
    all_records: list[StateCoreRecord] = [
        account_identity_record,
        *instrument_identities,
        *aliases,
        account,
        snapshot,
        *positions,
    ]
    _set_lineage_refs(all_records, lineage_refs)
    snapshot.payload = {
        **snapshot.payload,
        "import_batch_id": prepared.batch.batch_id,
        "receipt_manifest_id": prepared.manifest.manifest_id,
        "import_receipt_id": import_receipt_id,
        "import_receipt_ref": import_receipt_ref,
        "source_artifact_id": prepared.batch.source_artifact_id,
    }
    from typing import cast

    from finharness.capital_import_registry import receipt_index_contract_fields

    contract = receipt_index_contract_fields(
        source_kind=BROKER_READ_SOURCE_KIND,
        receipt_ref=import_receipt_ref,
        created_at_utc=source_descriptor.created_at_utc,
        source_ref=source_ref,
        upstream_receipt_id=cast(str | None, receipt_payload.get("upstream_receipt_id")),
        source_artifact_id=prepared.batch.source_artifact_id,
    )
    receipt_index = ReceiptIndex(
        receipt_id=import_receipt_id,
        kind=cast(str, contract["kind"]),
        path=cast(str, contract["path"]),
        created_at_utc=cast(str, contract["created_at_utc"]),
        source_refs=cast(list[str], contract["source_refs"]),
        refs=cast(list[str], contract["refs"]),
    )
    materialize_import_batch(
        [receipt_index, *all_records],
        source=BROKER_READ_SOURCE_KIND,
        batch=prepared.batch,
        manifest=prepared.manifest,
        artifact_store=active_artifact_store,
        engine=engine,
    )
    result = BrokerReadImportResult(
        batch_id=prepared.batch.batch_id,
        manifest_id=prepared.manifest.manifest_id,
        snapshot_id=active_snapshot_id,
        receipt_id=import_receipt_id,
        receipt_ref=import_receipt_ref,
        source_artifact_id=prepared.batch.source_artifact_id,
        upstream_receipt_id=(
            str(payload["receipt_id"]) if payload.get("receipt_id") is not None else None
        ),
        account_count=1,
        position_count=len(positions),
        record_counts=dict(record_counts),
        findings=list(snapshot.payload["findings"]),
        as_of_utc=snapshot.as_of_utc,
        completeness_status=str(snapshot.payload["completeness_status"]),
        execution_allowed=False,
    )
    return result, snapshot


def ingest_broker_read_receipt(
    path: str | Path,
    *,
    engine: Engine,
    receipt_root: str | Path | None = None,
    artifact_store: ArtifactStore | None = None,
    snapshot_id: str | None = None,
) -> BrokerReadImportResult:
    """Materialize one broker-read receipt through the canonical import envelope."""
    result, _snapshot = _ingest_broker_read_receipt_with_snapshot(
        path,
        engine=engine,
        receipt_root=receipt_root,
        artifact_store=artifact_store,
        snapshot_id=snapshot_id,
    )
    return result


def ingest_portfolio_snapshot_from_payload(
    payload: dict[str, Any],
    *,
    source_ref: str,
    engine: Engine,
) -> Snapshot:
    """Reject the legacy direct-mutation surface; use the pure normalizer instead."""
    del payload, source_ref, engine
    raise StateCoreStoreError(
        "direct broker payload materialization is not a production import surface; "
        "persist an immutable broker-read receipt and use ingest_broker_read_receipt"
    )


def ingest_portfolio_snapshot_from_receipt(
    path: str | Path,
    *,
    engine: Engine,
    receipt_root: str | Path | None = None,
    artifact_store: ArtifactStore | None = None,
) -> Snapshot:
    """Compatibility wrapper routed through the canonical broker import adapter."""
    _result, snapshot = _ingest_broker_read_receipt_with_snapshot(
        path,
        engine=engine,
        receipt_root=receipt_root,
        artifact_store=artifact_store,
    )
    return snapshot
