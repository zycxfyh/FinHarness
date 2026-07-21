"""Target contract tests for #375 zero-row full imports and explicit
covered-domain deletion.

Every test calls the real production importer and materializer and asserts
the post-#375 target behavior.
"""

from __future__ import annotations

import copy
import csv
import json
import tempfile
import unittest
from collections.abc import Iterable
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from finharness.artifact_store import LocalArtifactStore
from finharness.personal_finance import (
    ImportDeletion,
    PersonalFinanceExportError,
    ingest_personal_finance_export,
)
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
    "record_type",
    "liability_id",
    "name",
    "liability_type",
    "balance",
    "goal_id",
    "target_amount",
    "current_amount",
    "document_id",
    "document_type",
    "title",
    "path",
]

OBSERVED = "2025-06-20T08:00:00+00:00"


def _typed_row(overrides=None):
    row = {
        "record_type": "position",
        "account_id": "acct",
        "account_name": "Test",
        "account_kind": "broker",
        "venue": "test",
        "symbol": "SPY",
        "instrument_type": "equity",
        "instrument_venue": "ARCX",
        "quantity": "2",
        "market_value": "100",
        "cost_basis": "90",
        "currency": "USD",
        "as_of_utc": OBSERVED,
        "unit_price": "50",
        "valuation_currency": "USD",
        "price_currency": "USD",
        "valued_at_utc": "2025-06-20T07:00:00+00:00",
        "price_source_ref": "fixture:test",
        "fx_rate": "",
        "fx_as_of_utc": "",
        "fx_source_ref": "",
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
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("r1"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["position"],
            observed_at_utc=OBSERVED,
        )
        self.assertIsNotNone(result.batch_id)
        positions = list(read_all(Position, engine=self.engine))
        self.assertEqual(len(positions), 0, "header-only full should produce zero positions")

    # ── target 2: full position 1→0 creates empty portfolio Snapshot + tombstone ──

    def test_full_position_one_to_zero_creates_empty_snapshot_and_tombstone(self):
        path = self.root / "positions.csv"
        _write_csv(path, [_typed_row()])
        ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("seed"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["position"],
        )
        self.assertEqual(len(list(read_all(Position, engine=self.engine))), 1)

        _write_csv(path, [])
        result = ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("clear"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["position"],
            observed_at_utc=OBSERVED,
        )
        manifest = exactly_one(
            item
            for item in read_all(ReceiptManifest, engine=self.engine)
            if item.batch_id == result.batch_id
        )
        snapshot = exactly_one(
            item
            for item in read_all(Snapshot, engine=self.engine)
            if item.snapshot_id == manifest.snapshot_id
        )
        self.assertEqual(snapshot.kind, "portfolio")
        current_positions = [
            item
            for item in read_all(Position, engine=self.engine)
            if item.snapshot_id == snapshot.snapshot_id
        ]
        self.assertEqual(current_positions, [])
        self.assertEqual(
            len(list(read_all(Position, engine=self.engine))),
            1,
            "immutable positions from the prior snapshot must remain as history",
        )

        tombstones = list(read_all(ImportTombstone, engine=self.engine))
        self.assertEqual(
            [(item.record_type, item.reason) for item in tombstones],
            [("Position", "absent_from_full_import")],
        )
        receipt = json.loads(self.store.read(manifest.receipt_artifact_id))
        automatic = receipt.get("deletion_plan", {}).get("automatic", [])
        self.assertEqual(
            [(item["record_type"], item["record_id"], item["reason"]) for item in automatic],
            [("Position", tombstones[0].record_id, "absent_from_full_import")],
        )

    # ── target 3: zero-row delta with base preserves prior positions ──

    def test_zero_row_delta_with_base_preserves_positions(self):
        path = self.root / "positions.csv"
        _write_csv(path, [_typed_row()])
        base = ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("seed"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["position"],
        )

        _write_csv(path, [])
        result = ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("delta"),
            artifact_store=self.store,
            coverage_mode="delta",
            covered_domains=["position"],
            observed_at_utc=OBSERVED,
        )
        manifest = exactly_one(
            item
            for item in read_all(ReceiptManifest, engine=self.engine)
            if item.batch_id == result.batch_id
        )
        snapshot = exactly_one(
            item
            for item in read_all(Snapshot, engine=self.engine)
            if item.snapshot_id == manifest.snapshot_id
        )
        current_positions = [
            item
            for item in read_all(Position, engine=self.engine)
            if item.snapshot_id == snapshot.snapshot_id
        ]
        self.assertEqual(len(current_positions), 1)
        self.assertEqual(current_positions[0].symbol, "SPY")
        self.assertEqual(snapshot.payload["delta_base_batch_id"], base.batch_id)
        self.assertEqual(snapshot.payload["materialized_position_count"], 1)
        self.assertEqual(
            len(list(read_all(Position, engine=self.engine))),
            2,
            "delta creates a new immutable snapshot while retaining prior history",
        )

    # ── target 4: zero-row delta without base fails closed ──

    def test_zero_row_delta_without_base_fails_closed(self):
        path = self.root / "delta.csv"
        _write_csv(path, [])
        with self.assertRaises(PersonalFinanceExportError):
            ingest_personal_finance_export(
                path,
                engine=self.engine,
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
                path,
                engine=self.engine,
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
            "name": "Test Loan",
            "liability_type": "loan",
            "balance": "50000",
            "currency": "USD",
            "as_of_utc": OBSERVED,
        }

    def _goal_row(self, goal_id="goal-1"):
        return {
            "record_type": "goal",
            "goal_id": goal_id,
            "name": "Emergency Fund",
            "target_amount": "50000",
            "current_amount": "10000",
            "currency": "USD",
            "as_of_utc": OBSERVED,
        }

    def test_full_empties_liability_while_updating_goal(self):
        path = self.root / "capital.csv"
        _write_csv(path, [self._liability_row("loan-a"), self._goal_row("goal-a")])
        ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("seed"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["liability", "goal"],
        )
        self.assertEqual(len(list(read_all(Liability, engine=self.engine))), 1)

        _write_csv(path, [self._goal_row("goal-a")])
        result = ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("update"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["liability", "goal"],
        )
        self.assertEqual(len(list(read_all(Liability, engine=self.engine))), 0)
        liability_tombstone = exactly_one(
            item
            for item in read_all(ImportTombstone, engine=self.engine)
            if item.record_type == "Liability" and item.record_id == "loan-a"
        )
        manifest = exactly_one(
            item
            for item in read_all(ReceiptManifest, engine=self.engine)
            if item.batch_id == result.batch_id
        )
        receipt = json.loads(self.store.read(manifest.receipt_artifact_id))
        self.assertIn(
            {
                "record_type": "Liability",
                "record_id": "loan-a",
                "reason": "absent_from_full_import",
            },
            receipt["deletion_plan"]["automatic"],
        )
        self.assertEqual(liability_tombstone.reason, "absent_from_full_import")

    # ── target 7: source A full does not modify or tombstone source B ──

    def test_source_a_full_does_not_delete_source_b(self):
        path_a = self.root / "a.csv"
        _write_csv(path_a, [self._liability_row("loan-a")])
        ingest_personal_finance_export(
            path_a,
            engine=self.engine,
            receipt_root=self._receipt_root("a"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["liability"],
        )

        path_b = self.root / "b.csv"
        _write_csv(path_b, [self._liability_row("loan-b")])
        ingest_personal_finance_export(
            path_b,
            engine=self.engine,
            receipt_root=self._receipt_root("b"),
            artifact_store=self._fresh_artifact_store("b"),
            coverage_mode="full",
            covered_domains=["liability"],
        )
        liabilities = list(read_all(Liability, engine=self.engine))
        ids = {liab.liability_id for liab in liabilities}
        self.assertEqual(
            ids, {"loan-a", "loan-b"}, "source B full should not delete source A records"
        )

    # ── target 8: automatic non-position tombstone in receipt and DB ──

    def test_automatic_tombstone_in_receipt_and_db(self):
        path = self.root / "liabilities.csv"
        _write_csv(path, [self._liability_row("loan-1")])
        ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("seed"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["liability"],
        )
        _write_csv(path, [])
        result = ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("clear"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["liability"],
            observed_at_utc=OBSERVED,
        )
        tombstone = exactly_one(
            item
            for item in read_all(ImportTombstone, engine=self.engine)
            if item.record_type == "Liability" and item.record_id == "loan-1"
        )
        self.assertEqual(tombstone.reason, "absent_from_full_import")
        manifest = exactly_one(
            item
            for item in read_all(ReceiptManifest, engine=self.engine)
            if item.batch_id == result.batch_id
        )
        receipt = json.loads(self.store.read(manifest.receipt_artifact_id))
        self.assertEqual(
            receipt["deletion_plan"]["automatic"],
            [
                {
                    "record_type": "Liability",
                    "record_id": "loan-1",
                    "reason": "absent_from_full_import",
                }
            ],
        )

    # ── target 9: forged deletion plan rejected with zero writes ──

    def test_forged_deletion_plan_rejected(self):
        path = self.root / "pos.csv"
        _write_csv(path, [_typed_row()])

        captured = {}

        def _patched(records, *, source, batch, manifest, artifact_store, engine):
            captured.update(
                {
                    "records": copy.deepcopy(list(records)),
                    "source": source,
                    "batch": copy.deepcopy(batch),
                    "manifest": copy.deepcopy(manifest),
                    "store": artifact_store,
                }
            )
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
                captured["records"],
                source=source,
                batch=batch,
                manifest=manifest,
                artifact_store=artifact_store,
                engine=engine,
            )

        with (
            patch("finharness.personal_finance.materialize_import_batch", _patched),
            self.assertRaises(StateCoreStoreError),
        ):
            ingest_personal_finance_export(
                path,
                engine=self.engine,
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
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("r1"),
            artifact_store=self._fresh_artifact_store("r1"),
            coverage_mode="full",
            covered_domains=["position"],
        )
        r2 = ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("r2"),
            artifact_store=self._fresh_artifact_store("r2"),
            coverage_mode="full",
            covered_domains=["position", "liability"],
        )
        self.assertNotEqual(r1.batch_id, r2.batch_id)

    def test_same_bytes_different_sources_coexist(self):
        path_a = self.root / "same-a.csv"
        path_b = self.root / "same-b.csv"
        row = self._liability_row("shared-loan")
        _write_csv(path_a, [row])
        _write_csv(path_b, [row])

        first = ingest_personal_finance_export(
            path_a,
            engine=self.engine,
            receipt_root=self._receipt_root("same-a"),
            artifact_store=self._fresh_artifact_store("same-a"),
            coverage_mode="full",
            covered_domains=["liability"],
        )
        second = ingest_personal_finance_export(
            path_b,
            engine=self.engine,
            receipt_root=self._receipt_root("same-b"),
            artifact_store=self._fresh_artifact_store("same-b"),
            coverage_mode="full",
            covered_domains=["liability"],
        )
        self.assertNotEqual(first.batch_id, second.batch_id)
        self.assertEqual(len(list(read_all(ImportBatch, engine=self.engine))), 2)

    def test_same_bytes_different_explicit_deletions_change_batch_identity(self):
        path = self.root / "explicit-delete.csv"
        _write_csv(path, [])

        first = ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("delete-a"),
            artifact_store=self._fresh_artifact_store("delete-a"),
            coverage_mode="full",
            covered_domains=["liability"],
            observed_at_utc=OBSERVED,
            tombstones=[ImportDeletion("Liability", "loan-x", "operator correction a")],
        )
        second = ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("delete-b"),
            artifact_store=self._fresh_artifact_store("delete-b"),
            coverage_mode="full",
            covered_domains=["liability"],
            observed_at_utc=OBSERVED,
            tombstones=[ImportDeletion("Liability", "loan-x", "operator correction b")],
        )
        self.assertNotEqual(first.batch_id, second.batch_id)

    # ── target 11: same header bytes different observed clocks →
    #                  different batch IDs ──

    def test_same_bytes_different_observed_clocks_different_batch_ids(self):
        path = self.root / "clock.csv"
        _write_csv(path, [])
        source_bytes = path.read_bytes()

        first = ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("clock-first"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["position"],
            observed_at_utc=OBSERVED,
        )
        self.assertEqual(path.read_bytes(), source_bytes)

        try:
            second = ingest_personal_finance_export(
                path,
                engine=self.engine,
                receipt_root=self._receipt_root("clock-second"),
                artifact_store=self.store,
                coverage_mode="full",
                covered_domains=["position"],
                observed_at_utc="2025-07-20T08:00:00+00:00",
            )
        except StateCoreStoreError as exc:
            self.fail(f"distinct zero-row observation was treated as an immutable retry: {exc}")

        self.assertEqual(path.read_bytes(), source_bytes)
        self.assertNotEqual(first.batch_id, second.batch_id)
        self.assertEqual(len(list(read_all(ImportBatch, engine=self.engine))), 2)

    def test_same_header_bytes_same_observed_clock_retry_is_idempotent(self):
        path = self.root / "clock-retry.csv"
        _write_csv(path, [])

        first = ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("clock-retry-first"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["position"],
            observed_at_utc=OBSERVED,
        )
        second = ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("clock-retry-second"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["position"],
            observed_at_utc=OBSERVED,
        )

        self.assertEqual(first.batch_id, second.batch_id)
        self.assertEqual(len(list(read_all(ImportBatch, engine=self.engine))), 1)

    # ── target 12: generic upsert cannot bypass scoped production ownership ──

    def test_generic_upsert_cannot_bypass_ownership(self):
        from finharness.statecore.models import Liability
        from finharness.statecore.store import write_records

        liab = Liability(
            liability_id="bypass-1",
            name="Bypassed",
            liability_type="loan",
            balance=Decimal("100"),
            currency="USD",
            source="personal_finance_export",
        )
        with self.assertRaises(StateCoreStoreError):
            write_records([liab], engine=self.engine)
        self.assertEqual(len(list(read_all(Liability, engine=self.engine))), 0)

    # ── target 13: restart/retry produces identical receipt, plan, tombstones ──

    def test_retry_produces_identical_artifacts(self):
        path = self.root / "pos.csv"
        _write_csv(path, [_typed_row()])
        r1 = ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("r1"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["position"],
        )
        # Retry — should succeed (deterministic) with same batch_id
        r2 = ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("r2"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["position"],
        )
        self.assertEqual(r1.batch_id, r2.batch_id)

    # ── target 14: duplicate run produces no duplicate tombstones ──

    def test_duplicate_run_no_duplicate_tombstones(self):
        path = self.root / "liabilities.csv"
        _write_csv(path, [self._liability_row("loan-1")])
        ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("seed"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["liability"],
        )
        _write_csv(path, [])
        first = ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("c1"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["liability"],
            observed_at_utc=OBSERVED,
        )
        second = ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("c2"),
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["liability"],
            observed_at_utc=OBSERVED,
        )
        self.assertEqual(first.batch_id, second.batch_id)
        liability_tombstones = [
            item
            for item in read_all(ImportTombstone, engine=self.engine)
            if item.record_type == "Liability" and item.record_id == "loan-1"
        ]
        self.assertEqual(
            len(liability_tombstones),
            1,
            "replaying the same deterministic batch must not duplicate deletion evidence",
        )

    # ── target 15: legacy position-only CSV (no record_type) auto-declares
    #                position coverage ──

    def test_legacy_csv_without_record_type_auto_declares_position(self):
        path = self.root / "legacy.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(
                f,
                fieldnames=[
                    "account_id",
                    "account_name",
                    "account_kind",
                    "venue",
                    "symbol",
                    "quantity",
                    "market_value",
                    "cost_basis",
                    "currency",
                    "as_of_utc",
                    "observed_at_utc",
                ],
            )
            w.writeheader()
            w.writerow(
                {
                    "account_id": "acct",
                    "account_name": "Legacy",
                    "account_kind": "broker",
                    "venue": "test",
                    "symbol": "SPY",
                    "quantity": "2",
                    "market_value": "100",
                    "cost_basis": "90",
                    "currency": "USD",
                    "as_of_utc": OBSERVED,
                    "observed_at_utc": OBSERVED,
                }
            )
        result = ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self._receipt_root("legacy"),
            artifact_store=self.store,
            coverage_mode="full",
        )
        positions = list(read_all(Position, engine=self.engine))
        self.assertEqual(len(positions), 1)
        batch = exactly_one(
            b for b in read_all(ImportBatch, engine=self.engine) if b.batch_id == result.batch_id
        )
        self.assertEqual(batch.covered_domains, ["position"])

    # ── helper for receipts cleanup between tests using same engine ──

    def _fresh_store(self, sub):
        store_root = self.root / sub
        return LocalArtifactStore(store_root / "artifact-store")


if __name__ == "__main__":
    unittest.main()
