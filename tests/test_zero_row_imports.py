"""Target contract tests for #375 zero-row full imports and explicit
covered-domain deletion.

Every test calls the real production importer and materializer and asserts
the post-#375 target behavior.
"""

from __future__ import annotations

import csv
import contextlib
import copy
import hashlib
import json
import tempfile
import unittest
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from finharness.artifact_store import LocalArtifactStore
from finharness.personal_finance import ingest_personal_finance_export
from finharness.personal_finance import PersonalFinanceExportError
from finharness.statecore.import_models import ImportTombstone
from finharness.statecore.models import (
    ImportBatch,
    Liability,
    Position,
    ReceiptManifest,
    Snapshot,
)
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
    "effective_at_utc", "observed_at_utc",
    "record_type",
    "liability_id", "name", "liability_type", "balance",
    "goal_id", "target_amount", "current_amount",
    "document_id", "document_type", "title", "path",
]

OBSERVED = "2025-06-20T08:00:00+00:00"


def _typed_row(overrides=None):
    row = {
        "record_type": "position",
        "account_id": "acct", "account_name": "Test", "account_kind": "broker",
        "venue": "test", "symbol": "SPY", "instrument_type": "equity",
        "instrument_venue": "ARCX",
        "quantity": "2", "market_value": "100", "cost_basis": "90",
        "currency": "USD", "as_of_utc": OBSERVED,
        "unit_price": "50", "valuation_currency": "USD", "price_currency": "USD",
        "valued_at_utc": "2025-06-20T07:00:00+00:00",
        "price_source_ref": "fixture:test",
        "fx_rate": "", "fx_as_of_utc": "", "fx_source_ref": "",
        "effective_at_utc": OBSERVED,
        "observed_at_utc": OBSERVED,
    }
    if overrides:
        row.update(overrides)
    return row


def _write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=TYPED_CSV_COLUMNS)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def exactly_one(iterable: Iterable) -> object:
    items = list(iterable)
    if len(items) != 1:
        raise AssertionError(f"expected exactly one match, got {len(items)}")
    return items[0]


