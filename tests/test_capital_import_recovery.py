"""Acceptance coverage for receipt/database reconciliation and safe recovery."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlmodel import Session, select

from finharness.artifact_store import LocalArtifactStore
from finharness.capital_import_recovery import (
    audit_capital_imports,
    batch_is_verified,
    recover_capital_imports,
)
from finharness.personal_finance import ingest_personal_finance_export
from finharness.statecore.models import Position, ReceiptIndex, ReceiptManifest, Snapshot
from finharness.statecore.store import (
    StateCoreStoreError,
    init_state_core,
)


class CapitalImportRecoveryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts"
        self.source = self.root / "capital.csv"
        self.engine = init_state_core(self.root / "state.db")
        self.addCleanup(self.engine.dispose)
        self.store = LocalArtifactStore(self.receipt_root / "artifact-store")
        with self.source.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
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
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "account_id": "Assets:Cash",
                    "account_name": "Cash",
                    "account_kind": "cash",
                    "venue": "manual",
                    "symbol": "USD",
                    "quantity": "100",
                    "market_value": "100",
                    "cost_basis": "",
                    "currency": "USD",
                    "as_of_utc": "2026-07-13T00:00:00+00:00",
                }
            )

    def ingest(self):
        return ingest_personal_finance_export(
            self.source,
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )

    def test_clean_materialization_is_verified(self) -> None:
        result = self.ingest()
        report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(report.ok)
        self.assertEqual(report.verified_batch_ids, (result.batch_id,))
        self.assertTrue(
            batch_is_verified(
                result.batch_id,
                engine=self.engine,
                receipt_root=self.receipt_root,
                artifact_store=self.store,
            )
        )

    def test_missing_and_corrupt_receipt_files_fail_closed_then_restore(self) -> None:
        result = self.ingest()
        receipt_path = Path(result.receipt_ref)
        receipt_path.unlink()
        missing = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertIn("receipt_file_missing", {item.code for item in missing.findings})
        self.assertFalse(
            batch_is_verified(
                result.batch_id,
                engine=self.engine,
                receipt_root=self.receipt_root,
                artifact_store=self.store,
            )
        )
        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered.after.ok)
        receipt_path.write_text("{corrupt", encoding="utf-8")
        corrupt = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertIn("receipt_file_hash_mismatch", {item.code for item in corrupt.findings})
        second = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(second.after.ok)

    def test_receipt_without_materialization_replays_idempotently(self) -> None:
        with (
            patch(
                "finharness.personal_finance.materialize_import_batch",
                side_effect=StateCoreStoreError("crash before database commit"),
            ),
            self.assertRaises(StateCoreStoreError),
        ):
            self.ingest()
        before = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertEqual(
            {item.code for item in before.findings},
            {"receipt_without_materialization"},
        )
        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered.after.ok)
        self.assertTrue(any(action.startswith("replayed:") for action in recovered.actions))
        replay = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(replay.after.ok)
        self.assertFalse(any(action.startswith("replayed:") for action in replay.actions))

    def test_db_rows_without_immutable_receipt_bytes_never_verify(self) -> None:
        result = self.ingest()
        with Session(self.engine) as session:
            manifest = session.exec(select(ReceiptManifest)).one()
        descriptor = self.store.descriptor(manifest.receipt_artifact_id)
        object_path = (
            self.receipt_root
            / "artifact-store"
            / "objects"
            / descriptor.content_sha256[:2]
            / f"{descriptor.content_sha256}.bin"
        )
        object_path.unlink()
        report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertNotIn(result.batch_id, report.verified_batch_ids)
        self.assertIn(
            "manifest_receipt_artifact_hash_mismatch",
            {item.code for item in report.findings},
        )
        recovery = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertFalse(recovery.after.ok)
        self.assertTrue(recovery.unresolved_findings)
        with Session(self.engine) as session:
            self.assertIsNotNone(session.get(Snapshot, result.snapshot_id))

    def test_missing_snapshot_and_stale_indexes_are_repaired(self) -> None:
        result = self.ingest()
        with Session(self.engine) as session:
            for position in session.exec(
                select(Position).where(Position.snapshot_id == result.snapshot_id)
            ).all():
                session.delete(position)
            session.flush()
            snapshot = session.get(Snapshot, result.snapshot_id)
            assert snapshot is not None
            session.delete(snapshot)
            session.commit()
        index_path = self.receipt_root / "artifact-store" / "index.json"
        index_path.write_text(
            json.dumps(
                {
                    "schema": "finharness.artifact_index.v1",
                    "artifacts": {"stale": "0" * 64},
                }
            ),
            encoding="utf-8",
        )
        stale = ReceiptIndex(
            receipt_id="stale_import_index",
            kind="personal_finance_export",
            path=str(self.root / "missing.json"),
        )
        with Session(self.engine) as session:
            session.add(stale)
            session.commit()
        before = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        codes = {item.code for item in before.findings}
        self.assertIn("materialized_snapshot_missing", codes)
        self.assertIn("artifact_stale_index", codes)
        self.assertIn("receipt_index_without_manifest", codes)
        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered.after.ok)
        with Session(self.engine) as session:
            receipt_ids = {
                item.receipt_id for item in session.exec(select(ReceiptIndex)).all()
            }
        self.assertNotIn(
            "stale_import_index",
            receipt_ids,
        )
        recovery_path = self.receipt_root / "recovery" / f"{recovered.recovery_id}.json"
        self.assertTrue(recovery_path.is_file())


if __name__ == "__main__":
    unittest.main()
