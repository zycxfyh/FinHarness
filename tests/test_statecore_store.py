from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import inspect, text
from sqlmodel import Session

from finharness.statecore.models import (
    Account,
    Position,
    Proposal,
    ReceiptIndex,
    Snapshot,
)
from finharness.statecore.store import (
    StateCoreStoreError,
    get_account,
    get_snapshot,
    init_state_core,
    open_state_core,
    read_all,
    write_records,
)


class StateCoreStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "state-core.sqlite"
        self.addCleanup(self.tmp.cleanup)

    def test_init_creates_six_tables_and_wal_mode(self) -> None:
        engine = init_state_core(self.db_path)

        inspector = inspect(engine)
        self.assertTrue(
            {
                "accounts",
                "positions",
                "snapshots",
                "receipt_index",
                "proposals",
                "attestations",
            }.issubset(set(inspector.get_table_names()))
        )
        with engine.connect() as connection:
            journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()
        self.assertEqual(str(journal_mode).lower(), "wal")
        snapshot_indexes = {
            index["name"] for index in inspector.get_indexes("snapshots")
        }
        position_indexes = {
            index["name"] for index in inspector.get_indexes("positions")
        }
        self.assertIn("ix_snapshots_kind_as_of_utc", snapshot_indexes)
        self.assertIn("ix_positions_snapshot_id", position_indexes)

    def test_write_and_read_round_trip(self) -> None:
        engine = init_state_core(self.db_path)
        account = Account(
            account_id="acct_manual",
            kind="broker",
            venue="manual",
            display_name="Manual Brokerage",
            source_refs=["data/receipts/sample.json"],
        )
        snapshot = Snapshot(
            snapshot_id="snap_portfolio_1",
            kind="portfolio",
            payload={"total_market_value": 101.25},
            source_refs=["data/receipts/sample.json"],
        )
        position = Position(
            position_id="pos_1",
            snapshot_id=snapshot.snapshot_id,
            account_id=account.account_id,
            symbol="SPY",
            quantity=1.5,
            market_value=101.25,
            cost_basis=None,
            source_refs=["data/receipts/sample.json"],
        )
        receipt = ReceiptIndex(
            receipt_id="receipt_1",
            kind="portfolio_snapshot",
            path="data/receipts/sample.json",
            refs=["snap_portfolio_1"],
        )

        write_records([account, snapshot, position, receipt], engine=engine)

        loaded_account = get_account("acct_manual", engine=engine)
        loaded_snapshot = get_snapshot("snap_portfolio_1", engine=engine)
        positions = read_all(Position, engine=engine)
        receipts = read_all(ReceiptIndex, engine=engine)

        self.assertEqual(loaded_account, account)
        self.assertEqual(loaded_snapshot, snapshot)
        self.assertEqual(len(positions), 1)
        self.assertIsNone(positions[0].cost_basis)
        self.assertEqual(receipts[0].path, "data/receipts/sample.json")
        self.assertEqual(receipts[0].source_refs, [])

    def test_write_records_is_atomic(self) -> None:
        engine = init_state_core(self.db_path)
        existing = Account(
            account_id="acct_1",
            kind="broker",
            venue="manual",
            display_name="Existing",
        )
        duplicate = Account(
            account_id="acct_1",
            kind="broker",
            venue="manual",
            display_name="Duplicate",
        )
        new_snapshot = Snapshot(
            snapshot_id="snap_should_not_commit",
            kind="portfolio",
            payload={},
        )

        write_records([existing], engine=engine)
        with self.assertRaises(StateCoreStoreError):
            write_records([new_snapshot, duplicate], engine=engine)

        self.assertIsNone(get_snapshot("snap_should_not_commit", engine=engine))
        self.assertEqual(len(read_all(Account, engine=engine)), 1)

    def test_corrupt_database_fails_closed(self) -> None:
        self.db_path.write_text("not sqlite", encoding="utf-8")

        with self.assertRaises(StateCoreStoreError):
            open_state_core(self.db_path)

    def test_missing_database_requires_explicit_create(self) -> None:
        with self.assertRaises(StateCoreStoreError):
            open_state_core(self.db_path)

        engine = init_state_core(self.db_path)
        self.assertTrue(self.db_path.exists())
        engine.dispose()

    def test_proposal_cannot_persist_execution_authority(self) -> None:
        engine = init_state_core(self.db_path)
        proposal = Proposal(
            proposal_id="prop_1",
            kind="rebalance",
            claim="Consider reducing concentration.",
            evidence={"snapshot_id": "snap_1"},
            assumptions={"operator_review": "required"},
            limitations={"not_investment_advice": True},
            non_claims=["Not execution authorization."],
            execution_allowed=True,
        )

        with self.assertRaises(StateCoreStoreError):
            write_records([proposal], engine=engine)

    def test_json_columns_store_structured_values(self) -> None:
        engine = init_state_core(self.db_path)
        snapshot = Snapshot(
            snapshot_id="snap_json",
            kind="portfolio",
            payload={"positions": [{"symbol": "SPY"}]},
            source_refs=["data/receipts/r.json"],
        )

        write_records([snapshot], engine=engine)

        with Session(engine) as session:
            row = session.get(Snapshot, "snap_json")
        self.assertEqual(row.payload["positions"][0]["symbol"], "SPY")
        self.assertEqual(json.loads(json.dumps(row.source_refs)), ["data/receipts/r.json"])

    def test_foreign_keys_are_enforced_on_new_connections(self) -> None:
        engine = init_state_core(self.db_path)
        account = Account(
            account_id="acct_fk",
            kind="broker",
            venue="manual",
            display_name="Foreign Key Account",
        )
        write_records([account], engine=engine)

        engine.dispose()
        orphan_position = Position(
            position_id="pos_orphan",
            snapshot_id="snap_missing",
            account_id=account.account_id,
            symbol="SPY",
            quantity=1.0,
            market_value=100.0,
        )

        with self.assertRaises(StateCoreStoreError):
            write_records([orphan_position], engine=engine)


if __name__ == "__main__":
    unittest.main()