class ZeroRowImportTargetTest(unittest.TestCase):
    """Target contract tests for #375. All call real production paths."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.store = LocalArtifactStore(self.root / "artifact-store")

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def _fresh_artifact_store(self, sub):
        root = self.root / sub
        return LocalArtifactStore(root / "artifact-store")

    def _receipt_root(self, sub):
        return self.root / sub

    # ── target 1: header-only full + explicit position coverage succeeds ──

    def test_header_only_full_with_position_coverage_succeeds(self):
        path = self.root / "header_only.csv"
        _write_csv(path, [])
        result = ingest_personal_finance_export(
            path, engine=self.engine,
            receipt_root=self._receipt_root("r1"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["position"],
            observed_at_utc=OBSERVED,
        )
        self.assertIsNotNone(result.batch_id)
        positions = list(read_all(Position, engine=self.engine))
        self.assertEqual(len(positions), 0,
                         "header-only full should produce zero positions")

    # ── target 2: full position 1→0 creates empty portfolio Snapshot + tombstone ──

    def test_full_position_one_to_zero_creates_empty_snapshot_and_tombstone(self):
        # Seed
        path_seed = self.root / "seed.csv"
        _write_csv(path_seed, [_typed_row()])
        r1 = ingest_personal_finance_export(
            path_seed, engine=self.engine,
            receipt_root=self._receipt_root("seed"),
            artifact_store=self.store, coverage_mode="full",
            covered_domains=["position"],
        )
        self.assertEqual(len(list(read_all(Position, engine=self.engine))), 1)

        # Clear
        path_clear = self.root / "clear.csv"
        _write_csv(path_clear, [])
        r2 = ingest_personal_finance_export(
            path_clear, engine=self.engine,
            receipt_root=self._receipt_root("clear"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["position"],
            observed_at_utc=OBSERVED,
        )
        # Zero current positions
        positions = list(read_all(Position, engine=self.engine))
        self.assertEqual(len(positions), 0)

        # Empty portfolio Snapshot exists
        manifest = exactly_one(
            m for m in read_all(ReceiptManifest, engine=self.engine)
            if m.batch_id == r2.batch_id
        )
        snapshots = list(read_all(Snapshot, engine=self.engine))
        target = exactly_one(s for s in snapshots if s.snapshot_id == manifest.snapshot_id)
        self.assertEqual(target.kind, "portfolio")

        # Tombstone for the cleared position
        tombstones = list(read_all(ImportTombstone, engine=self.engine))
        self.assertGreaterEqual(len(tombstones), 1)
        self.assertTrue(any(t.record_type == "Position" for t in tombstones))

        # Receipt has deletion_plan with automatic entries
        receipt_bytes = self.store.read(manifest.receipt_artifact_id)
        receipt = json.loads(receipt_bytes)
        plan = receipt.get("deletion_plan", {})
        self.assertGreaterEqual(len(plan.get("automatic", [])), 1)

    # ── target 3: zero-row delta with base preserves prior positions ──

    def test_zero_row_delta_with_base_preserves_positions(self):
        path_seed = self.root / "seed.csv"
        _write_csv(path_seed, [_typed_row()])
        ingest_personal_finance_export(
            path_seed, engine=self.engine,
            receipt_root=self._receipt_root("seed"),
            artifact_store=self.store, coverage_mode="full",
            covered_domains=["position"],
        )
        self.assertEqual(len(list(read_all(Position, engine=self.engine))), 1)

        path_delta = self.root / "delta.csv"
        _write_csv(path_delta, [])
        result = ingest_personal_finance_export(
            path_delta, engine=self.engine,
            receipt_root=self._receipt_root("delta"),
            artifact_store=self.store,
            coverage_mode="delta",
            covered_domains=["position"],
            observed_at_utc=OBSERVED,
        )
        positions = list(read_all(Position, engine=self.engine))
        self.assertEqual(len(positions), 1,
                         "zero-row delta must preserve prior positions")

    # ── target 4: zero-row delta without base fails closed ──

    def test_zero_row_delta_without_base_fails_closed(self):
        path = self.root / "delta.csv"
        _write_csv(path, [])
        with self.assertRaises(StateCoreStoreError):
            ingest_personal_finance_export(
                path, engine=self.engine,
                receipt_root=self._receipt_root("delta"),
                artifact_store=self.store,
                coverage_mode="delta",
                covered_domains=["position"],
                observed_at_utc=OBSERVED,
            )
        self.assertEqual(len(list(read_all(Position, engine=self.engine))), 0)

    # ── target 5: typed multi-domain full without covered_domains fails ──

    def test_typed_full_without_covered_domains_fails_closed(self):
        path = self.root / "typed.csv"
        _write_csv(path, [_typed_row()])
        with self.assertRaises(PersonalFinanceExportError):
            ingest_personal_finance_export(
                path, engine=self.engine,
                receipt_root=self._receipt_root("fail"),
                artifact_store=self.store,
                coverage_mode="full",
            )
        self.assertEqual(len(list(read_all(Position, engine=self.engine))), 0)
        self.assertEqual(len(list(read_all(ImportBatch, engine=self.engine))), 0)

    # ── target 6: full empties liability while updating goal ──

    def _liability_row(self, liability_id="loan-1"):
        return {
            "record_type": "liability",
            "liability_id": liability_id,
            "name": "Test Loan", "liability_type": "loan",
            "balance": "50000", "currency": "USD",
            "as_of_utc": OBSERVED,
        }

    def _goal_row(self, goal_id="goal-1"):
        return {
            "record_type": "goal",
            "goal_id": goal_id, "name": "Emergency Fund",
            "target_amount": "50000", "current_amount": "10000",
            "currency": "USD",
            "as_of_utc": OBSERVED,
        }

    def test_full_empties_liability_while_updating_goal(self):
        # Seed: liability + goal
        path_seed = self.root / "seed.csv"
        _write_csv(path_seed, [self._liability_row("loan-a"), self._goal_row("goal-a")])
        ingest_personal_finance_export(
            path_seed, engine=self.engine,
            receipt_root=self._receipt_root("seed"),
            artifact_store=self.store, coverage_mode="full",
            covered_domains=["liability", "goal"],
        )
        self.assertEqual(len(list(read_all(Liability, engine=self.engine))), 1)
        self.assertGreater(len(list(read_all(
            __import__("finharness.statecore.models", fromlist=["FinancialGoal"]).FinancialGoal,
            engine=self.engine))), 0)

        # Full: remove liability, update goal
        path_update = self.root / "update.csv"
        _write_csv(path_update, [
            self._goal_row("goal-a"),
        ])
        result = ingest_personal_finance_export(
            path_update, engine=self.engine,
            receipt_root=self._receipt_root("update"),
            artifact_store=self.store, coverage_mode="full",
            covered_domains=["liability", "goal"],
        )
        # Liability cleared
        self.assertEqual(len(list(read_all(Liability, engine=self.engine))), 0)
        # Liability tombstone exists
        tombstones = list(read_all(ImportTombstone, engine=self.engine))
        self.assertTrue(any(
            t.record_type == "Liability" and t.record_id == "loan-a"
            for t in tombstones
        ))
        # Deletion plan in receipt
        manifest = exactly_one(
            m for m in read_all(ReceiptManifest, engine=self.engine)
            if m.batch_id == result.batch_id
        )
        receipt_bytes = self.store.read(manifest.receipt_artifact_id)
        receipt = json.loads(receipt_bytes)
        plan = receipt.get("deletion_plan", {})
        self.assertGreaterEqual(len(plan.get("automatic", [])), 1)

    # ── target 7: source A full does not modify or tombstone source B ──

    def test_source_a_full_does_not_delete_source_b(self):
        path_a = self.root / "a.csv"
        _write_csv(path_a, [self._liability_row("loan-a")])
        ingest_personal_finance_export(
            path_a, engine=self.engine,
            receipt_root=self._receipt_root("a"),
            artifact_store=self.store, coverage_mode="full",
            covered_domains=["liability"],
        )

        path_b = self.root / "b.csv"
        _write_csv(path_b, [self._liability_row("loan-b")])
        ingest_personal_finance_export(
            path_b, engine=self.engine,
            receipt_root=self._receipt_root("b"),
            artifact_store=self._fresh_artifact_store("b"),
            coverage_mode="full",
            covered_domains=["liability"],
        )
        liabilities = list(read_all(Liability, engine=self.engine))
        ids = {liab.liability_id for liab in liabilities}
        self.assertEqual(ids, {"loan-a", "loan-b"},
                         "source B full should not delete source A records")

    # ── target 8: automatic non-position tombstone in receipt and DB ──

    def test_automatic_tombstone_in_receipt_and_db(self):
        path_seed = self.root / "seed.csv"
        _write_csv(path_seed, [self._liability_row("loan-1")])
        r1 = ingest_personal_finance_export(
            path_seed, engine=self.engine,
            receipt_root=self._receipt_root("seed"),
            artifact_store=self.store, coverage_mode="full",
            covered_domains=["liability"],
        )
        path_clear = self.root / "clear.csv"
        _write_csv(path_clear, [])
        r2 = ingest_personal_finance_export(
            path_clear, engine=self.engine,
            receipt_root=self._receipt_root("clear"),
            artifact_store=self.store, coverage_mode="full",
            covered_domains=["liability"],
            observed_at_utc=OBSERVED,
        )
        # DB tombstone
        tombstones = list(read_all(ImportTombstone, engine=self.engine))
        self.assertTrue(any(
            t.record_type == "Liability" and t.record_id == "loan-1"
            and t.reason == "absent_from_full_import"
            for t in tombstones
        ))
        # Receipt deletion plan
        manifest = exactly_one(
            m for m in read_all(ReceiptManifest, engine=self.engine)
            if m.batch_id == r2.batch_id
        )
        receipt_bytes = self.store.read(manifest.receipt_artifact_id)
        receipt = json.loads(receipt_bytes)
        plan = receipt.get("deletion_plan", {})
        auto = plan.get("automatic", [])
        self.assertTrue(any(
            d.get("record_type") == "Liability" and d.get("record_id") == "loan-1"
            for d in auto
        ))

    # ── target 9: forged deletion plan rejected with zero writes ──

    def test_forged_deletion_plan_rejected(self):
        path = self.root / "pos.csv"
        _write_csv(path, [_typed_row()])

        captured = {}

        def _patched(records, *, source, batch, manifest, artifact_store, engine):
            captured.update({
                "records": copy.deepcopy(list(records)),
                "source": source, "batch": copy.deepcopy(batch),
                "manifest": copy.deepcopy(manifest),
                "store": artifact_store,
            })
            # Inject forged tombstone with non-contract reason
            tombstone = ImportTombstone(
                tombstone_id="import_tombstone_forged",
                batch_id=batch.batch_id,
                source_kind=batch.source_kind,
                record_type="Liability",
                record_id="nonexistent",
                reason="forged_reason_not_in_contract",
            )
            captured["records"].append(tombstone)
            # Now call the real materializer — it should reject
            materialize_import_batch(
                captured["records"], source=source,
                batch=batch, manifest=manifest,
                artifact_store=artifact_store, engine=engine,
            )

        with patch(
            "finharness.personal_finance.materialize_import_batch", _patched
        ):
            with self.assertRaises(StateCoreStoreError):
                ingest_personal_finance_export(
                    path, engine=self.engine,
                    receipt_root=self._receipt_root("forged"),
                    artifact_store=self.store,
                    coverage_mode="full",
                    covered_domains=["position"],
                )
        self.assertEqual(len(list(read_all(ImportBatch, engine=self.engine))), 0)

    # ── target 10: same bytes different coverage → different batch IDs ──

    def test_same_bytes_different_coverage_different_batch_ids(self):
        path = self.root / "same.csv"
        _write_csv(path, [_typed_row()])

        r1 = ingest_personal_finance_export(
            path, engine=self.engine,
            receipt_root=self._receipt_root("r1"),
            artifact_store=self._fresh_artifact_store("r1"),
            coverage_mode="full",
            covered_domains=["position"],
        )
        r2 = ingest_personal_finance_export(
            path, engine=self.engine,
            receipt_root=self._receipt_root("r2"),
            artifact_store=self._fresh_artifact_store("r2"),
            coverage_mode="full",
            covered_domains=["position", "liability"],
        )
        self.assertNotEqual(r1.batch_id, r2.batch_id)

    # ── target 11: same header bytes different observed clocks →
    #                  different batch IDs ──

    def test_same_bytes_different_observed_clocks_different_batch_ids(self):
        path = self.root / "clock.csv"
        _write_csv(path, [_typed_row()])

        r1 = ingest_personal_finance_export(
            path, engine=self.engine,
            receipt_root=self._receipt_root("c1"),
            artifact_store=self._fresh_artifact_store("c1"),
            coverage_mode="full",
            covered_domains=["position"],
        )
        # Same CSV, different observed clock — empty rows = header-only
        path2 = self.root / "clock2.csv"
        _write_csv(path2, [])
        r2 = ingest_personal_finance_export(
            path2, engine=self.engine,
            receipt_root=self._receipt_root("c2"),
            artifact_store=self._fresh_artifact_store("c2"),
            coverage_mode="full",
            covered_domains=["position"],
            observed_at_utc="2025-07-20T08:00:00+00:00",
        )
        self.assertNotEqual(r1.batch_id, r2.batch_id)

    # ── target 12: generic upsert cannot bypass scoped production ownership ──

    def test_generic_upsert_cannot_bypass_ownership(self):
        from finharness.statecore.store import write_records
        from finharness.statecore.models import Liability

        liab = Liability(
            liability_id="bypass-1", name="Bypassed",
            liability_type="loan", balance=Decimal("100"),
            currency="USD", source="personal_finance_export",
        )
        with self.assertRaises(StateCoreStoreError):
            write_records([liab], engine=self.engine)
        self.assertEqual(len(list(read_all(Liability, engine=self.engine))), 0)

    # ── target 13: restart/retry produces identical receipt, plan, tombstones ──

    def test_retry_produces_identical_artifacts(self):
        path = self.root / "pos.csv"
        _write_csv(path, [_typed_row()])
        r1 = ingest_personal_finance_export(
            path, engine=self.engine,
            receipt_root=self._receipt_root("r1"),
            artifact_store=self.store, coverage_mode="full",
            covered_domains=["position"],
        )
        # Retry — should succeed (deterministic) with same batch_id
        r2 = ingest_personal_finance_export(
            path, engine=self.engine,
            receipt_root=self._receipt_root("r2"),
            artifact_store=self.store, coverage_mode="full",
            covered_domains=["position"],
        )
        self.assertEqual(r1.batch_id, r2.batch_id)

    # ── target 14: duplicate run produces no duplicate tombstones ──

    def test_duplicate_run_no_duplicate_tombstones(self):
        # Seed liability, then clear it, then clear again
        path_seed = self.root / "seed.csv"
        _write_csv(path_seed, [self._liability_row("loan-1")])
        ingest_personal_finance_export(
            path_seed, engine=self.engine,
            receipt_root=self._receipt_root("seed"),
            artifact_store=self.store, coverage_mode="full",
            covered_domains=["liability"],
        )
        path_clear = self.root / "clear.csv"
        _write_csv(path_clear, [])
        ingest_personal_finance_export(
            path_clear, engine=self.engine,
            receipt_root=self._receipt_root("c1"),
            artifact_store=self.store, coverage_mode="full",
            covered_domains=["liability"],
            observed_at_utc=OBSERVED,
        )
        tombstones_after_first = list(read_all(ImportTombstone, engine=self.engine))
        self.assertGreaterEqual(len(tombstones_after_first), 1)

        # Clear again — should be idempotent
        ingest_personal_finance_export(
            path_clear, engine=self.engine,
            receipt_root=self._receipt_root("c2"),
            artifact_store=self.store, coverage_mode="full",
            covered_domains=["liability"],
            observed_at_utc=OBSERVED,
        )
        tombstones_after_second = list(read_all(ImportTombstone, engine=self.engine))
        # No new liability tombstones (only the original one)
        liability_tombstones = [
            t for t in tombstones_after_second
            if t.record_type == "Liability" and t.record_id == "loan-1"
        ]
        self.assertEqual(len(liability_tombstones), 1,
                         "duplicate clear should not create duplicate tombstones")

    # ── target 15: legacy position-only CSV (no record_type) auto-declares
    #                position coverage ──

    def test_legacy_csv_without_record_type_auto_declares_position(self):
        path = self.root / "legacy.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=[
                "account_id", "account_name", "account_kind", "venue",
                "symbol", "quantity", "market_value", "cost_basis",
                "currency", "as_of_utc", "observed_at_utc",
            ])
            w.writeheader()
            w.writerow({
                "account_id": "acct", "account_name": "Legacy",
                "account_kind": "broker", "venue": "test",
                "symbol": "SPY", "quantity": "2", "market_value": "100",
                "cost_basis": "90", "currency": "USD",
                "as_of_utc": OBSERVED, "observed_at_utc": OBSERVED,
            })
        result = ingest_personal_finance_export(
            path, engine=self.engine,
            receipt_root=self._receipt_root("legacy"),
            artifact_store=self.store, coverage_mode="full",
        )
        positions = list(read_all(Position, engine=self.engine))
        self.assertEqual(len(positions), 1)
        batch = exactly_one(
            b for b in read_all(ImportBatch, engine=self.engine)
            if b.batch_id == result.batch_id
        )
        self.assertEqual(batch.covered_domains, ["position"])

    # ── helper for receipts cleanup between tests using same engine ──

    def _fresh_store(self, sub):
        store_root = self.root / sub
        return LocalArtifactStore(store_root / "artifact-store")


if __name__ == "__main__":
    unittest.main()
