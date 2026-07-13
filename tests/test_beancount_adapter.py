from __future__ import annotations

import json
import os
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from finharness.beancount_adapter import (
    BeancountLedgerError,
    ingest_beancount_ledger,
)
from finharness.statecore.models import (
    Account,
    CashflowEvent,
    Liability,
    Position,
    ReceiptIndex,
    Snapshot,
)
from finharness.statecore.store import init_state_core, read_all

FIXTURE = Path(__file__).parent / "fixtures" / "sample_ledger.beancount"


class BeancountAdapterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts" / "beancount"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def test_mirrors_holdings_and_liabilities_via_bean_query(self) -> None:
        result = ingest_beancount_ledger(
            FIXTURE,
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

        self.assertFalse(result.execution_allowed)
        self.assertEqual(result.account_count, 2)
        self.assertEqual(result.position_count, 2)
        self.assertEqual(result.liability_count, 1)

        accounts = read_all(Account, engine=self.engine)
        positions = read_all(Position, engine=self.engine)
        liabilities = read_all(Liability, engine=self.engine)
        snapshots = read_all(Snapshot, engine=self.engine)
        receipts = read_all(ReceiptIndex, engine=self.engine)

        self.assertEqual(
            {account.display_name for account in accounts},
            {"Assets:Brokerage", "Assets:Cash"},
        )
        by_symbol = {position.symbol: position for position in positions}
        self.assertEqual(set(by_symbol), {"SPY", "USD"})
        # 10 SPY priced at 600.00 USD on 2026-06-18.
        self.assertEqual(by_symbol["SPY"].market_value, 6000.0)
        self.assertEqual(by_symbol["SPY"].quantity, 10.0)

        self.assertEqual(len(liabilities), 1)
        self.assertEqual(liabilities[0].balance, Decimal("1200.00"))
        self.assertEqual(liabilities[0].currency, "USD")
        self.assertIsInstance(liabilities[0].balance, Decimal)

        self.assertEqual(snapshots[0].kind, "portfolio")
        self.assertEqual(receipts[0].kind, "beancount_ledger")
        receipt_payload = json.loads(
            (self.root / "receipts" / "beancount" / f"{result.receipt_id}.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertFalse(receipt_payload["execution_allowed"])
        self.assertEqual(receipt_payload["record_counts"]["position"], 2)

    def test_included_file_change_changes_content_hash(self) -> None:
        accounts = self.root / "accounts.beancount"
        main = self.root / "main.beancount"
        accounts.write_text(
            "2026-01-01 open Assets:Brokerage\n2026-01-01 open Assets:Cash USD\n",
            encoding="utf-8",
        )
        main.write_text(
            'include "accounts.beancount"\n\n'
            '2026-01-02 * "Buy"\n'
            "  Assets:Brokerage  10 SPY {500.00 USD}\n"
            "  Assets:Cash      -5000.00 USD\n\n"
            "2026-06-18 price SPY 600.00 USD\n",
            encoding="utf-8",
        )

        first = ingest_beancount_ledger(main, engine=self.engine, receipt_root=self.receipt_root)
        # Re-import unchanged: identical content -> identical snapshot id.
        again = ingest_beancount_ledger(main, engine=self.engine, receipt_root=self.receipt_root)
        self.assertEqual(first.snapshot_id, again.snapshot_id)

        # Change only the *included* file: the content hash must change.
        accounts.write_text(
            "2026-01-01 open Assets:Brokerage\n2026-01-01 open Assets:Cash USD\n; edited\n",
            encoding="utf-8",
        )
        changed = ingest_beancount_ledger(main, engine=self.engine, receipt_root=self.receipt_root)
        self.assertNotEqual(first.snapshot_id, changed.snapshot_id)
        self.assertNotEqual(first.receipt_id, changed.receipt_id)

    def test_main_file_change_changes_content_hash(self) -> None:
        ledger = self.root / "main-only.beancount"
        ledger.write_text(
            "2026-01-01 open Assets:Brokerage\n"
            "2026-01-01 open Assets:Cash USD\n"
            '2026-01-02 * "Buy"\n'
            "  Assets:Brokerage  10 SPY {500.00 USD}\n"
            "  Assets:Cash      -5000.00 USD\n"
            "2026-06-18 price SPY 600.00 USD\n",
            encoding="utf-8",
        )
        first = ingest_beancount_ledger(ledger, engine=self.engine, receipt_root=self.receipt_root)

        ledger.write_text(
            "2026-01-01 open Assets:Brokerage\n"
            "2026-01-01 open Assets:Cash USD\n"
            '2026-01-02 * "Buy"\n'
            "  Assets:Brokerage  10 SPY {500.00 USD}\n"
            "  Assets:Cash      -5000.00 USD\n"
            "2026-06-18 price SPY 610.00 USD\n",
            encoding="utf-8",
        )
        changed = ingest_beancount_ledger(
            ledger, engine=self.engine, receipt_root=self.receipt_root
        )

        self.assertNotEqual(first.snapshot_id, changed.snapshot_id)
        self.assertNotEqual(first.receipt_id, changed.receipt_id)

    def test_unpriced_holding_is_flagged_not_valued_as_money(self) -> None:
        ledger = self.root / "gold.beancount"
        ledger.write_text(
            'option "operating_currency" "USD"\n'
            "2026-01-01 open Assets:Brokerage\n"
            "2026-01-01 open Assets:Cash USD\n"
            "2026-01-01 open Equity:Opening\n"
            '2026-01-02 * "Buy"\n'
            "  Assets:Brokerage  10 SPY {500.00 USD}\n"
            "  Assets:Brokerage  5 GOLD {100.00 USD}\n"
            "  Assets:Cash      -5500.00 USD\n"
            "  Equity:Opening\n"
            "2026-06-18 price SPY 600.00 USD\n",
            encoding="utf-8",
        )

        result = ingest_beancount_ledger(
            ledger, engine=self.engine, receipt_root=self.receipt_root
        )

        positions = {p.symbol: p for p in read_all(Position, engine=self.engine)}
        # GOLD has no price: quantity kept, but no fake money value.
        self.assertEqual(positions["GOLD"].quantity, Decimal("5"))
        self.assertIsNone(positions["GOLD"].market_value)
        self.assertEqual(positions["GOLD"].valuation_status, "unpriced")
        # SPY is priced; USD cash is money: both keep real values.
        self.assertEqual(positions["SPY"].market_value, Decimal("6000.00"))
        snapshots = read_all(Snapshot, engine=self.engine)
        self.assertEqual(snapshots[0].payload["data_gaps_unpriced"], ["GOLD"])
        receipt = json.loads(
            (self.receipt_root / f"{result.receipt_id}.json").read_text(encoding="utf-8")
        )
        self.assertEqual(receipt["data_gaps_unpriced"], ["GOLD"])

    def test_relative_ledger_path_is_resolved(self) -> None:
        # The CLI passes a path relative to the working directory; beancount
        # reports absolute include paths, so resolution must not double the path.
        relative = Path(os.path.relpath(FIXTURE, Path.cwd()))
        self.assertFalse(relative.is_absolute())

        result = ingest_beancount_ledger(
            relative, engine=self.engine, receipt_root=self.receipt_root
        )

        self.assertEqual(result.position_count, 2)
        self.assertEqual(result.liability_count, 1)

    def test_recurring_cashflows_are_derived_and_replaced_on_reimport(self) -> None:
        ledger = self.root / "flows.beancount"
        lines = [
            'option "operating_currency" "USD"',
            "2025-01-01 open Assets:Cash USD",
            "2025-01-01 open Income:Salary USD",
            "2025-01-01 open Expenses:Rent USD",
        ]
        for month in range(1, 5):  # Jan..Apr; Apr (latest) is dropped as partial
            lines.append(f'2025-{month:02d}-25 * "Salary"')
            lines.append("  Assets:Cash    5000.00 USD")
            lines.append("  Income:Salary")
            lines.append(f'2025-{month:02d}-05 * "Rent"')
            lines.append("  Expenses:Rent  2000.00 USD")
            lines.append("  Assets:Cash")
        ledger.write_text("\n".join(lines) + "\n", encoding="utf-8")

        result = ingest_beancount_ledger(
            ledger, engine=self.engine, receipt_root=self.receipt_root
        )
        self.assertEqual(result.cashflow_count, 2)

        flows = {flow.category: flow for flow in read_all(CashflowEvent, engine=self.engine)}
        self.assertEqual(set(flows), {"income", "expense"})
        # Window = Jan..Mar (Apr dropped as partial): income +5000/mo, expenses -2000/mo.
        self.assertEqual(flows["income"].amount, Decimal("5000.00"))
        self.assertEqual(flows["expense"].amount, Decimal("-2000.00"))
        self.assertEqual(flows["income"].frequency, "monthly")
        self.assertIsInstance(flows["income"].amount, Decimal)

        # Re-import: source-scoped replace keeps exactly two (no duplicates).
        ingest_beancount_ledger(ledger, engine=self.engine, receipt_root=self.receipt_root)
        self.assertEqual(len(read_all(CashflowEvent, engine=self.engine)), 2)

    def test_missing_ledger_fails_closed(self) -> None:
        with self.assertRaises(BeancountLedgerError):
            ingest_beancount_ledger(
                self.root / "does-not-exist.beancount",
                engine=self.engine,
                receipt_root=self.receipt_root,
            )
        self.assertEqual(read_all(Position, engine=self.engine), [])
        self.assertEqual(read_all(ReceiptIndex, engine=self.engine), [])

    def test_loader_errors_deny_partial_import(self) -> None:
        invalid = self.root / "invalid.beancount"
        invalid.write_text(
            "2026-01-01 open Assets:Cash USD\n"
            '2026-01-02 * "Unbalanced"\n'
            "  Assets:Cash  10.00 USD\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(BeancountLedgerError, "partial import denied"):
            ingest_beancount_ledger(
                invalid, engine=self.engine, receipt_root=self.receipt_root
            )
        self.assertEqual(read_all(Snapshot, engine=self.engine), [])
        self.assertFalse(self.receipt_root.exists())


if __name__ == "__main__":
    unittest.main()
