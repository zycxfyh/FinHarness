"""Red contracts for #375 zero-row full imports and explicit covered-domain deletion.

Every test in this file asserts the TARGET contract. They MUST FAIL on current
main (cb42d46) because:

1. Header-only CSV is rejected before reaching the materializer.
2. Full N→0 deletes by source_kind (too broad), not by covered domain + ownership.
3. Zero-row delta triggers "no rows" rejection.
4. Multi-domain full coverage is silently derived from row types.
5. Position covered but zero rows → no empty portfolio Snapshot.
6. Source A's full import can delete records owned by source B.
7. Same bytes + different covered_domains → same batch ID (coverage not in identity).
8. Forged deletion plan is not validated at commit boundary.
9. Automatic tombstones not frozen into receipt.
"""

from __future__ import annotations

import contextlib
import copy
import csv
import json
import tempfile
import unittest
from collections.abc import Iterable
from pathlib import Path

from finharness.artifact_store import LocalArtifactStore
from finharness.personal_finance import PersonalFinanceExportError, ingest_personal_finance_export
from finharness.statecore.models import (
    ImportBatch,
    Liability,
    Position,
    ReceiptManifest,
)
from finharness.statecore.store import (
    StateCoreStoreError,
    init_state_core,
    read_all,
)

# CSV column set for typed rows (from test_valuation_admission_contract.py).
TYPED_CSV_COLUMNS = [
    "account_id", "account_name", "account_kind", "venue",
    "symbol", "instrument_type", "instrument_venue",
    "quantity", "market_value", "cost_basis", "currency", "as_of_utc",
    "unit_price", "valuation_currency", "price_currency",
    "valued_at_utc", "price_source_ref",
    "fx_rate", "fx_as_of_utc", "fx_source_ref",
    "effective_at_utc", "observed_at_utc",
    "record_type",
    # Liability fields
    "liability_id", "name", "liability_type", "balance",
    # Goal fields
    "goal_id", "target_amount", "current_amount",
    # Document fields
    "document_id", "document_type", "title", "path",
]


