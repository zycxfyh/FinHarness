from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import inspect, text
from sqlmodel import Session

from finharness.statecore.import_models import ImportTombstone
from finharness.statecore.models import (
    Account,
    ImportBatch,
    Position,
    Proposal,
    ReceiptIndex,
    ReviewEvent,
    Snapshot,
)
from finharness.statecore.store import (
    CURRENT_STATE_CORE_USER_VERSION,
    StateCoreStoreError,
    ensure_state_core_schema,
    get_account,
    get_snapshot,
    init_state_core,
    migrate_state_core,
    open_state_core,
    read_all,
    write_records,
)


class StateCoreStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "state-core.sqlite"
        self.addCleanup(self.tmp.cleanup)

    @staticmethod
    def _create_v13_import_batches(connection, *, batch_id: str | None = "batch-v13") -> None:
        connection.exec_driver_sql(
            "CREATE TABLE import_batches ("
            "schema_version VARCHAR NOT NULL, as_of_utc VARCHAR NOT NULL, "
            "authority_level VARCHAR NOT NULL, batch_id VARCHAR PRIMARY KEY, "
            "source_kind VARCHAR NOT NULL, source_id VARCHAR NOT NULL, "
            "coverage_mode VARCHAR NOT NULL, source_sha256 VARCHAR NOT NULL, "
            "source_artifact_id VARCHAR NOT NULL, adapter_version VARCHAR NOT NULL, "
            "import_schema_version VARCHAR NOT NULL, record_counts JSON NOT NULL, "
            "covered_domains JSON NOT NULL, supersedes_batch_id VARCHAR, "
            "correction_reason VARCHAR, corporate_action_status VARCHAR NOT NULL, "
            "corporate_action_gaps JSON NOT NULL, completeness_status VARCHAR NOT NULL, "
            "time_semantics JSON NOT NULL, findings JSON NOT NULL, "
            "CONSTRAINT uq_import_batches_content_contract UNIQUE ("
            "source_kind, source_id, source_sha256, adapter_version, "
            "import_schema_version, coverage_mode, supersedes_batch_id))"
        )
        if batch_id is not None:
            connection.execute(
                text(
                    "INSERT INTO import_batches VALUES ("
                    "'finharness.state_core.v1','2026-07-20T00:00:00+00:00',"
                    "'read_only',:batch_id,'personal_finance_export','source-a','full',"
                    "'same-hash','artifact-a','adapter-v4','manifest-v3','{}',"
                    "'[\"liability\"]',NULL,NULL,'not_applicable','[]','complete','{}','[]')"
                ),
                {"batch_id": batch_id},
            )
        connection.exec_driver_sql("PRAGMA user_version = 13")

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
        snapshot_indexes = {index["name"] for index in inspector.get_indexes("snapshots")}
        position_indexes = {index["name"] for index in inspector.get_indexes("positions")}
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

    def test_position_money_round_trips_as_exact_decimal(self) -> None:
        engine = init_state_core(self.db_path)
        account = Account(
            account_id="acct_dec",
            kind="broker",
            venue="manual",
            display_name="Decimal Brokerage",
        )
        snapshot = Snapshot(snapshot_id="snap_dec", kind="portfolio")
        # 0.1 + 0.2 drifts to 0.30000000000000004 in float; Decimal stays exact.
        positions = [
            Position(
                position_id="pos_a",
                snapshot_id="snap_dec",
                account_id="acct_dec",
                symbol="AAA",
                quantity=Decimal("1"),
                market_value=Decimal("0.1"),
            ),
            Position(
                position_id="pos_b",
                snapshot_id="snap_dec",
                account_id="acct_dec",
                symbol="BBB",
                quantity=Decimal("1"),
                market_value=Decimal("0.2"),
            ),
        ]
        write_records([account, snapshot, *positions], engine=engine)

        loaded = read_all(Position, engine=engine)
        for position in loaded:
            self.assertIsInstance(position.market_value, Decimal)
        total = sum((position.market_value for position in loaded), Decimal("0"))
        self.assertEqual(total, Decimal("0.3"))

    def test_legacy_real_affinity_money_reads_back_clean_decimal(self) -> None:
        # A database created before the Decimal migration has REAL affinity on
        # money columns; reads must still yield clean Decimals (not float noise).
        engine = open_state_core(self.db_path, create=True)
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE accounts (account_id TEXT PRIMARY KEY, kind TEXT, "
                    "venue TEXT, display_name TEXT, schema_version TEXT, as_of_utc TEXT, "
                    "authority_level TEXT, source_refs JSON, created_at_utc TEXT)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE snapshots (snapshot_id TEXT PRIMARY KEY, kind TEXT, "
                    "schema_version TEXT, as_of_utc TEXT, authority_level TEXT, "
                    "payload JSON, source_refs JSON)"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE positions (position_id TEXT PRIMARY KEY, snapshot_id TEXT, "
                    "account_id TEXT, symbol TEXT, quantity REAL, market_value REAL, "
                    "cost_basis REAL, schema_version TEXT, as_of_utc TEXT, "
                    "authority_level TEXT, source_refs JSON)"
                )
            )

        ensure_state_core_schema(engine)

        write_records(
            [
                Account(account_id="a", kind="broker", venue="m", display_name="A"),
                Snapshot(snapshot_id="s", kind="portfolio"),
                Position(
                    position_id="p1",
                    snapshot_id="s",
                    account_id="a",
                    symbol="AAA",
                    quantity=Decimal("1"),
                    market_value=Decimal("0.1"),
                ),
                Position(
                    position_id="p2",
                    snapshot_id="s",
                    account_id="a",
                    symbol="BBB",
                    quantity=Decimal("1"),
                    market_value=Decimal("0.2"),
                ),
            ],
            engine=engine,
        )

        loaded = read_all(Position, engine=engine)
        total = sum((position.market_value for position in loaded), Decimal("0"))
        self.assertEqual(total, Decimal("0.3"))
        self.assertEqual({str(p.market_value) for p in loaded}, {"0.1", "0.2"})

    def test_migration_rebuilds_legacy_real_money_columns_as_text(self) -> None:
        engine = init_state_core(self.db_path)
        write_records(
            [
                Account(account_id="a", kind="broker", venue="m", display_name="A"),
                Snapshot(snapshot_id="s", kind="portfolio"),
            ],
            engine=engine,
        )
        # Simulate a pre-Decimal database: positions money columns as REAL, and
        # the schema version reset so the migration treats it as unmigrated.
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE positions"))
            connection.execute(
                text(
                    "CREATE TABLE positions (position_id TEXT PRIMARY KEY, snapshot_id TEXT, "
                    "account_id TEXT, symbol TEXT, quantity REAL, market_value REAL, "
                    "cost_basis REAL, schema_version TEXT, as_of_utc TEXT, authority_level TEXT, "
                    "source_refs JSON, FOREIGN KEY(account_id) REFERENCES accounts(account_id), "
                    "FOREIGN KEY(snapshot_id) REFERENCES snapshots(snapshot_id))"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO positions (position_id, snapshot_id, account_id, symbol, "
                    "quantity, market_value, cost_basis, schema_version, as_of_utc, "
                    "authority_level, source_refs) VALUES ('p1','s','a','AAA',1,0.1,NULL,"
                    "'finharness.state_core.v1','2026-06-19T00:00:00+00:00','read_only','[]')"
                )
            )
            connection.exec_driver_sql("PRAGMA user_version = 0")

        migrate_state_core(engine)

        with engine.connect() as connection:
            self.assertEqual(
                int(connection.execute(text("PRAGMA user_version")).scalar_one()),
                CURRENT_STATE_CORE_USER_VERSION,
            )
            self.assertEqual(
                connection.execute(text("SELECT typeof(market_value) FROM positions")).scalar_one(),
                "text",
            )
        loaded = read_all(Position, engine=engine)
        self.assertIsInstance(loaded[0].market_value, Decimal)
        self.assertEqual(loaded[0].market_value, Decimal("0.1"))
        self.assertIsNone(loaded[0].cost_basis)
        # Idempotent: a second run is a no-op.
        migrate_state_core(engine)
        self.assertEqual(len(read_all(Position, engine=engine)), 1)

    def test_migration_adds_decision_scaffold_to_legacy_proposals(self) -> None:
        engine = init_state_core(self.db_path)
        write_records(
            [Proposal(proposal_id="p_old", kind="cash_buffer_low", claim="legacy")],
            engine=engine,
        )
        # Simulate a pre-P4 database: proposals without decision_scaffold, version reset.
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE proposals DROP COLUMN decision_scaffold"))
            connection.exec_driver_sql("PRAGMA user_version = 2")
        with engine.connect() as connection:
            columns = {
                row[1] for row in connection.execute(text("PRAGMA table_info(proposals)")).all()
            }
            self.assertNotIn("decision_scaffold", columns)  # legacy state confirmed

        migrate_state_core(engine)

        with engine.connect() as connection:
            self.assertEqual(
                int(connection.execute(text("PRAGMA user_version")).scalar_one()),
                CURRENT_STATE_CORE_USER_VERSION,
            )
            columns = {
                row[1] for row in connection.execute(text("PRAGMA table_info(proposals)")).all()
            }
            self.assertIn("decision_scaffold", columns)
            self.assertEqual(
                connection.execute(
                    text("SELECT decision_scaffold FROM proposals WHERE proposal_id='p_old'")
                ).scalar_one(),
                "{}",
            )
        # The legacy row loads through the ORM with an empty scaffold dict.
        loaded = read_all(Proposal, engine=engine)
        self.assertEqual(loaded[0].decision_scaffold, {})
        # Idempotent: a second run is a no-op.
        migrate_state_core(engine)

    def test_migration_adds_auth03_bindings_without_forging_legacy_identity(self) -> None:
        engine = open_state_core(self.db_path, create=True)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE agent_authority_grants (agent_authority_grant_id VARCHAR PRIMARY KEY)"
            )
            connection.exec_driver_sql("INSERT INTO agent_authority_grants VALUES ('legacy-grant')")
            connection.exec_driver_sql("PRAGMA user_version = 5")

        migrate_state_core(engine)

        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT mandate_version_id, principal_id, agent_runtime_id, "
                    "max_uses, max_total_notional FROM agent_authority_grants"
                )
            ).one()
            self.assertEqual(tuple(row), (None, None, None, None, None))
            self.assertEqual(
                int(connection.execute(text("PRAGMA user_version")).scalar_one()),
                CURRENT_STATE_CORE_USER_VERSION,
            )
        migrate_state_core(engine)

    def test_migration_adds_currency_bindings_without_guessing_legacy_currency(self) -> None:
        engine = open_state_core(self.db_path, create=True)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE agent_authority_grants (agent_authority_grant_id VARCHAR PRIMARY KEY)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE agent_authority_grant_consumptions ("
                "grant_consumption_id VARCHAR PRIMARY KEY)"
            )
            connection.exec_driver_sql("INSERT INTO agent_authority_grants VALUES ('legacy-grant')")
            connection.exec_driver_sql(
                "INSERT INTO agent_authority_grant_consumptions VALUES ('legacy-consumption')"
            )
            connection.exec_driver_sql("PRAGMA user_version = 11")

        migrate_state_core(engine)

        inspector = inspect(engine)
        self.assertIn(
            "notional_currency",
            {column["name"] for column in inspector.get_columns("agent_authority_grants")},
        )
        self.assertIn(
            "requested_notional_currency",
            {
                column["name"]
                for column in inspector.get_columns("agent_authority_grant_consumptions")
            },
        )
        with engine.connect() as connection:
            self.assertIsNone(
                connection.execute(
                    text("SELECT notional_currency FROM agent_authority_grants")
                ).scalar_one()
            )
            self.assertIsNone(
                connection.execute(
                    text(
                        "SELECT requested_notional_currency FROM agent_authority_grant_consumptions"
                    )
                ).scalar_one()
            )
            self.assertEqual(
                int(connection.execute(text("PRAGMA user_version")).scalar_one()),
                CURRENT_STATE_CORE_USER_VERSION,
            )
        migrate_state_core(engine)

    def test_migration_marks_legacy_import_semantics_unknown(self) -> None:
        engine = open_state_core(self.db_path, create=True)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE import_batches ("
                "schema_version VARCHAR NOT NULL, as_of_utc VARCHAR NOT NULL, "
                "authority_level VARCHAR NOT NULL, batch_id VARCHAR PRIMARY KEY, "
                "source_kind VARCHAR NOT NULL, source_id VARCHAR NOT NULL, "
                "coverage_mode VARCHAR NOT NULL, source_sha256 VARCHAR NOT NULL, "
                "source_artifact_id VARCHAR NOT NULL, adapter_version VARCHAR NOT NULL, "
                "import_schema_version VARCHAR NOT NULL, record_counts JSON NOT NULL)"
            )
            connection.exec_driver_sql(
                "INSERT INTO import_batches VALUES ("
                "'finharness.state_core.v1','2026-07-12T00:00:00+00:00','read_only',"
                "'legacy-batch','legacy','source','full','hash','artifact','v1','v1','{}')"
            )
            connection.exec_driver_sql("PRAGMA user_version = 7")

        migrate_state_core(engine)

        batch = read_all(ImportBatch, engine=engine)[0]
        self.assertEqual(batch.completeness_status, "legacy_unknown")
        self.assertEqual(batch.time_semantics, {})
        self.assertEqual(batch.findings, [])
        self.assertEqual(batch.covered_domains, [])
        self.assertIsNone(batch.supersedes_batch_id)
        self.assertEqual(batch.corporate_action_status, "unsupported_gap")
        self.assertEqual(
            batch.corporate_action_gaps,
            ["corporate_action_semantics_not_supported"],
        )
        with engine.connect() as connection:
            self.assertIn("import_tombstones", inspect(connection).get_table_names())
        migrate_state_core(engine)

    def test_v13_import_batch_schema_migrates_to_v14_contract_identity(self) -> None:
        engine = open_state_core(self.db_path, create=True)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE import_batches ("
                "schema_version VARCHAR NOT NULL, as_of_utc VARCHAR NOT NULL, "
                "authority_level VARCHAR NOT NULL, batch_id VARCHAR PRIMARY KEY, "
                "source_kind VARCHAR NOT NULL, source_id VARCHAR NOT NULL, "
                "coverage_mode VARCHAR NOT NULL, source_sha256 VARCHAR NOT NULL, "
                "source_artifact_id VARCHAR NOT NULL, adapter_version VARCHAR NOT NULL, "
                "import_schema_version VARCHAR NOT NULL, record_counts JSON NOT NULL, "
                "covered_domains JSON NOT NULL, supersedes_batch_id VARCHAR, "
                "correction_reason VARCHAR, corporate_action_status VARCHAR NOT NULL, "
                "corporate_action_gaps JSON NOT NULL, completeness_status VARCHAR NOT NULL, "
                "time_semantics JSON NOT NULL, findings JSON NOT NULL, "
                "CONSTRAINT uq_import_batches_content_contract UNIQUE ("
                "source_kind, source_id, source_sha256, adapter_version, "
                "import_schema_version, coverage_mode, supersedes_batch_id))"
            )
            connection.exec_driver_sql(
                "INSERT INTO import_batches VALUES ("
                "'finharness.state_core.v1','2026-07-20T00:00:00+00:00','read_only',"
                "'batch-v13','personal_finance_export','source-a','full','same-hash',"
                "'artifact-a','adapter-v4','manifest-v3','{}','[\"liability\"]',"
                "NULL,NULL,'not_applicable','[]','complete','{}','[]')"
            )
            connection.exec_driver_sql("PRAGMA user_version = 13")

        migrate_state_core(engine)

        migrated_batch = read_all(ImportBatch, engine=engine)[0]
        self.assertIsInstance(migrated_batch.record_counts, dict)
        self.assertIsInstance(migrated_batch.covered_domains, list)
        self.assertIsInstance(migrated_batch.corporate_action_gaps, list)
        self.assertIsInstance(migrated_batch.time_semantics, dict)
        self.assertIsInstance(migrated_batch.findings, list)
        self.assertEqual(migrated_batch.record_counts, {})
        self.assertEqual(migrated_batch.covered_domains, ["liability"])
        self.assertEqual(migrated_batch.corporate_action_gaps, [])
        self.assertEqual(migrated_batch.time_semantics, {})
        self.assertEqual(migrated_batch.findings, [])

        inspector = inspect(engine)
        columns = {column["name"] for column in inspector.get_columns("import_batches")}
        self.assertIn("contract_digest", columns)
        constraints = {
            item["name"]: tuple(item["column_names"])
            for item in inspector.get_unique_constraints("import_batches")
        }
        self.assertEqual(
            constraints["uq_import_batches_content_contract"],
            (
                "source_kind",
                "source_id",
                "source_sha256",
                "adapter_version",
                "import_schema_version",
                "contract_digest",
            ),
        )
        with engine.connect() as connection:
            version = int(connection.execute(text("PRAGMA user_version")).scalar_one())
            digest = connection.execute(
                text("SELECT contract_digest FROM import_batches WHERE batch_id='batch-v13'")
            ).scalar_one()
            connection.execute(
                text(
                    "INSERT INTO import_batches ("
                    "schema_version, as_of_utc, authority_level, batch_id, source_kind, "
                    "source_id, coverage_mode, source_sha256, source_artifact_id, "
                    "adapter_version, import_schema_version, contract_digest, record_counts, "
                    "covered_domains, supersedes_batch_id, correction_reason, "
                    "corporate_action_status, corporate_action_gaps, completeness_status, "
                    "time_semantics, findings) VALUES ("
                    "'finharness.state_core.v1','2026-07-20T00:00:00+00:00','read_only',"
                    "'batch-v14-b','personal_finance_export','source-b','full','same-hash',"
                    "'artifact-b','adapter-v4','manifest-v3',:digest,'{}','[\"liability\"]',"
                    "NULL,NULL,'not_applicable','[]','complete','{}','[]')"
                ),
                {"digest": digest},
            )
            connection.commit()
        self.assertEqual(version, 14)
        self.assertTrue(str(digest).startswith("legacy:"))
        self.assertEqual(len(read_all(ImportBatch, engine=engine)), 2)
        migrate_state_core(engine)

    def test_v14_migration_preserves_preexisting_import_fk_violations(self) -> None:
        engine = open_state_core(self.db_path, create=True)
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
            connection.commit()
            with connection.begin():
                self._create_v13_import_batches(connection, batch_id=None)
                ImportTombstone.__table__.create(connection)
                connection.execute(
                    ImportTombstone.__table__.insert(),
                    {
                        "schema_version": "finharness.state_core.v1",
                        "as_of_utc": "2026-07-20T00:00:00+00:00",
                        "authority_level": "read_only",
                        "tombstone_id": "orphan-before-v14",
                        "batch_id": "missing-before-v14",
                        "source_kind": "personal_finance_export",
                        "record_type": "Liability",
                        "record_id": "legacy-orphan",
                        "reason": "legacy_orphan",
                        "source_refs": [],
                    },
                )
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            connection.commit()

        try:
            migrate_state_core(engine)
        except StateCoreStoreError as exc:
            self.fail(f"v14 rejected a foreign-key violation that predated migration: {exc}")

        with engine.connect() as connection:
            version = int(connection.execute(text("PRAGMA user_version")).scalar_one())
            violations = connection.exec_driver_sql(
                "PRAGMA foreign_key_check(import_tombstones)"
            ).all()
        self.assertEqual(version, 14)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0][2], "import_batches")

    def test_v14_migration_new_fk_violation_rolls_back_atomically(self) -> None:
        engine = open_state_core(self.db_path, create=True)
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = OFF")
            connection.commit()
            with connection.begin():
                self._create_v13_import_batches(connection)
                ImportTombstone.__table__.create(connection)
                connection.execute(
                    ImportTombstone.__table__.insert(),
                    {
                        "schema_version": "finharness.state_core.v1",
                        "as_of_utc": "2026-07-20T00:00:00+00:00",
                        "authority_level": "read_only",
                        "tombstone_id": "valid-before-v14",
                        "batch_id": "batch-v13",
                        "source_kind": "personal_finance_export",
                        "record_type": "Liability",
                        "record_id": "legacy-valid",
                        "reason": "legacy_valid",
                        "source_refs": [],
                    },
                )
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            connection.commit()

        from finharness.statecore import store as store_module

        original = store_module._rebuild_import_batches_unique

        def inject_new_violation(connection) -> None:
            original(connection)
            connection.execute(
                text("DELETE FROM import_batches WHERE batch_id = 'batch-v13'")
            )

        with (
            patch.object(
                store_module,
                "_rebuild_import_batches_unique",
                inject_new_violation,
            ),
            self.assertRaisesRegex(StateCoreStoreError, "foreign-key violations"),
        ):
            migrate_state_core(engine)

        with engine.connect() as connection:
            version = int(connection.execute(text("PRAGMA user_version")).scalar_one())
            foreign_keys = int(connection.execute(text("PRAGMA foreign_keys")).scalar_one())
            batch_count = int(
                connection.execute(
                    text("SELECT COUNT(*) FROM import_batches WHERE batch_id='batch-v13'")
                ).scalar_one()
            )
            violations = connection.exec_driver_sql(
                "PRAGMA foreign_key_check(import_tombstones)"
            ).all()
        self.assertEqual(version, 13)
        self.assertEqual(foreign_keys, 1)
        self.assertEqual(batch_count, 1)
        self.assertEqual(violations, [])

    def test_migration_adds_identity_bindings_without_forging_legacy_identity(self) -> None:
        engine = open_state_core(self.db_path, create=True)
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE accounts ("
                "account_id VARCHAR PRIMARY KEY, kind VARCHAR NOT NULL, "
                "venue VARCHAR NOT NULL, display_name VARCHAR NOT NULL, "
                "source_refs JSON NOT NULL, created_at_utc VARCHAR NOT NULL, "
                "schema_version VARCHAR NOT NULL, as_of_utc VARCHAR NOT NULL, "
                "authority_level VARCHAR NOT NULL)"
            )
            connection.exec_driver_sql(
                "CREATE TABLE positions ("
                "position_id VARCHAR PRIMARY KEY, snapshot_id VARCHAR NOT NULL, "
                "account_id VARCHAR NOT NULL, symbol VARCHAR NOT NULL, "
                "quantity TEXT NOT NULL, market_value TEXT NOT NULL, cost_basis TEXT, "
                "source_refs JSON NOT NULL, schema_version VARCHAR NOT NULL, "
                "as_of_utc VARCHAR NOT NULL, authority_level VARCHAR NOT NULL)"
            )
            connection.exec_driver_sql(
                "INSERT INTO accounts VALUES "
                "('legacy', 'broker', 'legacy', 'Legacy', '[]', '2026-01-01Z', "
                "'finharness.state_core.v1', '2026-01-01Z', 'read_only')"
            )
            connection.exec_driver_sql(
                "INSERT INTO positions VALUES "
                "('legacy-pos', 'legacy-snapshot', 'legacy', 'ABC', '1', '10', NULL, "
                "'[]', 'finharness.state_core.v1', '2026-01-01Z', 'read_only')"
            )
            connection.exec_driver_sql("PRAGMA user_version = 8")

        ensure_state_core_schema(engine)

        with engine.connect() as connection:
            account = connection.execute(
                text("SELECT canonical_account_id FROM accounts WHERE account_id='legacy'")
            ).one()
            position = connection.execute(
                text(
                    "SELECT instrument_id, valuation_currency, unit_price, price_currency, "
                    "valued_at_utc, fx_rate, valuation_status FROM positions "
                    "WHERE position_id='legacy-pos'"
                )
            ).one()
            tables = set(inspect(connection).get_table_names())
            version = int(connection.execute(text("PRAGMA user_version")).scalar_one())
        self.assertIsNone(account[0])
        self.assertIsNone(position[0])
        self.assertEqual(position[1:6], (None, None, None, None, None))
        self.assertEqual(position[6], "unknown_legacy")
        self.assertTrue(
            {"account_identities", "instrument_identities", "identity_aliases"} <= tables
        )
        self.assertEqual(version, CURRENT_STATE_CORE_USER_VERSION)

    def test_migration_updates_review_event_kind_constraint_for_agent_artifacts(self) -> None:
        engine = init_state_core(self.db_path)
        write_records(
            [Proposal(proposal_id="p_review", kind="cash_buffer_low", claim="legacy")],
            engine=engine,
        )
        # Simulate the v3 review_events table whose closed kind set did not yet include
        # Agent review artifacts.
        with engine.begin() as connection:
            connection.execute(text("DROP TABLE review_events"))
            connection.execute(
                text(
                    "CREATE TABLE review_events ("
                    "schema_version VARCHAR NOT NULL, as_of_utc VARCHAR NOT NULL, "
                    "authority_level VARCHAR NOT NULL, review_event_id VARCHAR NOT NULL, "
                    "proposal_id VARCHAR NOT NULL, kind VARCHAR NOT NULL, "
                    "attester VARCHAR NOT NULL, reason VARCHAR NOT NULL, text VARCHAR, "
                    "attestation_ref VARCHAR, compare_with VARCHAR, source_refs JSON NOT NULL, "
                    "content_hash VARCHAR NOT NULL, execution_allowed BOOLEAN NOT NULL, "
                    "created_at_utc VARCHAR NOT NULL, PRIMARY KEY (review_event_id), "
                    "FOREIGN KEY(proposal_id) REFERENCES proposals (proposal_id), "
                    "CONSTRAINT ck_review_events_execution_allowed_false "
                    "CHECK (execution_allowed = 0), "
                    "CONSTRAINT ck_review_events_kind_closed CHECK "
                    "(kind IN ('annotation', 'archive', 'reopen', 'compare_mark')))"
                )
            )
            connection.exec_driver_sql("PRAGMA user_version = 3")

        migrate_state_core(engine)

        with engine.connect() as connection:
            self.assertEqual(
                int(connection.execute(text("PRAGMA user_version")).scalar_one()),
                CURRENT_STATE_CORE_USER_VERSION,
            )
            table_sql = connection.execute(
                text(
                    "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'review_events'"
                )
            ).scalar_one()
            self.assertIn("agent_review_note", table_sql)
            self.assertIn("agent_scaffold_revision_apply_candidate", table_sql)
        write_records(
            [
                ReviewEvent(
                    review_event_id="rev_agent_note",
                    proposal_id="p_review",
                    kind="agent_review_note",
                    attester="agent:review-note",
                    reason="draft review note",
                    text="{}",
                )
            ],
            engine=engine,
        )
        write_records(
            [
                ReviewEvent(
                    review_event_id="rev_agent_scaffold_candidate",
                    proposal_id="p_review",
                    kind="agent_scaffold_revision_apply_candidate",
                    attester="agent:scaffold-candidate",
                    reason="draft scaffold apply candidate",
                    text="{}",
                )
            ],
            engine=engine,
        )
        self.assertEqual(
            {event.kind for event in read_all(ReviewEvent, engine=engine)},
            {"agent_review_note", "agent_scaffold_revision_apply_candidate"},
        )
        # Idempotent: a second run is a no-op.
        migrate_state_core(engine)

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
