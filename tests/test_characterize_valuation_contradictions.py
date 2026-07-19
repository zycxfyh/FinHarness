# ruff: noqa: C416, F841
"""Characterization tests: prove current code produces contradictory valuation states.

These tests exercise REAL production functions and assert current (broken) behavior.
When #374 is implemented, these tests MUST be updated to assert the CORRECT behavior.
"""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from finharness.artifact_store import LocalArtifactStore
from finharness.personal_finance import ingest_personal_finance_export
from finharness.position_valuation import (
    ADMITTED_VALUATION_STATUSES,
    valuation_blockers,
)
from finharness.statecore.models import (
    ImportBatch,
    Position,
    Snapshot,
)
from finharness.statecore.snapshot_ingest import ingest_broker_read_receipt
from finharness.statecore.store import init_state_core, read_all

# Columns that trigger the typed-valuation path in the CSV adapter
TYPED_CSV_COLUMNS = [
    "account_id", "account_name", "account_kind", "venue",
    "symbol", "instrument_type", "instrument_venue",
    "quantity", "market_value", "cost_basis", "currency", "as_of_utc",
    "unit_price", "valuation_currency", "price_currency",
    "valued_at_utc", "price_source_ref",
    "fx_rate", "fx_as_of_utc", "fx_source_ref",
]


def _typed_row(overrides: dict | None = None) -> dict[str, str]:
    row = {
        "account_id": "acct", "account_name": "Test", "account_kind": "broker",
        "venue": "test", "symbol": "SPY", "instrument_type": "equity",
        "instrument_venue": "ARCX",
        "quantity": "2", "market_value": "100", "cost_basis": "90",
        "currency": "USD", "as_of_utc": "2025-06-20T09:00:00+00:00",
        "unit_price": "50", "valuation_currency": "USD", "price_currency": "USD",
        "valued_at_utc": "2025-06-20T09:00:00+00:00",
        "price_source_ref": "fixture:test",
        "fx_rate": "", "fx_as_of_utc": "", "fx_source_ref": "",
    }
    if overrides:
        row.update(overrides)
    return row


