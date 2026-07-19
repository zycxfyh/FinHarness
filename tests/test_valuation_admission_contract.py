# ruff: noqa: E501, RUF015, F841, SIM117
"""Target contract tests for #374 canonical valuation assessment.

Every test asserts the CORRECT future contract. They FAIL on current main
because adapters derive valuation_status independently and the materializer
does not enforce canonical assessment at the commit boundary.
"""

from __future__ import annotations

import contextlib
import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path

from finharness.artifact_store import LocalArtifactStore
from finharness.beancount_adapter import ingest_beancount_ledger
from finharness.personal_finance import ingest_personal_finance_export
from finharness.position_valuation import valuation_blockers
from finharness.project_paths import ROOT
from finharness.statecore.models import (
    ImportBatch,
    Position,
    ReceiptIndex,
    ReceiptManifest,
    Snapshot,
)
from finharness.statecore.snapshot_ingest import ingest_broker_read_receipt
from finharness.statecore.store import (
    StateCoreStoreError,
    init_state_core,
    materialize_import_batch,
    read_all,
)

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "valuation"

TYPED_CSV_COLUMNS = [
    "account_id", "account_name", "account_kind", "venue",
    "symbol", "instrument_type", "instrument_venue",
    "quantity", "market_value", "cost_basis", "currency", "as_of_utc",
    "unit_price", "valuation_currency", "price_currency",
    "valued_at_utc", "price_source_ref",
    "fx_rate", "fx_as_of_utc", "fx_source_ref",
]

# ============================================================================
# helpers
# ============================================================================


def _typed_row(overrides: dict | None = None) -> dict[str, str]:
    row = {
        "account_id": "acct", "account_name": "Test", "account_kind": "broker",
        "venue": "test", "symbol": "SPY", "instrument_type": "equity",
        "instrument_venue": "ARCX",
        "quantity": "2", "market_value": "100", "cost_basis": "90",
        "currency": "USD", "as_of_utc": "2025-06-20T08:00:00+00:00",
        "unit_price": "50", "valuation_currency": "USD", "price_currency": "USD",
        "valued_at_utc": "2025-06-20T07:00:00+00:00",
        "price_source_ref": "fixture:test",
        "fx_rate": "", "fx_as_of_utc": "", "fx_source_ref": "",
    }
    if overrides:
        row.update(overrides)
    return row


def _assert_import_surface_agreement(test: unittest.TestCase, result, engine):
    """Verify batch/receipt/snapshot/result/position status agreement."""
    batches = list(read_all(ImportBatch, engine=engine))
    snapshots = list(read_all(Snapshot, engine=engine))
    manifests = list(read_all(ReceiptManifest, engine=engine))
    positions = list(read_all(Position, engine=engine))
    test.assertEqual(len(batches), 1)
    test.assertEqual(len(snapshots), 1)
    test.assertEqual(len(manifests), 1)
    test.assertTrue(positions)
    bc = batches[0].completeness_status
    sc = snapshots[0].payload.get("completeness_status")
    rc = result.completeness_status
    # completeness must agree across batch, snapshot, and result
    test.assertEqual(bc, sc, f"batch={bc} != snapshot={sc}")
    test.assertEqual(bc, rc, f"batch={bc} != result={rc}")
    # every Position status must agree with completeness
    for pos in positions:
        blockers = valuation_blockers(pos)
        has_blockers = bool(blockers)
        is_valued = pos.valuation_status in ("valued", "valued_converted")
        if has_blockers:
            test.assertFalse(is_valued, f"Position {pos.symbol} has blockers {blockers} but status={pos.valuation_status}")
        test.assertFalse(is_valued and bc == "blocked", f"Position {pos.symbol} is valued but completeness=blocked")


# ============================================================================
# CSV contract tests
# ============================================================================


