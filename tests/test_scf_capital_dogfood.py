# finharness-test-runner: pytest
from __future__ import annotations

import csv
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from scripts.run_scf_capital_dogfood import (
    SCF_CSV_NAME,
    SCF_SHA256,
    load_scf_rows,
    select_household,
    write_finharness_export,
)


def _row(*, yy1: str, y1: str, weight: str, net_worth: str) -> dict[str, str]:
    assets = str(float(net_worth) + 100000)
    return {
        "YY1": yy1,
        "Y1": y1,
        "WGT": weight,
        "AGE": "40",
        "INCOME": "80000",
        "FIN": "50000",
        "NFIN": str(float(assets) - 50000),
        "ASSET": assets,
        "MRTHEL": "70000",
        "RESDBT": "0",
        "CCBAL": "5000",
        "INSTALL": "15000",
        "ODEBT": "10000",
        "DEBT": "100000",
        "NETWORTH": net_worth,
    }


def test_selects_closest_first_implicate_to_weighted_median() -> None:
    rows = [
        _row(yy1="1", y1="11", weight="1", net_worth="100000"),
        _row(yy1="1", y1="12", weight="1", net_worth="900000"),
        _row(yy1="2", y1="21", weight="3", net_worth="200000"),
        _row(yy1="3", y1="31", weight="1", net_worth="900000"),
    ]
    selected, median = select_household(rows)
    assert selected["YY1"] == "2"
    assert selected["Y1"] == "21"
    assert str(median) == "200000"


def test_scf_zip_and_generated_export_are_deterministic(tmp_path: Path) -> None:
    archive = tmp_path / "scf.zip"
    rows = [
        _row(yy1="10", y1="101", weight="1", net_worth="200000"),
        _row(yy1="11", y1="111", weight="1", net_worth="300000"),
    ]
    columns = list(rows[0])
    csv_path = tmp_path / SCF_CSV_NAME
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.write(csv_path, SCF_CSV_NAME)

    loaded = load_scf_rows(archive)
    selected, _median = select_household(loaded)
    destination = tmp_path / "capital.csv"
    metadata = write_finharness_export(
        selected,
        destination,
        as_of_utc=datetime(2026, 7, 23, tzinfo=UTC).isoformat(),
    )
    generated = list(csv.DictReader(destination.open(encoding="utf-8")))
    assert metadata["row_count"] == 7
    assert metadata["asset_delta"] == "0.0"
    assert metadata["debt_delta"] == "0"
    assert {row["record_type"] for row in generated} == {
        "position",
        "liability",
        "cashflow",
    }
    assert sum(float(row["market_value"] or 0) for row in generated) == float(
        selected["ASSET"]
    )
    assert sum(float(row["balance"] or 0) for row in generated) == float(
        selected["DEBT"]
    )
    assert len(SCF_SHA256) == 64