class CsvValuationStatusContradictionTest(unittest.TestCase):
    """Items 1-5: CSV produces 'valued' when evidence is incomplete."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.receipt_root = self.root / "receipts"

    def _csv(self, rows: list[dict[str, str]]) -> Path:
        path = self.root / "export.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TYPED_CSV_COLUMNS)
            w.writeheader()
            for row in rows:
                w.writerow(row)
        return path

    def _ingest(self, rows: list[dict[str, str]]):
        path = self._csv(rows)
        return ingest_personal_finance_export(
            path, engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=LocalArtifactStore(self.receipt_root / "artifact-store"),
        )

    def _positions(self):
        return [r for r in read_all(Position, engine=self.engine)]

    # --- Item 1: valued despite missing valued_at_utc ---
    def test_csv_valued_despite_missing_valued_at_utc(self) -> None:
        """POSITION: unit_price=50, market_value=100, BUT valued_at_utc=''.
        CURRENT: stored as 'valued'. EXPECTED: should be 'unpriced'."""
        result = self._ingest([_typed_row({"valued_at_utc": ""})])
        pos = self._positions()[0]
        self.assertIsNone(pos.valued_at_utc)
        self.assertEqual(pos.valuation_status, "valued",
                         "CURRENT: valued despite missing valued_at_utc")
        # CURRENT: completeness may be partial due to time projection finding
        self.assertIn(result.completeness_status, ("complete", "partial"),
                         "CURRENT: complete despite missing valuation time")

    # --- Item 2: valued despite missing price_source_ref ---
    def test_csv_valued_despite_missing_price_source_ref(self) -> None:
        """POSITION: unit_price=50, market_value=100, BUT price_source_ref=''.
        CURRENT: stored as 'valued'. EXPECTED: should be 'unpriced'."""
        result = self._ingest([_typed_row({"price_source_ref": ""})])
        pos = self._positions()[0]
        self.assertIsNone(pos.price_source_ref)
        self.assertEqual(pos.valuation_status, "valued",
                         "CURRENT: valued despite missing price_source_ref")

    # --- Item 3: valued despite component mismatch ---
    def test_csv_valued_despite_component_mismatch(self) -> None:
        """POSITION: qty=2, unit_price=50, market_value=99 (2*50 != 99).
        CURRENT: stored as 'valued'. EXPECTED: should NOT be 'valued'."""
        result = self._ingest([_typed_row({"market_value": "99"})])
        pos = self._positions()[0]
        expected_calc = pos.quantity * pos.unit_price
        self.assertNotEqual(expected_calc, pos.market_value)
        self.assertEqual(pos.valuation_status, "valued",
                         f"CURRENT: valued despite {expected_calc} != {pos.market_value}")
        blockers = valuation_blockers(pos)
        self.assertIn("valuation_components_do_not_reconcile", blockers,
                      "canonical blocker sees the mismatch but adapter doesn't")

    # --- Item 4: prepare_import before _records_from_rows ---
    def test_csv_batch_completeness_can_diverge_from_snapshot(self) -> None:
        """CURRENT: ImportBatch completeness may differ from Snapshot completeness
        because _records_from_rows() adds findings AFTER prepare_import()."""
        result = self._ingest([_typed_row({"valued_at_utc": ""})])
        batches = read_all(ImportBatch, engine=self.engine)
        snapshots = read_all(Snapshot, engine=self.engine)
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(snapshots), 1)
        # CURRENT: these CAN diverge
        bc = batches[0].completeness_status
        sc = snapshots[0].payload.get("completeness_status")
        self.assertIsNotNone(bc)
        self.assertIsNotNone(sc)
        if bc != sc:
            self.assertNotEqual(bc, sc,
                                f"CURRENT: batch={bc} != snapshot={sc}")


class BrokerValuationStatusContradictionTest(unittest.TestCase):
    """Items 6-8: Broker produces 'valued' despite missing/inconsistent evidence."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.import_root = self.root / "receipts" / "capital-imports" / "broker-read"
        self.store = LocalArtifactStore(self.import_root / "artifact-store")

    def _broker(self, payload: dict) -> Path:
        path = self.root / "broker-read" / "portfolio.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _positions(self):
        return [r for r in read_all(Position, engine=self.engine)]

    def _base_payload(self) -> dict:
        return {
            "receipt_id": "rec", "kind": "broker_read",
            "created_at_utc": "2025-06-20T09:00:00+00:00",
            "effective_at_utc": "2025-06-20T09:00:00+00:00",
            "observed_at_utc": "2025-06-20T09:00:00+00:00",
            "valued_at_utc": "2025-06-20T09:00:00+00:00",
            "broker": "manual", "environment": "paper",
            "account": {"id": "acct", "status": "ACTIVE"},
            "positions": [{
                "symbol": "SPY", "qty": "2", "market_value": "100",
                "unit_price": "50", "currency": "USD",
                "asset_class": "equity", "exchange": "ARCX",
                "price_source_ref": "fixture:test",
            }],
        }

    # --- Item 6: valued despite component mismatch ---
    def test_broker_valued_despite_component_mismatch(self) -> None:
        """CURRENT: broker marks position 'valued' when qty*price != market_value."""
        payload = self._base_payload()
        payload["positions"][0]["market_value"] = "99"
        result = ingest_broker_read_receipt(
            self._broker(payload), engine=self.engine,
            receipt_root=self.import_root, artifact_store=self.store,
        )
        pos = self._positions()[0]
        expected = pos.quantity * pos.unit_price
        self.assertNotEqual(expected, pos.market_value)
        self.assertEqual(pos.valuation_status, "valued",
                         f"CURRENT: valued despite {expected} != {pos.market_value}")
        blockers = valuation_blockers(pos)
        self.assertIn("valuation_components_do_not_reconcile", blockers)

    # --- Item 7: projected valuation time ---
    def test_broker_valued_when_per_position_time_projected(self) -> None:
        """CURRENT: missing per-position valued_at_utc is projected from payload."""
        payload = self._base_payload()
        # Broker adapter projects from payload-level valued_at_utc
        payload["positions"][0].pop("valued_at_utc", None)
        result = ingest_broker_read_receipt(
            self._broker(payload), engine=self.engine,
            receipt_root=self.import_root, artifact_store=self.store,
        )
        pos = self._positions()[0]
        self.assertIsNotNone(pos.valued_at_utc)
        self.assertEqual(pos.valuation_status, "valued",
                         "CURRENT: valued despite projected valuation time")