class CsvValuationContractTest(unittest.TestCase):

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
        return ingest_personal_finance_export(
            self._csv(rows), engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=LocalArtifactStore(self.receipt_root / "artifact-store"),
        )

    def test_missing_valued_at_utc_produces_unpriced_and_blocked(self) -> None:
        result = self._ingest([_typed_row({"valued_at_utc": ""})])
        positions = list(read_all(Position, engine=self.engine))
        pos = positions[0]
        self.assertIsNone(pos.valued_at_utc)
        self.assertEqual(pos.valuation_status, "unpriced")
        blockers = valuation_blockers(pos)
        self.assertIn("valued_at_utc_missing", blockers)
        self.assertEqual(result.completeness_status, "blocked")
        _assert_import_surface_agreement(self, result, self.engine)

    def test_missing_price_source_ref_produces_unpriced_and_blocked(self) -> None:
        result = self._ingest([_typed_row({"price_source_ref": ""})])
        pos = list(read_all(Position, engine=self.engine))[0]
        self.assertIsNone(pos.price_source_ref)
        self.assertEqual(pos.valuation_status, "unpriced")
        blockers = valuation_blockers(pos)
        self.assertIn("price_source_ref_missing", blockers)
        self.assertEqual(result.completeness_status, "blocked")
        _assert_import_surface_agreement(self, result, self.engine)

    def test_component_mismatch_produces_unpriced_and_blocked(self) -> None:
        result = self._ingest([_typed_row({"market_value": "99"})])
        pos = list(read_all(Position, engine=self.engine))[0]
        expected_calc = pos.quantity * pos.unit_price
        self.assertNotEqual(expected_calc, pos.market_value)
        self.assertNotEqual(pos.valuation_status, "valued")
        blockers = valuation_blockers(pos)
        self.assertIn("valuation_components_do_not_reconcile", blockers)
        self.assertEqual(result.completeness_status, "blocked")
        _assert_import_surface_agreement(self, result, self.engine)


# ============================================================================
# Broker contract tests
# ============================================================================


class BrokerValuationContractTest(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.import_root = self.root / "receipts" / "capital-imports" / "broker-read"
        self.store = LocalArtifactStore(self.import_root / "artifact-store")

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

    def _ingest(self, payload: dict):
        path = self.root / "broker-read" / "portfolio.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return ingest_broker_read_receipt(
            path, engine=self.engine,
            receipt_root=self.import_root, artifact_store=self.store,
        )

    def test_component_mismatch_produces_unpriced(self) -> None:
        payload = self._base_payload()
        payload["positions"][0]["market_value"] = "99"
        self._ingest(payload)
        pos = list(read_all(Position, engine=self.engine))[0]
        expected = pos.quantity * pos.unit_price
        self.assertNotEqual(expected, pos.market_value)
        self.assertNotEqual(pos.valuation_status, "valued")


# ============================================================================
# Canonical blocker isolation: construct Position directly
# ============================================================================


class ValuationBlockersIsolationTest(unittest.TestCase):

    def test_stored_valued_with_missing_time_not_admitted(self) -> None:
        """valuation_blockers() must re-derive coarse status from evidence,
        not trust stored valuation_status='valued' when valued_at_utc=None."""
        pos = Position(
            position_id="pos_iso", snapshot_id="snap", account_id="acct",
            symbol="SPY", quantity=2, market_value=100, cost_basis=90,
            valuation_currency="USD", unit_price=50, price_currency="USD",
            valued_at_utc=None, price_source_ref="fixture:test",
            as_of_utc="2025-06-20T08:00:00+00:00",
            valuation_status="valued",
        )
        blockers = valuation_blockers(pos)
        self.assertIn("valued_at_utc_missing", blockers)
        self.assertTrue(bool(blockers))

    def test_stored_valued_with_missing_source_not_admitted(self) -> None:
        pos = Position(
            position_id="pos_iso2", snapshot_id="snap", account_id="acct",
            symbol="SPY", quantity=2, market_value=100, cost_basis=90,
            valuation_currency="USD", unit_price=50, price_currency="USD",
            valued_at_utc="2025-06-20T08:00:00+00:00", price_source_ref=None,
            as_of_utc="2025-06-20T08:00:00+00:00",
            valuation_status="valued",
        )
        blockers = valuation_blockers(pos)
        self.assertIn("price_source_ref_missing", blockers)


# ============================================================================
# Delta carry-forward
# ============================================================================


