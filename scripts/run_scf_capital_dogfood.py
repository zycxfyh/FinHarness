#!/usr/bin/env python3
"""Run a reproducible Capital World dogfood over Federal Reserve SCF 2022 data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import tempfile
import urllib.request
import zipfile
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from finharness.agent_context import build_capital_summary_context
from finharness.personal_finance import ingest_personal_finance_export
from finharness.statecore.capital_world import resolve_capital_world
from finharness.statecore.store import init_state_core

SCHEMA = "finharness.scf_capital_dogfood.v1"
SCF_URL = "https://www.federalreserve.gov/econres/files/scfp2022excel.zip"
SCF_SHA256 = "9721aa73ef1df237d0c5a7ce2578ff9a45c8e5a2ef8efc4fab132c6885ace050"
SCF_CSV_NAME = "SCFP2022.csv"
SCF_CITATION = {
    "creator": "Board of Governors of the Federal Reserve System",
    "name": "2022 Survey of Consumer Finances",
    "doi": "10.17016/8799",
    "publication_year": 2023,
}

CSV_FIELDS = (
    "record_type",
    "account_id",
    "account_name",
    "account_kind",
    "venue",
    "symbol",
    "instrument_type",
    "instrument_venue",
    "quantity",
    "market_value",
    "cost_basis",
    "currency",
    "as_of_utc",
    "unit_price",
    "valuation_currency",
    "price_currency",
    "valued_at_utc",
    "price_source_ref",
    "fx_rate",
    "fx_as_of_utc",
    "fx_source_ref",
    "effective_at_utc",
    "observed_at_utc",
    "liability_id",
    "name",
    "liability_type",
    "balance",
    "interest_rate",
    "due_date",
    "cashflow_id",
    "description",
    "amount",
    "event_date",
    "category",
    "frequency",
)

ASSET_COMPONENTS = (
    ("FIN", "SCF:FINANCIAL_ASSETS", "financial_assets", "portfolio"),
    ("NFIN", "SCF:NONFINANCIAL_ASSETS", "nonfinancial_assets", "other"),
)
LIABILITY_COMPONENTS = (
    ("MRTHEL", "scf_mortgage_home_equity", "mortgage"),
    ("RESDBT", "scf_other_residential_debt", "mortgage"),
    ("CCBAL", "scf_credit_card_balance", "credit_card"),
    ("INSTALL", "scf_installment_debt", "loan"),
    ("ODEBT", "scf_other_debt", "other"),
)


class ScfDogfoodError(RuntimeError):
    pass


def _download(destination: Path) -> None:
    request = urllib.request.Request(  # noqa: S310 - pinned Federal Reserve HTTPS URL
        SCF_URL,
        headers={"User-Agent": "FinHarness/SCF-dogfood"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 - pinned HTTPS source
        destination.write_bytes(response.read())


def _verify(path: Path) -> str:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != SCF_SHA256:
        raise ScfDogfoodError(f"SCF archive digest mismatch: {digest}")
    return digest


def _decimal(row: dict[str, str], field: str) -> Decimal:
    value = row.get(field, "").strip()
    return Decimal(value or "0")


def _first_implicate(row: dict[str, str]) -> bool:
    value = row.get("Y1", "").strip()
    return value.endswith("1")


def _weighted_median(rows: list[dict[str, str]], field: str) -> Decimal:
    ordered = sorted(rows, key=lambda row: _decimal(row, field))
    total = sum((_decimal(row, "WGT") for row in ordered), Decimal("0"))
    threshold = total / 2
    cumulative = Decimal("0")
    for row in ordered:
        cumulative += _decimal(row, "WGT")
        if cumulative >= threshold:
            return _decimal(row, field)
    raise ScfDogfoodError("SCF weighted median could not be computed")


def select_household(rows: list[dict[str, str]]) -> tuple[dict[str, str], Decimal]:
    eligible = [
        row
        for row in rows
        if _first_implicate(row)
        and _decimal(row, "ASSET") > 0
        and _decimal(row, "DEBT") > 0
        and _decimal(row, "FIN") > 0
        and _decimal(row, "NFIN") > 0
    ]
    if not eligible:
        raise ScfDogfoodError("SCF extract has no eligible first-implicate household")
    median = _weighted_median(eligible, "NETWORTH")
    selected = min(
        eligible,
        key=lambda row: (
            abs(_decimal(row, "NETWORTH") - median),
            int(row["YY1"]),
        ),
    )
    return selected, median


def load_scf_rows(archive: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(archive) as bundle:
        try:
            with bundle.open(SCF_CSV_NAME) as raw:
                text = (line.decode("utf-8-sig") for line in raw)
                return list(csv.DictReader(text))
        except KeyError as exc:
            raise ScfDogfoodError(f"SCF archive omitted {SCF_CSV_NAME}") from exc


def _position_row(
    *,
    symbol: str,
    instrument_type: str,
    account_kind: str,
    amount: Decimal,
    as_of_utc: str,
    source_ref: str,
) -> dict[str, str]:
    text = format(amount.quantize(Decimal("0.01")), "f")
    return {
        "record_type": "position",
        "account_id": f"Assets:SCF:{symbol.split(':')[-1]}",
        "account_name": symbol.replace("SCF:", "SCF ").replace("_", " ").title(),
        "account_kind": account_kind,
        "venue": "federal_reserve_scf",
        "symbol": symbol,
        "instrument_type": instrument_type,
        "instrument_venue": "SCF2022",
        "quantity": "1",
        "market_value": text,
        "currency": "USD",
        "as_of_utc": as_of_utc,
        "unit_price": text,
        "valuation_currency": "USD",
        "price_currency": "USD",
        "valued_at_utc": as_of_utc,
        "price_source_ref": source_ref,
        "effective_at_utc": as_of_utc,
        "observed_at_utc": as_of_utc,
    }


def write_finharness_export(
    household: dict[str, str],
    destination: Path,
    *,
    as_of_utc: str,
) -> dict[str, Any]:
    source_ref = f"dataset:frb-scf-2022:household:{household['YY1']}:implicate:{household['Y1']}"
    rows: list[dict[str, str]] = []
    for field, symbol, instrument_type, account_kind in ASSET_COMPONENTS:
        amount = _decimal(household, field)
        if amount > 0:
            rows.append(
                _position_row(
                    symbol=symbol,
                    instrument_type=instrument_type,
                    account_kind=account_kind,
                    amount=amount,
                    as_of_utc=as_of_utc,
                    source_ref=source_ref,
                )
            )
    for field, liability_id, liability_type in LIABILITY_COMPONENTS:
        amount = _decimal(household, field)
        if amount > 0:
            rows.append(
                {
                    "record_type": "liability",
                    "liability_id": liability_id,
                    "name": field,
                    "liability_type": liability_type,
                    "balance": format(amount.quantize(Decimal("0.01")), "f"),
                    "currency": "USD",
                    "as_of_utc": as_of_utc,
                    "valued_at_utc": as_of_utc,
                    "effective_at_utc": as_of_utc,
                    "observed_at_utc": as_of_utc,
                }
            )
    mapped_assets = sum(
        (_decimal(household, field) for field, *_rest in ASSET_COMPONENTS),
        Decimal("0"),
    )
    mapped_debt = sum(
        (_decimal(household, field) for field, *_rest in LIABILITY_COMPONENTS),
        Decimal("0"),
    )
    expected_assets = _decimal(household, "ASSET")
    expected_debt = _decimal(household, "DEBT")
    if mapped_assets != expected_assets:
        raise ScfDogfoodError(
            f"SCF asset mapping is not conservative: {mapped_assets} != {expected_assets}"
        )
    if mapped_debt != expected_debt:
        raise ScfDogfoodError(
            f"SCF debt mapping is not conservative: {mapped_debt} != {expected_debt}"
        )

    income = _decimal(household, "INCOME")
    if income > 0:
        rows.append(
            {
                "record_type": "cashflow",
                "cashflow_id": "scf_annual_family_income",
                "description": "SCF annual family income",
                "amount": format(income.quantize(Decimal("0.01")), "f"),
                "currency": "USD",
                "event_date": as_of_utc[:10],
                "category": "income",
                "frequency": "annual",
                "as_of_utc": as_of_utc,
                "valued_at_utc": as_of_utc,
                "effective_at_utc": as_of_utc,
                "observed_at_utc": as_of_utc,
            }
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return {
        "source_ref": source_ref,
        "row_count": len(rows),
        "mapped_assets": str(mapped_assets),
        "mapped_debt": str(mapped_debt),
        "asset_delta": str(expected_assets - mapped_assets),
        "debt_delta": str(expected_debt - mapped_debt),
    }


def run_dogfood(
    *,
    source_zip: Path,
    output_root: Path,
    now: datetime,
) -> dict[str, Any]:
    digest = _verify(source_zip)
    rows = load_scf_rows(source_zip)
    household, weighted_median = select_household(rows)
    as_of_utc = now.astimezone(UTC).isoformat()
    source = output_root / "scf-household.csv"
    export = write_finharness_export(household, source, as_of_utc=as_of_utc)
    db = output_root / "state.sqlite"
    receipts = output_root / "receipts"
    engine = init_state_core(db)
    try:
        imported = ingest_personal_finance_export(
            source,
            engine=engine,
            receipt_root=receipts,
        )
        knowledge_cutoff = datetime.now(UTC).isoformat()
        world = resolve_capital_world(
            engine=engine,
            as_of_utc=as_of_utc,
            known_at_utc=knowledge_cutoff,
            use_case="agent_context",
        )
        context = build_capital_summary_context(engine)
    finally:
        engine.dispose()
    if imported.completeness_status != "complete":
        raise ScfDogfoodError(
            "SCF import did not preserve complete explicit clocks: "
            f"{imported.completeness_status}"
        )
    if world.trust.status != "admitted":
        raise ScfDogfoodError(
            f"SCF Capital World was not admitted: {world.trust.status} "
            f"{world.trust.blockers}"
        )
    return {
        "schema": SCHEMA,
        "dataset": {
            "url": SCF_URL,
            "sha256": digest,
            "citation": SCF_CITATION,
            "public_record_count": len(rows),
            "selection": "closest eligible first-implicate household to weighted median NETWORTH",
        },
        "household": {
            "yy1": household["YY1"],
            "y1": household["Y1"],
            "weight": household["WGT"],
            "age": household["AGE"],
            "income": household["INCOME"],
            "assets": household["ASSET"],
            "debt": household["DEBT"],
            "net_worth": household["NETWORTH"],
            "eligible_weighted_median_net_worth": str(weighted_median),
        },
        "import": {
            "batch_id": imported.batch_id,
            "snapshot_id": imported.snapshot_id,
            "completeness_status": imported.completeness_status,
            "generated_rows": export["row_count"],
            "source_ref": export["source_ref"],
            "conservation": {
                "mapped_assets": export["mapped_assets"],
                "mapped_debt": export["mapped_debt"],
                "asset_delta": export["asset_delta"],
                "debt_delta": export["debt_delta"],
            },
        },
        "capital_world": {
            "world_id": world.world_id,
            "basis_digest": world.basis_digest,
            "status": world.trust.status,
            "blockers": list(world.trust.blockers),
            "selected_batch_ids": [item.batch_id for item in world.selected_sources],
        },
        "agent_context": {
            "world_id": context.summary.get("world_id"),
            "trust": context.summary.get("trust"),
            "data_gaps": list(context.data_gaps),
        },
        "execution_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-zip", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="finharness-scf-dogfood-") as tmp:
        root = args.output_root or Path(tmp) / "run"
        root.mkdir(parents=True, exist_ok=True)
        archive = args.source_zip or Path(tmp) / "scfp2022excel.zip"
        if args.source_zip is None:
            _download(archive)
        result = run_dogfood(source_zip=archive, output_root=root, now=datetime.now(UTC))
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
