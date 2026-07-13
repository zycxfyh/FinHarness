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
from collections.abc import Callable
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
from finharness.import_provenance import persist_source_evidence, prepare_import
from finharness.project_paths import ROOT
from finharness.statecore.models import (
    Account,
    CashflowEvent,
    DocumentRef,
    FinancialGoal,
    InsurancePolicy,
    Liability,
    Position,
    ReceiptIndex,
    Snapshot,
    SourcedStateCoreBase,
    TaxEvent,
)
from finharness.statecore.store import (
    StateCoreRecord,
    materialize_import_batch,
)

DEFAULT_PERSONAL_FINANCE_RECEIPT_ROOT = ROOT / "data" / "receipts" / "personal-finance"
ADAPTER_VERSION = "finharness.personal_finance_export.v2"
EXPORT_KIND = "personal_finance_export"
POSITION_COLUMNS = {
    "account_id",
    "account_name",
    "account_kind",
    "venue",
    "symbol",
    "quantity",
    "market_value",
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
        raise PersonalFinanceExportError(
            f"personal-finance export unreadable: {exc}"
        ) from exc


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


def _single_as_of(rows: list[dict[str, str]]) -> str:
    as_of_values = {
        _required_text(row, "as_of_utc", row_number=index)
        for index, row in enumerate(rows, start=1)
    }
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
    rows: list[dict[str, str]], *, ingested_at_utc: str
) -> tuple[dict[str, str | None], list[ImportFinding]]:
    as_of = _single_as_of(rows)
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
        "coverage_mode": "full",
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


def _build_position(row: dict[str, str], index: int, ctx: _IngestContext) -> Position:
    account_id = _required_text(row, "account_id", row_number=index)
    symbol = _required_text(row, "symbol", row_number=index).upper()
    _currency(row, row_number=index)
    ctx.accounts.setdefault(
        account_id,
        Account(
            account_id=account_id,
            kind=_required_text(row, "account_kind", row_number=index),
            venue=_required_text(row, "venue", row_number=index),
            display_name=_required_text(row, "account_name", row_number=index),
            as_of_utc=ctx.as_of_utc,
            authority_level="read_only",
            source_refs=ctx.source_refs,
        ),
    )
    return Position(
        position_id=_safe_id(f"pos_{ctx.snapshot_id}_{index}_{account_id}_{symbol}"),
        snapshot_id=ctx.snapshot_id,
        account_id=account_id,
        symbol=symbol,
        quantity=_decimal_value(row, "quantity", row_number=index),
        market_value=_decimal_value(row, "market_value", row_number=index),
        cost_basis=_optional_decimal(row, "cost_basis", row_number=index),
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
    time_semantics: dict[str, str | None],
    findings: list[ImportFinding],
) -> list[StateCoreRecord]:
    ctx = _IngestContext(
        snapshot_id=snapshot_id,
        as_of_utc=as_of_utc,
        source_refs=source_refs,
        accounts={},
    )
    built: list[StateCoreRecord] = [
        _ROW_BUILDERS[_row_type(row)](row, index, ctx)
        for index, row in enumerate(rows, start=1)
    ]
    # Tag source-owned rows so a re-import replaces exactly this adapter's rows.
    for record in built:
        if isinstance(record, SourcedStateCoreBase):
            record.source = EXPORT_KIND
    # Only stamp a portfolio snapshot when holdings are present; otherwise a
    # liabilities-only (or goals-only) export would shadow the latest real
    # holdings snapshot and zero out the cockpit's positions view.
    has_positions = any(isinstance(record, Position) for record in built)
    snapshot = Snapshot(
        snapshot_id=snapshot_id,
        kind="portfolio" if has_positions else "personal_finance",
        as_of_utc=as_of_utc,
        authority_level="read_only",
        payload=_payload_for_snapshot(
            rows,
            source_path,
            time_semantics=time_semantics,
            findings=findings,
        ),
        source_refs=source_refs,
    )
    return [snapshot, *ctx.accounts.values(), *built]


