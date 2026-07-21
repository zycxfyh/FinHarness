# ruff: noqa: E501, E402
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
from finharness.statecore.import_models import ImportTombstone
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

    def ingest_liability_deletion(self):
        fieldnames = [
            "record_type",
            "liability_id",
            "name",
            "liability_type",
            "balance",
            "currency",
            "as_of_utc",
        ]
        with self.source.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(
                {
                    "record_type": "liability",
                    "liability_id": "loan-recovery",
                    "name": "Recovery Loan",
                    "liability_type": "loan",
                    "balance": "100",
                    "currency": "USD",
                    "as_of_utc": "2026-07-13T00:00:00+00:00",
                }
            )
        ingest_personal_finance_export(
            self.source,
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["liability"],
        )
        with self.source.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
        result = ingest_personal_finance_export(
            self.source,
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["liability"],
            observed_at_utc="2026-07-14T00:00:00+00:00",
        )
        with Session(self.engine) as session:
            tombstone = session.exec(
                select(ImportTombstone).where(ImportTombstone.batch_id == result.batch_id)
            ).one()
        return result, tombstone

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

    def test_missing_tombstone_fails_audit_and_recovery_restores_it(self) -> None:
        result, tombstone = self.ingest_liability_deletion()
        with Session(self.engine) as session:
            persisted = session.get(ImportTombstone, tombstone.tombstone_id)
            assert persisted is not None
            session.delete(persisted)
            session.commit()

        before = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertFalse(before.ok)
        self.assertIn("import_tombstone_missing", {item.code for item in before.findings})
        self.assertNotIn(result.batch_id, before.verified_batch_ids)

        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered.after.ok)
        with Session(self.engine) as session:
            restored = session.get(ImportTombstone, tombstone.tombstone_id)
        self.assertIsNotNone(restored)
        assert restored is not None
        self.assertEqual(restored.reason, "absent_from_full_import")

    def test_tombstone_contract_drift_fails_audit_and_is_repaired(self) -> None:
        result, tombstone = self.ingest_liability_deletion()
        with Session(self.engine) as session:
            persisted = session.get(ImportTombstone, tombstone.tombstone_id)
            assert persisted is not None
            persisted.reason = "forged_reason"
            session.commit()

        before = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertFalse(before.ok)
        self.assertIn(
            "import_tombstone_contract_mismatch",
            {item.code for item in before.findings},
        )
        self.assertNotIn(result.batch_id, before.verified_batch_ids)

        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered.after.ok)
        with Session(self.engine) as session:
            restored = session.get(ImportTombstone, tombstone.tombstone_id)
        assert restored is not None
        self.assertEqual(restored.reason, "absent_from_full_import")

    def test_receipt_undeclared_extra_tombstone_fails_closed(self) -> None:
        result, tombstone = self.ingest_liability_deletion()
        with Session(self.engine) as session:
            session.add(
                ImportTombstone(
                    tombstone_id="extra-undeclared-tombstone",
                    batch_id=result.batch_id,
                    source_kind=tombstone.source_kind,
                    record_type="Liability",
                    record_id="undeclared-record",
                    reason="not_in_receipt_plan",
                    source_refs=list(tombstone.source_refs),
                    as_of_utc=tombstone.as_of_utc,
                    authority_level=tombstone.authority_level,
                )
            )
            session.commit()

        report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertFalse(report.ok)
        self.assertIn("import_tombstone_extra", {item.code for item in report.findings})
        self.assertNotIn(result.batch_id, report.verified_batch_ids)

    def test_missing_snapshot_requires_recovery_not_ordinary_retry(self) -> None:
        result = self.ingest()
        with Session(self.engine) as session:
            for position in session.exec(
                select(Position).where(Position.snapshot_id == result.snapshot_id)
            ).all():
                session.delete(position)
            snapshot = session.get(Snapshot, result.snapshot_id)
            assert snapshot is not None
            session.delete(snapshot)
            session.commit()

        with self.assertRaisesRegex(StateCoreStoreError, "recovery"):
            self.ingest()
        with Session(self.engine) as session:
            self.assertIsNone(session.get(Snapshot, result.snapshot_id))

        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered.after.ok)
        with Session(self.engine) as session:
            self.assertIsNotNone(session.get(Snapshot, result.snapshot_id))

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


from finharness.statecore.snapshot_ingest import ingest_broker_read_receipt


