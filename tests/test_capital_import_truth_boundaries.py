"""Adversarial contracts for current authority, replay isolation, and provenance."""

from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import inspect, text
from sqlmodel import Session, select

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
    IdentityAlias,
    InstrumentIdentity,
    InstrumentIdentitySourceClaim,
    Liability,
    Position,
    ReceiptManifest,
    Snapshot,
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

    def _downgrade_import_tables_to_v16(self) -> None:
        with self.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
            connection.commit()
            with connection.begin():
                connection.exec_driver_sql(
                    "DROP TABLE IF EXISTS instrument_identity_source_claims"
                )
                connection.exec_driver_sql(
                    "ALTER TABLE import_domain_heads "
                    "RENAME TO import_domain_heads_v17"
                )
                connection.exec_driver_sql(
                    "ALTER TABLE receipt_manifests "
                    "RENAME TO receipt_manifests_v17"
                )
                connection.exec_driver_sql(
                    "CREATE TABLE receipt_manifests ("
                    "schema_version VARCHAR NOT NULL, "
                    "as_of_utc VARCHAR NOT NULL, "
                    "authority_level VARCHAR NOT NULL, "
                    "manifest_id VARCHAR PRIMARY KEY, "
                    "batch_id VARCHAR NOT NULL, "
                    "receipt_id VARCHAR NOT NULL, "
                    "receipt_ref VARCHAR NOT NULL, "
                    "receipt_sha256 VARCHAR NOT NULL, "
                    "receipt_artifact_id VARCHAR NOT NULL, "
                    "source_artifact_id VARCHAR NOT NULL, "
                    "snapshot_id VARCHAR NOT NULL, "
                    "materialization_status VARCHAR NOT NULL, "
                    "record_counts JSON NOT NULL, "
                    "materialized_at_utc VARCHAR NOT NULL, "
                    "FOREIGN KEY(batch_id) REFERENCES import_batches(batch_id), "
                    "UNIQUE(batch_id), UNIQUE(receipt_id), "
                    "CHECK(materialization_status = 'materialized'))"
                )
                connection.exec_driver_sql(
                    "INSERT INTO receipt_manifests SELECT "
                    "schema_version, as_of_utc, authority_level, manifest_id, "
                    "batch_id, receipt_id, receipt_ref, receipt_sha256, "
                    "receipt_artifact_id, source_artifact_id, snapshot_id, "
                    "materialization_status, record_counts, materialized_at_utc "
                    "FROM receipt_manifests_v17"
                )
                connection.exec_driver_sql(
                    "CREATE TABLE import_domain_heads ("
                    "schema_version VARCHAR NOT NULL, "
                    "as_of_utc VARCHAR NOT NULL, "
                    "authority_level VARCHAR NOT NULL, "
                    "domain_head_id VARCHAR PRIMARY KEY, "
                    "source_kind VARCHAR NOT NULL, source_id VARCHAR NOT NULL, "
                    "domain VARCHAR NOT NULL, batch_id VARCHAR NOT NULL, "
                    "manifest_id VARCHAR NOT NULL, materialized_at_utc VARCHAR NOT NULL, "
                    "FOREIGN KEY(batch_id) REFERENCES import_batches(batch_id), "
                    "FOREIGN KEY(manifest_id) REFERENCES receipt_manifests(manifest_id), "
                    "UNIQUE(source_kind, source_id, domain))"
                )
                connection.exec_driver_sql(
                    "INSERT INTO import_domain_heads SELECT "
                    "schema_version, as_of_utc, authority_level, domain_head_id, "
                    "source_kind, source_id, domain, batch_id, manifest_id, "
                    "materialized_at_utc FROM import_domain_heads_v17"
                )
                connection.exec_driver_sql("DROP TABLE import_domain_heads_v17")
                connection.exec_driver_sql("DROP TABLE receipt_manifests_v17")
                connection.exec_driver_sql("PRAGMA user_version = 16")
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            connection.commit()

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
            corrupted_manifest_id = first_manifest.manifest_id
            domain_head_id = head.domain_head_id
        with self.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
            connection.commit()
            with connection.begin():
                connection.exec_driver_sql(
                    "UPDATE import_domain_heads SET manifest_id = ? "
                    "WHERE domain_head_id = ?",
                    (corrupted_manifest_id, domain_head_id),
                )
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            connection.commit()
        with Session(self.engine) as session:
            liability = session.get(Liability, "loan-b")
            assert liability is not None
            session.delete(liability)
            session.commit()

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

    def test_domain_head_revision_changes_only_on_current_transition(self) -> None:
        source = self.root / "liabilities.csv"
        self._write_liability(source, "loan-a", "100", OBSERVED_A)
        first = self._ingest_liability(source, OBSERVED_A)
        with Session(self.engine) as session:
            head = session.exec(
                select(ImportDomainHead).where(ImportDomainHead.domain == "liability")
            ).one()
            self.assertEqual(head.head_revision, 1)

        retried = self._ingest_liability(source, OBSERVED_A)
        self.assertEqual(retried.batch_id, first.batch_id)
        with Session(self.engine) as session:
            head = session.exec(
                select(ImportDomainHead).where(ImportDomainHead.domain == "liability")
            ).one()
            self.assertEqual(head.head_revision, 1)

        self._write_liability(source, "loan-b", "200", OBSERVED_B)
        second = self._ingest_liability(source, OBSERVED_B)
        with Session(self.engine) as session:
            head = session.exec(
                select(ImportDomainHead).where(ImportDomainHead.domain == "liability")
            ).one()
            self.assertEqual(head.batch_id, second.batch_id)
            self.assertEqual(head.head_revision, 2)
            liability = session.get(Liability, "loan-b")
            assert liability is not None
            session.delete(liability)
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
            self.assertEqual(head.batch_id, second.batch_id)
            self.assertEqual(head.head_revision, 2)

    def test_invalid_head_blocks_ordinary_idempotent_retry(self) -> None:
        source = self.root / "liabilities.csv"
        self._write_liability(source, "loan-a", "100", OBSERVED_A)
        result = self._ingest_liability(source, OBSERVED_A)
        with Session(self.engine) as session:
            head = session.exec(
                select(ImportDomainHead).where(ImportDomainHead.domain == "liability")
            ).one()
            head.materialized_at_utc = "1999-01-01T00:00:00+00:00"
            session.add(head)
            session.commit()

        with self.assertRaisesRegex(Exception, "recovery"):
            self._ingest_liability(source, OBSERVED_A)
        with Session(self.engine) as session:
            head = session.exec(
                select(ImportDomainHead).where(ImportDomainHead.domain == "liability")
            ).one()
        self.assertEqual(head.batch_id, result.batch_id)
        self.assertEqual(
            head.materialized_at_utc,
            "1999-01-01T00:00:00+00:00",
        )

    def test_stale_recovery_authority_is_revalidated_inside_transaction(self) -> None:
        source = self.root / "liabilities.csv"
        self._write_liability(source, "loan-a", "100", OBSERVED_A)
        first_bytes = source.read_bytes()
        first = self._ingest_liability(source, OBSERVED_A)
        self._write_liability(source, "loan-b", "200", OBSERVED_B)
        second = self._ingest_liability(source, OBSERVED_B)
        staged = self.root / "stale-replay.csv"
        staged.write_bytes(first_bytes)

        with self.assertRaisesRegex(Exception, "authority changed"):
            ingest_personal_finance_export(
                staged,
                engine=self.engine,
                receipt_root=self.receipt_root,
                artifact_store=self.store,
                snapshot_id=first.snapshot_id,
                coverage_mode="full",
                covered_domains=["liability"],
                observed_at_utc=OBSERVED_A,
                _recovery_replay=True,
                _recovery_projection_domains=["liability"],
                _recovery_source_ref=str(source),
            )
        with Session(self.engine) as session:
            head = session.exec(
                select(ImportDomainHead).where(ImportDomainHead.domain == "liability")
            ).one()
            liabilities = list(session.exec(select(Liability)).all())
        self.assertEqual(head.batch_id, second.batch_id)
        self.assertEqual([row.liability_id for row in liabilities], ["loan-b"])

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

    def _write_broker_json(
        self,
        path: Path,
        *,
        receipt_id: str = "receipt_broker_spy",
        account_id: str = "acct-broker",
        quantity: str = "3",
    ) -> None:
        path.write_text(
            json.dumps(
                {
                    "receipt_id": receipt_id,
                    "kind": "broker_read",
                    "created_at_utc": OBSERVED_B,
                    "effective_at_utc": OBSERVED_B,
                    "observed_at_utc": OBSERVED_B,
                    "valued_at_utc": OBSERVED_B,
                    "broker": "manual",
                    "environment": "paper",
                    "account": {"id": account_id, "status": "ACTIVE"},
                    "positions": [
                        {
                            "symbol": "SPY",
                            "qty": quantity,
                            "market_value": str(int(quantity) * 50),
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
            claims = list(
                session.exec(select(InstrumentIdentitySourceClaim)).all()
            )
            self.assertEqual(len(claims), 2)
            personal_claim = session.exec(
                select(InstrumentIdentitySourceClaim).where(
                    InstrumentIdentitySourceClaim.batch_id
                    == personal_result.batch_id
                )
            ).one()
            personal_claim.source_refs = ["forged:instrument-claim"]
            session.add(personal_claim)
            session.commit()

        drifted = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        personal_codes = {
            finding.code
            for finding in drifted.findings
            if finding.batch_id == personal_result.batch_id
        }
        broker_codes = {
            finding.code
            for finding in drifted.findings
            if finding.batch_id == broker_result.batch_id
        }
        self.assertIn("materialized_record_content_mismatch", personal_codes)
        self.assertNotIn("materialized_record_content_mismatch", broker_codes)

        claim_recovery = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(claim_recovery.after.ok, claim_recovery.after)
        for batch_id in (personal_result.batch_id, broker_result.batch_id):
            self.assertTrue(
                batch_is_verified(
                    batch_id,
                    engine=self.engine,
                    receipt_root=self.receipt_root,
                    artifact_store=self.store,
                )
            )

        with Session(self.engine) as session:
            personal_claim = session.exec(
                select(InstrumentIdentitySourceClaim).where(
                    InstrumentIdentitySourceClaim.batch_id
                    == personal_result.batch_id
                )
            ).one()
            self.assertNotEqual(
                personal_claim.source_refs,
                ["forged:instrument-claim"],
            )
            for position in session.exec(
                select(Position).where(
                    Position.snapshot_id == personal_result.snapshot_id
                )
            ).all():
                session.delete(position)
            personal_snapshot = session.get(Snapshot, personal_result.snapshot_id)
            assert personal_snapshot is not None
            session.delete(personal_snapshot)
            session.commit()

        recovered_personal = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered_personal.after.ok, recovered_personal.after)
        for batch_id in (personal_result.batch_id, broker_result.batch_id):
            self.assertTrue(
                batch_is_verified(
                    batch_id,
                    engine=self.engine,
                    receipt_root=self.receipt_root,
                    artifact_store=self.store,
                )
            )

        with Session(self.engine) as session:
            for position in session.exec(
                select(Position).where(
                    Position.snapshot_id == broker_result.snapshot_id
                )
            ).all():
                session.delete(position)
            broker_snapshot = session.get(Snapshot, broker_result.snapshot_id)
            assert broker_snapshot is not None
            session.delete(broker_snapshot)
            session.commit()

        recovered_broker = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovered_broker.after.ok, recovered_broker.after)
        for batch_id in (personal_result.batch_id, broker_result.batch_id):
            self.assertTrue(
                batch_is_verified(
                    batch_id,
                    engine=self.engine,
                    receipt_root=self.receipt_root,
                    artifact_store=self.store,
                )
            )
        with Session(self.engine) as session:
            self.assertEqual(len(list(session.exec(select(InstrumentIdentity)).all())), 1)
            self.assertEqual(
                len(list(session.exec(select(InstrumentIdentitySourceClaim)).all())),
                2,
            )

    def test_v15_upgrade_runs_legacy_v16_then_exact_v17(self) -> None:
        source = self.root / "liabilities.csv"
        self._write_liability(source, "loan-a", "100", OBSERVED_A)
        result = self._ingest_liability(source, OBSERVED_A)
        self._downgrade_import_tables_to_v16()
        with self.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
            connection.commit()
            with connection.begin():
                connection.exec_driver_sql("DROP TABLE import_domain_heads")
                connection.exec_driver_sql("PRAGMA user_version = 15")
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            connection.commit()

        migrate_state_core(self.engine)

        inspector = inspect(self.engine)
        self.assertIn(
            "head_revision",
            {
                column["name"]
                for column in inspector.get_columns("import_domain_heads")
            },
        )
        with Session(self.engine) as session:
            head = session.exec(select(ImportDomainHead)).one()
        self.assertEqual(head.batch_id, result.batch_id)
        self.assertEqual(head.head_revision, 1)

    def test_two_broker_sources_share_canonical_instrument_and_alias(self) -> None:
        source_a = self.root / "broker-a.json"
        source_b = self.root / "broker-b.json"
        self._write_broker_json(
            source_a,
            receipt_id="receipt_broker_a",
            account_id="acct-broker-a",
            quantity="2",
        )
        self._write_broker_json(
            source_b,
            receipt_id="receipt_broker_b",
            account_id="acct-broker-b",
            quantity="3",
        )
        first = ingest_broker_read_receipt(
            source_a,
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        second = ingest_broker_read_receipt(
            source_b,
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
        for batch_id in (first.batch_id, second.batch_id):
            self.assertTrue(
                batch_is_verified(
                    batch_id,
                    engine=self.engine,
                    receipt_root=self.receipt_root,
                    artifact_store=self.store,
                )
            )
        with Session(self.engine) as session:
            self.assertEqual(
                len(list(session.exec(select(InstrumentIdentity)).all())),
                1,
            )
            self.assertEqual(
                len(list(session.exec(select(InstrumentIdentitySourceClaim)).all())),
                2,
            )
            instrument_aliases = [
                alias
                for alias in session.exec(select(IdentityAlias)).all()
                if alias.identity_kind == "instrument"
            ]
        self.assertEqual(len(instrument_aliases), 1)
        self.assertEqual(instrument_aliases[0].source_refs, [])

    def test_v17_migration_rebuilds_exact_head_contract(self) -> None:
        source = self.root / "liabilities.csv"
        self._write_liability(source, "loan-a", "100", OBSERVED_A)
        result = self._ingest_liability(source, OBSERVED_A)
        self._downgrade_import_tables_to_v16()

        migrate_state_core(self.engine)

        inspector = inspect(self.engine)
        head_columns = {
            column["name"]
            for column in inspector.get_columns("import_domain_heads")
        }
        manifest_constraints = {
            tuple(item["column_names"])
            for item in inspector.get_unique_constraints("receipt_manifests")
        }
        head_foreign_keys = {
            (
                tuple(item.get("constrained_columns") or ()),
                tuple(item.get("referred_columns") or ()),
            )
            for item in inspector.get_foreign_keys("import_domain_heads")
        }
        claim_foreign_keys = {
            (
                tuple(item.get("constrained_columns") or ()),
                tuple(item.get("referred_columns") or ()),
            )
            for item in inspector.get_foreign_keys(
                "instrument_identity_source_claims"
            )
        }
        self.assertIn("head_revision", head_columns)
        self.assertIn(("manifest_id", "batch_id"), manifest_constraints)
        exact_binding = (
            ("manifest_id", "batch_id"),
            ("manifest_id", "batch_id"),
        )
        self.assertIn(exact_binding, head_foreign_keys)
        self.assertIn(exact_binding, claim_foreign_keys)
        self.assertIn(
            "instrument_identity_source_claims",
            set(inspector.get_table_names()),
        )
        with Session(self.engine) as session:
            head = session.exec(select(ImportDomainHead)).one()
        self.assertEqual(head.batch_id, result.batch_id)
        self.assertEqual(head.head_revision, 1)
        with self.engine.connect() as connection:
            self.assertEqual(
                int(connection.execute(text("PRAGMA user_version")).scalar_one()),
                17,
            )

    def test_v17_migration_rejects_mismatched_head_atomically(self) -> None:
        source = self.root / "liabilities.csv"
        self._write_liability(source, "loan-a", "100", OBSERVED_A)
        first = self._ingest_liability(source, OBSERVED_A)
        self._write_liability(source, "loan-b", "200", OBSERVED_B)
        self._ingest_liability(source, OBSERVED_B)
        self._downgrade_import_tables_to_v16()
        with self.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
            connection.commit()
            with connection.begin():
                first_manifest_id = connection.execute(
                    text(
                        "SELECT manifest_id FROM receipt_manifests "
                        "WHERE batch_id = :batch_id"
                    ),
                    {"batch_id": first.batch_id},
                ).scalar_one()
                connection.execute(
                    text(
                        "UPDATE import_domain_heads "
                        "SET manifest_id = :manifest_id"
                    ),
                    {"manifest_id": first_manifest_id},
                )
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            connection.commit()

        with self.assertRaisesRegex(Exception, "migration"):
            migrate_state_core(self.engine)

        inspector = inspect(self.engine)
        self.assertNotIn(
            "head_revision",
            {
                column["name"]
                for column in inspector.get_columns("import_domain_heads")
            },
        )
        with self.engine.connect() as connection:
            self.assertEqual(
                int(connection.execute(text("PRAGMA user_version")).scalar_one()),
                16,
            )

    def test_v16_migration_never_uses_inverse_clock_to_choose_current(self) -> None:
        source = self.root / "liabilities.csv"
        self._write_liability(source, "loan-a", "100", OBSERVED_A)
        first = self._ingest_liability(source, OBSERVED_A)
        self._write_liability(source, "loan-b", "200", OBSERVED_B)
        second = self._ingest_liability(source, OBSERVED_B)
        with Session(self.engine) as session:
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
        self._downgrade_import_tables_to_v16()
        with self.engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
            connection.commit()
            with connection.begin():
                connection.exec_driver_sql("DROP TABLE import_domain_heads")
                connection.exec_driver_sql("PRAGMA user_version = 15")
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            connection.commit()

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

    def test_v5_current_requires_v6_reimport_then_becomes_historical(self) -> None:
        source = self.root / "liabilities.csv"
        self._write_liability(source, "loan-a", "100", OBSERVED_A)
        with patch(
            "finharness.import_provenance.IMPORT_MANIFEST_SCHEMA_VERSION",
            "finharness.import_manifest.v5",
        ):
            legacy = self._ingest_liability(source, OBSERVED_A)

        legacy_report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertFalse(legacy_report.ok)
        self.assertIn(
            "legacy_import_manifest_reimport_required",
            {finding.code for finding in legacy_report.findings},
        )
        self.assertFalse(
            batch_is_verified(
                legacy.batch_id,
                engine=self.engine,
                receipt_root=self.receipt_root,
                artifact_store=self.store,
            )
        )

        current = self._ingest_liability(source, OBSERVED_A)
        self.assertNotEqual(current.batch_id, legacy.batch_id)
        current_report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        self.assertTrue(current_report.ok, current_report)
        self.assertIn(
            "legacy_import_manifest_reimport_required",
            {finding.code for finding in current_report.findings},
        )
        self.assertNotIn(legacy.batch_id, current_report.verified_batch_ids)
        self.assertIn(current.batch_id, current_report.verified_batch_ids)

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
