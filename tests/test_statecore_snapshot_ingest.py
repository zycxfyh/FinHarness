# ruff: noqa: E501, E402, SIM117
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from finharness.capital_import_recovery import audit_capital_imports
from finharness.statecore.models import (
    AccountIdentity,
    ImportBatch,
    InstrumentIdentity,
    Position,
    ReceiptIndex,
    ReceiptManifest,
    Snapshot,
)
from finharness.statecore.receipt_index import index_receipts, receipt_index_record_from_path
from finharness.statecore.snapshot_ingest import (
    BROKER_READ_MATERIALIZED_SOURCE,
    BROKER_READ_SOURCE_KIND,
    ingest_broker_read_receipt,
    ingest_portfolio_snapshot_from_payload,
    ingest_portfolio_snapshot_from_receipt,
    portfolio_records_from_broker_payload,
)
from finharness.statecore.store import StateCoreStoreError, read_all, upsert_records
from tests._statecore_fixtures import StateCoreFixture


class StateCoreSnapshotIngestTest(unittest.TestCase):
    def setUp(self) -> None:
        self.fx = StateCoreFixture()
        self.root = self.fx.root
        self.db_path = self.fx.db_path
        self.receipt_root = self.fx.receipt_root
        self.import_root = self.receipt_root / "capital-imports" / "broker-read"
        self.engine = self.fx.engine
        self.addCleanup(self.fx.cleanup)

    def _write_receipt(self, relative_path: str, payload: dict[str, object]) -> Path:
        return self.fx.write_receipt(relative_path, payload)

    def _broker_payload(
        self,
        *,
        receipt_id: str = "receipt_portfolio_1",
        market_value: str = "100.5",
    ) -> dict[str, object]:
        return {
            "receipt_id": receipt_id,
            "kind": "broker_read",
            "created_at_utc": "2026-06-17T01:02:03+00:00",
            "effective_at_utc": "2026-06-17T01:02:03+00:00",
            "observed_at_utc": "2026-06-17T01:02:03+00:00",
            "valued_at_utc": "2026-06-17T01:00:00+00:00",
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
                    "market_value": market_value,
                    "unit_price": "50.25",
                    "currency": "USD",
                    "asset_class": "equity",
                    "exchange": "ARCX",
                },
                {
                    "symbol": "QQQ",
                    "quantity": "1",
                    "current_price": "49.75",
                    "cost_basis": "45.00",
                    "currency": "USD",
                    "asset_class": "equity",
                    "exchange": "XNAS",
                },
            ],
            "execution_allowed": False,
        }

    def test_index_receipts_records_paths_and_receipt_refs(self) -> None:
        receipt = self._write_receipt(
            "broker/portfolio.json",
            {
                "receipt_id": "receipt_portfolio_1",
                "kind": "broker_read_portfolio",
                "created_at_utc": "2026-06-17T01:02:03+00:00",
                "receipt_refs": ["receipt_market_1"],
                "snapshot": {"receipt_ref": "data/receipts/market-data/receipt_mds_1.json"},
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
        self.assertEqual(portfolio.kind, "broker_read_portfolio")
        self.assertEqual(portfolio.path, str(receipt.resolve()))
        self.assertEqual(portfolio.source_refs, [str(receipt.resolve())])
        self.assertIn("receipt_market_1", portfolio.refs)
        fallback = next(row for row in rows if row.receipt_id == "daily__no-id")
        self.assertEqual(fallback.kind, "daily_evidence")
        unreadable = next(row for row in rows if row.receipt_id == "broken__truncated")
        self.assertEqual(unreadable.kind, "unreadable_json")
        with self.assertRaises(StateCoreStoreError):
            receipt_index_record_from_path(bad_report, receipt_root=self.receipt_root)

    def test_manifested_broker_import_binds_artifacts_batch_manifest_and_rows(self) -> None:
        receipt = self._write_receipt("broker/portfolio.json", self._broker_payload())
        source_sha = hashlib.sha256(receipt.read_bytes()).hexdigest()

        result = ingest_broker_read_receipt(
            receipt,
            engine=self.engine,
            receipt_root=self.import_root,
        )

        batches = read_all(ImportBatch, engine=self.engine)
        manifests = read_all(ReceiptManifest, engine=self.engine)
        snapshots = read_all(Snapshot, engine=self.engine)
        positions = sorted(read_all(Position, engine=self.engine), key=lambda row: row.symbol)
        receipts = read_all(ReceiptIndex, engine=self.engine)

        self.assertIsNotNone(batches[0].stable_source_id)
        version = hashlib.sha256(
            f"{batches[0].stable_source_id}\x00{source_sha}".encode()
        ).hexdigest()[:24]
        self.assertEqual(result.snapshot_id, f"snap_broker_read_{version}")
        self.assertEqual(result.batch_id, batches[0].batch_id)
        self.assertEqual(result.manifest_id, manifests[0].manifest_id)
        self.assertEqual(result.receipt_id, manifests[0].receipt_id)
        self.assertNotEqual(result.receipt_id, "receipt_portfolio_1")
        self.assertEqual(batches[0].source_kind, BROKER_READ_SOURCE_KIND)
        self.assertEqual(batches[0].source_sha256, source_sha)
        self.assertEqual(manifests[0].snapshot_id, result.snapshot_id)
        self.assertEqual(manifests[0].receipt_ref, result.receipt_ref)
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0].payload["import_batch_id"], result.batch_id)
        self.assertEqual(snapshots[0].payload["receipt_manifest_id"], result.manifest_id)
        self.assertEqual(snapshots[0].payload["import_receipt_ref"], result.receipt_ref)
        self.assertIn(str(receipt.resolve()), snapshots[0].source_refs)
        self.assertIn(result.receipt_ref, snapshots[0].source_refs)
        self.assertEqual([row.symbol for row in positions], ["QQQ", "SPY"])
        self.assertTrue(all(position.instrument_id for position in positions))
        self.assertEqual(len(read_all(AccountIdentity, engine=self.engine)), 1)
        self.assertEqual(len(read_all(InstrumentIdentity, engine=self.engine)), 2)
        self.assertEqual(len(receipts), 1)
        self.assertEqual(receipts[0].receipt_id, result.receipt_id)
        self.assertEqual(receipts[0].path, result.receipt_ref)

    def test_compatibility_wrapper_routes_through_manifested_adapter(self) -> None:
        receipt = self._write_receipt("broker/wrapper.json", self._broker_payload())
        snapshot = ingest_portfolio_snapshot_from_receipt(
            receipt,
            engine=self.engine,
            receipt_root=self.import_root,
        )
        self.assertEqual(len(read_all(ImportBatch, engine=self.engine)), 1)
        self.assertEqual(len(read_all(ReceiptManifest, engine=self.engine)), 1)
        self.assertEqual(
            snapshot.payload["import_batch_id"],
            read_all(ImportBatch, engine=self.engine)[0].batch_id,
        )

    def test_same_input_is_idempotent(self) -> None:
        receipt = self._write_receipt("broker/repeat.json", self._broker_payload())
        first = ingest_broker_read_receipt(
            receipt, engine=self.engine, receipt_root=self.import_root
        )
        second = ingest_broker_read_receipt(
            receipt, engine=self.engine, receipt_root=self.import_root
        )
        self.assertEqual(first, second)
        self.assertEqual(len(read_all(ImportBatch, engine=self.engine)), 1)
        self.assertEqual(len(read_all(ReceiptManifest, engine=self.engine)), 1)
        self.assertEqual(len(read_all(Snapshot, engine=self.engine)), 1)
        self.assertEqual(len(read_all(Position, engine=self.engine)), 2)

    def test_same_bytes_from_distinct_source_paths_do_not_share_import_identity(self) -> None:
        first_path = self._write_receipt("broker/path-a.json", self._broker_payload())
        second_path = self._write_receipt("broker/path-b.json", self._broker_payload())
        first = ingest_broker_read_receipt(
            first_path, engine=self.engine, receipt_root=self.import_root
        )
        second = ingest_broker_read_receipt(
            second_path, engine=self.engine, receipt_root=self.import_root
        )
        self.assertNotEqual(first.batch_id, second.batch_id)
        self.assertNotEqual(first.manifest_id, second.manifest_id)
        self.assertNotEqual(first.receipt_id, second.receipt_id)
        self.assertNotEqual(first.snapshot_id, second.snapshot_id)
        self.assertEqual(len(read_all(Snapshot, engine=self.engine)), 2)

    def test_recovery_snapshot_override_must_match_exact_source_identity(self) -> None:
        receipt = self._write_receipt("broker/recovery-id.json", self._broker_payload())
        with self.assertRaisesRegex(StateCoreStoreError, "exact source identity"):
            ingest_broker_read_receipt(
                receipt,
                engine=self.engine,
                receipt_root=self.import_root,
                snapshot_id="snap_caller_supplied",
            )
        self.assertEqual(read_all(ImportBatch, engine=self.engine), [])
        self.assertEqual(read_all(ReceiptManifest, engine=self.engine), [])
        self.assertEqual(read_all(Snapshot, engine=self.engine), [])

    def test_changed_bytes_with_same_upstream_receipt_id_create_new_version(self) -> None:
        receipt = self._write_receipt("broker/versioned.json", self._broker_payload())
        first = ingest_broker_read_receipt(
            receipt, engine=self.engine, receipt_root=self.import_root
        )
        receipt.write_text(
            json.dumps(self._broker_payload(market_value="110.5")),
            encoding="utf-8",
        )
        second = ingest_broker_read_receipt(
            receipt, engine=self.engine, receipt_root=self.import_root
        )
        self.assertEqual(first.upstream_receipt_id, second.upstream_receipt_id)
        self.assertNotEqual(first.batch_id, second.batch_id)
        self.assertNotEqual(first.manifest_id, second.manifest_id)
        self.assertNotEqual(first.snapshot_id, second.snapshot_id)
        self.assertEqual(len(read_all(Snapshot, engine=self.engine)), 2)

    def test_direct_payload_materialization_fails_closed_but_normalizer_remains_pure(self) -> None:
        payload = {
            "receipt_id": "receipt_dry_run_1",
            "created_at_utc": "2026-06-17T03:00:00+00:00",
            "broker": "alpaca",
            "environment": "paper",
            "pre_trade": {"account_id": "acct-paper", "buying_power": "1000"},
            "plan": {"symbol": "SPY", "side": "buy", "notional": "25"},
            "order": {"symbol": "SPY", "side": "buy", "notional": "25"},
        }
        _account, snapshot, positions = portfolio_records_from_broker_payload(
            payload,
            source_ref="data/receipts/alpaca-paper-dca/example.json",
        )
        self.assertEqual(positions, [])
        self.assertEqual(snapshot.payload["position_count"], 0)
        with self.assertRaisesRegex(StateCoreStoreError, "not a production import surface"):
            ingest_portfolio_snapshot_from_payload(
                payload,
                source_ref="data/receipts/alpaca-paper-dca/example.json",
                engine=self.engine,
            )
        self.assertEqual(read_all(Snapshot, engine=self.engine), [])
        self.assertEqual(read_all(ImportBatch, engine=self.engine), [])

    def test_float_money_and_missing_currency_fail_closed_during_normalization(self) -> None:
        base = {
            "receipt_id": "receipt_bad_money",
            "created_at_utc": "2026-07-13T07:00:00+00:00",
            "positions": [{"symbol": "SPY", "qty": "1", "market_value": "10", "currency": "USD"}],
        }
        float_payload = {**base, "positions": [{**base["positions"][0], "market_value": 0.1}]}
        with self.assertRaisesRegex(StateCoreStoreError, "not float"):
            portfolio_records_from_broker_payload(float_payload, source_ref="bad-float.json")
        missing_currency = {
            **base,
            "positions": [{"symbol": "SPY", "qty": "1", "market_value": "10"}],
        }
        with self.assertRaisesRegex(StateCoreStoreError, "three-letter currency"):
            portfolio_records_from_broker_payload(
                missing_currency,
                source_ref="bad-currency.json",
            )

    def test_partial_and_blocking_findings_are_bound_to_import(self) -> None:
        payload = {
            "receipt_id": "receipt_partial",
            "effective_at_utc": "2026-07-11T07:00:00+00:00",
            "observed_at_utc": "2026-07-13T07:00:00+00:00",
            "valued_at_utc": "2026-07-11T07:00:00+00:00",
            "positions": [
                {"symbol": "SPY", "qty": "1", "market_value": "10", "currency": "USD"},
                {"symbol": "QQQ", "qty": "2", "currency": "USD"},
            ],
        }
        receipt = self._write_receipt("broker/partial.json", payload)
        result = ingest_broker_read_receipt(
            receipt, engine=self.engine, receipt_root=self.import_root
        )
        batch = read_all(ImportBatch, engine=self.engine)[0]
        snapshot = read_all(Snapshot, engine=self.engine)[0]
        receipt_payload = json.loads(Path(result.receipt_ref).read_text(encoding="utf-8"))
        self.assertEqual(result.completeness_status, "blocked")
        self.assertEqual(batch.completeness_status, "blocked")
        self.assertEqual(snapshot.payload["completeness_status"], "blocked")
        self.assertEqual(receipt_payload["completeness_status"], "blocked")
        self.assertEqual(batch.findings, snapshot.payload["findings"])
        self.assertEqual(batch.findings, receipt_payload["findings"])

    def test_generic_broker_writes_are_rejected_by_registry_bound_guard(self) -> None:
        with self.assertRaisesRegex(StateCoreStoreError, "materialize_import_batch"):
            upsert_records(
                [
                    ReceiptIndex(
                        receipt_id="receipt_direct_broker",
                        kind=BROKER_READ_SOURCE_KIND,
                        path="direct.json",
                        created_at_utc="2026-07-13T07:00:00+00:00",
                    ),
                    Snapshot(
                        snapshot_id="snap_direct_broker",
                        kind="portfolio",
                        as_of_utc="2026-07-13T07:00:00+00:00",
                        payload={"source": BROKER_READ_MATERIALIZED_SOURCE},
                        source_refs=["direct.json"],
                    ),
                ],
                engine=self.engine,
            )

    def test_artifacts_survive_materialization_failure_without_partial_database_world(self) -> None:
        receipt = self._write_receipt("broker/failure.json", self._broker_payload())
        with patch(
            "finharness.statecore.snapshot_ingest.materialize_import_batch",
            side_effect=StateCoreStoreError("injected materialization failure"),
        ), self.assertRaisesRegex(StateCoreStoreError, "injected"):
            ingest_broker_read_receipt(
                receipt,
                engine=self.engine,
                receipt_root=self.import_root,
            )
        self.assertEqual(read_all(ImportBatch, engine=self.engine), [])
        self.assertEqual(read_all(ReceiptManifest, engine=self.engine), [])
        self.assertEqual(read_all(Snapshot, engine=self.engine), [])
        report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.import_root,
        )
        self.assertIn(
            "receipt_without_materialization",
            {finding.code for finding in report.findings},
        )


