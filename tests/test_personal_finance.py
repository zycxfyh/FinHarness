from __future__ import annotations

import csv
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from finharness.personal_finance import (
    PersonalFinanceExportError,
    ingest_personal_finance_export,
)
from finharness.statecore.models import (
    Account,
    CashflowEvent,
    DocumentRef,
    FinancialGoal,
    InsurancePolicy,
    Liability,
    Position,
    ReceiptIndex,
    Snapshot,
    TaxEvent,
)
from finharness.statecore.store import init_state_core, read_all


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
            "quantity",
            "market_value",
            "cost_basis",
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
                    "quantity": "1.5",
                    "market_value": "750.25",
                    "cost_basis": "700.00",
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
            {account.account_id for account in accounts},
            {"Assets:Brokerage", "Assets:Cash"},
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