class DeltaCarryForwardContractTest(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.receipt_root = self.root / "receipts"
        self.store = LocalArtifactStore(self.receipt_root / "artifact-store")

    def _csv(self, rows: list[dict[str, str]]) -> Path:
        path = self.root / "export.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TYPED_CSV_COLUMNS)
            w.writeheader()
            for row in rows:
                w.writerow(row)
        return path

    def test_carried_position_produces_stale_and_blocked(self) -> None:
        """Full import: AAA at T-25h. Delta import at T-1h: only BBB.
        Carried AAA must be stale, completeness blocked."""
        old_time = "2025-06-19T07:00:00+00:00"
        new_time = "2025-06-20T08:00:00+00:00"
        gap_hours = 25
        # Full import: Position AAA
        result1 = ingest_personal_finance_export(
            self._csv([_typed_row({
                "account_id": "acct_a", "symbol": "AAA",
                "valued_at_utc": old_time, "as_of_utc": old_time,
            })]), engine=self.engine,
            receipt_root=self.receipt_root, artifact_store=self.store,
        )
        batch1_id = result1.batch_id
        # Delta import: only Position BBB
        result2 = ingest_personal_finance_export(
            self._csv([_typed_row({
                "account_id": "acct_b", "symbol": "BBB",
                "valued_at_utc": new_time, "as_of_utc": new_time,
            })]), engine=self.engine,
            receipt_root=self.receipt_root, artifact_store=self.store,
            coverage_mode="delta", supersedes_batch_id=batch1_id,
            correction_reason="add position B",
        )
        final = list(read_all(Position, engine=self.engine))
        aaa = [p for p in final if p.symbol == "AAA"]
        bbb = [p for p in final if p.symbol == "BBB"]
        self.assertEqual(len(aaa), 1, "AAA must be carried forward")
        self.assertEqual(len(bbb), 1, "BBB must be present")
        self.assertEqual(aaa[0].valuation_status, "stale")
        blockers = valuation_blockers(aaa[0])
        self.assertIn("market_price_stale", blockers)
        self.assertEqual(result2.completeness_status, "blocked")


# ============================================================================
# Beancount contract tests (checked-in fixtures)
# ============================================================================


class BeancountValuationContractTest(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.receipt_root = self.root / "receipts"
        self.store = LocalArtifactStore(self.receipt_root / "artifact-store")

    def _ingest(self, fixture_path: Path):
        return ingest_beancount_ledger(
            fixture_path, engine=self.engine,
            receipt_root=self.receipt_root, artifact_store=self.store,
        )

    def test_unrelated_commodity_price_does_not_refresh_other_holding(self) -> None:
        result = self._ingest(FIXTURE_DIR / "unrelated_price.beancount")
        positions = list(read_all(Position, engine=self.engine))
        aaa = [p for p in positions if p.symbol == "AAA"]
        bbb = [p for p in positions if p.symbol == "BBB"]
        self.assertEqual(len(aaa), 1)
        self.assertEqual(len(bbb), 1)
        self.assertEqual(aaa[0].valued_at_utc, "2025-06-10T00:00:00+00:00")
        self.assertEqual(bbb[0].valued_at_utc, "2025-06-20T00:00:00+00:00")
        self.assertEqual(aaa[0].valuation_status, "stale")
        blockers = valuation_blockers(aaa[0])
        self.assertTrue(any("stale" in b for b in blockers),
                        f"AAA stale finding missing: {blockers}")
        self.assertEqual(result.completeness_status, "blocked")

    def test_distinct_price_times_produce_distinct_valued_at_utc(self) -> None:
        self._ingest(FIXTURE_DIR / "distinct_price_times.beancount")
        positions = list(read_all(Position, engine=self.engine))
        aaa = [p for p in positions if p.symbol == "AAA"]
        bbb = [p for p in positions if p.symbol == "BBB"]
        self.assertEqual(len(aaa), 1)
        self.assertEqual(len(bbb), 1)
        self.assertEqual(aaa[0].valued_at_utc, "2025-06-18T00:00:00+00:00")
        self.assertEqual(bbb[0].valued_at_utc, "2025-06-15T00:00:00+00:00")


# ============================================================================
# Direct materializer: three source kinds
# ============================================================================


class DirectMaterializerValuationRejectionTest(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.import_root = self.root / "receipts" / "capital-imports" / "broker-read"
        self.store = LocalArtifactStore(self.import_root / "artifact-store")

    def _assert_db_empty(self):
        self.assertEqual(list(read_all(ImportBatch, engine=self.engine)), [])
        self.assertEqual(list(read_all(ReceiptManifest, engine=self.engine)), [])
        self.assertEqual(list(read_all(Snapshot, engine=self.engine)), [])
        self.assertEqual(list(read_all(Position, engine=self.engine)), [])
        self.assertEqual(list(read_all(ReceiptIndex, engine=self.engine)), [])

    def _capture_broker_envelope(self):
        from unittest.mock import patch

        captured = {}
        def patched(records, *, source, batch, manifest, artifact_store, engine):
            captured["records"] = copy.deepcopy(list(records))
            captured["source"] = source
            captured["batch"] = copy.deepcopy(batch)
            captured["manifest"] = copy.deepcopy(manifest)
            captured["store"] = artifact_store
            raise StateCoreStoreError("capture-only")
        payload = {
            "receipt_id": "rec_cap", "kind": "broker_read",
            "created_at_utc": "2025-06-20T09:00:00+00:00",
            "effective_at_utc": "2025-06-20T09:00:00+00:00",
            "observed_at_utc": "2025-06-20T09:00:00+00:00",
            "valued_at_utc": "2025-06-20T09:00:00+00:00",
            "broker": "manual", "environment": "paper",
            "account": {"id": "acct_cap", "status": "ACTIVE"},
            "positions": [{
                "symbol": "SPY", "qty": "2", "market_value": "100",
                "unit_price": "50", "currency": "USD",
                "asset_class": "equity", "exchange": "ARCX",
                "price_source_ref": "fixture:capture",
            }],
        }
        path = self.root / "broker-read" / "portfolio.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        with patch("finharness.statecore.snapshot_ingest.materialize_import_batch", patched):
            with contextlib.suppress(StateCoreStoreError):
                ingest_broker_read_receipt(
                    path, engine=self.engine,
                    receipt_root=self.import_root, artifact_store=self.store,
                )
        return captured

    def _capture_csv_envelope(self):
        from unittest.mock import patch

        captured = {}
        def patched(records, *, source, batch, manifest, artifact_store, engine):
            captured["records"] = copy.deepcopy(list(records))
            captured["source"] = source
            captured["batch"] = copy.deepcopy(batch)
            captured["manifest"] = copy.deepcopy(manifest)
            captured["store"] = artifact_store
            raise StateCoreStoreError("capture-only")
        csv_root = self.root / "receipts_csv"
        path = self.root / "export.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TYPED_CSV_COLUMNS)
            w.writeheader()
            w.writerow(_typed_row())
        with patch("finharness.personal_finance.materialize_import_batch", patched):
            with contextlib.suppress(StateCoreStoreError):
                ingest_personal_finance_export(
                    path, engine=self.engine,
                    receipt_root=csv_root,
                    artifact_store=LocalArtifactStore(csv_root / "artifact-store"),
                )
        return captured

    def _capture_beancount_envelope(self):
        from unittest.mock import patch

        captured = {}
        def patched(records, *, source, batch, manifest, artifact_store, engine):
            captured["records"] = copy.deepcopy(list(records))
            captured["source"] = source
            captured["batch"] = copy.deepcopy(batch)
            captured["manifest"] = copy.deepcopy(manifest)
            captured["store"] = artifact_store
            raise StateCoreStoreError("capture-only")
        bean_root = self.root / "receipts_bean"
        fixture = FIXTURE_DIR / "distinct_price_times.beancount"
        with patch("finharness.personal_finance.materialize_import_batch", patched):
            with contextlib.suppress(StateCoreStoreError):
                ingest_beancount_ledger(
                    fixture, engine=self.engine,
                    receipt_root=bean_root,
                    artifact_store=LocalArtifactStore(bean_root / "artifact-store"),
                )
        return captured

    # --- CSV: missing valued_at_utc, forged valued ---
    def test_csv_forged_valued_missing_time_rejected(self) -> None:
        cap = self._capture_csv_envelope()
        for r in cap["records"]:
            if isinstance(r, Position):
                r.valued_at_utc = None
                r.valuation_status = "valued"
        with self.assertRaisesRegex(StateCoreStoreError, "valuation_"):
            materialize_import_batch(
                cap["records"], source=cap["source"],
                batch=cap["batch"], manifest=cap["manifest"],
                artifact_store=cap["store"], engine=self.engine,
            )
        self._assert_db_empty()

    # --- Beancount: missing price_source_ref, forged valued ---
    def test_beancount_forged_valued_missing_source_rejected(self) -> None:
        cap = self._capture_beancount_envelope()
        for r in cap["records"]:
            if isinstance(r, Position):
                r.price_source_ref = None
                r.valuation_status = "valued"
        with self.assertRaisesRegex(StateCoreStoreError, "valuation_"):
            materialize_import_batch(
                cap["records"], source=cap["source"],
                batch=cap["batch"], manifest=cap["manifest"],
                artifact_store=cap["store"], engine=self.engine,
            )
        self._assert_db_empty()

    # --- Broker: component mismatch, forged valued ---
    def test_broker_forged_valued_component_mismatch_rejected(self) -> None:
        cap = self._capture_broker_envelope()
        for r in cap["records"]:
            if isinstance(r, Position):
                r.market_value = r.quantity * r.unit_price + 1
                r.valuation_status = "valued"
        with self.assertRaisesRegex(StateCoreStoreError, "valuation_"):
            materialize_import_batch(
                cap["records"], source=cap["source"],
                batch=cap["batch"], manifest=cap["manifest"],
                artifact_store=cap["store"], engine=self.engine,
            )
        self._assert_db_empty()


if __name__ == "__main__":
    unittest.main()