if __name__ == "__main__":
    unittest.main()
import copy
import tempfile

from finharness.artifact_store import LocalArtifactStore
from finharness.statecore.store import (
    init_state_core,
    materialize_import_batch,
)


class MaterializerNegativeMatrixTest(unittest.TestCase):
    """Part E: materializer corruption tests — every mutation fails before DB write."""

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
            "receipt_id": "receipt_matrix",
            "kind": "broker_read",
            "created_at_utc": "2026-07-18T09:00:00+00:00",
            "effective_at_utc": "2026-07-18T09:00:00+00:00",
            "observed_at_utc": "2026-07-18T09:00:00+00:00",
            "valued_at_utc": "2026-07-18T09:00:00+00:00",
            "broker": "manual", "environment": "paper",
            "account": {"id": "acct_matrix", "status": "ACTIVE"},
            "positions": [{
                "symbol": "SPY", "qty": "2", "market_value": "100",
                "unit_price": "50", "currency": "USD",
                "asset_class": "equity", "exchange": "ARCX",
                "price_source_ref": "fixture:matrix",
            }],
        }), encoding="utf-8")

    def _capture_envelope(self):
        captured = {}
        _orig = materialize_import_batch

        def patched(records, *, source, batch, manifest, artifact_store, engine):
            captured["records"] = copy.deepcopy(list(records))
            captured["source"] = source
            captured["batch"] = copy.deepcopy(batch)
            captured["manifest"] = copy.deepcopy(manifest)
            captured["store"] = artifact_store
            raise StateCoreStoreError("capture-only")
        with patch("finharness.statecore.snapshot_ingest.materialize_import_batch", patched):
            with self.assertRaises(StateCoreStoreError):
                ingest_broker_read_receipt(
                    self.source, engine=self.engine,
                    receipt_root=self.import_root, artifact_store=self.store,
                )
        return captured

    def _assert_db_empty(self):
        self.assertEqual(read_all(ImportBatch, engine=self.engine), [])
        self.assertEqual(read_all(ReceiptManifest, engine=self.engine), [])
        self.assertEqual(read_all(ReceiptIndex, engine=self.engine), [])
        self.assertEqual(read_all(Snapshot, engine=self.engine), [])

    def _corrupt_and_assert(self, mutate_fn, expected_msg_contains=""):
        cap = self._capture_envelope()
        mutate_fn(cap)
        with self.assertRaisesRegex(StateCoreStoreError, expected_msg_contains):
            materialize_import_batch(
                cap["records"], source=cap["source"],
                batch=cap["batch"], manifest=cap["manifest"],
                artifact_store=cap["store"], engine=self.engine,
            )
        self._assert_db_empty()

    def _corrupt_snapshot_payload(self, key, new_value=None, *, remove=False):
        def mutate(cap):
            for r in cap["records"]:
                if isinstance(r, Snapshot):
                    if remove:
                        del r.payload[key]
                    else:
                        r.payload[key] = new_value
        msg = "missing required import binding" if remove else "binding mismatch"
        self._corrupt_and_assert(mutate, msg)

    # --- Snapshot binding: missing ---
    def test_missing_import_batch_id(self) -> None:
        self._corrupt_snapshot_payload("import_batch_id", remove=True)
    def test_missing_receipt_manifest_id(self) -> None:
        self._corrupt_snapshot_payload("receipt_manifest_id", remove=True)
    def test_missing_import_receipt_id(self) -> None:
        self._corrupt_snapshot_payload("import_receipt_id", remove=True)
    def test_missing_import_receipt_ref(self) -> None:
        self._corrupt_snapshot_payload("import_receipt_ref", remove=True)
    def test_missing_source_artifact_id(self) -> None:
        self._corrupt_snapshot_payload("source_artifact_id", remove=True)
    def test_missing_record_counts(self) -> None:
        self._corrupt_snapshot_payload("record_counts", remove=True)
    def test_missing_completeness_status(self) -> None:
        self._corrupt_snapshot_payload("completeness_status", remove=True)
    def test_missing_findings(self) -> None:
        self._corrupt_snapshot_payload("findings", remove=True)

    # --- Snapshot binding: wrong ---
    def test_wrong_import_batch_id(self) -> None:
        self._corrupt_snapshot_payload("import_batch_id", "wrong")
    def test_wrong_receipt_manifest_id(self) -> None:
        self._corrupt_snapshot_payload("receipt_manifest_id", "wrong")
    def test_wrong_import_receipt_id(self) -> None:
        self._corrupt_snapshot_payload("import_receipt_id", "wrong")
    def test_wrong_import_receipt_ref(self) -> None:
        self._corrupt_snapshot_payload("import_receipt_ref", "wrong")
    def test_wrong_source_artifact_id(self) -> None:
        self._corrupt_snapshot_payload("source_artifact_id", "wrong")
    def test_wrong_record_counts(self) -> None:
        self._corrupt_snapshot_payload("record_counts", {"x": 1})
    def test_wrong_completeness_status(self) -> None:
        self._corrupt_snapshot_payload("completeness_status", "wrong")
    def test_wrong_findings(self) -> None:
        self._corrupt_snapshot_payload("findings", [{"code": "wrong"}])

    # --- ReceiptIndex contract ---
    def test_wrong_receipt_index_kind(self) -> None:
        def mutate(cap):
            for r in cap["records"]:
                if isinstance(r, ReceiptIndex):
                    r.kind = "wrong_kind"
        self._corrupt_and_assert(mutate, "receipt index kind|does not match the receipt manifest|contract mismatch")
    def test_wrong_receipt_index_path(self) -> None:
        def mutate(cap):
            for r in cap["records"]:
                if isinstance(r, ReceiptIndex):
                    r.path = "wrong_path"
        self._corrupt_and_assert(mutate, "receipt index kind|does not match the receipt manifest|contract mismatch")
    def test_wrong_created_at_utc(self) -> None:
        def mutate(cap):
            for r in cap["records"]:
                if isinstance(r, ReceiptIndex):
                    r.created_at_utc = "2000-01-01T00:00:00+00:00"
        self._corrupt_and_assert(mutate, "receipt index kind|does not match the receipt manifest|contract mismatch")
    def test_wrong_source_refs(self) -> None:
        def mutate(cap):
            for r in cap["records"]:
                if isinstance(r, ReceiptIndex):
                    r.source_refs = ["wrong"]
        self._corrupt_and_assert(mutate, "receipt index kind|does not match the receipt manifest|contract mismatch")
    def test_wrong_refs(self) -> None:
        def mutate(cap):
            for r in cap["records"]:
                if isinstance(r, ReceiptIndex):
                    r.refs = ["wrong_ref"]
        self._corrupt_and_assert(mutate, "receipt index kind|does not match the receipt manifest|contract mismatch")

    # --- Snapshot cardinality ---
    def test_zero_snapshots(self) -> None:
        def mutate(cap):
            cap["records"] = [r for r in cap["records"] if not isinstance(r, Snapshot)]
        self._corrupt_and_assert(mutate, "found 0 snapshots")
    def test_wrong_snapshot_id(self) -> None:
        def mutate(cap):
            for r in cap["records"]:
                if isinstance(r, Snapshot):
                    r.snapshot_id = "wrong_snap"
        self._corrupt_and_assert(mutate, "snapshot id")
    def test_extra_snapshot(self) -> None:
        def mutate(cap):
            extra = Snapshot(
                snapshot_id="extra", kind="portfolio",
                as_of_utc="2026-07-18T09:00:00+00:00",
                payload={"source": "broker_read_import"},
            )
            cap["records"] = [*list(cap["records"]), extra]
        self._corrupt_and_assert(mutate, "found 2 snapshots")
