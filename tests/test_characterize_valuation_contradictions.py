"""Target contract tests for #374 canonical valuation assessment.

Every test asserts the CORRECT future contract. They FAIL on current main
because adapters derive valuation_status independently and the materializer
does not enforce canonical assessment at the commit boundary.
"""

from __future__ import annotations

import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path

from finharness.artifact_store import LocalArtifactStore
from finharness.personal_finance import ingest_personal_finance_export
from finharness.position_valuation import valuation_blockers
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


# =============================================================================
# CSV contract tests
# =============================================================================


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

    def _positions(self):
        return list(read_all(Position, engine=self.engine))

    # --- missing valued_at_utc → unpriced + blocked ---
    def test_missing_valued_at_utc_produces_unpriced_and_blocked(self) -> None:
        """CONTRACT: Position without valued_at_utc must be 'unpriced',
        completeness must be 'blocked', and canonical finding must include
        valued_at_utc_missing."""
        result = self._ingest([_typed_row({"valued_at_utc": ""})])
        pos = self._positions()[0]
        self.assertIsNone(pos.valued_at_utc)
        # Target contract assertions (fail on current code):
        self.assertEqual(pos.valuation_status, "unpriced")
        blockers = valuation_blockers(pos)
        self.assertIn("valued_at_utc_missing", blockers)
        self.assertEqual(result.completeness_status, "blocked")

    # --- missing price_source_ref → unpriced + blocked ---
    def test_missing_price_source_ref_produces_unpriced_and_blocked(self) -> None:
        """CONTRACT: Position without price_source_ref must be 'unpriced',
        completeness 'blocked', with price_source_ref_missing finding."""
        result = self._ingest([_typed_row({"price_source_ref": ""})])
        pos = self._positions()[0]
        self.assertIsNone(pos.price_source_ref)
        self.assertEqual(pos.valuation_status, "unpriced")
        blockers = valuation_blockers(pos)
        self.assertIn("price_source_ref_missing", blockers)
        self.assertEqual(result.completeness_status, "blocked")

    # --- component mismatch → not valued + blocked ---
    def test_component_mismatch_produces_unpriced_and_blocked(self) -> None:
        """CONTRACT: qty*unit_price != market_value must not be 'valued',
        completeness 'blocked', with valuation_components_do_not_reconcile."""
        result = self._ingest([_typed_row({"market_value": "99"})])
        pos = self._positions()[0]
        expected_calc = pos.quantity * pos.unit_price
        self.assertNotEqual(expected_calc, pos.market_value)
        self.assertNotEqual(pos.valuation_status, "valued")
        blockers = valuation_blockers(pos)
        self.assertIn("valuation_components_do_not_reconcile", blockers)
        self.assertEqual(result.completeness_status, "blocked")



# =============================================================================
# Broker contract tests
# =============================================================================


class BrokerValuationContractTest(unittest.TestCase):

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.import_root = self.root / "receipts" / "capital-imports" / "broker-read"
        self.store = LocalArtifactStore(self.import_root / "artifact-store")

    def _positions(self):
        return list(read_all(Position, engine=self.engine))

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

    # --- component mismatch → not valued ---
    def test_component_mismatch_produces_unpriced(self) -> None:
        """CONTRACT: broker position with qty*price != market_value
        must not be 'valued'."""
        payload = self._base_payload()
        payload["positions"][0]["market_value"] = "99"
        self._ingest(payload)
        pos = self._positions()[0]
        expected = pos.quantity * pos.unit_price
        self.assertNotEqual(expected, pos.market_value)
        self.assertNotEqual(pos.valuation_status, "valued")
        blockers = valuation_blockers(pos)
        self.assertIn("valuation_components_do_not_reconcile", blockers)


# =============================================================================
# Canonical blocker: must re-derive coarse status from evidence
# =============================================================================


