# ruff: noqa: E501, E402
"""Acceptance coverage for receipt/database reconciliation and safe recovery."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import delete
from sqlmodel import Session, select

from finharness.artifact_store import LocalArtifactStore
from finharness.beancount_adapter import ingest_beancount_ledger
from finharness.capital_import_recovery import (
    _temporarily_restore_replay_sources,
    audit_capital_imports,
    batch_is_verified,
    recover_capital_imports,
)
from finharness.personal_finance import ingest_personal_finance_export
from finharness.statecore.import_models import ImportBatch, ImportDomainHead, ImportTombstone
from finharness.statecore.models import (
    Account,
    AccountIdentity,
    Liability,
    Position,
    ReceiptIndex,
    ReceiptManifest,
    Snapshot,
)
from finharness.statecore.store import (
    StateCoreStoreError,
    init_state_core,
    migrate_state_core,
    source_owner_key,
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

    def test_receipt_without_materialization_remains_fail_closed(self) -> None:
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
        self.assertFalse(recovered.after.ok)
        self.assertIn(
            "import_domain_head_missing",
            {item.code for item in recovered.after.findings},
        )
        with Session(self.engine) as session:
            self.assertEqual(list(session.exec(select(ImportDomainHead)).all()), [])
            self.assertEqual(list(session.exec(select(Account)).all()), [])
            self.assertEqual(list(session.exec(select(Position)).all()), [])


    def test_missing_tombstone_fails_audit_and_recovery_restores_it(self) -> None:
        result, tombstone = self.ingest_liability_deletion()
        with Session(self.engine) as session:
            persisted = session.get(ImportTombstone, tombstone.tombstone_id)
            assert persisted is not None
            session.delete(persisted)
            session.commit()

        with self.assertRaisesRegex(StateCoreStoreError, "recovery"):
            ingest_personal_finance_export(
                self.source,
                engine=self.engine,
                receipt_root=self.receipt_root,
                artifact_store=self.store,
                coverage_mode="full",
                covered_domains=["liability"],
                observed_at_utc="2026-07-14T00:00:00+00:00",
            )
        with Session(self.engine) as session:
            self.assertIsNone(session.get(ImportTombstone, tombstone.tombstone_id))

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

    def test_missing_receipt_index_requires_recovery_not_ordinary_retry(self) -> None:
        result = self.ingest()
        with Session(self.engine) as session:
            receipt_index = session.get(ReceiptIndex, result.receipt_id)
            assert receipt_index is not None
            session.delete(receipt_index)
            session.commit()

        with self.assertRaisesRegex(StateCoreStoreError, "recovery"):
            self.ingest()
        with Session(self.engine) as session:
            self.assertIsNone(session.get(ReceiptIndex, result.receipt_id))

        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered.after.ok)
        with Session(self.engine) as session:
            self.assertIsNotNone(session.get(ReceiptIndex, result.receipt_id))

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


    def _write_liability_export(
        self,
        liability_id: str,
        *,
        balance: str,
        observed_at: str,
    ) -> None:
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
                    "liability_id": liability_id,
                    "name": liability_id,
                    "liability_type": "loan",
                    "balance": balance,
                    "currency": "USD",
                    "as_of_utc": observed_at,
                }
            )

    def _ingest_liability(self, observed_at: str):
        return ingest_personal_finance_export(
            self.source,
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["liability"],
            observed_at_utc=observed_at,
        )

    def test_missing_current_materialized_record_blocks_retry_then_recovers(self) -> None:
        observed = "2026-07-13T00:00:00+00:00"
        self._write_liability_export("loan-current", balance="100", observed_at=observed)
        result = self._ingest_liability(observed)
        with Session(self.engine) as session:
            row = session.get(Liability, "loan-current")
            assert row is not None
            session.delete(row)
            session.commit()

        report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertIn("materialized_record_missing", {item.code for item in report.findings})
        self.assertNotIn(result.batch_id, report.verified_batch_ids)
        with self.assertRaisesRegex(StateCoreStoreError, "recovery"):
            self._ingest_liability(observed)

        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered.after.ok, recovered.after)
        with Session(self.engine) as session:
            restored = session.get(Liability, "loan-current")
        self.assertIsNotNone(restored)

    def test_extra_current_owner_scoped_record_fails_materialization_proof(self) -> None:
        observed = "2026-07-13T00:00:00+00:00"
        self._write_liability_export("loan-expected", balance="100", observed_at=observed)
        result = self._ingest_liability(observed)
        with Session(self.engine) as session:
            session.add(
                Liability(
                    liability_id="loan-extra",
                    name="loan-extra",
                    liability_type="loan",
                    balance="9",
                    currency="USD",
                    source=source_owner_key("personal_finance_export", str(self.source)),
                    source_refs=[result.receipt_ref, str(self.source)],
                )
            )
            session.commit()

        report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertIn("materialized_record_extra", {item.code for item in report.findings})
        self.assertNotIn(result.batch_id, report.verified_batch_ids)

    def test_historical_recovery_never_restores_superseded_current_projection(self) -> None:
        first_time = "2026-07-13T00:00:00+00:00"
        second_time = "2026-07-14T00:00:00+00:00"
        self._write_liability_export("loan-a", balance="100", observed_at=first_time)
        first = self._ingest_liability(first_time)
        self._write_liability_export("loan-b", balance="200", observed_at=second_time)
        second = self._ingest_liability(second_time)

        with Session(self.engine) as session:
            first_snapshot = session.get(Snapshot, first.snapshot_id)
            assert first_snapshot is not None
            session.delete(first_snapshot)
            session.commit()

        before = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        historical = [
            item
            for item in before.findings
            if item.batch_id == first.batch_id and item.code == "materialized_record_missing"
        ]
        self.assertTrue(historical, before)
        self.assertEqual(
            {item.recovery_action for item in historical},
            {"restore_historical_evidence"},
        )

        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered.after.ok, recovered.after)
        with Session(self.engine) as session:
            liabilities = list(session.exec(select(Liability)).all())
            restored_snapshot = session.get(Snapshot, first.snapshot_id)
            liability_head = session.exec(
                select(ImportDomainHead).where(ImportDomainHead.domain == "liability")
            ).one()
        self.assertEqual(liability_head.batch_id, second.batch_id)
        self.assertEqual([item.liability_id for item in liabilities], ["loan-b"])
        self.assertEqual(str(liabilities[0].balance), "200")
        self.assertIsNotNone(restored_snapshot)
        self.assertTrue(batch_is_verified(
            second.batch_id,
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        ))



    def test_v16_migration_backfills_unique_latest_domain_head(self) -> None:
        first_time = "2026-07-13T00:00:00+00:00"
        second_time = "2026-07-14T00:00:00+00:00"
        self._write_liability_export("loan-a", balance="100", observed_at=first_time)
        first = self._ingest_liability(first_time)
        self._write_liability_export("loan-b", balance="200", observed_at=second_time)
        second = self._ingest_liability(second_time)
        with Session(self.engine) as session:
            session.exec(delete(ImportDomainHead))
            first_manifest = session.exec(
                select(ReceiptManifest).where(ReceiptManifest.batch_id == first.batch_id)
            ).one()
            second_manifest = session.exec(
                select(ReceiptManifest).where(ReceiptManifest.batch_id == second.batch_id)
            ).one()
            first_manifest.materialized_at_utc = "2026-07-13T00:00:00+00:00"
            second_manifest.materialized_at_utc = "2026-07-14T00:00:00+00:00"
            session.add(first_manifest)
            session.add(second_manifest)
            session.commit()
        with self.engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA user_version = 15")

        migrate_state_core(self.engine)

        with Session(self.engine) as session:
            head = session.exec(
                select(ImportDomainHead).where(ImportDomainHead.domain == "liability")
            ).one()
        self.assertEqual(head.batch_id, second.batch_id)

    def test_v16_migration_leaves_tied_domain_history_unresolved(self) -> None:
        first_time = "2026-07-13T00:00:00+00:00"
        second_time = "2026-07-14T00:00:00+00:00"
        self._write_liability_export("loan-a", balance="100", observed_at=first_time)
        first = self._ingest_liability(first_time)
        self._write_liability_export("loan-b", balance="200", observed_at=second_time)
        second = self._ingest_liability(second_time)
        with Session(self.engine) as session:
            session.exec(delete(ImportDomainHead))
            for batch_id in (first.batch_id, second.batch_id):
                manifest = session.exec(
                    select(ReceiptManifest).where(ReceiptManifest.batch_id == batch_id)
                ).one()
                manifest.materialized_at_utc = "2026-07-14T00:00:00+00:00"
                session.add(manifest)
            session.commit()
        with self.engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA user_version = 15")

        migrate_state_core(self.engine)

        with Session(self.engine) as session:
            heads = list(session.exec(select(ImportDomainHead)).all())
        self.assertEqual(heads, [])
        report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertFalse(report.ok)
        self.assertIn("import_domain_head_missing", {item.code for item in report.findings})

    def test_beancount_historical_recovery_uses_exact_bundle_without_rollback(self) -> None:
        ledger = self.root / "ledger.beancount"

        def ledger_text(balance: str, date: str) -> str:
            return (
                'option "operating_currency" "USD"\n'
                "2026-01-01 open Liabilities:Loan USD\n"
                "2026-01-01 open Equity:Opening\n\n"
                f'{date} * "Liability state"\n'
                f"  Liabilities:Loan  -{balance} USD\n"
                f"  Equity:Opening     {balance} USD\n"
            )

        first_bytes = ledger_text("100.00", "2026-01-02")
        second_bytes = ledger_text("200.00", "2026-01-03")
        ledger.write_text(first_bytes, encoding="utf-8")
        first = ingest_beancount_ledger(
            ledger,
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        ledger.write_text(second_bytes, encoding="utf-8")
        second = ingest_beancount_ledger(
            ledger,
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )

        with Session(self.engine) as session:
            first_snapshot = session.get(Snapshot, first.snapshot_id)
            assert first_snapshot is not None
            session.delete(first_snapshot)
            session.commit()

        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered.after.ok, recovered.after)
        self.assertEqual(ledger.read_text(encoding="utf-8"), second_bytes)
        with Session(self.engine) as session:
            liability = session.get(Liability, "liab_Liabilities_Loan_USD")
            restored_snapshot = session.get(Snapshot, first.snapshot_id)
        self.assertIsNotNone(liability)
        assert liability is not None
        self.assertEqual(str(liability.balance), "200.00")
        self.assertIsNotNone(restored_snapshot)
        self.assertTrue(
            batch_is_verified(
                second.batch_id,
                engine=self.engine,
                receipt_root=self.receipt_root,
                artifact_store=self.store,
            )
        )


    def test_runtime_recovery_preserves_valid_head_when_clocks_run_backward(self) -> None:
        later_clock = "2026-07-14T00:00:00+00:00"
        earlier_clock = "2026-07-13T00:00:00+00:00"
        self._write_liability_export("loan-a", balance="100", observed_at=later_clock)
        with patch("finharness.personal_finance.datetime") as clock:
            clock.now.return_value = datetime.fromisoformat(later_clock)
            first = self._ingest_liability(later_clock)
        self._write_liability_export("loan-b", balance="200", observed_at=earlier_clock)
        with patch("finharness.personal_finance.datetime") as clock:
            clock.now.return_value = datetime.fromisoformat(earlier_clock)
            second = self._ingest_liability(earlier_clock)
        with Session(self.engine) as session:
            head = session.exec(
                select(ImportDomainHead).where(ImportDomainHead.domain == "liability")
            ).one()
            self.assertEqual(head.batch_id, second.batch_id)
            snapshot = session.get(Snapshot, first.snapshot_id)
            assert snapshot is not None
            session.delete(snapshot)
            session.commit()

        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered.after.ok, recovered.after)
        with Session(self.engine) as session:
            head = session.exec(
                select(ImportDomainHead).where(ImportDomainHead.domain == "liability")
            ).one()
            liabilities = list(session.exec(select(Liability)).all())
        self.assertEqual(head.batch_id, second.batch_id)
        self.assertEqual([item.liability_id for item in liabilities], ["loan-b"])
        self.assertEqual(str(liabilities[0].balance), "200")

    def test_receipt_without_batch_never_gains_projection_authority_from_clock(self) -> None:
        current_time = "2026-07-13T00:00:00+00:00"
        orphan_time = "2026-07-14T00:00:00+00:00"
        self._write_liability_export("loan-current", balance="200", observed_at=current_time)
        current = self._ingest_liability(current_time)
        self._write_liability_export("loan-orphan", balance="999", observed_at=orphan_time)
        with (
            patch(
                "finharness.personal_finance.materialize_import_batch",
                side_effect=StateCoreStoreError("crash before database commit"),
            ),
            self.assertRaises(StateCoreStoreError),
        ):
            self._ingest_liability(orphan_time)

        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered.after.ok, recovered.after)
        with Session(self.engine) as session:
            head = session.exec(
                select(ImportDomainHead).where(ImportDomainHead.domain == "liability")
            ).one()
            liabilities = list(session.exec(select(Liability)).all())
            batches = list(session.exec(select(ImportBatch)).all())
        self.assertEqual(head.batch_id, current.batch_id)
        self.assertEqual([item.liability_id for item in liabilities], ["loan-current"])
        self.assertEqual(str(liabilities[0].balance), "200")
        self.assertEqual(len(batches), 2)

    def test_multifile_replay_prepare_failure_restores_every_changed_file(self) -> None:
        main = self.root / "ledger.beancount"
        included = self.root / "included.beancount"
        main.write_bytes(b"current-main")
        included.write_bytes(b"current-include")
        from finharness import capital_import_recovery as recovery_module

        original_write = recovery_module.atomic_write_bytes
        calls = 0

        def fail_second_write(path: Path, content: bytes) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("injected second replay write failure")
            original_write(path, content)

        with (
            patch(
                "finharness.capital_import_recovery.atomic_write_bytes",
                side_effect=fail_second_write,
            ),
            self.assertRaises(OSError),_temporarily_restore_replay_sources(
            [(main, b"historical-main"), (included, b"historical-include")]
        )
        ):
            self.fail("replay context must not be entered")

        self.assertEqual(main.read_bytes(), b"current-main")
        self.assertEqual(included.read_bytes(), b"current-include")

    def test_same_identity_liability_content_drift_requires_recovery(self) -> None:
        observed = "2026-07-13T00:00:00+00:00"
        self._write_liability_export("loan-content", balance="100", observed_at=observed)
        result = self._ingest_liability(observed)
        with Session(self.engine) as session:
            liability = session.get(Liability, "loan-content")
            assert liability is not None
            liability.balance = "999999"
            liability.currency = "EUR"
            liability.source_refs = ["forged:source"]
            session.add(liability)
            session.commit()

        report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertIn(
            "materialized_record_content_mismatch",
            {item.code for item in report.findings},
        )
        self.assertNotIn(result.batch_id, report.verified_batch_ids)
        with self.assertRaisesRegex(StateCoreStoreError, "recovery"):
            self._ingest_liability(observed)

        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered.after.ok, recovered.after)
        with Session(self.engine) as session:
            liability = session.get(Liability, "loan-content")
        assert liability is not None
        self.assertEqual(str(liability.balance), "100")
        self.assertEqual(liability.currency, "USD")
        self.assertNotEqual(liability.source_refs, ["forged:source"])

    def test_same_identity_position_content_drift_requires_recovery(self) -> None:
        result = self.ingest()
        with Session(self.engine) as session:
            position = session.exec(
                select(Position).where(Position.snapshot_id == result.snapshot_id)
            ).one()
            original_quantity = str(position.quantity)
            original_market_value = str(position.market_value)
            original_valued_at_utc = position.valued_at_utc
            position.quantity = "999"
            position.market_value = "999999"
            position.valued_at_utc = "1999-01-01T00:00:00+00:00"
            session.add(position)
            session.commit()

        report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertIn(
            "materialized_record_content_mismatch",
            {item.code for item in report.findings},
        )
        self.assertNotIn(result.batch_id, report.verified_batch_ids)
        with self.assertRaisesRegex(StateCoreStoreError, "recovery"):
            self.ingest()

        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered.after.ok, recovered.after)
        with Session(self.engine) as session:
            position = session.exec(
                select(Position).where(Position.snapshot_id == result.snapshot_id)
            ).one()
        self.assertEqual(str(position.quantity), original_quantity)
        self.assertEqual(str(position.market_value), original_market_value)
        self.assertEqual(position.valued_at_utc, original_valued_at_utc)


    def test_receipt_only_recovery_without_any_head_stays_fail_closed(self) -> None:
        observed = "2026-07-14T00:00:00+00:00"
        self._write_liability_export("loan-orphan", balance="999", observed_at=observed)
        with (
            patch(
                "finharness.personal_finance.materialize_import_batch",
                side_effect=StateCoreStoreError("crash before database commit"),
            ),
            self.assertRaises(StateCoreStoreError),
        ):
            self._ingest_liability(observed)

        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertFalse(recovered.after.ok)
        self.assertIn(
            "import_domain_head_missing",
            {item.code for item in recovered.after.findings},
        )
        with Session(self.engine) as session:
            self.assertEqual(list(session.exec(select(ImportDomainHead)).all()), [])
            self.assertEqual(list(session.exec(select(Liability)).all()), [])
            self.assertEqual(len(list(session.exec(select(ImportBatch)).all())), 1)

    def test_historical_replay_does_not_rewrite_shared_identity_registry(self) -> None:
        first = self.ingest()
        first_native_id = "Assets:Cash"
        with Session(self.engine) as session:
            first_identity = session.exec(
                select(AccountIdentity).where(
                    AccountIdentity.source_native_id == first_native_id
                )
            ).one()
            first_identity_id = first_identity.canonical_account_id

        fieldnames = [
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
        ]
        with self.source.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(
                {
                    "account_id": "Assets:Broker",
                    "account_name": "Broker",
                    "account_kind": "broker",
                    "venue": "manual",
                    "symbol": "USD",
                    "quantity": "200",
                    "market_value": "200",
                    "cost_basis": "",
                    "currency": "USD",
                    "as_of_utc": "2026-07-14T00:00:00+00:00",
                }
            )
        second = self.ingest()
        with Session(self.engine) as session:
            historical_identity = session.get(AccountIdentity, first_identity_id)
            assert historical_identity is not None
            historical_identity.source_refs = ["forged:historical-registry"]
            session.add(historical_identity)
            for position in session.exec(
                select(Position).where(Position.snapshot_id == first.snapshot_id)
            ).all():
                session.delete(position)
            snapshot = session.get(Snapshot, first.snapshot_id)
            assert snapshot is not None
            session.delete(snapshot)
            session.commit()

        before = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        first_codes = {
            item.code for item in before.findings if item.batch_id == first.batch_id
        }
        self.assertIn("materialized_record_missing", first_codes)
        self.assertNotIn("materialized_record_content_mismatch", first_codes)

        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered.after.ok, recovered.after)
        with Session(self.engine) as session:
            historical_identity = session.get(AccountIdentity, first_identity_id)
            head = session.exec(
                select(ImportDomainHead).where(ImportDomainHead.domain == "position")
            ).one()
        assert historical_identity is not None
        self.assertEqual(
            historical_identity.source_refs,
            ["forged:historical-registry"],
        )
        self.assertEqual(head.batch_id, second.batch_id)

    def test_current_shared_identity_content_drift_requires_recovery(self) -> None:
        result = self.ingest()
        with Session(self.engine) as session:
            identity = session.exec(select(AccountIdentity)).one()
            original_refs = list(identity.source_refs)
            identity.source_refs = ["forged:current-registry"]
            session.add(identity)
            session.commit()

        report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertIn(
            "materialized_record_content_mismatch",
            {item.code for item in report.findings},
        )
        self.assertNotIn(result.batch_id, report.verified_batch_ids)

        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered.after.ok, recovered.after)
        with Session(self.engine) as session:
            identity = session.exec(select(AccountIdentity)).one()
        self.assertEqual(identity.source_refs, original_refs)


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