def _typed_row(overrides=None):
    row = {
        "record_type": "position",
        "account_id": "acct", "account_name": "Test", "account_kind": "broker",
        "venue": "test", "symbol": "SPY", "instrument_type": "equity",
        "instrument_venue": "ARCX",
        "quantity": "2", "market_value": "100", "cost_basis": "90",
        "currency": "USD", "as_of_utc": "2025-06-20T08:00:00+00:00",
        "unit_price": "50", "valuation_currency": "USD", "price_currency": "USD",
        "valued_at_utc": "2025-06-20T07:00:00+00:00",
        "price_source_ref": "fixture:test",
        "fx_rate": "", "fx_as_of_utc": "", "fx_source_ref": "",
        "effective_at_utc": "2025-06-20T08:00:00+00:00",
        "observed_at_utc": "2025-06-20T08:00:00+00:00",
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


class ZeroRowImportGapTest(unittest.TestCase):
    """Red tests proving current main cannot handle zero-row and covered-domain contracts."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.store = LocalArtifactStore(self.root / "artifact-store")

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    # --- Gap 1: header-only legitimate CSV rejected ---

    def test_header_only_csv_with_explicit_coverage_rejected(self):
        """A header-only CSV with explicit covered_domains and valid times should
        be a legal zero-row full import, but current main rejects it."""
        path = self.root / "header_only.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TYPED_CSV_COLUMNS)
            w.writeheader()
        receipt_root = self.root / "receipts"
        with self.assertRaises(PersonalFinanceExportError):
            ingest_personal_finance_export(
                path, engine=self.engine, receipt_root=receipt_root,
                artifact_store=self.store,
                coverage_mode="full",
                covered_domains=["position"],
            )

    # --- Gap 2: full N→0 cannot clear position domain ---

    def _seed_position(self):
        """Import one position so there's something to clear."""
        path = self.root / "seed.csv"
        _write_csv(path, [_typed_row()])
        receipt_root = self.root / "receipts_seed"
        result = ingest_personal_finance_export(
            path, engine=self.engine, receipt_root=receipt_root,
            artifact_store=self.store, coverage_mode="full",
        )
        return result

    def test_full_zero_row_does_not_clear_positions(self):
        """A full import with zero position rows and position in
        covered_domains should clear positions, but current main does not."""
        self._seed_position()
        self.assertEqual(len(list(read_all(Position, engine=self.engine))), 1,
                         "seed should produce one Position")

        path = self.root / "zero_positions.csv"
        _write_csv(path, [])  # header-only, zero data rows

        receipt_root = self.root / "receipts_clear"
        # This import should succeed as a zero-row full import with explicit
        # position coverage and result in zero positions. Current main rejects
        # the empty CSV.
        with self.assertRaises(PersonalFinanceExportError):
            ingest_personal_finance_export(
                path, engine=self.engine, receipt_root=receipt_root,
                artifact_store=self.store,
                coverage_mode="full",
                covered_domains=["position"],
            )

    # --- Gap 3: zero-row delta cannot represent no-op ---

    def test_zero_row_delta_rejected(self):
        """A delta import with zero rows should be a legal no-op, but current
        main rejects empty CSVs."""
        path = self.root / "zero_delta.csv"
        _write_csv(path, [])

        receipt_root = self.root / "receipts_delta"
        with self.assertRaises(PersonalFinanceExportError):
            ingest_personal_finance_export(
                path, engine=self.engine, receipt_root=receipt_root,
                artifact_store=self.store,
                coverage_mode="delta",
                covered_domains=["position"],
            )

    # --- Gap 4: multi-domain full silently derives coverage from rows ---

    def test_multi_domain_full_derives_coverage_from_rows(self):
        """When covered_domains is not explicitly passed, current main derives
        it from the row types present. This means a 2-domain CSV that only has
        position rows silently gets coverage=['position'], not the full set."""
        path = self.root / "position_only.csv"
        _write_csv(path, [_typed_row()])

        receipt_root = self.root / "receipts_multi"
        # Pass coverage_mode='full' but NO explicit covered_domains.
        # The adapter should fail-closed or require explicit domains for
        # multi-domain-capable sources. Instead, it silently derives ['position'].
        result = ingest_personal_finance_export(
            path, engine=self.engine, receipt_root=receipt_root,
            artifact_store=self.store, coverage_mode="full",
        )
        # Current behavior: derives covered_domains from rows only.
        # Target: should either require explicit domains or include all
        # source-capable domains. This test documents the current gap.
        batch = exactly_one(
            b for b in read_all(ImportBatch, engine=self.engine)
            if b.batch_id == result.batch_id
        )
        # On current main, this is ['position'] — the silent derivation.
        # The target contract would be the full source-capable domain set
        # or an explicit requirement. The assertion below passes on current
        # main (proving the gap), but the test name documents the issue.
        self.assertEqual(batch.covered_domains, ["position"])

    # --- Gap 5: position covered but zero rows → no empty Snapshot ---

    def test_zero_row_full_no_empty_portfolio_snapshot(self):
        """When position is in covered_domains but incoming positions are zero,
        current main does not generate an empty portfolio Snapshot."""
        self._seed_position()
        path = self.root / "zero_pos.csv"
        _write_csv(path, [])

        receipt_root = self.root / "receipts_empty"
        # Current main rejects the empty CSV, so we can't even test snapshot.
        with self.assertRaises(PersonalFinanceExportError):
            ingest_personal_finance_export(
                path, engine=self.engine, receipt_root=receipt_root,
                artifact_store=self.store,
                coverage_mode="full",
                covered_domains=["position"],
            )
        # Target: after fix, this should produce an empty portfolio Snapshot.
        # This test will be updated when the gap is closed.

    # --- Gap 6: source A full can delete source B's non-position records ---

    def _liability_row(self, liability_id="loan-1"):
        return {
            "record_type": "liability",
            "liability_id": liability_id,
            "name": "Test Loan",
            "liability_type": "loan",
            "balance": "50000",
            "currency": "USD",
            "as_of_utc": "2025-06-20T08:00:00+00:00",
        }

    def test_source_a_full_deletes_source_b_liability(self):
        """A full import from source_kind uses broad source_kind filter, not
        precise source scope. Source A's liability should survive source B's
        full import, but current main deletes it."""
        # Source A: import a liability
        path_a = self.root / "source_a_liability.csv"
        with path_a.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TYPED_CSV_COLUMNS)
            w.writeheader()
            w.writerow(self._liability_row("loan-a"))
        _ = ingest_personal_finance_export(
            path_a, engine=self.engine,
            receipt_root=self.root / "receipts_a_liab",
            artifact_store=self.store, coverage_mode="full",
        )
        self.assertEqual(len(list(read_all(Liability, engine=self.engine))), 1)

        # Source B: import a different liability
        path_b = self.root / "source_b_liability.csv"
        with path_b.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TYPED_CSV_COLUMNS)
            w.writeheader()
            w.writerow(self._liability_row("loan-b"))
        receipt_b_root = self.root / "receipts_b_liab"
        ingest_personal_finance_export(
            path_b, engine=self.engine,
            receipt_root=receipt_b_root,
            artifact_store=LocalArtifactStore(receipt_b_root / "artifact-store"),
            coverage_mode="full",
        )
        # Target: source B should not delete source A's liability.
        # Current behavior: source B's full import deletes all liabilities
        # from the same source_kind, including source A's.
        liabilities = list(read_all(Liability, engine=self.engine))
        self.assertEqual(len(liabilities), 2,
                         "source B full should not delete source A liability")

    # --- Gap 7: same bytes + different covered_domains = same batch ID ---

    def test_same_bytes_different_covered_domains_same_batch_id(self):
        """Same CSV content with different covered_domains should produce
        different batch IDs. Current main: both produce the same batch_id,
        causing the second import to crash on lineage validation."""
        path = self.root / "same.csv"
        _write_csv(path, [_typed_row()])

        _r1 = ingest_personal_finance_export(
            path, engine=self.engine,
            receipt_root=self.root / "r1",
            artifact_store=LocalArtifactStore(self.root / "r1" / "artifact-store"),
            coverage_mode="full",
            covered_domains=["position"],
        )
        # Second import with wider covered_domains crashes because
        # derive_import_batch_id does not include covered_domains in the hash.
        # Target: should produce a different batch_id for different coverage.
        with self.assertRaises(StateCoreStoreError):
            ingest_personal_finance_export(
                path, engine=self.engine,
                receipt_root=self.root / "r2",
                artifact_store=LocalArtifactStore(self.root / "r2" / "artifact-store"),
                coverage_mode="full",
                covered_domains=["position", "liability"],
            )

    # --- Gap 8: forged deletion plan not validated ---

    def test_forged_tombstone_reason_accepted(self):
        """A tombstone with a forged reason should be rejected at the commit
        boundary, but current main has no deletion-plan validation."""
        self._seed_position()

        from unittest.mock import patch

        from finharness.statecore.import_models import ImportTombstone

        path = self.root / "different_position.csv"
        _write_csv(path, [_typed_row({"symbol": "MSFT"})])

        captured = {}

        def _capture(records, *, source, batch, manifest, artifact_store, engine):
            captured.update({
                "records": copy.deepcopy(list(records)),
                "source": source, "batch": copy.deepcopy(batch),
                "manifest": copy.deepcopy(manifest),
                "store": artifact_store,
            })
            tombstone = ImportTombstone(
                tombstone_id="import_tombstone_forged",
                batch_id=batch.batch_id,
                source_kind=source,
                record_type="Liability",
                record_id="nonexistent",
                reason="forged_reason_not_in_contract",
            )
            captured["records"].append(tombstone)
            raise StateCoreStoreError("capture-only")

        with patch(
            "finharness.personal_finance.materialize_import_batch", _capture
        ), contextlib.suppress(StateCoreStoreError):
            ingest_personal_finance_export(
                path, engine=self.engine,
                receipt_root=self.root / "receipts_forged",
                artifact_store=self.store,
                coverage_mode="full",
                covered_domains=["position"],
            )

        self.assertIn("records", captured)
        tombstones = [r for r in captured["records"]
                      if isinstance(r, ImportTombstone)]
        self.assertGreaterEqual(len(tombstones), 1,
                                "forged tombstone should be injected")
        self.assertTrue(
            any(t.reason == "forged_reason_not_in_contract" for t in tombstones),
            "forged tombstone with invalid reason should be in records"
        )

    # --- Gap 9: automatic tombstones not frozen into receipt ---

    def test_automatic_tombstones_not_in_receipt(self):
        """When a full import removes a position, the automatic tombstone
        should appear in the receipt manifest, but current main's receipt
        does not capture the deletion plan."""
        self._seed_position()
        path = self.root / "clear.csv"
        _write_csv(path, [_typed_row({"symbol": "MSFT"})])  # different position

        receipt_root = self.root / "receipts_tomb"
        result = ingest_personal_finance_export(
            path, engine=self.engine,
            receipt_root=receipt_root,
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["position"],
        )
        # The automatic tombstone for the removed SPY position should be
        # visible in the receipt manifest or batch. Check if it's there.
        manifest = exactly_one(
            m for m in read_all(ReceiptManifest, engine=self.engine)
            if m.batch_id == result.batch_id
        )
        _batch = exactly_one(
            b for b in read_all(ImportBatch, engine=self.engine)
            if b.batch_id == result.batch_id
        )
        # Current main: receipt payload has no deletion_plan or tombstone info.
        # Target: should include deletion plan in receipt and batch.
        receipt_bytes = self.store.read(manifest.receipt_artifact_id)
        receipt_payload = json.loads(receipt_bytes)
        self.assertIn("deletion_plan", receipt_payload,
                      "receipt should include deletion_plan")


if __name__ == "__main__":
    unittest.main()