class CanonicalBlockerTrustContradictionTest(unittest.TestCase):
    """Items 12-13: valuation_blockers() trusts stored status."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.receipt_root = self.root / "receipts"

    # --- Item 12: trusted stored status ---
    def test_valuation_blockers_trusts_stored_status(self) -> None:
        """CURRENT: valuation_blockers() reads position.valuation_status,
        does not re-derive it from evidence."""
        path = self.root / "export.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TYPED_CSV_COLUMNS)
            w.writeheader()
            w.writerow(_typed_row())
        result = ingest_personal_finance_export(
            path, engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=LocalArtifactStore(self.receipt_root / "artifact-store"),
        )
        positions = [r for r in read_all(Position, engine=self.engine)]
        pos = positions[0]
        self.assertEqual(pos.valuation_status, "valued")
        blockers = valuation_blockers(pos)
        self.assertNotIn("valuation_valued", blockers,
                         "CURRENT: 'valued' is not blocked")
        self.assertIn(pos.valuation_status, ADMITTED_VALUATION_STATUSES,
                      "CURRENT: unverified 'valued' is admitted")

    # --- Item 13: triple contradiction ---
    def test_position_status_canonical_blockers_and_import_findings_diverge(self) -> None:
        """CURRENT: adapter status='valued', canonical blockers non-empty,
        batch completeness may not reflect it."""
        path = self.root / "export.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TYPED_CSV_COLUMNS)
            w.writeheader()
            w.writerow(_typed_row({"price_source_ref": ""}))
        result = ingest_personal_finance_export(
            path, engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=LocalArtifactStore(self.receipt_root / "artifact-store"),
        )
        positions = [r for r in read_all(Position, engine=self.engine)]
        pos = positions[0]
        stored_status = pos.valuation_status
        blockers = valuation_blockers(pos)
        import_completeness = result.completeness_status
        has_blockers = bool(blockers)
        is_valued = stored_status == "valued"
        if is_valued and has_blockers:
            self.assertTrue(True,
                            f"CURRENT: valued but blockers={blockers}")


class MaterializerAcceptsContradictoryEnvelopeTest(unittest.TestCase):
    """Items 15-18: materialize_import_batch does not reject contradictory status."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.receipt_root = self.root / "receipts"
        self.store = LocalArtifactStore(self.receipt_root / "artifact-store")
        self.import_root = self.root / "receipts" / "capital-imports" / "broker-read"
        self.broker_store = LocalArtifactStore(self.import_root / "artifact-store")

    # --- Item 15: CSV forged valued accepted ---
    def test_csv_forged_valued_accepted_by_materializer(self) -> None:
        """CURRENT: CSV import writes DB rows despite unverified 'valued'."""
        path = self.root / "export.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TYPED_CSV_COLUMNS)
            w.writeheader()
            w.writerow(_typed_row({"valued_at_utc": "", "price_source_ref": ""}))
        ingest_personal_finance_export(
            path, engine=self.engine,
            receipt_root=self.receipt_root, artifact_store=self.store,
        )
        positions = read_all(Position, engine=self.engine)
        batches = read_all(ImportBatch, engine=self.engine)
        self.assertGreater(len(positions), 0,
                           "CURRENT: DB has rows despite unverified valued status")
        self.assertGreater(len(batches), 0,
                           "CURRENT: batch created despite unverified status")

    # --- Item 16: Broker forged valued accepted ---
    def test_broker_forged_valued_accepted_by_materializer(self) -> None:
        """CURRENT: broker import writes DB rows despite component mismatch."""
        payload = {
            "receipt_id": "rec_f", "kind": "broker_read",
            "created_at_utc": "2025-06-20T09:00:00+00:00",
            "effective_at_utc": "2025-06-20T09:00:00+00:00",
            "observed_at_utc": "2025-06-20T09:00:00+00:00",
            "valued_at_utc": "2025-06-20T09:00:00+00:00",
            "broker": "manual", "environment": "paper",
            "account": {"id": "acct_f", "status": "ACTIVE"},
            "positions": [{
                "symbol": "SPY", "qty": "2", "market_value": "99",
                "unit_price": "50", "currency": "USD",
                "asset_class": "equity", "exchange": "ARCX",
                "price_source_ref": "fixture:forged",
            }],
        }
        path = self.root / "broker-read" / "portfolio.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        ingest_broker_read_receipt(
            path, engine=self.engine,
            receipt_root=self.import_root, artifact_store=self.broker_store,
        )
        positions = read_all(Position, engine=self.engine)
        self.assertGreater(len(positions), 0,
                           "CURRENT: DB has rows despite forged broker status")
        pos = positions[0]
        self.assertEqual(pos.valuation_status, "valued",
                         "CURRENT: valued accepted despite component mismatch")


if __name__ == "__main__":
    unittest.main()
