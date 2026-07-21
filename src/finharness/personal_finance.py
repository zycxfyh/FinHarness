"""Read-only personal-finance CSV import adapter.

This adapter ingests a CSV that already matches the FinHarness import contract
(see ``docs/how-to/import-personal-finance-export.md``) and mirrors it into the
state core with a receipt. The CSV shape is defined by FinHarness, not by any
upstream tool; producing it from a real ledger is the caller's job. For a direct
connection to a real Beancount ledger, use ``finharness.beancount_adapter``
instead, which runs ``bean-query`` and needs no hand-written CSV.

FinHarness does not parse or replace personal accounting ledgers here.
"""

from __future__ import annotations

import csv
import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import Engine
from sqlmodel import Session, select

from finharness.artifact_store import ArtifactStore, ArtifactStoreError, LocalArtifactStore
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
    valuation_assessment_summary,
)
from finharness.import_provenance import (
    ImportProvenanceError,
    build_import_tombstone,
    derive_import_batch_id,
    normalize_import_deletions,
    persist_source_evidence,
    prepare_import,
)
from finharness.position_valuation import (
    ValuationAssessment,
    ValuationEvidence,
    assess_position_valuation,
)
from finharness.project_paths import ROOT
from finharness.statecore.identities import (
    account_identity,
    instrument_identity,
    unresolved_instrument_finding,
)
from finharness.statecore.import_identity import materialized_record_identities
from finharness.statecore.models import (
    Account,
    AccountIdentity,
    CashflowEvent,
    DocumentRef,
    FinancialGoal,
    IdentityAlias,
    ImportBatch,
    ImportDomainHead,
    ImportTombstone,
    InstrumentIdentity,
    InsurancePolicy,
    Liability,
    Position,
    ReceiptIndex,
    ReceiptManifest,
    Snapshot,
    SourcedStateCoreBase,
    TaxEvent,
)
from finharness.statecore.store import (
    StateCoreRecord,
    latest_source_manifest_for_domain,
    materialize_import_batch,
    plan_full_import_deletions,
    recovery_materialization_options,
)

DEFAULT_PERSONAL_FINANCE_RECEIPT_ROOT = ROOT / "data" / "receipts" / "personal-finance"
ADAPTER_VERSION = "finharness.personal_finance_export.v5"
EXPORT_KIND = "personal_finance_export"
POSITION_COLUMNS = {
    "account_id",
    "account_name",
    "account_kind",
    "venue",
    "symbol",
    "quantity",
    "currency",
    "as_of_utc",
}
ROW_TYPE_COLUMN = "record_type"
DEFAULT_ROW_TYPE = "position"
RECORD_TYPE_COLUMNS = {
    "position": POSITION_COLUMNS,
    "liability": {"liability_id", "name", "liability_type", "balance", "currency", "as_of_utc"},
    "goal": {"goal_id", "name", "target_amount", "current_amount", "currency", "as_of_utc"},
    "cashflow": {
        "cashflow_id",
        "description",
        "amount",
        "currency",
        "event_date",
        "category",
        "as_of_utc",
    },
    "tax_event": {"tax_event_id", "event_type", "jurisdiction", "due_date", "as_of_utc"},
    "insurance": {
        "policy_id",
        "policy_type",
        "provider",
        "coverage_amount",
        "currency",
        "as_of_utc",
    },
    "document": {"document_id", "document_type", "title", "path", "as_of_utc"},
}
DELETION_RECORD_DOMAINS = {
    "Position": "position",
    "Liability": "liability",
    "FinancialGoal": "goal",
    "CashflowEvent": "cashflow",
    "TaxEvent": "tax_event",
    "InsurancePolicy": "insurance",
    "DocumentRef": "document",
}
NON_CLAIMS = (
    "Read-only personal finance export ingestion.",
    "Not tax, accounting, or investment advice.",
    "Not execution authorization.",
)


class PersonalFinanceExportError(RuntimeError):
    """Raised when a personal-finance export cannot be safely ingested."""

    def __init__(self, message: str, *, findings: tuple[ImportFinding, ...] = ()) -> None:
        self.findings = findings
        super().__init__(message)


