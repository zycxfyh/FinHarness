# finharness-test-runner: pytest
from __future__ import annotations

import csv
import hashlib
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from scripts.run_capital_readonly_dogfood import run_capital_readonly_dogfood
from scripts.run_scf_capital_dogfood import SCF_CSV_NAME


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


def _scf_zip(tmp_path: Path) -> Path:
    rows = [
        _row(yy1="10", y1="101", weight="3", net_worth="200000"),
        _row(yy1="11", y1="111", weight="1", net_worth="500000"),
    ]
    csv_path = tmp_path / SCF_CSV_NAME
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    archive = tmp_path / "scf.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.write(csv_path, SCF_CSV_NAME)
    return archive


def test_public_dataset_dogfood_is_read_only_and_replayable(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    archive = _scf_zip(tmp_path)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    report = run_capital_readonly_dogfood(
        source_zip=archive,
        output_root=tmp_path / "run",
        expected_sha256=digest,
        now=datetime(2026, 7, 23, tzinfo=UTC),
    )
    assert report["import"]["completeness_status"] == "complete"
    assert report["import"]["conservation"] == {
        "asset_delta": "0.0",
        "debt_delta": "0",
    }
    assert report["work"]["outcome"] == "succeeded"
    assert report["work"]["stop_reason"] == "completed"
    assert report["work"]["audit_disposition"] == "complete"
    assert report["work"]["all_tool_side_effects_read"] is True
    assert report["audit"]["world_status"] == "admitted"
    assert report["audit"]["blockers"] == []
    assert report["hermetic_replay"]["same_typed_contract"] is True
    assert report["read_only_proof"]["logical_db_unchanged"] is True
    assert report["read_only_proof"]["domain_receipts_unchanged"] is True
    assert report["real_model"]["status"] == "unavailable"
    assert report["execution_allowed"] is False
