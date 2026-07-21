"""Adversarial contracts for current authority, replay isolation, and provenance."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import delete
from sqlmodel import Session, SQLModel, select

from finharness.artifact_store import LocalArtifactStore
from finharness.capital_import_recovery import (
    CapitalImportRecoveryError,
    audit_capital_imports,
    batch_is_verified,
    recover_capital_imports,
)
from finharness.personal_finance import ingest_personal_finance_export
from finharness.statecore.import_models import ImportDomainHead
from finharness.statecore.models import (
    InstrumentIdentity,
    Liability,
    Position,
    ReceiptManifest,
)
from finharness.statecore.snapshot_ingest import ingest_broker_read_receipt
from finharness.statecore.store import init_state_core, migrate_state_core

OBSERVED_A = "2026-07-13T00:00:00+00:00"
OBSERVED_B = "2026-07-14T00:00:00+00:00"


class CapitalImportTruthBoundaryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts"
        self.store = LocalArtifactStore(self.receipt_root / "artifact-store")
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)

    def _write_liability(self, path: Path, liability_id: str, balance: str, observed: str) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "record_type",
                    "liability_id",
                    "name",
                    "liability_type",
                    "balance",
                    "currency",
                    "as_of_utc",
                    "observed_at_utc",
                ],
            )
            writer.writeheader()
            writer.writerow(
                {
                    "record_type": "liability",
                    "liability_id": liability_id,
                    "name": liability_id,
                    "liability_type": "loan",
                    "balance": balance,
                    "currency": "USD",
                    "as_of_utc": observed,
                    "observed_at_utc": observed,
                }
            )

    def _ingest_liability(self, path: Path, observed: str):
        return ingest_personal_finance_export(
            path,
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["liability"],
            observed_at_utc=observed,
        )

    def test_invalid_head_manifest_never_authorizes_projection_or_rewrites_head(self) -> None:
        source = self.root / "liabilities.csv"
        self._write_liability(source, "loan-a", "100", OBSERVED_A)
        first = self._ingest_liability(source, OBSERVED_A)
        self._write_liability(source, "loan-b", "200", OBSERVED_B)
        second = self._ingest_liability(source, OBSERVED_B)

        with Session(self.engine) as session:
            first_manifest = session.exec(
                select(ReceiptManifest).where(ReceiptManifest.batch_id == first.batch_id)
            ).one()
            head = session.exec(
                select(ImportDomainHead).where(ImportDomainHead.domain == "liability")
            ).one()
            self.assertEqual(head.batch_id, second.batch_id)
            head.manifest_id = first_manifest.manifest_id
            session.add(head)
            liability = session.get(Liability, "loan-b")
            assert liability is not None
            session.delete(liability)
            session.commit()
            corrupted_manifest_id = head.manifest_id

        recovered = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertFalse(recovered.after.ok)
        self.assertIn(
            "import_domain_head_invalid",
            {finding.code for finding in recovered.after.findings},
        )
        with Session(self.engine) as session:
            head = session.exec(
                select(ImportDomainHead).where(ImportDomainHead.domain == "liability")
            ).one()
            self.assertEqual(head.manifest_id, corrupted_manifest_id)
            self.assertIsNone(session.get(Liability, "loan-b"))

    def test_replay_never_writes_the_user_source_path(self) -> None:
        source = self.root / "liabilities.csv"
        self._write_liability(source, "loan-a", "100", OBSERVED_A)
        self._ingest_liability(source, OBSERVED_A)
        current_bytes = b"current-user-owned-bytes\n"
        source.write_bytes(current_bytes)
        with Session(self.engine) as session:
            liability = session.get(Liability, "loan-a")
            assert liability is not None
            session.delete(liability)
            session.commit()

        from finharness import capital_import_recovery as recovery_module

        original_write = recovery_module.atomic_write_bytes

        def reject_user_source_write(path: Path, content: bytes) -> None:
            if path.resolve() == source.resolve():
                raise OSError("recovery attempted to write the user source")
            original_write(path, content)

        with patch(
            "finharness.capital_import_recovery.atomic_write_bytes",
            side_effect=reject_user_source_write,
        ):
            recovered = recover_capital_imports(
                engine=self.engine,
                receipt_root=self.receipt_root,
                artifact_store=self.store,
            )
        self.assertTrue(recovered.after.ok, recovered.after)
        self.assertEqual(source.read_bytes(), current_bytes)
        with Session(self.engine) as session:
            self.assertIsNotNone(session.get(Liability, "loan-a"))

    def test_source_integrity_failure_aborts_recovery_and_emits_no_success_receipt(self) -> None:
        source = self.root / "liabilities.csv"
        self._write_liability(source, "loan-a", "100", OBSERVED_A)
        self._ingest_liability(source, OBSERVED_A)
        with Session(self.engine) as session:
            liability = session.get(Liability, "loan-a")
            assert liability is not None
            session.delete(liability)
            session.commit()

        from finharness import capital_import_recovery as recovery_module

        failure = recovery_module.ReplaySourceIntegrityError(
            "critical source integrity failure",
            affected_paths=(str(source),),
        )
        with (
            patch("finharness.capital_import_recovery._replay_receipt", side_effect=failure),
            self.assertRaisesRegex(CapitalImportRecoveryError, "critical source integrity"),
        ):
            recover_capital_imports(
                engine=self.engine,
                receipt_root=self.receipt_root,
                artifact_store=self.store,
            )
        recovery_dir = self.receipt_root / "recovery"
        self.assertFalse(recovery_dir.exists() and any(recovery_dir.iterdir()))

    def _write_position_csv(self, path: Path) -> None:
        fieldnames = [
            "record_type", "account_id", "account_name", "account_kind", "venue",
            "symbol", "instrument_type", "instrument_venue", "quantity", "market_value",
            "cost_basis", "currency", "as_of_utc", "unit_price", "valuation_currency",
            "price_currency", "valued_at_utc", "price_source_ref", "effective_at_utc",
            "observed_at_utc",
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(
                {
                    "record_type": "position",
                    "account_id": "acct-personal",
                    "account_name": "Personal",
                    "account_kind": "broker",
                    "venue": "manual",
                    "symbol": "SPY",
                    "instrument_type": "equity",
                    "instrument_venue": "ARCX",
                    "quantity": "2",
                    "market_value": "100",
                    "cost_basis": "90",
                    "currency": "USD",
                    "as_of_utc": OBSERVED_A,
                    "unit_price": "50",
                    "valuation_currency": "USD",
                    "price_currency": "USD",
                    "valued_at_utc": OBSERVED_A,
                    "price_source_ref": "fixture:personal",
                    "effective_at_utc": OBSERVED_A,
                    "observed_at_utc": OBSERVED_A,
                }
            )

    def _write_broker_json(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "receipt_id": "receipt_broker_spy",
                    "kind": "broker_read",
                    "created_at_utc": OBSERVED_B,
                    "effective_at_utc": OBSERVED_B,
                    "observed_at_utc": OBSERVED_B,
                    "valued_at_utc": OBSERVED_B,
                    "broker": "manual",
                    "environment": "paper",
                    "account": {"id": "acct-broker", "status": "ACTIVE"},
                    "positions": [
                        {
                            "symbol": "SPY",
                            "qty": "3",
                            "market_value": "150",
                            "unit_price": "50",
                            "currency": "USD",
                            "asset_class": "equity",
                            "exchange": "ARCX",
                            "price_source_ref": "fixture:broker",
                        }
                    ],
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    def test_two_current_sources_can_share_one_canonical_instrument(self) -> None:
        personal = self.root / "personal.csv"
        broker = self.root / "broker.json"
        self._write_position_csv(personal)
        self._write_broker_json(broker)
        personal_result = ingest_personal_finance_export(
            personal,
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
            coverage_mode="full",
            covered_domains=["position"],
        )
        broker_result = ingest_broker_read_receipt(
            broker,
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )

        report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(report.ok, report)
        self.assertTrue(
            batch_is_verified(
                personal_result.batch_id,
                engine=self.engine,
                receipt_root=self.receipt_root,
                artifact_store=self.store,
            )
        )
        self.assertTrue(
            batch_is_verified(
                broker_result.batch_id,
                engine=self.engine,
                receipt_root=self.receipt_root,
                artifact_store=self.store,
            )
        )
        with Session(self.engine) as session:
            instruments = list(session.exec(select(InstrumentIdentity)).all())
            self.assertEqual(len(instruments), 1)
            claims = session.execute(
                select(SQLModel.metadata.tables["instrument_identity_source_claims"])
            ).all()
            self.assertEqual(len(claims), 2)

    def test_v16_migration_never_uses_inverse_clock_to_choose_current(self) -> None:
        source = self.root / "liabilities.csv"
        self._write_liability(source, "loan-a", "100", OBSERVED_A)
        first = self._ingest_liability(source, OBSERVED_A)
        self._write_liability(source, "loan-b", "200", OBSERVED_B)
        second = self._ingest_liability(source, OBSERVED_B)
        with Session(self.engine) as session:
            session.exec(delete(ImportDomainHead))
            first_manifest = session.exec(
                select(ReceiptManifest).where(ReceiptManifest.batch_id == first.batch_id)
            ).one()
            second_manifest = session.exec(
                select(ReceiptManifest).where(ReceiptManifest.batch_id == second.batch_id)
            ).one()
            first_manifest.materialized_at_utc = "2026-07-15T00:00:00+00:00"
            second_manifest.materialized_at_utc = "2026-07-12T00:00:00+00:00"
            session.add(first_manifest)
            session.add(second_manifest)
            session.commit()
        with self.engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA user_version = 15")

        migrate_state_core(self.engine)

        with Session(self.engine) as session:
            self.assertEqual(list(session.exec(select(ImportDomainHead)).all()), [])
        report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertFalse(report.ok)
        self.assertIn(
            "import_domain_head_missing",
            {finding.code for finding in report.findings},
        )

    def test_same_basename_source_path_drift_changes_content_commitment(self) -> None:
        trusted = self.root / "trusted" / "receipt_portfolio.json"
        trusted.parent.mkdir()
        self._write_broker_json(trusted)
        result = ingest_broker_read_receipt(
            trusted,
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        forged = self.root / "forged" / "receipt_portfolio.json"
        with Session(self.engine) as session:
            position = session.exec(
                select(Position).where(Position.snapshot_id == result.snapshot_id)
            ).one()
            position.source_refs = [
                str(forged.resolve()) if ref == str(trusted.resolve()) else ref
                for ref in position.source_refs
            ]
            session.add(position)
            session.commit()

        report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertIn(
            "materialized_record_content_mismatch",
            {finding.code for finding in report.findings},
        )


if __name__ == "__main__":
    unittest.main()
