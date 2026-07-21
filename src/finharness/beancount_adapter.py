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

import base64
import hashlib
import json
from collections.abc import Sequence
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
from finharness.capital_import_valuation import (
    assess_positions,
    merge_valuation_findings,
    valuation_assessment_summary,
)
from finharness.import_provenance import (
    canonical_json_bytes,
    persist_source_evidence,
    prepare_import,
)
from finharness.position_valuation import ValuationEvidence, assess_position_valuation
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
    IdentityAlias,
    InstrumentIdentity,
    Liability,
    Position,
    ReceiptIndex,
    Snapshot,
    utc_now_iso,
)
from finharness.statecore.store import (
    materialize_import_batch,
    recovery_materialization_options,
    source_owner_key,
)

DEFAULT_BEANCOUNT_RECEIPT_ROOT = ROOT / "data" / "receipts" / "beancount"
ADAPTER_VERSION = "finharness.beancount_ledger.v4"
BEANCOUNT_SOURCE_BUNDLE_SCHEMA = "finharness.beancount_source_bundle.v1"
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
) -> tuple[list[str], set[str], str, dict[tuple[str, str], tuple[str, Decimal, str]]]:
    """Return loaded files, operating currencies, effective_at, and direct Price index.

    Price index keys are ``(base_commodity, quote_currency)`` and values are
    ``(valued_at_utc, unit_price, price_source_ref)`` for the latest unambiguous
    direct Price directive.
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
    effective_at = f"{max(dated).isoformat()}T00:00:00+00:00"
    # Collect all direct Price directives; resolve latest per (base, quote).
    by_key: dict[tuple[str, str], list[tuple[Any, Decimal, str, int]]] = {}
    for entry in entries:
        if type(entry).__name__ != "Price":
            continue
        base = str(getattr(entry, "currency", "") or "").upper()
        amount = getattr(entry, "amount", None)
        if not base or amount is None:
            continue
        quote = str(getattr(amount, "currency", "") or "").upper()
        number = getattr(amount, "number", None)
        if not quote or number is None:
            continue
        meta = getattr(entry, "meta", None) or {}
        filename = str(meta.get("filename") or source_path)
        lineno = int(meta.get("lineno") or 0)
        locator = f"{display_path(Path(filename))}#price:{base}/{quote}@{entry.date}:L{lineno}"
        by_key.setdefault((base, quote), []).append(
            (entry.date, Decimal(str(number)), locator, lineno)
        )
    price_index: dict[tuple[str, str], tuple[str, Decimal, str]] = {}
    for key, rows in by_key.items():
        latest_date = max(item[0] for item in rows)
        same_day = [item for item in rows if item[0] == latest_date]
        prices = {item[1] for item in same_day}
        if len(prices) > 1:
            raise BeancountLedgerError(
                "beancount_price_evidence_ambiguous: "
                f"conflicting Price directives for {key[0]}/{key[1]} on {latest_date}"
            )
        _date, price, locator, _lineno = same_day[0]
        valued_at = f"{latest_date.isoformat()}T00:00:00+00:00"
        price_index[key] = (valued_at, price, locator)
    return loaded_files, operating, effective_at, price_index


def _select_direct_price(
    price_index: dict[tuple[str, str], tuple[str, Decimal, str]],
    *,
    commodity: str,
    preferred_quotes: set[str],
) -> tuple[str, Decimal, str, str] | None:
    """Return (valued_at, unit_price, price_source_ref, quote_currency) if any."""
    commodity_key = commodity.upper()
    candidates: list[tuple[str, Decimal, str, str]] = []
    for (base, quote), (valued_at, price, locator) in price_index.items():
        if base != commodity_key:
            continue
        if preferred_quotes and quote not in preferred_quotes:
            continue
        candidates.append((valued_at, price, locator, quote))
    if not candidates and preferred_quotes:
        # Fall back to any quote currency for the commodity.
        for (base, quote), (valued_at, price, locator) in price_index.items():
            if base == commodity_key:
                candidates.append((valued_at, price, locator, quote))
    if not candidates:
        return None
    if len(candidates) > 1:
        # Prefer operating-currency quote if multiple commodities quotes exist.
        preferred = [item for item in candidates if item[3] in preferred_quotes]
        pool = preferred or candidates
        if len({(item[0], item[1], item[3]) for item in pool}) > 1:
            raise BeancountLedgerError(
                "beancount_price_evidence_ambiguous: "
                f"multiple direct Price quotes for {commodity_key}"
            )
        return pool[0]
    return candidates[0]


def _ledger_evidence_bytes(files: list[str]) -> bytes:
    """Return a replayable canonical bundle for the ledger include graph."""
    return canonical_json_bytes(
        {
            "schema": BEANCOUNT_SOURCE_BUNDLE_SCHEMA,
            "files": [
                {
                    "path": display_path(Path(path)),
                    "content_base64": base64.b64encode(Path(path).read_bytes()).decode("ascii"),
                }
                for path in files
            ],
        }
    )


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
    price_index: dict[tuple[str, str], tuple[str, Decimal, str]],
) -> tuple[
    list[Account],
    list[AccountIdentity],
    list[InstrumentIdentity],
    list[IdentityAlias],
    list[Position],
    list[Liability],
    list[str],
    list[str],
]:
    accounts: dict[str, Account] = {}
    account_identities: dict[str, AccountIdentity] = {}
    instrument_identities: dict[str, InstrumentIdentity] = {}
    aliases: dict[str, IdentityAlias] = {}
    positions: list[Position] = []
    liabilities: list[Liability] = []
    data_gaps: list[str] = []
    unresolved_identities: list[str] = []
    source_namespace = f"beancount:{source_refs[-1]}"
    ledger_ref = source_refs[-1]
    for index, (account, currency, units_inv, market_inv) in enumerate(rows, start=1):
        units = _amount(units_inv)
        if units is None or units[0] == 0:
            continue
        market = _amount(market_inv)
        if account.startswith(f"{assets_root}:"):
            account_identity_record, account_alias = account_identity(
                source_namespace=source_namespace,
                source_native_id=account,
                source_refs=source_refs,
            )
            canonical_account_id = account_identity_record.canonical_account_id
            account_identities.setdefault(canonical_account_id, account_identity_record)
            aliases.setdefault(account_alias.alias_id, account_alias)
            accounts.setdefault(
                canonical_account_id,
                Account(
                    account_id=canonical_account_id,
                    canonical_account_id=canonical_account_id,
                    kind="beancount",
                    venue="beancount",
                    display_name=account,
                    as_of_utc=as_of_utc,
                    authority_level="read_only",
                    source_refs=source_refs,
                ),
            )
            commodity = currency.upper()
            position_id = _safe_id(f"pos_{snapshot_id}_{index}_{account}_{currency}")
            instrument_id: str | None = None
            is_cash = commodity in {value.upper() for value in operating_currencies}
            if is_cash:
                instrument, alias = instrument_identity(
                    symbol=currency,
                    instrument_type="cash",
                    venue="global",
                    quote_currency=currency,
                    provider_namespace=source_namespace,
                    source_refs=source_refs,
                )
                instrument_id = instrument.instrument_id
                instrument_identities.setdefault(instrument_id, instrument)
                aliases.setdefault(alias.alias_id, alias)
                try:
                    cash_currency = currency_code(commodity, field="valuation_currency")
                except CapitalImportContractError as exc:
                    raise BeancountLedgerError(str(exc)) from exc
                market_value = units[0]
                unit_price = Decimal("1")
                valuation_currency = cash_currency
                price_currency = cash_currency
                valued_at_utc = as_of_utc
                price_source_ref = f"{ledger_ref}#nominal-cash:{cash_currency}"
            else:
                unresolved_identities.append(commodity)
                direct = _select_direct_price(
                    price_index,
                    commodity=commodity,
                    preferred_quotes={value.upper() for value in operating_currencies},
                )
                if direct is None:
                    market_value = None
                    valuation_currency = None
                    unit_price = None
                    price_currency = None
                    valued_at_utc = None
                    price_source_ref = None
                    data_gaps.append(commodity)
                else:
                    valued_at_utc, unit_price, price_source_ref, quote = direct
                    try:
                        price_currency = currency_code(quote, field="price_currency")
                        valuation_currency = price_currency
                    except CapitalImportContractError as exc:
                        raise BeancountLedgerError(str(exc)) from exc
                    market_value = units[0] * unit_price
                    # beanquery market inventory is not provenance for unit_price.
                    del market_inv, market
            evidence = ValuationEvidence(
                quantity=units[0],
                market_value=market_value,
                valuation_currency=valuation_currency,
                unit_price=unit_price,
                price_currency=price_currency,
                valued_at_utc=valued_at_utc,
                price_source_ref=price_source_ref,
            )
            provisional = assess_position_valuation(
                evidence,
                record_id=position_id,
                record_number=index,
                evaluated_at_utc=as_of_utc,
                check_freshness=False,
                allow_unknown_legacy=False,
            )
            positions.append(
                Position(
                    position_id=position_id,
                    snapshot_id=snapshot_id,
                    account_id=canonical_account_id,
                    instrument_id=instrument_id,
                    symbol=commodity,
                    quantity=units[0],
                    market_value=market_value,
                    valuation_currency=valuation_currency,
                    unit_price=unit_price,
                    price_currency=price_currency,
                    valued_at_utc=valued_at_utc,
                    price_source_ref=price_source_ref,
                    valuation_status=provisional.status.value,
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
    return (
        list(accounts.values()),
        list(account_identities.values()),
        list(instrument_identities.values()),
        list(aliases.values()),
        positions,
        liabilities,
        sorted(set(data_gaps)),
        sorted(set(unresolved_identities)),
    )


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
    _recovery_replay: bool = False,
    _recovery_projection_domains: Sequence[str] | None = None,
) -> BeancountImportResult:
    """Mirror a real Beancount ledger's holdings and liabilities into state core."""
    source_path = Path(ledger_path)
    if not source_path.exists():
        raise BeancountLedgerError(f"beancount ledger missing: {source_path}")
    source_files, operating_currencies, effective_at_utc, price_index = _ledger_metadata(
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
    # Provisional clocks without batch-level valued_at; Position owns valuation times.
    try:
        time_contract, time_findings = build_time_semantics(
            effective_at=effective_at_utc,
            observed_at=source_descriptor.created_at_utc,
            valued_at=None,
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
    (
        accounts,
        account_identities,
        instrument_identities,
        identity_aliases,
        positions,
        liabilities,
        data_gaps,
        unresolved_identities,
    ) = _records_from_rows(
        rows,
        snapshot_id=active_snapshot_id,
        as_of_utc=as_of_utc,
        source_refs=source_refs,
        assets_root=assets_root,
        liabilities_root=liabilities_root,
        operating_currencies=operating_currencies,
        price_index=price_index,
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
    findings.extend(
        ImportFinding(
            finding.code,
            finding.severity,
            finding.message,
            record_type="position",
            field=finding.field,
        )
        for symbol in unresolved_identities
        for finding in [
            unresolved_instrument_finding(
                record_id=f"symbol:{symbol}", missing_fields=("instrument_type", "venue")
            )
        ]
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
    assessments = assess_positions(positions, evaluated_at_utc=as_of_utc)
    # Replace positions with copies carrying derived status (avoid mutating
    # SQLModel instances in-place which triggers ObjectDereferencedError).
    status_map = {}
    for position, assessment in zip(positions, assessments, strict=True):
        p = Position(**position.model_dump())
        p.valuation_status = assessment.status.value
        status_map[position.position_id] = p
    positions = [status_map[p.position_id] for p in positions]
    findings = merge_valuation_findings(findings, assessments)
    ownership_scope = source_owner_key(LEDGER_KIND, display_path(source_path))
    for record in [*liabilities, *cashflows]:
        record.source = ownership_scope
    # Batch-level valued_at is only set when every position agrees; else None.
    position_valued_ats = {
        position.valued_at_utc for position in positions if position.valued_at_utc
    }
    batch_valued_at = next(iter(position_valued_ats)) if len(position_valued_ats) == 1 else None
    try:
        time_contract, _ = build_time_semantics(
            effective_at=effective_at_utc,
            observed_at=source_descriptor.created_at_utc,
            valued_at=batch_valued_at,
            ingested_at=source_descriptor.created_at_utc,
        )
    except CapitalImportContractError as exc:
        raise BeancountLedgerError(str(exc)) from exc
    final_completeness = completeness_status(findings)
    time_semantics = time_contract.as_dict()
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
            "completeness_status": final_completeness,
            "time_semantics": time_semantics,
            "findings": [finding.as_dict() for finding in findings],
            "non_claims": list(NON_CLAIMS),
            "valuation_assessment": valuation_assessment_summary(
                positions,
                evaluated_at_utc=as_of_utc,
            ),
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
    receipt_payload["valuation_assessment"] = valuation_assessment_summary(
        positions,
        evaluated_at_utc=as_of_utc,
    )
    receipt_index = ReceiptIndex(
        receipt_id=receipt_id,
        kind=LEDGER_KIND,
        path=receipt_ref,
        created_at_utc=source_descriptor.created_at_utc,
        source_refs=source_refs,
        refs=[display_path(source_path)],
    )
    expected_materialized_identities = materialized_record_identities(
        [
            receipt_index,
            *account_identities,
            *instrument_identities,
            *identity_aliases,
            *accounts,
            snapshot,
            *positions,
            *liabilities,
            *cashflows,
        ]
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
        completeness_status=final_completeness,
        time_semantics=time_semantics,
        findings=[finding.as_dict() for finding in findings],
        materialized_record_identities=expected_materialized_identities,
        covered_domains=["account", "position", "liability", "cashflow"],
        corporate_action_status="unsupported_gap" if positions else "not_applicable",
    )
    materialize_import_batch(
        [
            receipt_index,
            *account_identities,
            *instrument_identities,
            *identity_aliases,
            *accounts,
            snapshot,
            *positions,
            *liabilities,
            *cashflows,
        ],
        source=LEDGER_KIND,
        batch=prepared.batch,
        manifest=prepared.manifest,
        artifact_store=active_artifact_store,
        engine=engine,
        **recovery_materialization_options(
            recovery_replay=_recovery_replay,
            recovery_projection_domains=_recovery_projection_domains,
        ),
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
        as_of_utc=as_of_utc,
        completeness_status=final_completeness,
        cashflow_count=len(cashflows),
        execution_allowed=False,
    )


def result_json(result: BeancountImportResult) -> str:
    return json.dumps(result.as_dict(), ensure_ascii=False, indent=2, sort_keys=True)