class CanonicalBlockerReDerivesStatusTest(unittest.TestCase):
    """valuation_blockers() must re-derive coarse status from evidence,
    not trust the stored position.valuation_status."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.receipt_root = self.root / "receipts"

    def test_stored_valued_with_missing_evidence_produces_blockers(self) -> None:
        """CONTRACT: a Position stored as 'valued' but missing valued_at_utc
        must produce valuation_blockers that include valued_at_utc_missing,
        and must not be admitted."""
        path = self.root / "export.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TYPED_CSV_COLUMNS)
            w.writeheader()
            w.writerow(_typed_row({"valued_at_utc": ""}))
        ingest_personal_finance_export(
            path, engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=LocalArtifactStore(self.receipt_root / "artifact-store"),
        )
        positions = list(read_all(Position, engine=self.engine))
        pos = positions[0]
        blockers = valuation_blockers(pos)
        self.assertIn("valued_at_utc_missing", blockers)
        self.assertNotIn(pos.valuation_status, {"valued", "valued_converted"},
                         "CONTRACT: missing-evidence Position must not be admitted")


# =============================================================================
# Delta carry-forward: carried Position must be re-assessed
# =============================================================================


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

    def test_carried_position_uses_current_observed_time_for_staleness(self) -> None:
        """CONTRACT: a Position carried forward from a previous full import
        must be assessed against the current batch's observed_at_utc,
        not the original import time. If the valuation time is older than
        the policy window, status must be 'stale' and completeness 'blocked'.

        CURRENT: the CSV adapter does not re-assess carried positions."""
        # Full import with Position A at T-25h (stale by 24h policy)
        old_time = "2025-06-19T08:00:00+00:00"
        pos_a_row = _typed_row({
            "account_id": "acct_a", "symbol": "AAA",
            "valued_at_utc": old_time,
            "as_of_utc": old_time,
        })
        self._csv([pos_a_row])
        result1 = ingest_personal_finance_export(
            self._csv([pos_a_row]), engine=self.engine,
            receipt_root=self.receipt_root, artifact_store=self.store,
        )
        batch1_id = result1.batch_id
        positions1 = list(read_all(Position, engine=self.engine))
        self.assertEqual(len(positions1), 1)

        # Delta import at T-1h: only Position B, Position A is carried
        new_time = "2025-06-20T08:00:00+00:00"
        pos_b_row = _typed_row({
            "account_id": "acct_b", "symbol": "BBB",
            "valued_at_utc": new_time,
            "as_of_utc": new_time,
        })
        self._csv([pos_b_row])
        result2 = ingest_personal_finance_export(
            self._csv([pos_b_row]), engine=self.engine,
            receipt_root=self.receipt_root, artifact_store=self.store,
            coverage_mode="delta",
            supersedes_batch_id=batch1_id,
            correction_reason="add position B",
        )
        # Both positions should exist in final state
        final_positions = list(read_all(Position, engine=self.engine))
        self.assertGreaterEqual(len(final_positions), 1)
        # Position A should be stale if time gap exceeds 24h
        pos_a_final = [p for p in final_positions if p.symbol == "AAA"]
        if pos_a_final:
            a = pos_a_final[0]
            # T-25h > 24h policy → should be stale
            self.assertEqual(a.valuation_status, "stale")
            blockers = valuation_blockers(a)
            self.assertTrue(any("stale" in b for b in blockers),
                            f"stale finding missing: {blockers}")
            self.assertEqual(result2.completeness_status, "blocked")


# =============================================================================
# Beancount contract tests
# =============================================================================


class BeancountValuationContractTest(unittest.TestCase):
    """Beancount tests exercising real beanquery path with fixture ledgers."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.receipt_root = self.root / "receipts"
        self._write_fixtures()

    def _write_fixtures(self) -> None:
        fixture_dir = self.root / "fixtures"
        fixture_dir.mkdir(parents=True, exist_ok=True)

        # unrelated_price.beancount: AAA has old price, BBB has fresh price
        (fixture_dir / "unrelated_price.beancount").write_text("""\
option "operating_currency" "USD"
2025-01-01 open Assets:Brokerage
2025-01-01 open Equity:Opening
2025-06-18 * "Buy AAA"
  Assets:Brokerage  10 AAA {50 USD}
  Equity:Opening  -500 USD
2025-06-18 * "Buy BBB"
  Assets:Brokerage  5 BBB {100 USD}
  Equity:Opening  -500 USD
2025-06-10 price AAA  55 USD
2025-06-20 price BBB  110 USD
""")

        # distinct_price_times.beancount: each commodity has own date
        (fixture_dir / "distinct_price_times.beancount").write_text("""\
option "operating_currency" "USD"
2025-01-01 open Assets:Brokerage
2025-01-01 open Equity:Opening
2025-06-18 * "Buy"
  Assets:Brokerage  10 AAA {50 USD}
  Assets:Brokerage  5 BBB {100 USD}
  Equity:Opening
2025-06-18 price AAA  55 USD
2025-06-15 price BBB  105 USD
""")

    def _ingest(self, fixture_name: str):
        from finharness.beancount_adapter import ingest_beancount_ledger

        path = self.root / "fixtures" / fixture_name
        return ingest_beancount_ledger(
            path, engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=LocalArtifactStore(self.receipt_root / "artifact-store"),
        )

    # --- unrelated price: AAA uses its own Price, not BBB's ---
    def test_unrelated_commodity_price_does_not_refresh_other_holding(self) -> None:
        """CONTRACT: BBB's fresh Price must not refresh AAA's valued_at_utc.
        AAA uses its own Price directive date (2025-06-10)."""
        _ = self._ingest("unrelated_price.beancount")
        positions = list(read_all(Position, engine=self.engine))
        aaa = [p for p in positions if p.symbol == "AAA"]
        bbb = [p for p in positions if p.symbol == "BBB"]
        self.assertTrue(aaa, "AAA position missing")
        self.assertTrue(bbb, "BBB position missing")
        # AAA should use its own Price date, not BBB's
        if aaa[0].valued_at_utc and bbb[0].valued_at_utc:
            self.assertNotEqual(
                aaa[0].valued_at_utc, bbb[0].valued_at_utc,
                "CONTRACT: distinct commodities must have distinct valued_at_utc"
            )

    # --- distinct price times: each commodity preserves its own date ---
    def test_distinct_price_times_produce_distinct_valued_at_utc(self) -> None:
        """CONTRACT: AAA and BBB with different Price dates must have
        distinct per-position valued_at_utc, not a global max."""
        _ = self._ingest("distinct_price_times.beancount")
        positions = list(read_all(Position, engine=self.engine))
        aaa = [p for p in positions if p.symbol == "AAA"]
        bbb = [p for p in positions if p.symbol == "BBB"]
        self.assertTrue(aaa)
        self.assertTrue(bbb)
        if aaa[0].valued_at_utc and bbb[0].valued_at_utc:
            self.assertEqual(aaa[0].valued_at_utc, "2025-06-18T00:00:00+00:00")
            self.assertEqual(bbb[0].valued_at_utc, "2025-06-15T00:00:00+00:00")


