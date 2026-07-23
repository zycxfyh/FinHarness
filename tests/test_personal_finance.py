from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from finharness.artifact_store import LocalArtifactStore
from finharness.import_provenance import receipt_provenance
from finharness.personal_finance import (
    ImportDeletion,
    PersonalFinanceExportError,
    ingest_personal_finance_export,
)
from finharness.statecore.diff import diff_snapshots
from finharness.statecore.models import (
    Account,
    AccountIdentity,
    CashflowEvent,
    DocumentRef,
    FinancialGoal,
    ImportBatch,
    ImportTombstone,
    InsurancePolicy,
    Liability,
    Position,
    ReceiptIndex,
    ReceiptManifest,
    Snapshot,
    TaxEvent,
)
from finharness.statecore.store import (
    StateCoreStoreError,
    init_state_core,
    read_all,
    upsert_records,
)


class PersonalFinanceExportAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "state-core.sqlite"
        self.receipt_root = self.root / "receipts" / "personal-finance"
        self.engine = init_state_core(self.db_path)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def write_export(self, rows: list[dict[str, str]], *, columns: list[str] | None = None) -> Path:
        path = self.root / "beancount-export.csv"
        fieldnames = columns or [
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
        ]
        with path.open("w", encoding="utf-8", newline="") as target:
            writer = csv.DictWriter(target, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return path

    def test_ingests_mature_tool_export_into_state_core_with_receipt(self) -> None:
        export = self.write_export(
            [
                {
                    "account_id": "Assets:Brokerage",
                    "account_name": "Brokerage",
                    "account_kind": "broker",
                    "venue": "beancount",
                    "symbol": "SPY",
                    "instrument_type": "equity",
                    "instrument_venue": "ARCX",
                    "quantity": "1.5",
                    "market_value": "750.25",
                    "cost_basis": "700.00",
                    "currency": "USD",
                    "as_of_utc": "2026-06-19T00:00:00+00:00",
                },
                {
                    "account_id": "Assets:Cash",
                    "account_name": "Cash",
                    "account_kind": "cash",
                    "venue": "beancount",
                    "symbol": "CASH:USD",
                    "quantity": "1000",
                    "market_value": "1000",
                    "cost_basis": "",
                    "currency": "USD",
                    "as_of_utc": "2026-06-19T00:00:00+00:00",
                },
            ]
        )

        result = ingest_personal_finance_export(
            export,
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

        accounts = read_all(Account, engine=self.engine)
        positions = read_all(Position, engine=self.engine)
        liabilities = read_all(Liability, engine=self.engine)
        goals = read_all(FinancialGoal, engine=self.engine)
        cashflows = read_all(CashflowEvent, engine=self.engine)
        tax_events = read_all(TaxEvent, engine=self.engine)
        insurance = read_all(InsurancePolicy, engine=self.engine)
        documents = read_all(DocumentRef, engine=self.engine)
        snapshots = read_all(Snapshot, engine=self.engine)
        receipts = read_all(ReceiptIndex, engine=self.engine)

        self.assertFalse(result.execution_allowed)
        self.assertEqual(result.account_count, 2)
        self.assertEqual(result.position_count, 2)
        self.assertEqual(result.liability_count, 0)
        self.assertEqual(result.goal_count, 0)
        self.assertEqual(result.cashflow_count, 0)
        self.assertEqual(result.tax_event_count, 0)
        self.assertEqual(result.insurance_policy_count, 0)
        self.assertEqual(result.document_count, 0)
        self.assertEqual(
            {
                identity.source_native_id
                for identity in read_all(AccountIdentity, engine=self.engine)
            },
            {"Assets:Brokerage", "Assets:Cash"},
        )
        self.assertEqual(
            {account.account_id for account in accounts},
            {account.canonical_account_id for account in accounts},
        )
        self.assertEqual({position.symbol for position in positions}, {"SPY", "CASH:USD"})
        self.assertEqual(liabilities, [])
        self.assertEqual(goals, [])
        self.assertEqual(cashflows, [])
        self.assertEqual(tax_events, [])
        self.assertEqual(insurance, [])
        self.assertEqual(documents, [])
        self.assertEqual(snapshots[0].kind, "portfolio")
        self.assertEqual(snapshots[0].payload["source"], "personal_finance_export")
        self.assertEqual(snapshots[0].payload["record_counts"], {"position": 2})
        receipt_payload = json.loads(Path(result.receipt_ref).read_text(encoding="utf-8"))
        self.assertFalse(receipt_payload["execution_allowed"])
        self.assertEqual(receipt_payload["record_counts"], {"position": 2})
        self.assertEqual(receipts[0].kind, "personal_finance_export")
        self.assertEqual(receipts[0].path, result.receipt_ref)
        batches = read_all(ImportBatch, engine=self.engine)
        manifests = read_all(ReceiptManifest, engine=self.engine)
        self.assertEqual([batch.batch_id for batch in batches], [result.batch_id])
        self.assertEqual([manifest.manifest_id for manifest in manifests], [result.manifest_id])
        self.assertEqual(manifests[0].materialization_status, "materialized")
        self.assertEqual(
            manifests[0].receipt_sha256,
            hashlib.sha256(Path(result.receipt_ref).read_bytes()).hexdigest(),
        )

    def test_duplicate_content_is_one_batch_and_one_manifest(self) -> None:
        export = self.write_export(
            [
                {
                    "account_id": "Assets:Cash",
                    "account_name": "Cash",
                    "account_kind": "cash",
                    "venue": "manual",
                    "symbol": "USD",
                    "quantity": "10",
                    "market_value": "10",
                    "cost_basis": "",
                    "currency": "USD",
                    "as_of_utc": "2026-06-19T00:00:00+00:00",
                }
            ]
        )
        first = ingest_personal_finance_export(
            export, engine=self.engine, receipt_root=self.receipt_root
        )
        receipt_bytes = Path(first.receipt_ref).read_bytes()
        second = ingest_personal_finance_export(
            export, engine=self.engine, receipt_root=self.receipt_root
        )
        self.assertEqual(first.batch_id, second.batch_id)
        self.assertEqual(first.manifest_id, second.manifest_id)
        self.assertEqual(Path(second.receipt_ref).read_bytes(), receipt_bytes)
        self.assertEqual(len(read_all(ImportBatch, engine=self.engine)), 1)
        self.assertEqual(len(read_all(ReceiptManifest, engine=self.engine)), 1)

    def test_delta_preserves_omitted_positions_and_replays_deterministically(self) -> None:
        base = self.write_export(
            [
                {
                    "account_id": "Assets:Brokerage",
                    "account_name": "Brokerage",
                    "account_kind": "broker",
                    "venue": "manual",
                    "symbol": symbol,
                    "quantity": quantity,
                    "market_value": value,
                    "cost_basis": "",
                    "currency": "USD",
                    "as_of_utc": "2026-06-19T00:00:00+00:00",
                }
                for symbol, quantity, value in (("SPY", "1", "100"), ("QQQ", "2", "200"))
            ]
        )
        first = ingest_personal_finance_export(
            base, engine=self.engine, receipt_root=self.receipt_root
        )
        delta = self.write_export(
            [
                {
                    "account_id": "Assets:Brokerage",
                    "account_name": "Brokerage",
                    "account_kind": "broker",
                    "venue": "manual",
                    "symbol": "SPY",
                    "quantity": "1.5",
                    "market_value": "150",
                    "cost_basis": "",
                    "currency": "USD",
                    "as_of_utc": "2026-06-20T00:00:00+00:00",
                }
            ]
        )
        result = ingest_personal_finance_export(
            delta,
            engine=self.engine,
            receipt_root=self.receipt_root,
            coverage_mode="delta",
        )
        before_replay = sorted(
            (
                position.symbol,
                position.quantity,
                position.market_value,
                position.position_id,
            )
            for position in read_all(Position, engine=self.engine)
            if position.snapshot_id == result.snapshot_id
        )
        replay = ingest_personal_finance_export(
            delta,
            engine=self.engine,
            receipt_root=self.receipt_root,
            coverage_mode="delta",
        )
        after_replay = sorted(
            (
                position.symbol,
                position.quantity,
                position.market_value,
                position.position_id,
            )
            for position in read_all(Position, engine=self.engine)
            if position.snapshot_id == replay.snapshot_id
        )
        self.assertEqual(first.snapshot_id != result.snapshot_id, True)
        self.assertEqual({row[0] for row in before_replay}, {"SPY", "QQQ"})
        self.assertEqual(before_replay, after_replay)
        batch = next(
            batch
            for batch in read_all(ImportBatch, engine=self.engine)
            if batch.batch_id == result.batch_id
        )
        self.assertEqual(batch.coverage_mode, "delta")

    def test_full_import_records_disappeared_position_tombstone(self) -> None:
        base = self.write_export(
            [
                {
                    "account_id": "Assets:Brokerage",
                    "account_name": "Brokerage",
                    "account_kind": "broker",
                    "venue": "manual",
                    "symbol": symbol,
                    "quantity": "1",
                    "market_value": "100",
                    "cost_basis": "",
                    "currency": "USD",
                    "as_of_utc": "2026-06-19T00:00:00+00:00",
                }
                for symbol in ("SPY", "QQQ")
            ]
        )
        first = ingest_personal_finance_export(
            base, engine=self.engine, receipt_root=self.receipt_root
        )
        removed_position = next(
            position
            for position in read_all(Position, engine=self.engine)
            if position.snapshot_id == first.snapshot_id and position.symbol == "QQQ"
        )
        corrected = self.write_export(
            [
                {
                    "account_id": "Assets:Brokerage",
                    "account_name": "Brokerage",
                    "account_kind": "broker",
                    "venue": "manual",
                    "symbol": "SPY",
                    "quantity": "1",
                    "market_value": "110",
                    "cost_basis": "",
                    "currency": "USD",
                    "as_of_utc": "2026-06-20T00:00:00+00:00",
                }
            ]
        )
        second = ingest_personal_finance_export(
            corrected,
            engine=self.engine,
            receipt_root=self.receipt_root,
            supersedes_batch_id=first.batch_id,
            correction_reason="source export repaired a stale QQQ row",
        )
        latest_symbols = {
            position.symbol
            for position in read_all(Position, engine=self.engine)
            if position.snapshot_id == second.snapshot_id
        }
        self.assertEqual(latest_symbols, {"SPY"})
        tombstone = next(iter(read_all(ImportTombstone, engine=self.engine)))
        self.assertEqual(tombstone.record_id, removed_position.position_id)
        self.assertEqual(tombstone.reason, "absent_from_full_import")
        diff = diff_snapshots(first.snapshot_id, second.snapshot_id, engine=self.engine)
        self.assertEqual(diff.changed[0].change_reason, "correction")
        self.assertEqual(diff.removed[0].change_reason, "correction")
        self.assertEqual(
            diff.corporate_action_gaps,
            ("corporate_action_semantics_not_supported",),
        )
        receipt = json.loads(Path(second.receipt_ref).read_text(encoding="utf-8"))
        self.assertEqual(receipt["supersedes_batch_id"], first.batch_id)
        self.assertEqual(receipt["correction_reason"], "source export repaired a stale QQQ row")

    def test_delta_tombstone_deletes_source_owned_row(self) -> None:
        columns = [
            "record_type",
            "liability_id",
            "name",
            "liability_type",
            "balance",
            "currency",
            "as_of_utc",
        ]
        base = self.write_export(
            [
                {
                    "record_type": "liability",
                    "liability_id": liability_id,
                    "name": liability_id,
                    "liability_type": "loan",
                    "balance": balance,
                    "currency": "USD",
                    "as_of_utc": "2026-06-19T00:00:00+00:00",
                }
                for liability_id, balance in (("liab_a", "100"), ("liab_b", "200"))
            ],
            columns=columns,
        )
        ingest_personal_finance_export(base, engine=self.engine, receipt_root=self.receipt_root)
        delta = self.write_export(
            [
                {
                    "record_type": "liability",
                    "liability_id": "liab_a",
                    "name": "liab_a",
                    "liability_type": "loan",
                    "balance": "150",
                    "currency": "USD",
                    "as_of_utc": "2026-06-20T00:00:00+00:00",
                }
            ],
            columns=columns,
        )
        ingest_personal_finance_export(
            delta,
            engine=self.engine,
            receipt_root=self.receipt_root,
            coverage_mode="delta",
            tombstones=(ImportDeletion("Liability", "liab_b", "source row deleted"),),
        )
        self.assertEqual(
            {row.liability_id for row in read_all(Liability, engine=self.engine)},
            {"liab_a"},
        )
        tombstone = next(iter(read_all(ImportTombstone, engine=self.engine)))
        self.assertEqual(tombstone.reason, "source row deleted")

    def test_failed_materialization_leaves_replayable_evidence(self) -> None:
        export = self.write_export(
            [
                {
                    "account_id": "Assets:Cash",
                    "account_name": "Cash",
                    "account_kind": "cash",
                    "venue": "manual",
                    "symbol": "USD",
                    "quantity": "10",
                    "market_value": "10",
                    "cost_basis": "",
                    "currency": "USD",
                    "as_of_utc": "2026-06-19T00:00:00+00:00",
                }
            ]
        )
        with (
            patch(
                "finharness.personal_finance.materialize_import_batch",
                side_effect=StateCoreStoreError("simulated crash before commit"),
            ),
            self.assertRaises(StateCoreStoreError),
        ):
            ingest_personal_finance_export(
                export, engine=self.engine, receipt_root=self.receipt_root
            )
        artifact_store = LocalArtifactStore(self.receipt_root / "artifact-store")
        self.assertTrue(artifact_store.audit().ok)
        self.assertEqual(artifact_store.audit().descriptor_count, 3)
        self.assertEqual(read_all(ImportBatch, engine=self.engine), [])
        recovered = ingest_personal_finance_export(
            export, engine=self.engine, receipt_root=self.receipt_root
        )
        self.assertEqual(artifact_store.audit().descriptor_count, 3)
        self.assertEqual(
            receipt_provenance(recovered.receipt_id, engine=self.engine).status,
            "materialized",
        )

    def test_unmanifested_receipt_remains_explicitly_legacy(self) -> None:
        legacy = ReceiptIndex(
            receipt_id="legacy_receipt",
            kind="legacy_import",
            path="data/receipts/legacy.json",
        )
        upsert_records([legacy], engine=self.engine)
        status = receipt_provenance("legacy_receipt", engine=self.engine)
        self.assertEqual(status.status, "legacy_unmanifested")
        self.assertIsNone(status.batch_id)

    def test_direct_production_snapshot_cannot_bypass_manifest(self) -> None:
        direct = Snapshot(
            snapshot_id="direct_import",
            kind="portfolio",
            payload={"source": "personal_finance_export"},
        )
        with self.assertRaisesRegex(StateCoreStoreError, "materialize_import_batch"):
            upsert_records([direct], engine=self.engine)
        self.assertEqual(read_all(Snapshot, engine=self.engine), [])

    def test_ingests_typed_personal_finance_records_into_first_class_tables(self) -> None:
        columns = [
            "record_type",
            "account_id",
            "account_name",
            "account_kind",
            "venue",
            "symbol",
            "quantity",
            "market_value",
            "cost_basis",
            "as_of_utc",
            "liability_id",
            "name",
            "liability_type",
            "balance",
            "currency",
            "interest_rate",
            "due_date",
            "goal_id",
            "target_amount",
            "current_amount",
            "target_date",
            "status",
            "cashflow_id",
            "description",
            "amount",
            "event_date",
            "category",
            "frequency",
            "tax_event_id",
            "event_type",
            "jurisdiction",
            "estimated_amount",
            "policy_id",
            "policy_type",
            "provider",
            "coverage_amount",
            "premium_amount",
            "renewal_date",
            "document_id",
            "document_type",
            "title",
            "path",
            "related_object_id",
        ]
        as_of_utc = "2026-06-19T00:00:00+00:00"
        export = self.write_export(
            [
                {
                    "record_type": "position",
                    "account_id": "Assets:Brokerage",
                    "account_name": "Brokerage",
                    "account_kind": "broker",
                    "venue": "beancount",
                    "symbol": "SPY",
                    "quantity": "1.5",
                    "market_value": "750.25",
                    "currency": "USD",
                    "as_of_utc": as_of_utc,
                },
                {
                    "record_type": "liability",
                    "liability_id": "liab_mortgage",
                    "name": "Mortgage",
                    "liability_type": "mortgage",
                    "balance": "250000",
                    "currency": "USD",
                    "interest_rate": "0.035",
                    "due_date": "2046-01-01",
                    "as_of_utc": as_of_utc,
                },
                {
                    "record_type": "goal",
                    "goal_id": "goal_emergency",
                    "name": "Emergency Fund",
                    "target_amount": "30000",
                    "current_amount": "12000",
                    "currency": "USD",
                    "target_date": "2027-12-31",
                    "status": "active",
                    "as_of_utc": as_of_utc,
                },
                {
                    "record_type": "cashflow",
                    "cashflow_id": "cashflow_salary",
                    "description": "Salary",
                    "amount": "5000",
                    "currency": "USD",
                    "event_date": "2026-06-30",
                    "category": "income",
                    "frequency": "monthly",
                    "as_of_utc": as_of_utc,
                },
                {
                    "record_type": "tax_event",
                    "tax_event_id": "tax_2026_q2",
                    "event_type": "estimated_payment",
                    "jurisdiction": "US",
                    "due_date": "2026-06-15",
                    "estimated_amount": "1200",
                    "currency": "USD",
                    "status": "planned",
                    "as_of_utc": as_of_utc,
                },
                {
                    "record_type": "insurance",
                    "policy_id": "policy_home",
                    "policy_type": "home",
                    "provider": "Example Mutual",
                    "coverage_amount": "500000",
                    "premium_amount": "1250",
                    "currency": "USD",
                    "renewal_date": "2027-01-01",
                    "status": "active",
                    "as_of_utc": as_of_utc,
                },
                {
                    "record_type": "document",
                    "document_id": "doc_policy_home",
                    "document_type": "insurance_policy",
                    "title": "Home Policy Declaration",
                    "path": "documents/home-policy.pdf",
                    "related_object_id": "policy_home",
                    "as_of_utc": as_of_utc,
                },
            ],
            columns=columns,
        )

        result = ingest_personal_finance_export(
            export,
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

        self.assertEqual(result.account_count, 1)
        self.assertEqual(result.position_count, 1)
        self.assertEqual(result.liability_count, 1)
        self.assertEqual(result.goal_count, 1)
        self.assertEqual(result.cashflow_count, 1)
        self.assertEqual(result.tax_event_count, 1)
        self.assertEqual(result.insurance_policy_count, 1)
        self.assertEqual(result.document_count, 1)
        self.assertEqual(read_all(Liability, engine=self.engine)[0].balance, 250000)
        self.assertEqual(read_all(FinancialGoal, engine=self.engine)[0].current_amount, 12000)
        self.assertEqual(read_all(CashflowEvent, engine=self.engine)[0].frequency, "monthly")
        self.assertEqual(read_all(TaxEvent, engine=self.engine)[0].jurisdiction, "US")
        self.assertEqual(
            read_all(InsurancePolicy, engine=self.engine)[0].provider,
            "Example Mutual",
        )
        self.assertEqual(
            read_all(DocumentRef, engine=self.engine)[0].path,
            "documents/home-policy.pdf",
        )

        receipt_payload = json.loads(Path(result.receipt_ref).read_text(encoding="utf-8"))
        self.assertEqual(
            receipt_payload["record_counts"],
            {
                "position": 1,
                "liability": 1,
                "goal": 1,
                "cashflow": 1,
                "tax_event": 1,
                "insurance": 1,
                "document": 1,
            },
        )

    def test_invalid_export_fails_before_writing_state_or_receipt(self) -> None:
        export = self.write_export(
            [
                {
                    "account_id": "Assets:Brokerage",
                    "account_name": "Brokerage",
                    "symbol": "SPY",
                    "quantity": "1.5",
                    "market_value": "750.25",
                    "as_of_utc": "2026-06-19T00:00:00+00:00",
                }
            ],
            columns=[
                "account_id",
                "account_name",
                "symbol",
                "quantity",
                "market_value",
                "as_of_utc",
            ],
        )

        with self.assertRaises(PersonalFinanceExportError):
            ingest_personal_finance_export(
                export,
                engine=self.engine,
                receipt_root=self.receipt_root,
            )

        self.assertEqual(read_all(Account, engine=self.engine), [])
        self.assertEqual(read_all(Position, engine=self.engine), [])
        self.assertEqual(read_all(Snapshot, engine=self.engine), [])
        self.assertEqual(read_all(ReceiptIndex, engine=self.engine), [])
        self.assertFalse(self.receipt_root.exists())

    def test_explicit_clocks_and_currency_are_bound_to_manifest(self) -> None:
        columns = [
            "account_id",
            "account_name",
            "account_kind",
            "venue",
            "symbol",
            "instrument_type",
            "instrument_venue",
            "quantity",
            "market_value",
            "currency",
            "valuation_currency",
            "unit_price",
            "price_currency",
            "price_source_ref",
            "effective_at_utc",
            "observed_at_utc",
            "valued_at_utc",
            "as_of_utc",
        ]
        export = self.write_export(
            [
                {
                    "account_id": "Assets:Brokerage",
                    "account_name": "Brokerage",
                    "account_kind": "broker",
                    "venue": "manual",
                    "symbol": "SPY",
                    "instrument_type": "equity",
                    "instrument_venue": "ARCX",
                    "quantity": "0.10000000000000000001",
                    "market_value": "60.000000000000000006",
                    "currency": "USD",
                    "valuation_currency": "USD",
                    "unit_price": "600",
                    "price_currency": "USD",
                    "price_source_ref": "source:prices",
                    "effective_at_utc": "2026-07-13T06:00:00+00:00",
                    "observed_at_utc": "2026-07-13T07:00:00+00:00",
                    "valued_at_utc": "2026-07-13T06:30:00+00:00",
                    "as_of_utc": "2026-07-13T07:00:00+00:00",
                }
            ],
            columns=columns,
        )
        result = ingest_personal_finance_export(
            export, engine=self.engine, receipt_root=self.receipt_root
        )
        position = read_all(Position, engine=self.engine)[0]
        batch = read_all(ImportBatch, engine=self.engine)[0]
        self.assertEqual(position.quantity, Decimal("0.10000000000000000001"))
        self.assertEqual(position.market_value, Decimal("60.000000000000000006"))
        self.assertIsNotNone(position.instrument_id)
        self.assertEqual(position.valuation_status, "valued")
        self.assertEqual(result.completeness_status, "complete")
        self.assertEqual(batch.completeness_status, "complete")
        self.assertEqual(batch.time_semantics["valued_at_utc"], "2026-07-13T06:30:00+00:00")
        self.assertEqual(batch.findings, [])

    def test_missing_position_currency_fails_closed_with_structured_finding(self) -> None:
        export = self.write_export(
            [
                {
                    "account_id": "Assets:Brokerage",
                    "account_name": "Brokerage",
                    "account_kind": "broker",
                    "venue": "manual",
                    "symbol": "SPY",
                    "quantity": "1",
                    "market_value": "10",
                    "currency": "",
                    "as_of_utc": "2026-07-13T07:00:00+00:00",
                }
            ]
        )
        with self.assertRaises(PersonalFinanceExportError) as raised:
            ingest_personal_finance_export(
                export, engine=self.engine, receipt_root=self.receipt_root
            )
        self.assertEqual(raised.exception.findings[0].code, "invalid_or_missing_currency")
        self.assertEqual(read_all(Snapshot, engine=self.engine), [])

    def test_reimport_replaces_source_rows_instead_of_accumulating(self) -> None:
        columns = [
            "record_type",
            "account_id",
            "account_name",
            "account_kind",
            "venue",
            "symbol",
            "quantity",
            "market_value",
            "as_of_utc",
            "liability_id",
            "name",
            "liability_type",
            "balance",
            "currency",
        ]

        def position_row(as_of: str) -> dict[str, str]:
            return {
                "record_type": "position",
                "account_id": "Assets:Brokerage",
                "account_name": "Brokerage",
                "account_kind": "broker",
                "venue": "beancount",
                "symbol": "SPY",
                "quantity": "1",
                "market_value": "600",
                "currency": "USD",
                "as_of_utc": as_of,
            }

        def liability_row(liability_id: str, balance: str, as_of: str) -> dict[str, str]:
            return {
                "record_type": "liability",
                "liability_id": liability_id,
                "name": liability_id,
                "liability_type": "loan",
                "balance": balance,
                "currency": "USD",
                "as_of_utc": as_of,
            }

        first = self.write_export(
            [
                position_row("2026-06-19T00:00:00+00:00"),
                liability_row("liab_a", "100", "2026-06-19T00:00:00+00:00"),
                liability_row("liab_b", "200", "2026-06-19T00:00:00+00:00"),
            ],
            columns=columns,
        )
        ingest_personal_finance_export(first, engine=self.engine, receipt_root=self.receipt_root)
        self.assertEqual(
            {row.liability_id for row in read_all(Liability, engine=self.engine)},
            {"liab_a", "liab_b"},
        )

        # Re-import: liab_b no longer exists upstream; it must not linger.
        second = self.write_export(
            [
                position_row("2026-06-20T00:00:00+00:00"),
                liability_row("liab_a", "150", "2026-06-20T00:00:00+00:00"),
            ],
            columns=columns,
        )
        ingest_personal_finance_export(second, engine=self.engine, receipt_root=self.receipt_root)

        liabilities = read_all(Liability, engine=self.engine)
        self.assertEqual({row.liability_id for row in liabilities}, {"liab_a"})
        self.assertEqual(liabilities[0].balance, Decimal("150"))
        self.assertEqual(liabilities[0].source, "personal_finance_export")
        # Positions/snapshots accumulate as history: two imports -> two snapshots.
        self.assertEqual(len(read_all(Snapshot, engine=self.engine)), 2)


if __name__ == "__main__":
    unittest.main()
