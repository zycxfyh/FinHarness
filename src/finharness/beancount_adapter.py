"""Read-only Beancount ledger adapter via bean-query.

This adapter connects to a real Beancount ledger with the mature ``beanquery``
engine (the ``bean-query`` tool), reads holdings and liability balances, and
mirrors them into the state core with a receipt. Unlike the hand-written CSV
import contract in ``finharness.personal_finance``, this needs no intermediate
file: it queries the ledger directly.

FinHarness does not write the ledger, place orders, value tax positions, or
change risk limits. The ledger remains the source of truth; the state core
only holds a read-only mirror plus a receipt.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

import beanquery
from beancount import loader
from sqlalchemy import Engine

from finharness.artifact_store import ArtifactStore, LocalArtifactStore
from finharness.capital_import_contract import (
    CapitalImportContractError,
    ImportFinding,
    build_time_semantics,
    completeness_status,
    currency_code,
)
from finharness.import_provenance import persist_source_evidence, prepare_import
from finharness.project_paths import ROOT
from finharness.statecore.models import (
    Account,
    CashflowEvent,
    Liability,
    Position,
    ReceiptIndex,
    Snapshot,
    utc_now_iso,
)
from finharness.statecore.store import (
    StateCoreRecord,
    materialize_import_batch,
)

DEFAULT_BEANCOUNT_RECEIPT_ROOT = ROOT / "data" / "receipts" / "beancount"
ADAPTER_VERSION = "finharness.beancount_ledger.v2"
LEDGER_KIND = "beancount_ledger"
DEFAULT_ASSETS_ROOT = "Assets"
DEFAULT_LIABILITIES_ROOT = "Liabilities"
NON_CLAIMS = (
    "Read-only Beancount ledger mirror via bean-query.",
    "Not tax, accounting, or investment advice.",
    "Not execution authorization.",
)

# Static query: classify by account root in Python rather than building SQL
# dynamically, so root names stay configurable without string-formatted SQL.
BALANCES_QUERY = (
    "SELECT account, currency, "
    "units(sum(position)) AS units, value(sum(position)) AS market "
    "GROUP BY account, currency ORDER BY account, currency"
)

# Recurring cashflow run-rate: monthly Income/Expenses totals. Static query (no
# injected dates); the trailing window and base-currency extraction happen in
# Python so the SQL stays fixed and currency-agnostic.
CASHFLOW_QUERY = (
    "SELECT year, month, root(account, 1) AS cat, sum(position) AS total "
    "WHERE account ~ '^(Income|Expenses):' "
    "GROUP BY year, month, cat ORDER BY year, month"
)
CASHFLOW_WINDOW_MONTHS = 6


class BeancountLedgerError(RuntimeError):
    """Raised when a Beancount ledger cannot be safely ingested."""


@dataclass(frozen=True)
class BeancountImportResult:
    batch_id: str
    manifest_id: str
    snapshot_id: str
    receipt_id: str
    receipt_ref: str
    account_count: int
    position_count: int
    liability_count: int
    as_of_utc: str
    completeness_status: str
    cashflow_count: int = 0
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


def _ledger_metadata(
    source_path: Path,
) -> tuple[list[str], set[str], str, str | None]:
    """Return the ledger's loaded files and its declared operating currencies.

    Beancount already reports every loaded file as an absolute path in
    ``options_map["include"]`` (even when the ledger was opened with a relative
    path), so each entry only needs ``resolve`` to dedupe. The fallback resolves a
    lone relative ``source_path`` against the current directory.
    """
    entries, errors, options_map = loader.load_file(str(source_path))
    if errors:
        raise BeancountLedgerError(
            f"beancount loader reported {len(errors)} error(s); partial import denied"
        )
    included = options_map.get("include") or [str(source_path)]
    loaded_files = sorted({str(Path(raw_path).resolve()) for raw_path in included})
    try:
        operating = {currency_code(value) for value in options_map.get("operating_currency", [])}
    except CapitalImportContractError as exc:
        raise BeancountLedgerError(str(exc)) from exc
    dated = [entry.date for entry in entries if getattr(entry, "date", None) is not None]
    if not dated:
        raise BeancountLedgerError("beancount ledger has no effective dated entries")
    price_dates = [
        entry.date
        for entry in entries
        if type(entry).__name__ == "Price" and getattr(entry, "date", None) is not None
    ]
    effective_at = f"{max(dated).isoformat()}T00:00:00+00:00"
    valued_at = (
        f"{max(price_dates).isoformat()}T00:00:00+00:00" if price_dates else None
    )
    return loaded_files, operating, effective_at, valued_at


def _ledger_evidence_bytes(files: list[str]) -> bytes:
    """Canonical byte stream over the loaded ledger and every included file."""
    evidence = bytearray()
    for path in files:
        evidence.extend(Path(path).read_bytes())
        evidence.extend(b"\x00")
    return bytes(evidence)


def _combined_ledger_hash(files: list[str]) -> str:
    """Content hash over the whole ledger so any included file change is reflected."""
    return hashlib.sha256(_ledger_evidence_bytes(files)).hexdigest()


def _amount(inventory: Any) -> tuple[Decimal, str] | None:
    """Return the first (number, currency) of a beanquery Inventory cell."""
    positions = list(inventory)
    if not positions:
        return None
    units = positions[0].units
    return units.number, units.currency


def _query_rows(ledger_path: Path) -> list[tuple[str, str, Any, Any]]:
    try:
        connection = beanquery.connect(f"beancount:{ledger_path}")
        cursor = connection.execute(BALANCES_QUERY)
        return list(cursor.fetchall())
    except beanquery.Error as exc:
        raise BeancountLedgerError(f"beancount ledger query failed: {exc}") from exc


def _currency_amount(inventory: Any, currency: str) -> Decimal:
    """Sum only the given currency's units from a beanquery Inventory cell.

    Income/Expenses legs may carry pseudo-commodities (e.g. IRA contribution
    limits, vacation hours) alongside real money; those are ignored here so the
    run-rate is in real base currency, not a mix of unrelated units.
    """
    total = Decimal("0")
    for position in inventory:
        if position.units.currency == currency:
            total += position.units.number
    return total


def _cashflow_rows(ledger_path: Path) -> list[tuple[Any, Any, str, Any]]:
    try:
        connection = beanquery.connect(f"beancount:{ledger_path}")
        cursor = connection.execute(CASHFLOW_QUERY)
        return list(cursor.fetchall())
    except beanquery.Error as exc:
        raise BeancountLedgerError(f"beancount cashflow query failed: {exc}") from exc


def _derive_cashflows(
    rows: list[tuple[Any, Any, str, Any]],
    *,
    as_of_utc: str,
    source_refs: list[str],
    operating_currencies: set[str],
) -> list[CashflowEvent]:
    """Derive recurring monthly income/expense run-rate from ledger flows.

    Requires a single operating currency (otherwise the run-rate base is
    ambiguous and we derive nothing, leaving exposure to disclose the gap). The
    most recent month is dropped as likely-partial when history allows, then up
    to ``CASHFLOW_WINDOW_MONTHS`` complete months are averaged.
    """
    if len(operating_currencies) != 1:
        return []
    base = next(iter(operating_currencies))
    income: dict[tuple[int, int], Decimal] = {}
    expense: dict[tuple[int, int], Decimal] = {}
    for year, month, cat, total in rows:
        amount = _currency_amount(total, base)
        key = (int(year), int(month))
        if cat == "Income":
            # Income postings are credits (negative); flip to a positive inflow.
            income[key] = income.get(key, Decimal("0")) - amount
        elif cat == "Expenses":
            expense[key] = expense.get(key, Decimal("0")) + amount
    months = sorted(set(income) | set(expense))
    if not months:
        return []
    complete = months[:-1] if len(months) >= 2 else months
    window = complete[-CASHFLOW_WINDOW_MONTHS:]
    if not window:
        return []
    count = Decimal(len(window))
    avg_income = sum((income.get(m, Decimal("0")) for m in window), Decimal("0")) / count
    avg_expense = sum((expense.get(m, Decimal("0")) for m in window), Decimal("0")) / count
    last_year, last_month = window[-1]
    # Anchor to the last complete window month (a past date) so the run-rate
    # marker is not mistaken for a specific upcoming dated obligation.
    event_date = f"{last_year:04d}-{last_month:02d}-01"
    events: list[CashflowEvent] = []
    if avg_income > 0:
        events.append(
            CashflowEvent(
                cashflow_id="cf_beancount_recurring_income",
                description=f"Recurring monthly income (derived, {len(window)}-month average)",
                amount=avg_income,
                currency=base,
                event_date=event_date,
                category="income",
                frequency="monthly",
                as_of_utc=as_of_utc,
                authority_level="read_only",
                source=LEDGER_KIND,
                source_refs=source_refs,
            )
        )
    if avg_expense > 0:
        events.append(
            CashflowEvent(
                cashflow_id="cf_beancount_recurring_expenses",
                description=f"Recurring monthly expenses (derived, {len(window)}-month average)",
                amount=-avg_expense,
                currency=base,
                event_date=event_date,
                category="expense",
                frequency="monthly",
                as_of_utc=as_of_utc,
                authority_level="read_only",
                source=LEDGER_KIND,
                source_refs=source_refs,
            )
        )
    return events


def _records_from_rows(
    rows: list[tuple[str, str, Any, Any]],
    *,
    snapshot_id: str,
    as_of_utc: str,
    source_refs: list[str],
    assets_root: str,
    liabilities_root: str,
    operating_currencies: set[str],
) -> tuple[list[Account], list[Position], list[Liability], list[str]]:
    accounts: dict[str, Account] = {}
    positions: list[Position] = []
    liabilities: list[Liability] = []
    data_gaps: list[str] = []
    for index, (account, currency, units_inv, market_inv) in enumerate(rows, start=1):
        units = _amount(units_inv)
        if units is None or units[0] == 0:
            continue
        market = _amount(market_inv)
        if account.startswith(f"{assets_root}:"):
            accounts.setdefault(
                account,
                Account(
                    account_id=_safe_id(account),
                    kind="beancount",
                    venue="beancount",
                    display_name=account,
                    as_of_utc=as_of_utc,
                    authority_level="read_only",
                    source_refs=source_refs,
                ),
            )
            # With no price, value() returns the holding in its own commodity
            # (market currency == units currency, not an operating currency), so
            # the "value" is really a unit count. Do not present that as money:
            # record a data gap and keep the holding (quantity is correct) at 0.
            if market is None or (
                bool(operating_currencies)
                and market[1] == currency
                and currency not in operating_currencies
            ):
                market_value = Decimal("0")
                data_gaps.append(currency.upper())
            else:
                market_value = market[0]
                try:
                    currency_code(market[1], field="valuation_currency")
                except CapitalImportContractError as exc:
                    raise BeancountLedgerError(str(exc)) from exc
            positions.append(
                Position(
                    position_id=_safe_id(f"pos_{snapshot_id}_{index}_{account}_{currency}"),
                    snapshot_id=snapshot_id,
                    account_id=_safe_id(account),
                    symbol=currency.upper(),
                    quantity=units[0],
                    market_value=market_value,
                    as_of_utc=as_of_utc,
                    authority_level="read_only",
                    source_refs=source_refs,
                )
            )
        elif account.startswith(f"{liabilities_root}:"):
            balance, balance_ccy = market if market is not None else units
            try:
                balance_ccy = currency_code(balance_ccy)
            except CapitalImportContractError as exc:
                raise BeancountLedgerError(str(exc)) from exc
            liabilities.append(
                Liability(
                    liability_id=_safe_id(f"liab_{account}_{currency}"),
                    name=account,
                    liability_type=account.split(":", 1)[1].split(":", 1)[0],
                    balance=abs(balance),
                    currency=balance_ccy,
                    as_of_utc=as_of_utc,
                    authority_level="read_only",
                    source=LEDGER_KIND,
                    source_refs=source_refs,
                )
            )
    return list(accounts.values()), positions, liabilities, sorted(set(data_gaps))


def _receipt_payload(
    *,
    receipt_id: str,
    source_path: Path,
    source_hash: str,
    source_files: list[str],
    as_of_utc: str,
    snapshot_id: str,
    account_count: int,
    position_count: int,
    liability_count: int,
    cashflow_count: int,
    data_gaps: list[str],
) -> dict[str, Any]:
    return {
        "receipt_id": receipt_id,
        "kind": LEDGER_KIND,
        "adapter_version": ADAPTER_VERSION,
        "created_at_utc": as_of_utc,
        "source_ref": display_path(source_path),
        "source_sha256": source_hash,
        "source_files": [display_path(Path(path)) for path in source_files],
        "snapshot_id": snapshot_id,
        "record_counts": {
            "account": account_count,
            "position": position_count,
            "liability": liability_count,
            "cashflow": cashflow_count,
        },
        "data_gaps_unpriced": data_gaps,
        "non_claims": list(NON_CLAIMS),
        "execution_allowed": False,
    }


def ingest_beancount_ledger(
    ledger_path: str | Path,
    *,
    engine: Engine,
    receipt_root: str | Path = DEFAULT_BEANCOUNT_RECEIPT_ROOT,
    artifact_store: ArtifactStore | None = None,
    snapshot_id: str | None = None,
    assets_root: str = DEFAULT_ASSETS_ROOT,
    liabilities_root: str = DEFAULT_LIABILITIES_ROOT,
) -> BeancountImportResult:
    """Mirror a real Beancount ledger's holdings and liabilities into state core."""
    source_path = Path(ledger_path)
    if not source_path.exists():
        raise BeancountLedgerError(f"beancount ledger missing: {source_path}")
    source_files, operating_currencies, effective_at_utc, valued_at_utc = _ledger_metadata(
        source_path
    )
    rows = _query_rows(source_path)
    source_content = _ledger_evidence_bytes(source_files)
    source_hash = _combined_ledger_hash(source_files)
    active_artifact_store = artifact_store or LocalArtifactStore(
        Path(receipt_root) / "artifact-store"
    )
    source_descriptor = persist_source_evidence(
        source_kind=LEDGER_KIND,
        source_content=source_content,
        source_sha256=source_hash,
        artifact_store=active_artifact_store,
        created_at_utc=utc_now_iso(),
    )
    try:
        time_contract, time_findings = build_time_semantics(
            effective_at=effective_at_utc,
            observed_at=source_descriptor.created_at_utc,
            valued_at=valued_at_utc,
            ingested_at=source_descriptor.created_at_utc,
        )
    except CapitalImportContractError as exc:
        raise BeancountLedgerError(str(exc)) from exc
    as_of_utc = time_contract.observed_at_utc
    base_id = _safe_id(source_hash[:12])
    active_snapshot_id = snapshot_id or f"snap_beancount_{base_id}"
    receipt_id = f"receipt_beancount_ledger_{base_id}"
    receipt_path = Path(receipt_root) / f"{receipt_id}.json"
    receipt_ref = display_path(receipt_path)
    source_refs = [receipt_ref, display_path(source_path)]
    accounts, positions, liabilities, data_gaps = _records_from_rows(
        rows,
        snapshot_id=active_snapshot_id,
        as_of_utc=as_of_utc,
        source_refs=source_refs,
        assets_root=assets_root,
        liabilities_root=liabilities_root,
        operating_currencies=operating_currencies,
    )
    if not positions and not liabilities:
        raise BeancountLedgerError(
            "beancount ledger has no Assets or Liabilities balances to mirror"
        )
    findings = list(time_findings)
    findings.extend(
        ImportFinding(
            "unpriced_position",
            "partial",
            f"{symbol} has no admitted monetary valuation",
            record_type="position",
            field="market_value",
        )
        for symbol in data_gaps
    )
    if positions and valued_at_utc is None:
        findings.append(
            ImportFinding(
                "valuation_time_missing",
                "blocking",
                "holdings exist but the ledger has no dated price evidence",
                record_type="position",
                field="valued_at_utc",
            )
        )
    cashflow_rows = _cashflow_rows(source_path)
    if cashflow_rows and len(operating_currencies) != 1:
        findings.append(
            ImportFinding(
                "cashflow_currency_ambiguous",
                "partial",
                "cashflow rows were omitted because one operating currency was not declared",
                record_type="cashflow",
                field="currency",
            )
        )
    cashflows = _derive_cashflows(
        cashflow_rows,
        as_of_utc=as_of_utc,
        source_refs=source_refs,
        operating_currencies=operating_currencies,
    )
    snapshot = Snapshot(
        snapshot_id=active_snapshot_id,
        kind="portfolio" if positions else "personal_finance",
        as_of_utc=as_of_utc,
        authority_level="read_only",
        payload={
            "source": LEDGER_KIND,
            "source_ref": display_path(source_path),
            "adapter_version": ADAPTER_VERSION,
            "record_counts": {
                "account": len(accounts),
                "position": len(positions),
                "liability": len(liabilities),
                "cashflow": len(cashflows),
            },
            "data_gaps_unpriced": data_gaps,
            "coverage_mode": "full",
            "completeness_status": completeness_status(findings),
            "time_semantics": time_contract.as_dict(),
            "findings": [finding.as_dict() for finding in findings],
            "non_claims": list(NON_CLAIMS),
        },
        source_refs=source_refs,
    )
    receipt_payload = _receipt_payload(
        receipt_id=receipt_id,
        source_path=source_path,
        source_hash=source_hash,
        source_files=source_files,
        as_of_utc=as_of_utc,
        snapshot_id=active_snapshot_id,
        account_count=len(accounts),
        position_count=len(positions),
        liability_count=len(liabilities),
        cashflow_count=len(cashflows),
        data_gaps=data_gaps,
    )
    prepared = prepare_import(
        source_kind=LEDGER_KIND,
        source_id=display_path(source_path),
        source_content=source_content,
        source_sha256=source_hash,
        adapter_version=ADAPTER_VERSION,
        coverage_mode="full",
        record_counts={
            "account": len(accounts),
            "position": len(positions),
            "liability": len(liabilities),
            "cashflow": len(cashflows),
        },
        snapshot_id=active_snapshot_id,
        receipt_id=receipt_id,
        receipt_root=receipt_root,
        receipt_ref=receipt_ref,
        artifact_store=active_artifact_store,
        receipt_payload=receipt_payload,
        created_at_utc=as_of_utc,
        completeness_status=completeness_status(findings),
        time_semantics=time_contract.as_dict(),
        findings=[finding.as_dict() for finding in findings],
    )
    receipt_index = ReceiptIndex(
        receipt_id=receipt_id,
        kind=LEDGER_KIND,
        path=receipt_ref,
        created_at_utc=source_descriptor.created_at_utc,
        source_refs=source_refs,
        refs=[display_path(source_path)],
    )
    records: list[StateCoreRecord] = [
        snapshot,
        *accounts,
        *positions,
        *liabilities,
        *cashflows,
    ]
    materialize_import_batch(
        [receipt_index, *records],
        source=LEDGER_KIND,
        batch=prepared.batch,
        manifest=prepared.manifest,
        artifact_store=active_artifact_store,
        engine=engine,
    )
    return BeancountImportResult(
        batch_id=prepared.batch.batch_id,
        manifest_id=prepared.manifest.manifest_id,
        snapshot_id=active_snapshot_id,
        receipt_id=receipt_id,
        receipt_ref=receipt_ref,
        account_count=len(accounts),
        position_count=len(positions),
        liability_count=len(liabilities),
        cashflow_count=len(cashflows),
        as_of_utc=as_of_utc,
        completeness_status=completeness_status(findings),
    )


def result_json(result: BeancountImportResult) -> str:
    return json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