class RecoveryDriftMatrixTest(unittest.TestCase):
    """Part F: every ReceiptIndex drift is detected, blocks verification, and is repaired."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.import_root = self.root / "receipts" / "capital-imports" / "broker-read"
        self.store = LocalArtifactStore(self.import_root / "artifact-store")
        self.source = self.root / "broker-read" / "portfolio.json"
        self.source.parent.mkdir(parents=True, exist_ok=True)
        self.source.write_text(json.dumps({
            "receipt_id": "receipt_drift", "kind": "broker_read",
            "created_at_utc": "2026-07-18T09:00:00+00:00",
            "effective_at_utc": "2026-07-18T09:00:00+00:00",
            "observed_at_utc": "2026-07-18T09:00:00+00:00",
            "valued_at_utc": "2026-07-18T09:00:00+00:00",
            "broker": "manual", "environment": "paper",
            "account": {"id": "acct_drift", "status": "ACTIVE"},
            "positions": [{"symbol": "SPY", "qty": "2", "market_value": "100",
                           "unit_price": "50", "currency": "USD",
                           "asset_class": "equity", "exchange": "ARCX",
                           "price_source_ref": "fixture:drift"}],
        }), encoding="utf-8")
        self.result = ingest_broker_read_receipt(
            self.source, engine=self.engine,
            receipt_root=self.import_root, artifact_store=self.store,
        )

    def _mutate_and_verify(self, mutate, expected_code):
        with Session(self.engine) as session:
            index = session.get(ReceiptIndex, self.result.receipt_id)
            self.assertIsNotNone(index)
            mutate(index)
            session.commit()
        before = audit_capital_imports(engine=self.engine, receipt_root=self.import_root, artifact_store=self.store)
        codes = {f.code for f in before.findings}
        self.assertIn(expected_code, codes, f"missing {expected_code} in {codes}")
        self.assertFalse(batch_is_verified(self.result.batch_id, engine=self.engine, receipt_root=self.import_root, artifact_store=self.store))
        recovery = recover_capital_imports(engine=self.engine, receipt_root=self.import_root, artifact_store=self.store)
        actions = [a for a in recovery.actions if "rebuilt_receipt_index" in a]
        self.assertTrue(actions, f"no rebuild: {recovery.actions}")
        self.assertTrue(recovery.after.ok, recovery.after)
        self.assertTrue(batch_is_verified(self.result.batch_id, engine=self.engine, receipt_root=self.import_root, artifact_store=self.store))

    def test_kind_drift(self) -> None:
        self._mutate_and_verify(lambda i: setattr(i, "kind", "wrong_kind"), "manifest_receipt_index_missing_or_stale")
    def test_path_drift(self) -> None:
        self._mutate_and_verify(lambda i: setattr(i, "path", "wrong_path"), "receipt_index_path_drift")
    def test_created_at_drift(self) -> None:
        self._mutate_and_verify(lambda i: setattr(i, "created_at_utc", "2000-01-01T00:00:00+00:00"), "receipt_index_created_at_drift")
    def test_source_refs_drift(self) -> None:
        self._mutate_and_verify(lambda i: setattr(i, "source_refs", ["wrong"]), "receipt_index_source_refs_drift")
    def test_refs_upstream_drift(self) -> None:
        self._mutate_and_verify(lambda i: setattr(i, "refs", ["wu", "ws"]), "receipt_index_refs_drift")
    def test_refs_source_artifact_drift(self) -> None:
        first = "ri" if not hasattr(self, 'result') else (self.result.receipt_id or "")
        self._mutate_and_verify(lambda i: setattr(i, "refs", [first, "wrong_artifact"]), "receipt_index_refs_drift")
    def test_refs_receipt_artifact_substituted(self) -> None:
        self._mutate_and_verify(lambda i: setattr(i, "refs", ["ri", "receipt_artifact_instead"]), "receipt_index_refs_drift")
    def test_missing_index(self) -> None:
        with Session(self.engine) as session:
            index = session.get(ReceiptIndex, self.result.receipt_id)
            session.delete(index)
            session.commit()
        before = audit_capital_imports(engine=self.engine, receipt_root=self.import_root, artifact_store=self.store)
        codes = {f.code for f in before.findings}
        self.assertIn("manifest_receipt_index_missing_or_stale", codes, str(codes))
        recovery = recover_capital_imports(engine=self.engine, receipt_root=self.import_root, artifact_store=self.store)
        self.assertTrue(recovery.after.ok, recovery.after)
        self.assertTrue(batch_is_verified(self.result.batch_id, engine=self.engine, receipt_root=self.import_root, artifact_store=self.store))
    def test_legacy_broker_read_evidence_preserved(self) -> None:
        with Session(self.engine) as session:
            session.add(ReceiptIndex(receipt_id="receipt_legacy_drift", kind="broker_read", path="legacy.json", created_at_utc="2025-01-01T00:00:00+00:00"))
            session.commit()
        before = audit_capital_imports(engine=self.engine, receipt_root=self.import_root, artifact_store=self.store)
        self.assertTrue(before.ok, before)
        recover_capital_imports(engine=self.engine, receipt_root=self.import_root, artifact_store=self.store)
        with Session(self.engine) as session:
            legacy = session.get(ReceiptIndex, "receipt_legacy_drift")
            self.assertIsNotNone(legacy)
            self.assertEqual(legacy.kind, "broker_read")