@dataclass(frozen=True)
class PersonalFinanceImportResult:
    batch_id: str
    manifest_id: str
    snapshot_id: str
    receipt_id: str
    receipt_ref: str
    account_count: int
    position_count: int
    liability_count: int
    goal_count: int
    cashflow_count: int
    tax_event_count: int
    insurance_policy_count: int
    document_count: int
    as_of_utc: str
    completeness_status: str
    execution_allowed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ImportDeletion:
    """Explicit deletion requested by a delta import."""

    record_type: str
    record_id: str
    reason: str


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in value)


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise PersonalFinanceExportError(f"personal-finance export missing: {path}")
    try:
        with path.open("r", encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            fieldnames = set(reader.fieldnames or ())
            rows = [dict(row) for row in reader]
            _validate_columns(fieldnames, rows)
            return rows
    except OSError as exc:
        raise PersonalFinanceExportError(f"personal-finance export unreadable: {exc}") from exc


def _validate_columns(fieldnames: set[str], rows: list[dict[str, str]]) -> None:
    if ROW_TYPE_COLUMN not in fieldnames:
        missing = sorted(POSITION_COLUMNS - fieldnames)
        if missing:
            raise PersonalFinanceExportError(
                f"personal-finance export missing columns: {', '.join(missing)}"
            )
        return
    if "as_of_utc" not in fieldnames:
        raise PersonalFinanceExportError("personal-finance export missing columns: as_of_utc")
    for index, row in enumerate(rows, start=1):
        row_type = _row_type(row)
        required = RECORD_TYPE_COLUMNS.get(row_type)
        if required is None:
            valid = ", ".join(sorted(RECORD_TYPE_COLUMNS))
            raise PersonalFinanceExportError(
                f"personal-finance export row {index} has unsupported record_type "
                f"{row_type!r}; expected one of: {valid}"
            )
        missing = sorted(required - fieldnames)
        if missing:
            raise PersonalFinanceExportError(
                f"personal-finance export row {index} missing columns for "
                f"{row_type}: {', '.join(missing)}"
            )


def _row_type(row: dict[str, str]) -> str:
    return (row.get(ROW_TYPE_COLUMN) or DEFAULT_ROW_TYPE).strip().lower() or DEFAULT_ROW_TYPE


def _required_text(row: dict[str, str], column: str, *, row_number: int) -> str:
    value = (row.get(column) or "").strip()
    if not value:
        raise PersonalFinanceExportError(
            f"personal-finance export row {row_number} has empty {column}"
        )
    return value


def _decimal_value(row: dict[str, str], column: str, *, row_number: int) -> Decimal:
    raw = _required_text(row, column, row_number=row_number)
    try:
        return exact_decimal(raw, field=column, record_number=row_number)
    except CapitalImportContractError as exc:
        raise PersonalFinanceExportError(
            f"personal-finance export row {row_number} has invalid {column}: {raw}",
            findings=exc.findings,
        ) from exc


def _optional_decimal(row: dict[str, str], column: str, *, row_number: int) -> Decimal | None:
    raw = (row.get(column) or "").strip()
    if not raw:
        return None
    try:
        return exact_decimal(raw, field=column, record_number=row_number)
    except CapitalImportContractError as exc:
        raise PersonalFinanceExportError(
            f"personal-finance export row {row_number} has invalid {column}: {raw}",
            findings=exc.findings,
        ) from exc


def _optional_text(row: dict[str, str], column: str) -> str | None:
    value = (row.get(column) or "").strip()
    return value or None


def _currency(row: dict[str, str], *, row_number: int) -> str:
    try:
        return currency_code(
            row.get("currency"), record_type=_row_type(row), record_number=row_number
        )
    except CapitalImportContractError as exc:
        raise PersonalFinanceExportError(str(exc), findings=exc.findings) from exc


def _optional_currency(row: dict[str, str], column: str, *, row_number: int) -> str | None:
    value = _optional_text(row, column)
    if value is None:
        return None
    try:
        return currency_code(
            value,
            field=column,
            record_type=_row_type(row),
            record_number=row_number,
        )
    except CapitalImportContractError as exc:
        raise PersonalFinanceExportError(str(exc), findings=exc.findings) from exc


def _single_as_of(rows: list[dict[str, str]], *, fallback: str = "") -> str:
    as_of_values = {
        _required_text(row, "as_of_utc", row_number=index)
        for index, row in enumerate(rows, start=1)
    }
    if not as_of_values:
        if not fallback:
            raise PersonalFinanceExportError(
                "zero-row import requires an explicit observed_at_utc"
            )
        return fallback
    if len(as_of_values) != 1:
        raise PersonalFinanceExportError(
            "personal-finance export must contain exactly one as_of_utc value"
        )
    return next(iter(as_of_values))


def _single_clock(rows: list[dict[str, str]], column: str, fallback: str) -> str:
    values = {(row.get(column) or "").strip() for row in rows}
    values.discard("")
    if not values:
        return fallback
    if len(values) != 1:
        raise PersonalFinanceExportError(
            f"personal-finance export must contain exactly one {column} value"
        )
    return next(iter(values))


def _time_contract(
    rows: list[dict[str, str]], *, ingested_at_utc: str, fallback_observed: str = ""
) -> tuple[dict[str, str | None], list[ImportFinding]]:
    as_of = _single_as_of(rows, fallback=fallback_observed)
    explicit_fields = ("effective_at_utc", "observed_at_utc", "valued_at_utc")
    findings: list[ImportFinding] = []
    if any(not any((row.get(field) or "").strip() for row in rows) for field in explicit_fields):
        findings.append(
            ImportFinding(
                "legacy_as_of_projection",
                "partial",
                "one or more explicit capital clocks were projected from legacy as_of_utc",
            )
        )
    try:
        semantics, time_findings = build_time_semantics(
            effective_at=_single_clock(rows, "effective_at_utc", as_of),
            observed_at=_single_clock(rows, "observed_at_utc", as_of),
            valued_at=_single_clock(rows, "valued_at_utc", as_of),
            ingested_at=ingested_at_utc,
        )
    except CapitalImportContractError as exc:
        raise PersonalFinanceExportError(str(exc), findings=exc.findings) from exc
    findings.extend(time_findings)
    return semantics.as_dict(), findings


def _receipt_payload(
    *,
    receipt_id: str,
    source_path: Path,
    source_hash: str,
    as_of_utc: str,
    row_count: int,
    snapshot_id: str,
    record_counts: dict[str, int],
) -> dict[str, Any]:
    return {
        "receipt_id": receipt_id,
        "kind": EXPORT_KIND,
        "adapter_version": ADAPTER_VERSION,
        "created_at_utc": as_of_utc,
        "source_ref": display_path(source_path),
        "source_sha256": source_hash,
        "row_count": row_count,
        "record_counts": record_counts,
        "snapshot_id": snapshot_id,
        "non_claims": list(NON_CLAIMS),
        "execution_allowed": False,
    }


def _record_counts(rows: list[dict[str, str]]) -> dict[str, int]:
    counts = dict.fromkeys(RECORD_TYPE_COLUMNS, 0)
    for row in rows:
        counts[_row_type(row)] += 1
    return {key: value for key, value in counts.items() if value}


def _payload_for_snapshot(
    rows: list[dict[str, str]],
    source_path: Path,
    *,
    time_semantics: dict[str, str | None],
    findings: list[ImportFinding],
    coverage_mode: str,
) -> dict[str, Any]:
    position_currencies = sorted(
        {
            _currency(row, row_number=index)
            for index, row in enumerate(rows, start=1)
            if _row_type(row) == "position"
        }
    )
    return {
        "source": EXPORT_KIND,
        "source_ref": display_path(source_path),
        "adapter_version": ADAPTER_VERSION,
        "row_count": len(rows),
        "record_counts": _record_counts(rows),
        "supported_record_types": sorted(RECORD_TYPE_COLUMNS),
        "position_currencies": position_currencies,
        "coverage_mode": coverage_mode,
        "completeness_status": completeness_status(findings),
        "time_semantics": time_semantics,
        "findings": [finding.as_dict() for finding in findings],
        "non_claims": list(NON_CLAIMS),
    }


@dataclass(frozen=True)
class _IngestContext:
    snapshot_id: str
    as_of_utc: str
    source_refs: list[str]
    accounts: dict[str, Account]
    account_identities: dict[str, AccountIdentity]
    instrument_identities: dict[str, InstrumentIdentity]
    aliases: dict[str, IdentityAlias]
    source_namespace: str


def _build_position(row: dict[str, str], index: int, ctx: _IngestContext) -> Position:
    source_native_id = _required_text(row, "account_id", row_number=index)
    namespace = _optional_text(row, "source_namespace") or ctx.source_namespace
    account_identity_record, account_alias = account_identity(
        source_namespace=namespace,
        source_native_id=source_native_id,
        source_refs=ctx.source_refs,
    )
    account_id = account_identity_record.canonical_account_id
    symbol = _required_text(row, "symbol", row_number=index).upper()
    quote_currency = _currency(row, row_number=index)
    instrument_type = _optional_text(row, "instrument_type")
    instrument_venue = _optional_text(row, "instrument_venue")
    resolved_instrument_id: str | None = None
    if instrument_type and instrument_venue:
        instrument, instrument_alias = instrument_identity(
            symbol=symbol,
            instrument_type=instrument_type,
            venue=instrument_venue,
            quote_currency=quote_currency,
            provider_namespace=namespace,
            source_refs=ctx.source_refs,
        )
        resolved_instrument_id = instrument.instrument_id
        ctx.instrument_identities.setdefault(instrument.instrument_id, instrument)
        ctx.aliases.setdefault(instrument_alias.alias_id, instrument_alias)
    ctx.account_identities.setdefault(account_id, account_identity_record)
    ctx.aliases.setdefault(account_alias.alias_id, account_alias)
    ctx.accounts.setdefault(
        account_id,
        Account(
            account_id=account_id,
            canonical_account_id=account_id,
            kind=_required_text(row, "account_kind", row_number=index),
            venue=_required_text(row, "venue", row_number=index),
            display_name=_required_text(row, "account_name", row_number=index),
            as_of_utc=ctx.as_of_utc,
            authority_level="read_only",
            source_refs=ctx.source_refs,
        ),
    )
    market_value = _optional_decimal(row, "market_value", row_number=index)
    unit_price = _optional_decimal(row, "unit_price", row_number=index)
    valuation_currency = _optional_currency(row, "valuation_currency", row_number=index)
    price_currency = _optional_currency(row, "price_currency", row_number=index)
    valued_at_utc = _optional_text(row, "valued_at_utc")
    price_source_ref = _optional_text(row, "price_source_ref")
    fx_rate = _optional_decimal(row, "fx_rate", row_number=index)
    fx_as_of_utc = _optional_text(row, "fx_as_of_utc")
    fx_source_ref = _optional_text(row, "fx_source_ref")
    position_id = _safe_id(f"pos_{ctx.snapshot_id}_{index}_{account_id}_{symbol}")
    evidence = ValuationEvidence(
        quantity=_decimal_value(row, "quantity", row_number=index),
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
    # Provisional status; final assessment runs over the full/delta position set
    # with batch observed_at_utc before prepare_import.
    provisional = assess_position_valuation(
        evidence,
        record_id=position_id,
        record_number=index,
        evaluated_at_utc=ctx.as_of_utc,
        check_freshness=False,
        allow_unknown_legacy=False,
    )
    return Position(
        position_id=position_id,
        snapshot_id=ctx.snapshot_id,
        account_id=account_id,
        instrument_id=resolved_instrument_id,
        symbol=symbol,
        quantity=evidence.quantity,
        market_value=market_value,
        cost_basis=_optional_decimal(row, "cost_basis", row_number=index),
        valuation_currency=valuation_currency,
        unit_price=unit_price,
        price_currency=price_currency,
        valued_at_utc=valued_at_utc,
        price_source_ref=price_source_ref,
        fx_rate=fx_rate,
        fx_as_of_utc=fx_as_of_utc,
        fx_source_ref=fx_source_ref,
        valuation_status=provisional.status.value,
        as_of_utc=ctx.as_of_utc,
        authority_level="read_only",
        source_refs=ctx.source_refs,
    )


def _build_liability(row: dict[str, str], index: int, ctx: _IngestContext) -> Liability:
    return Liability(
        liability_id=_required_text(row, "liability_id", row_number=index),
        name=_required_text(row, "name", row_number=index),
        liability_type=_required_text(row, "liability_type", row_number=index),
        balance=_decimal_value(row, "balance", row_number=index),
        currency=_currency(row, row_number=index),
        account_id=_optional_text(row, "account_id"),
        interest_rate=_optional_decimal(row, "interest_rate", row_number=index),
        due_date=_optional_text(row, "due_date"),
        as_of_utc=ctx.as_of_utc,
        authority_level="read_only",
        source_refs=ctx.source_refs,
    )


def _build_goal(row: dict[str, str], index: int, ctx: _IngestContext) -> FinancialGoal:
    return FinancialGoal(
        goal_id=_required_text(row, "goal_id", row_number=index),
        name=_required_text(row, "name", row_number=index),
        target_amount=_decimal_value(row, "target_amount", row_number=index),
        current_amount=_decimal_value(row, "current_amount", row_number=index),
        currency=_currency(row, row_number=index),
        target_date=_optional_text(row, "target_date"),
        status=_optional_text(row, "status") or "active",
        as_of_utc=ctx.as_of_utc,
        authority_level="read_only",
        source_refs=ctx.source_refs,
    )


def _build_cashflow(row: dict[str, str], index: int, ctx: _IngestContext) -> CashflowEvent:
    return CashflowEvent(
        cashflow_id=_required_text(row, "cashflow_id", row_number=index),
        description=_required_text(row, "description", row_number=index),
        amount=_decimal_value(row, "amount", row_number=index),
        currency=_currency(row, row_number=index),
        event_date=_required_text(row, "event_date", row_number=index),
        category=_required_text(row, "category", row_number=index),
        account_id=_optional_text(row, "account_id"),
        frequency=_optional_text(row, "frequency"),
        as_of_utc=ctx.as_of_utc,
        authority_level="read_only",
        source_refs=ctx.source_refs,
    )


def _build_tax_event(row: dict[str, str], index: int, ctx: _IngestContext) -> TaxEvent:
    return TaxEvent(
        tax_event_id=_required_text(row, "tax_event_id", row_number=index),
        event_type=_required_text(row, "event_type", row_number=index),
        jurisdiction=_required_text(row, "jurisdiction", row_number=index),
        due_date=_required_text(row, "due_date", row_number=index),
        estimated_amount=_optional_decimal(row, "estimated_amount", row_number=index),
        currency=(
            _currency(row, row_number=index)
            if _optional_text(row, "estimated_amount") is not None
            else (_currency(row, row_number=index) if _optional_text(row, "currency") else None)
        ),
        status=_optional_text(row, "status") or "planned",
        as_of_utc=ctx.as_of_utc,
        authority_level="read_only",
        source_refs=ctx.source_refs,
    )


def _build_insurance(row: dict[str, str], index: int, ctx: _IngestContext) -> InsurancePolicy:
    return InsurancePolicy(
        policy_id=_required_text(row, "policy_id", row_number=index),
        policy_type=_required_text(row, "policy_type", row_number=index),
        provider=_required_text(row, "provider", row_number=index),
        coverage_amount=_decimal_value(row, "coverage_amount", row_number=index),
        premium_amount=_optional_decimal(row, "premium_amount", row_number=index),
        currency=_currency(row, row_number=index),
        renewal_date=_optional_text(row, "renewal_date"),
        status=_optional_text(row, "status") or "active",
        as_of_utc=ctx.as_of_utc,
        authority_level="read_only",
        source_refs=ctx.source_refs,
    )


def _build_document(row: dict[str, str], index: int, ctx: _IngestContext) -> DocumentRef:
    return DocumentRef(
        document_id=_required_text(row, "document_id", row_number=index),
        document_type=_required_text(row, "document_type", row_number=index),
        title=_required_text(row, "title", row_number=index),
        path=_required_text(row, "path", row_number=index),
        related_object_id=_optional_text(row, "related_object_id"),
        as_of_utc=ctx.as_of_utc,
        authority_level="read_only",
        source_refs=ctx.source_refs,
    )


_ROW_BUILDERS: dict[str, Callable[[dict[str, str], int, _IngestContext], StateCoreRecord]] = {
    "position": _build_position,
    "liability": _build_liability,
    "goal": _build_goal,
    "cashflow": _build_cashflow,
    "tax_event": _build_tax_event,
    "insurance": _build_insurance,
    "document": _build_document,
}


def _records_from_rows(
    *,
    rows: list[dict[str, str]],
    source_refs: list[str],
    snapshot_id: str,
    as_of_utc: str,
    source_path: Path,
    source_id: str,
    covered_domains: list[str] | None,
    time_semantics: dict[str, str | None],
    findings: list[ImportFinding],
    coverage_mode: str,
) -> list[StateCoreRecord]:
    ctx = _IngestContext(
        snapshot_id=snapshot_id,
        as_of_utc=as_of_utc,
        source_refs=source_refs,
        accounts={},
        account_identities={},
        instrument_identities={},
        aliases={},
        source_namespace=f"{EXPORT_KIND}:{display_path(source_path)}",
    )
    built: list[StateCoreRecord] = [
        _ROW_BUILDERS[_row_type(row)](row, index, ctx) for index, row in enumerate(rows, start=1)
    ]
    from finharness.statecore.store import source_owner_key

    owner_key = source_owner_key(EXPORT_KIND, source_id)
    for record in built:
        if isinstance(record, SourcedStateCoreBase):
            record.source = owner_key
    # When position is in covered_domains, this batch declares portfolio state.
    # Full N->0 must produce an empty portfolio Snapshot; delta zero-row with
    # delta zero-row with base carries prior positions and produces a portfolio Snapshot.
    has_portfolio_domain = "position" in (covered_domains or ())
    _has_positions = any(isinstance(record, Position) for record in built)
    snapshot_kind = (
        "portfolio" if has_portfolio_domain
        else "personal_finance"
    )
    snapshot = Snapshot(
        snapshot_id=snapshot_id,
        kind=snapshot_kind,
        as_of_utc=as_of_utc,
        authority_level="read_only",
        payload=_payload_for_snapshot(
            rows,
            source_path,
            time_semantics=time_semantics,
            findings=findings,
            coverage_mode=coverage_mode,
        ),
        source_refs=source_refs,
    )
    return [
        snapshot,
        *ctx.account_identities.values(),
        *ctx.instrument_identities.values(),
        *ctx.aliases.values(),
        *ctx.accounts.values(),
        *built,
    ]


def _finalize_valuation_on_records(
    records: list[StateCoreRecord],
    *,
    base_findings: list[ImportFinding],
    observed_at_utc: str,
    time_semantics: dict[str, str | None],
    coverage_mode: str,
    rows: list[dict[str, str]],
    source_path: Path,
) -> tuple[list[StateCoreRecord], list[ImportFinding], str]:
    """Assess final Position set, rewrite statuses/findings/completeness/snapshot."""
    positions = [record for record in records if isinstance(record, Position)]
    assessments = assess_positions(positions, evaluated_at_utc=observed_at_utc)
    # Build replacement positions with derived status; avoid mutating SQLModel
    # instances in-place to prevent ObjectDereferencedError.
    status_by_id = {}
    for position, assessment in zip(positions, assessments, strict=True):
        updated = Position(**position.model_dump())
        updated.valuation_status = assessment.status.value
        status_by_id[position.position_id] = updated
    rewritten: list[StateCoreRecord] = []
    for record in records:
        if isinstance(record, Position) and record.position_id in status_by_id:
            rewritten.append(status_by_id[record.position_id])
        else:
            rewritten.append(record)
    final_findings = merge_valuation_findings(base_findings, assessments)
    status = completeness_status(final_findings)
    original_snap = next((item for item in records if isinstance(item, Snapshot)), None)
    prior_delta = {
        key: (original_snap.payload or {}).get(key)
        for key in ("delta_base_batch_id", "materialized_position_count")
        if original_snap is not None and key in (original_snap.payload or {})
    }
    final_position_count = len(status_by_id)
    for record in rewritten:
        if not isinstance(record, Snapshot):
            continue
        payload = _payload_for_snapshot(
            rows,
            source_path,
            time_semantics=time_semantics,
            findings=final_findings,
            coverage_mode=coverage_mode,
        )
        payload.update(prior_delta)
        payload["completeness_status"] = status
        payload["findings"] = [finding.as_dict() for finding in final_findings]
        payload["record_counts"] = payload.get("record_counts", {})
        payload["record_counts"]["position"] = final_position_count
        payload["valuation_assessment"] = valuation_assessment_summary(
            [record for record in rewritten if isinstance(record, Position)],
            evaluated_at_utc=observed_at_utc,
        )
        record.payload = payload
    return rewritten, final_findings, status



def _position_identity(position: Position) -> tuple[str, str]:
    return (
        position.account_id,
        position.instrument_id or f"legacy-symbol:{position.symbol.upper()}",
    )


def _status_counts(
    assessments: list[ValuationAssessment],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for a in assessments:
        counts[a.status.value] = counts.get(a.status.value, 0) + 1
    return counts


def _latest_source_positions(
    *,
    engine: Engine,
    source_id: str,
    exclude_batch_id: str,
    artifact_store: ArtifactStore,
) -> tuple[str | None, list[Position]]:
    with Session(engine) as session:
        manifest = latest_source_manifest_for_domain(
            session,
            source_kind=EXPORT_KIND,
            source_id=source_id,
            domain="position",
            exclude_batch_id=exclude_batch_id,
        )
        if manifest is None:
            head = session.exec(
                select(ImportDomainHead).where(
                    ImportDomainHead.source_kind == EXPORT_KIND,
                    ImportDomainHead.source_id == source_id,
                    ImportDomainHead.domain == "position",
                )
            ).one_or_none()
            if head is None or head.batch_id != exclude_batch_id:
                return None, []
            current_manifest = session.get(ReceiptManifest, head.manifest_id)
            if current_manifest is None:
                return None, []
            try:
                payload = json.loads(
                    artifact_store.read(current_manifest.receipt_artifact_id)
                )
            except (ArtifactStoreError, UnicodeDecodeError, json.JSONDecodeError):
                return None, []
            base_batch_id = (
                str(payload.get("delta_base_batch_id") or "")
                if isinstance(payload, dict)
                else ""
            )
            if not base_batch_id:
                return None, []
            manifest = session.exec(
                select(ReceiptManifest).where(
                    ReceiptManifest.batch_id == base_batch_id
                )
            ).one_or_none()
        if manifest is None:
            return None, []
        positions = session.exec(
            select(Position).where(Position.snapshot_id == manifest.snapshot_id)
        ).all()
        return manifest.batch_id, list(positions)


def _materialize_delta_positions(
    records: list[StateCoreRecord],
    *,
    engine: Engine,
    source_id: str,
    snapshot_id: str,
    as_of_utc: str,
    tombstones: Sequence[ImportDeletion],
    exclude_batch_id: str,
    artifact_store: ArtifactStore,
) -> tuple[list[StateCoreRecord], str | None]:
    base_batch_id, previous = _latest_source_positions(
        engine=engine,
        source_id=source_id,
        exclude_batch_id=exclude_batch_id,
        artifact_store=artifact_store,
    )
    deleted_position_ids = {
        tombstone.record_id for tombstone in tombstones if tombstone.record_type == "Position"
    }
    incoming = [record for record in records if isinstance(record, Position)]
    incoming_keys = {_position_identity(position) for position in incoming}
    carried: list[Position] = []
    for position in previous:
        if position.position_id in deleted_position_ids:
            continue
        if _position_identity(position) in incoming_keys:
            continue
        identity_fragment = position.instrument_id or position.symbol.upper()
        carried.append(
            position.model_copy(
                update={
                    "position_id": _safe_id(
                        f"pos_{snapshot_id}_carried_{position.account_id}_{identity_fragment}"
                    ),
                    "snapshot_id": snapshot_id,
                    "as_of_utc": as_of_utc,
                }
            )
        )
    if not carried:
        return records, base_batch_id
    materialized = [*records, *carried]
    for record in materialized:
        if isinstance(record, Snapshot) and record.snapshot_id == snapshot_id:
            record.payload = {
                **record.payload,
                "delta_base_batch_id": base_batch_id,
                "materialized_position_count": len(incoming) + len(carried),
            }
    return materialized, base_batch_id


def _import_tombstones(
    *,
    batch: ImportBatch,
    deletions: Sequence[ImportDeletion],
) -> list[ImportTombstone]:
    try:
        return [
            build_import_tombstone(
                batch=batch,
                record_type=deletion.record_type,
                record_id=deletion.record_id,
                reason=deletion.reason,
            )
            for deletion in deletions
        ]
    except ImportProvenanceError as exc:
        raise PersonalFinanceExportError(str(exc)) from exc


def _identity_findings(rows: list[dict[str, str]]) -> list[ImportFinding]:
    findings: list[ImportFinding] = []
    for index, row in enumerate(rows, start=1):
        if _row_type(row) != "position":
            continue
        missing = [
            field
            for field in ("instrument_type", "instrument_venue")
            if not (row.get(field) or "").strip()
        ]
        if not missing:
            continue
        finding = unresolved_instrument_finding(record_id=f"row:{index}", missing_fields=missing)
        findings.append(
            ImportFinding(
                finding.code,
                finding.severity,
                finding.message,
                record_type="position",
                record_number=index,
                field=finding.field,
            )
        )
    return findings


def ingest_personal_finance_export(
    export_path: str | Path,
    *,
    engine: Engine,
    receipt_root: str | Path = DEFAULT_PERSONAL_FINANCE_RECEIPT_ROOT,
    artifact_store: ArtifactStore | None = None,
    snapshot_id: str | None = None,
    coverage_mode: Literal["full", "delta"] = "full",
    supersedes_batch_id: str | None = None,
    correction_reason: str | None = None,
    tombstones: Sequence[ImportDeletion] = (),
    covered_domains: Sequence[str] | None = None,
    observed_at_utc: str | None = None,
    _recovery_replay: bool = False,
    _recovery_projection_domains: Sequence[str] | None = None,
) -> PersonalFinanceImportResult:
    """Mirror a FinHarness-contract CSV export into the state core.

    The CSV is treated as input evidence from another tool. This function does
    not parse Beancount ledgers, call broker APIs, place orders, or change risk
    limits.
    """
    source_path = Path(export_path)
    if coverage_mode not in {"full", "delta"}:
        raise PersonalFinanceExportError("coverage_mode must be full or delta")
    rows = _read_rows(source_path)
    if not rows and covered_domains is None:
        raise PersonalFinanceExportError(
            "personal-finance export has no rows and no explicit covered_domains; "
            "zero-row imports require explicit covered_domains"
        )
    for tombstone in tombstones:
        if DELETION_RECORD_DOMAINS.get(tombstone.record_type) is None:
            raise PersonalFinanceExportError(
                f"unsupported import deletion record type: {tombstone.record_type}"
            )
    # Legacy CSV (no record_type column): adapter auto-declares position coverage.
    # Typed CSV (has record_type): full requires explicit covered_domains.
    with source_path.open("r", encoding="utf-8", newline="") as f:
        is_typed = ROW_TYPE_COLUMN in (csv.DictReader(f).fieldnames or ())
    if covered_domains is not None:
        resolved_covered_domains = sorted(set(covered_domains))
    elif is_typed and coverage_mode == "full":
        raise PersonalFinanceExportError(
            "typed multi-domain full import requires explicit covered_domains"
        )
    elif is_typed:
        resolved_covered_domains = sorted({_row_type(row) for row in rows})
    else:
        # Legacy position-only CSV
        resolved_covered_domains = ["position"]
    if not resolved_covered_domains or not set(resolved_covered_domains) <= set(
        RECORD_TYPE_COLUMNS
    ):
        raise PersonalFinanceExportError("covered_domains must use supported record types")
    explicit_deletions = normalize_import_deletions(
        [asdict(tombstone) for tombstone in tombstones]
    )
    source_hash = _file_hash(source_path)
    source_content = source_path.read_bytes()
    source_id = display_path(source_path)
    active_artifact_store = artifact_store or LocalArtifactStore(
        Path(receipt_root) / "artifact-store"
    )
    source_descriptor = persist_source_evidence(
        source_kind=EXPORT_KIND,
        source_content=source_content,
        source_sha256=source_hash,
        artifact_store=active_artifact_store,
        created_at_utc=datetime.now(UTC).isoformat(),
    )
    time_semantics, findings = _time_contract(
        rows, ingested_at_utc=source_descriptor.created_at_utc,
        fallback_observed=observed_at_utc or "",
    )
    findings.extend(_identity_findings(rows))
    as_of_utc = str(time_semantics["observed_at_utc"])
    batch_id = derive_import_batch_id(
        source_kind=EXPORT_KIND,
        source_id=source_id,
        source_sha256=source_hash,
        adapter_version=ADAPTER_VERSION,
        coverage_mode=coverage_mode,
        covered_domains=resolved_covered_domains,
        deletions=explicit_deletions,
        identity_time_semantics=time_semantics,
        supersedes_batch_id=supersedes_batch_id,
        correction_reason=correction_reason,
    )
    identity_suffix = batch_id.removeprefix("import_batch_")
    active_snapshot_id = snapshot_id or f"snap_personal_finance_{identity_suffix}"
    receipt_id = f"receipt_personal_finance_export_{identity_suffix}"
    receipt_path = Path(receipt_root) / f"{receipt_id}.json"
    record_counts = _record_counts(rows)
    receipt_payload = _receipt_payload(
        receipt_id=receipt_id,
        source_path=source_path,
        source_hash=source_hash,
        as_of_utc=as_of_utc,
        row_count=len(rows),
        snapshot_id=active_snapshot_id,
        record_counts=record_counts,
    )
    receipt_ref = display_path(receipt_path)
    source_refs = [receipt_ref, display_path(source_path)]
    records = _records_from_rows(
        rows=rows,
        source_refs=source_refs,
        snapshot_id=active_snapshot_id,
        as_of_utc=as_of_utc,
        source_path=source_path,
        source_id=source_id,
        covered_domains=resolved_covered_domains,
        time_semantics=time_semantics,
        findings=list(findings),
        coverage_mode=coverage_mode,
    )
    delta_base_batch_id: str | None = None
    if coverage_mode == "delta" and "position" in resolved_covered_domains:
        records, delta_base_batch_id = _materialize_delta_positions(
            records,
            engine=engine,
            source_id=source_id,
            snapshot_id=active_snapshot_id,
            as_of_utc=as_of_utc,
            tombstones=tombstones,
            exclude_batch_id=batch_id,
            artifact_store=active_artifact_store,
        )
        if delta_base_batch_id is None:
            raise PersonalFinanceExportError(
                "position delta import requires a materialized position base import"
            )
    records, final_findings, final_completeness = _finalize_valuation_on_records(
        records,
        base_findings=list(findings),
        observed_at_utc=as_of_utc,
        time_semantics=time_semantics,
        coverage_mode=coverage_mode,
        rows=rows,
        source_path=source_path,
    )
    # Materialized position counts include carried rows for delta receipts.
    final_position_count = sum(1 for record in records if isinstance(record, Position))
    record_counts = {**record_counts, "position": final_position_count}
    receipt_payload["record_counts"] = record_counts
    receipt_payload["delta_base_batch_id"] = delta_base_batch_id
    # Compute status counts for valuation_assessment.
    receipt_payload["valuation_assessment"] = valuation_assessment_summary(
        [record for record in records if isinstance(record, Position)],
        evaluated_at_utc=as_of_utc,
    )
    automatic_deletions = (
        plan_full_import_deletions(
            engine=engine,
            source_kind=EXPORT_KIND,
            source_id=source_id,
            covered_domains=resolved_covered_domains,
            records=records,
            batch_id=batch_id,
            artifact_store=active_artifact_store,
            explicit_deletions=explicit_deletions,
        )
        if coverage_mode == "full"
        else []
    )
    receipt_payload["deletion_plan"] = {
        "explicit": explicit_deletions,
        "automatic": automatic_deletions,
        "domain": "personal_finance",
        "covered_domains": resolved_covered_domains,
    }
    receipt_payload["deletions"] = explicit_deletions
    receipt_index = ReceiptIndex(
        receipt_id=receipt_id,
        kind=EXPORT_KIND,
        path=receipt_ref,
        created_at_utc=source_descriptor.created_at_utc,
        source_refs=source_refs,
        refs=[display_path(source_path)],
    )
    expected_materialized_identities = materialized_record_identities(
        [receipt_index, *records]
    )
    prepared = prepare_import(
        source_kind=EXPORT_KIND,
        source_id=source_id,
        source_content=source_content,
        source_sha256=source_hash,
        adapter_version=ADAPTER_VERSION,
        coverage_mode=coverage_mode,
        record_counts=record_counts,
        snapshot_id=active_snapshot_id,
        receipt_id=receipt_id,
        receipt_root=receipt_root,
        receipt_ref=receipt_ref,
        artifact_store=active_artifact_store,
        receipt_payload=receipt_payload,
        created_at_utc=source_descriptor.created_at_utc,
        completeness_status=final_completeness,
        time_semantics=time_semantics,
        findings=[finding.as_dict() for finding in final_findings],
        materialized_record_identities=expected_materialized_identities,
        covered_domains=resolved_covered_domains,
        identity_time_semantics=time_semantics,
        supersedes_batch_id=supersedes_batch_id,
        correction_reason=correction_reason,
        corporate_action_status=(
            "unsupported_gap" if final_position_count else "not_applicable"
        ),
    )
    if prepared.batch.batch_id != batch_id:
        raise PersonalFinanceExportError(
            "derived batch identity diverged from prepare_import batch_id"
        )
    deletion_records = _import_tombstones(batch=prepared.batch, deletions=tombstones)
    materialize_import_batch(
        [receipt_index, *records, *deletion_records],
        source=EXPORT_KIND,
        batch=prepared.batch,
        manifest=prepared.manifest,
        artifact_store=active_artifact_store,
        engine=engine,
        **recovery_materialization_options(
            recovery_replay=_recovery_replay,
            recovery_projection_domains=_recovery_projection_domains,
        ),
    )
    return PersonalFinanceImportResult(
        batch_id=prepared.batch.batch_id,
        manifest_id=prepared.manifest.manifest_id,
        snapshot_id=active_snapshot_id,
        receipt_id=receipt_id,
        receipt_ref=receipt_ref,
        account_count=sum(1 for record in records if isinstance(record, Account)),
        position_count=final_position_count,
        liability_count=sum(1 for record in records if isinstance(record, Liability)),
        goal_count=sum(1 for record in records if isinstance(record, FinancialGoal)),
        cashflow_count=sum(1 for record in records if isinstance(record, CashflowEvent)),
        tax_event_count=sum(1 for record in records if isinstance(record, TaxEvent)),
        insurance_policy_count=sum(1 for record in records if isinstance(record, InsurancePolicy)),
        document_count=sum(1 for record in records if isinstance(record, DocumentRef)),
        as_of_utc=as_of_utc,
        completeness_status=final_completeness,
        execution_allowed=False,
    )


def result_json(result: PersonalFinanceImportResult) -> str:
    return json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