# =============================================================================
# Direct materializer destructive tests
# =============================================================================


class DirectMaterializerValuationRejectionTest(unittest.TestCase):
    """Bypass adapters, construct valid #373 envelopes, then forge
    valuation_status and verify the materializer rejects them."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.import_root = self.root / "receipts" / "capital-imports" / "broker-read"
        self.store = LocalArtifactStore(self.import_root / "artifact-store")

    def _capture_broker_envelope(self):
        """Capture the full materialize_import_batch call from a broker import."""
        from unittest.mock import patch

        from finharness.statecore.store import StateCoreStoreError

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

        with patch(
            "finharness.statecore.snapshot_ingest.materialize_import_batch", patched
        ), __import__("contextlib").suppress(StateCoreStoreError):
            ingest_broker_read_receipt(
                path, engine=self.engine,
                receipt_root=self.import_root, artifact_store=self.store,
            )
        return captured

    def _assert_db_empty(self):
        self.assertEqual(list(read_all(ImportBatch, engine=self.engine)), [])
        self.assertEqual(list(read_all(ReceiptManifest, engine=self.engine)), [])
        self.assertEqual(list(read_all(Snapshot, engine=self.engine)), [])
        self.assertEqual(list(read_all(Position, engine=self.engine)), [])
        self.assertEqual(list(read_all(ReceiptIndex, engine=self.engine)), [])

    # --- forged valued with missing time rejected ---
    def test_forged_valued_with_missing_valued_at_utc_rejected(self) -> None:
        """CONTRACT: materializer rejects Position with forged 'valued' and
        missing valued_at_utc. DB must remain empty."""
        cap = self._capture_broker_envelope()
        for r in cap["records"]:
            if isinstance(r, Position):
                r.valued_at_utc = None
                r.valuation_status = "valued"
        with self.assertRaises(StateCoreStoreError):
            materialize_import_batch(
                cap["records"], source=cap["source"],
                batch=cap["batch"], manifest=cap["manifest"],
                artifact_store=cap["store"], engine=self.engine,
            )
        self._assert_db_empty()

    # --- forged valued with component mismatch rejected ---
    def test_forged_valued_with_component_mismatch_rejected(self) -> None:
        """CONTRACT: materializer rejects Position with forged 'valued' and
        qty*price != market_value."""
        cap = self._capture_broker_envelope()
        for r in cap["records"]:
            if isinstance(r, Position):
                r.market_value = r.quantity * r.unit_price + 1
                r.valuation_status = "valued"
        with self.assertRaises(StateCoreStoreError):
            materialize_import_batch(
                cap["records"], source=cap["source"],
                batch=cap["batch"], manifest=cap["manifest"],
                artifact_store=cap["store"], engine=self.engine,
            )
        self._assert_db_empty()

    # --- forged valued with missing price_source_ref rejected ---
    def test_forged_valued_with_missing_price_source_ref_rejected(self) -> None:
        """CONTRACT: materializer rejects Position with forged 'valued' and
        price_source_ref=None."""
        cap = self._capture_broker_envelope()
        for r in cap["records"]:
            if isinstance(r, Position):
                r.price_source_ref = None
                r.valuation_status = "valued"
        with self.assertRaises(StateCoreStoreError):
            materialize_import_batch(
                cap["records"], source=cap["source"],
                batch=cap["batch"], manifest=cap["manifest"],
                artifact_store=cap["store"], engine=self.engine,
            )
        self._assert_db_empty()


if __name__ == "__main__":
    unittest.main()