def ingest_personal_finance_export(
    export_path: str | Path,
    *,
    engine: Engine,
    receipt_root: str | Path = DEFAULT_PERSONAL_FINANCE_RECEIPT_ROOT,
    artifact_store: ArtifactStore | None = None,
    snapshot_id: str | None = None,
) -> PersonalFinanceImportResult:
    """Mirror a FinHarness-contract CSV export into the state core.

    The CSV is treated as input evidence from another tool. This function does
    not parse Beancount ledgers, call broker APIs, place orders, or change risk
    limits.
    """
    source_path = Path(export_path)
    rows = _read_rows(source_path)
    if not rows:
        raise PersonalFinanceExportError("personal-finance export has no rows")
    source_hash = _file_hash(source_path)
    source_content = source_path.read_bytes()
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
        rows, ingested_at_utc=source_descriptor.created_at_utc
    )
    as_of_utc = str(time_semantics["observed_at_utc"])
    base_id = _safe_id(source_hash[:12])
    active_snapshot_id = snapshot_id or f"snap_personal_finance_{base_id}"
    receipt_id = f"receipt_personal_finance_export_{base_id}"
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
    prepared = prepare_import(
        source_kind=EXPORT_KIND,
        source_id=display_path(source_path),
        source_content=source_content,
        source_sha256=source_hash,
        adapter_version=ADAPTER_VERSION,
        coverage_mode="full",
        record_counts=record_counts,
        snapshot_id=active_snapshot_id,
        receipt_id=receipt_id,
        receipt_root=receipt_root,
        receipt_ref=receipt_ref,
        artifact_store=active_artifact_store,
        receipt_payload=receipt_payload,
        created_at_utc=source_descriptor.created_at_utc,
        completeness_status=completeness_status(findings),
        time_semantics=time_semantics,
        findings=[finding.as_dict() for finding in findings],
    )
    source_refs = [receipt_ref, display_path(source_path)]
    receipt_index = ReceiptIndex(
        receipt_id=receipt_id,
        kind=EXPORT_KIND,
        path=receipt_ref,
        created_at_utc=source_descriptor.created_at_utc,
        source_refs=source_refs,
        refs=[display_path(source_path)],
    )
    records = _records_from_rows(
        rows=rows,
        source_refs=source_refs,
        snapshot_id=active_snapshot_id,
        as_of_utc=as_of_utc,
        source_path=source_path,
        time_semantics=time_semantics,
        findings=findings,
    )
    materialize_import_batch(
        [receipt_index, *records],
        source=EXPORT_KIND,
        batch=prepared.batch,
        manifest=prepared.manifest,
        artifact_store=active_artifact_store,
        engine=engine,
    )
    return PersonalFinanceImportResult(
        batch_id=prepared.batch.batch_id,
        manifest_id=prepared.manifest.manifest_id,
        snapshot_id=active_snapshot_id,
        receipt_id=receipt_id,
        receipt_ref=receipt_ref,
        account_count=sum(1 for record in records if isinstance(record, Account)),
        position_count=sum(1 for record in records if isinstance(record, Position)),
        liability_count=sum(1 for record in records if isinstance(record, Liability)),
        goal_count=sum(1 for record in records if isinstance(record, FinancialGoal)),
        cashflow_count=sum(1 for record in records if isinstance(record, CashflowEvent)),
        tax_event_count=sum(1 for record in records if isinstance(record, TaxEvent)),
        insurance_policy_count=sum(
            1 for record in records if isinstance(record, InsurancePolicy)
        ),
        document_count=sum(1 for record in records if isinstance(record, DocumentRef)),
        as_of_utc=as_of_utc,
        completeness_status=completeness_status(findings),
        execution_allowed=False,
    )


def result_json(result: PersonalFinanceImportResult) -> str:
    return json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
