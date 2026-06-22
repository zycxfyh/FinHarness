from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finharness.statecore.models import Position, ReceiptIndex, Snapshot
from finharness.statecore.receipt_index import index_receipts, receipt_index_record_from_path
from finharness.statecore.snapshot_ingest import (
    ingest_portfolio_snapshot_from_payload,
    ingest_portfolio_snapshot_from_receipt,
)
from finharness.statecore.store import StateCoreStoreError, init_state_core, read_all


class StateCoreSnapshotIngestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "state-core.sqlite"
        self.receipt_root = self.root / "receipts"
        self.receipt_root.mkdir()
        self.engine = init_state_core(self.db_path)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _write_receipt(self, relative_path: str, payload: dict[str, object]) -> Path:
        path = self.receipt_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_index_receipts_records_paths_and_receipt_refs(self) -> None:
        receipt = self._write_receipt(
            "broker/portfolio.json",
            {
                "receipt_id": "receipt_portfolio_1",
                "kind": "broker_read",
                "created_at_utc": "2026-06-17T01:02:03+00:00",
                "receipt_refs": ["receipt_market_1"],
                "snapshot": {
                    "receipt_ref": "data/receipts/market-data/receipt_mds_1.json"
                },
            },
        )
        self._write_receipt(
            "daily/no-id.json",
            {
                "workflow": "daily_evidence",
                "generated_at": "2026-06-17T02:00:00+00:00",
            },
        )
        raw_report = self.receipt_root / "hardening" / "latest-gitleaks-redacted.json"
        raw_report.parent.mkdir(parents=True, exist_ok=True)
        raw_report.write_text("[]", encoding="utf-8")
        bad_report = self.receipt_root / "broken" / "truncated.json"
        bad_report.parent.mkdir(parents=True, exist_ok=True)
        bad_report.write_text('{"not": "closed"', encoding="utf-8")

        indexed = index_receipts(receipt_root=self.receipt_root, engine=self.engine)

        rows = sorted(read_all(ReceiptIndex, engine=self.engine), key=lambda row: row.receipt_id)
        self.assertEqual(len(indexed), 4)
        self.assertEqual(len(rows), 4)
        portfolio = next(row for row in rows if row.receipt_id == "receipt_portfolio_1")
        self.assertEqual(portfolio.kind, "broker_read")
        self.assertEqual(portfolio.path, str(receipt.resolve()))
        self.assertEqual(portfolio.source_refs, [str(receipt.resolve())])
        self.assertIn("receipt_market_1", portfolio.refs)
        self.assertIn("data/receipts/market-data/receipt_mds_1.json", portfolio.refs)

        fallback = next(row for row in rows if row.receipt_id == "daily__no-id")
        self.assertEqual(fallback.receipt_id, "daily__no-id")
        self.assertEqual(fallback.kind, "daily_evidence")
        raw = next(row for row in rows if row.receipt_id == "hardening__latest-gitleaks-redacted")
        self.assertEqual(raw.kind, "raw_json_list")
        self.assertEqual(raw.refs, [])
        unreadable = next(row for row in rows if row.receipt_id == "broken__truncated")
        self.assertEqual(unreadable.kind, "unreadable_json")
        self.assertEqual(unreadable.path, str(bad_report.resolve()))

        with self.assertRaises(StateCoreStoreError):
            receipt_index_record_from_path(bad_report, receipt_root=self.receipt_root)

    def test_ingest_broker_read_receipt_creates_portfolio_snapshot_and_index(self) -> None:
        receipt = self._write_receipt(
            "broker/portfolio.json",
            {
                "receipt_id": "receipt_portfolio_1",
                "kind": "broker_read",
                "created_at_utc": "2026-06-17T01:02:03+00:00",
                "broker": "alpaca",
                "environment": "paper",
                "account": {
                    "id": "acct-1",
                    "status": "ACTIVE",
                    "portfolio_value": "150.25",
                },
                "positions": [
                    {
                        "symbol": "SPY",
                        "qty": "2",
                        "market_value": "100.5",
                    },
                    {
                        "symbol": "QQQ",
                        "quantity": "1",
                        "current_price": "49.75",
                        "cost_basis": "45.00",
                    },
                ],
            },
        )

        snapshot = ingest_portfolio_snapshot_from_receipt(receipt, engine=self.engine)

        snapshots = read_all(Snapshot, engine=self.engine)
        positions = sorted(read_all(Position, engine=self.engine), key=lambda row: row.symbol)
        receipts = read_all(ReceiptIndex, engine=self.engine)

        self.assertEqual(snapshot.snapshot_id, "snap_portfolio_receipt_portfolio_1")
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].kind, "portfolio")
        self.assertEqual(snapshots[0].source_refs, [str(receipt.resolve())])
        self.assertFalse(snapshots[0].payload["execution_allowed"])
        self.assertIn("Not execution authorization.", snapshots[0].payload["not_claimed"])
        self.assertEqual(snapshots[0].payload["position_count"], 2)

        self.assertEqual([row.symbol for row in positions], ["QQQ", "SPY"])
        self.assertEqual(positions[0].market_value, 49.75)
        self.assertEqual(positions[0].cost_basis, 45.0)
        self.assertEqual(positions[1].market_value, 100.5)
        self.assertIsNone(positions[1].cost_basis)

        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].receipt_id, "receipt_portfolio_1")
        self.assertEqual(receipts[0].path, str(receipt.resolve()))

    def test_orders_and_plans_do_not_invent_positions(self) -> None:
        payload = {
            "receipt_id": "receipt_dry_run_1",
            "created_at_utc": "2026-06-17T03:00:00+00:00",
            "broker": "alpaca",
            "environment": "paper",
            "pre_trade": {
                "account_id": "acct-paper",
                "buying_power": "1000",
            },
            "plan": {
                "symbol": "SPY",
                "side": "buy",
                "notional": "25",
            },
            "order": {
                "symbol": "SPY",
                "side": "buy",
                "notional": "25",
            },
        }

        snapshot = ingest_portfolio_snapshot_from_payload(
            payload,
            source_ref="data/receipts/alpaca-paper-dca/example.json",
            engine=self.engine,
        )

        positions = read_all(Position, engine=self.engine)
        loaded = read_all(Snapshot, engine=self.engine)[0]
        self.assertEqual(snapshot.snapshot_id, "snap_portfolio_receipt_dry_run_1")
        self.assertEqual(positions, [])
        self.assertEqual(loaded.payload["position_count"], 0)
        self.assertFalse(loaded.payload["positions_source_disclosed"])
        self.assertFalse(loaded.payload["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
