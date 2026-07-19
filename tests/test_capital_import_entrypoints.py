from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

from finharness.artifact_store import LocalArtifactStore
from finharness.capital_import_recovery import audit_capital_imports, recover_capital_imports
from finharness.capital_import_registry import (
    PRODUCTION_CAPITAL_IMPORT_ADAPTERS,
    PRODUCTION_CAPITAL_IMPORT_EXPOSURES,
    PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES,
    PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS,
    receipt_index_contract_fields,
    registry_projection,
)
from finharness.daily_change_brief import run_daily_change_brief
from finharness.project_paths import ROOT
from finharness.statecore.models import (
    ImportBatch,
    Proposal,
    ReceiptIndex,
    ReceiptManifest,
    Snapshot,
)
from finharness.statecore.snapshot_ingest import (
    BROKER_READ_MATERIALIZED_SOURCE,
    ingest_broker_read_receipt,
)
from finharness.statecore.store import (
    StateCoreStoreError,
    immediate_state_core_session,
    init_state_core,
    read_all,
    upsert_records,
)
from finharness.statecore.store import (
    materialize_import_batch as canonical_materialize_import_batch,
)


def _load_checker() -> ModuleType:
    path = ROOT / "scripts" / "check_capital_import_entrypoints.py"
    spec = importlib.util.spec_from_file_location("check_capital_import_entrypoints", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load checker: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _broker_payload(*, receipt_id: str, as_of_utc: str) -> dict[str, object]:
    return {
        "receipt_id": receipt_id,
        "kind": "broker_read",
        "created_at_utc": as_of_utc,
        "effective_at_utc": as_of_utc,
        "observed_at_utc": as_of_utc,
        "valued_at_utc": as_of_utc,
        "broker": "manual",
        "environment": "paper",
        "account": {"id": "acct_manifest", "status": "ACTIVE"},
        "positions": [
            {
                "symbol": "SPY",
                "qty": "2",
                "market_value": "100",
                "unit_price": "50",
                "currency": "USD",
                "asset_class": "equity",
                "exchange": "ARCX",
                "price_source_ref": "fixture:broker-manifest",
            }
        ],
        "execution_allowed": False,
    }


def _copy_validator_repository(target: Path) -> None:
    shutil.copytree(ROOT / "src", target / "src")
    shutil.copytree(ROOT / "scripts", target / "scripts")
    shutil.copy2(ROOT / "Taskfile.yml", target / "Taskfile.yml")
    projection = target / "docs" / "governance" / "capital-import-entrypoints.json"
    projection.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(
        ROOT / "docs" / "governance" / "capital-import-entrypoints.json",
        projection,
    )


class CapitalImportEntrypointInventoryTest(unittest.TestCase):
    def test_registry_has_exact_current_production_kinds(self) -> None:
        self.assertEqual(
            PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS,
            frozenset({"personal_finance_export", "beancount_ledger", "broker_read"}),
        )
        self.assertEqual(
            PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES,
            frozenset({"personal_finance_export", "beancount_ledger", "broker_read_import"}),
        )
        self.assertEqual(len(PRODUCTION_CAPITAL_IMPORT_ADAPTERS), 3)
        self.assertTrue(PRODUCTION_CAPITAL_IMPORT_EXPOSURES)
        self.assertFalse(
            {exposure.exposure_kind for exposure in PRODUCTION_CAPITAL_IMPORT_EXPOSURES}
            & {"api", "agent"}
        )

    def test_checked_in_projection_matches_code_registry(self) -> None:
        projection = json.loads(
            (ROOT / "docs" / "governance" / "capital-import-entrypoints.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(projection, registry_projection())

    def test_repository_checker_accepts_current_inventory(self) -> None:
        checker = _load_checker()
        report = checker.validate_capital_import_entrypoints()
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["findings"], [])
        self.assertFalse(
            {item["exposure_kind"] for item in report["discovered_exposures"]}
            & {"api", "agent"}
        )

    def test_full_validator_rejects_synthetic_repository_bypasses(self) -> None:
        checker = _load_checker()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            _copy_validator_repository(root)
            (root / "src" / "finharness" / "synthetic_import.py").write_text(
                """from finharness.statecore.models import Snapshot
from finharness.statecore.store import upsert_records


def ingest_synthetic_import(*, engine):
    source_kind = "synthetic_capital_import"
    upsert_records(
        [Snapshot(
            snapshot_id="snap_synthetic",
            kind="portfolio",
            payload={"source": source_kind},
            as_of_utc="2026-07-19T00:00:00+00:00",
        )],
        engine=engine,
    )
""",
                encoding="utf-8",
            )
            (root / "scripts" / "unregistered_broker_import.py").write_text(
                """from finharness.statecore.snapshot_ingest import ingest_broker_read_receipt


def main(*, engine, path):
    return ingest_broker_read_receipt(path, engine=engine)
""",
                encoding="utf-8",
            )
            api_path = root / "src" / "finharness" / "api" / "routes_synthetic_import.py"
            api_path.parent.mkdir(parents=True, exist_ok=True)
            api_path.write_text(
                """from finharness.statecore.snapshot_ingest import ingest_broker_read_receipt


def import_capital(*, engine, path):
    return ingest_broker_read_receipt(path, engine=engine)
""",
                encoding="utf-8",
            )
            (root / "src" / "finharness" / "agent_synthetic_import.py").write_text(
                """from finharness.statecore.snapshot_ingest import ingest_broker_read_receipt


def import_capital_tool(*, engine, path):
    return ingest_broker_read_receipt(path, engine=engine)
""",
                encoding="utf-8",
            )
            with (root / "Taskfile.yml").open("a", encoding="utf-8") as handle:
                handle.write(
                    "\n  synthetic:capital-import:\n"
                    "    cmds:\n"
                    "      - uv run python scripts/unregistered_broker_import.py\n"
                )
            report = checker.validate_capital_import_entrypoints(root=root)
        self.assertFalse(report["ok"], report)
        codes = {item["code"] for item in report["findings"]}
        self.assertTrue(
            {
                "unregistered_production_capital_import",
                "unregistered_script_capital_import_exposure",
                "unregistered_api_capital_import_exposure",
                "unregistered_agent_capital_import_exposure",
                "unregistered_task_capital_import_exposure",
            }
            <= codes,
            report,
        )

    def test_adapter_contract_is_reachable_from_registered_symbol(self) -> None:
        checker = _load_checker()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            module = root / "src" / "finharness" / "fake_adapter.py"
            module.parent.mkdir(parents=True, exist_ok=True)
            module.write_text(
                """from dataclasses import dataclass


@dataclass(frozen=True)
class FakeResult:
    batch_id: str
    manifest_id: str


def registered_adapter(*, engine):
    source_kind = "fake_import"
    return upsert_records([], engine=engine)


def unused_helper():
    prepare_import()
    materialize_import_batch()
""",
                encoding="utf-8",
            )
            findings = checker._adapter_contract_findings(
                SimpleNamespace(
                    adapter_id="fake",
                    module="finharness.fake_adapter",
                    symbol="registered_adapter",
                    result_type="FakeResult",
                ),
                root=root,
            )
        codes = {item["code"] for item in findings}
        self.assertIn("adapter_missing_canonical_envelope", codes)
        self.assertIn("adapter_direct_generic_write", codes)


class BrokerImportVerticalAcceptanceTest(unittest.TestCase):
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
        self.source.write_text(
            json.dumps(
                _broker_payload(
                    receipt_id="receipt_vertical",
                    as_of_utc="2026-07-18T09:00:00+00:00",
                )
            ),
            encoding="utf-8",
        )

    def _snapshot(self, source: str) -> Snapshot:
        return Snapshot(
            snapshot_id=f"snap_{source}",
            kind="portfolio",
            payload={"source": source},
            as_of_utc="2026-07-18T09:00:00+00:00",
        )

    def test_legacy_broker_evidence_index_is_allowed(self) -> None:
        upsert_records(
            [
                ReceiptIndex(
                    receipt_id="receipt_legacy_broker_evidence",
                    kind="broker_read",
                    path="legacy-broker.json",
                    created_at_utc="2026-07-18T09:00:00+00:00",
                )
            ],
            engine=self.engine,
        )
        report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.import_root,
            artifact_store=self.store,
        )
        self.assertTrue(report.ok, report)
        self.assertEqual(report.findings, ())

    def test_canonical_broker_receipt_generic_write_is_rejected(self) -> None:
        with self.assertRaisesRegex(StateCoreStoreError, "require materialize_import_batch"):
            upsert_records(
                [
                    ReceiptIndex(
                        receipt_id="receipt_canonical_broker",
                        kind="broker_read_import",
                        path="canonical.json",
                        created_at_utc="2026-07-18T09:00:00+00:00",
                    )
                ],
                engine=self.engine,
            )

    def test_canonical_broker_snapshot_generic_write_is_rejected(self) -> None:
        with self.assertRaisesRegex(StateCoreStoreError, "require materialize_import_batch"):
            upsert_records([self._snapshot("broker_read_import")], engine=self.engine)

    def test_legacy_broker_snapshot_generic_write_is_rejected(self) -> None:
        with self.assertRaisesRegex(StateCoreStoreError, "require materialize_import_batch"):
            upsert_records([self._snapshot("broker_read")], engine=self.engine)

    def test_materializer_rejects_snapshot_envelope_drift(self) -> None:
        def corrupt_snapshot(records, **kwargs):
            materialized = list(records)
            snapshot = next(item for item in materialized if isinstance(item, Snapshot))
            snapshot.payload = {**snapshot.payload, "import_batch_id": "wrong_batch"}
            return canonical_materialize_import_batch(materialized, **kwargs)

        with (
            patch(
                "finharness.statecore.snapshot_ingest.materialize_import_batch",
                side_effect=corrupt_snapshot,
            ),
            self.assertRaisesRegex(StateCoreStoreError, "snapshot does not bind"),
        ):
            ingest_broker_read_receipt(
                self.source,
                engine=self.engine,
                receipt_root=self.import_root,
                artifact_store=self.store,
            )
        self.assertEqual(read_all(ImportBatch, engine=self.engine), [])
        self.assertEqual(read_all(ReceiptManifest, engine=self.engine), [])
        self.assertEqual(read_all(Snapshot, engine=self.engine), [])

    def test_prepared_failure_replays_through_current_path_contract(self) -> None:
        with (
            patch(
                "finharness.statecore.snapshot_ingest.materialize_import_batch",
                side_effect=StateCoreStoreError("injected materialization failure"),
            ),
            self.assertRaisesRegex(StateCoreStoreError, "injected"),
        ):
            ingest_broker_read_receipt(
                self.source,
                engine=self.engine,
                receipt_root=self.import_root,
                artifact_store=self.store,
            )
        before = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.import_root,
            artifact_store=self.store,
        )
        self.assertEqual(
            {finding.code for finding in before.findings},
            {"receipt_without_materialization"},
        )
        self.assertEqual(read_all(ImportBatch, engine=self.engine), [])
        self.assertEqual(read_all(ReceiptManifest, engine=self.engine), [])
        self.assertEqual(read_all(Snapshot, engine=self.engine), [])
        recovery = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.import_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovery.after.ok, recovery.after)
        self.assertTrue(any(action.startswith("replayed:") for action in recovery.actions))
        self.assertEqual(len(read_all(ImportBatch, engine=self.engine)), 1)
        self.assertEqual(len(read_all(ReceiptManifest, engine=self.engine)), 1)
        self.assertEqual(len(read_all(Snapshot, engine=self.engine)), 1)

    def test_missing_import_index_rebuilds_full_canonical_lineage(self) -> None:
        result = ingest_broker_read_receipt(
            self.source,
            engine=self.engine,
            receipt_root=self.import_root,
            artifact_store=self.store,
        )
        batch = read_all(ImportBatch, engine=self.engine)[0]
        manifest = read_all(ReceiptManifest, engine=self.engine)[0]
        payload = json.loads(self.store.read(manifest.receipt_artifact_id))
        expected = receipt_index_contract_fields(
            source_kind=batch.source_kind,
            receipt_ref=manifest.receipt_ref,
            source_artifact_id=batch.source_artifact_id,
            time_semantics=batch.time_semantics,
            receipt_payload=payload,
        )
        with immediate_state_core_session(self.engine) as session:
            index = session.get(ReceiptIndex, result.receipt_id)
            self.assertIsNotNone(index)
            session.delete(index)
        before = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.import_root,
            artifact_store=self.store,
        )
        self.assertIn(
            "manifest_receipt_index_missing_or_stale",
            {finding.code for finding in before.findings},
        )
        recovery = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.import_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovery.after.ok, recovery.after)
        rebuilt = read_all(ReceiptIndex, engine=self.engine)
        self.assertEqual(len(rebuilt), 1)
        self.assertEqual(rebuilt[0].kind, BROKER_READ_MATERIALIZED_SOURCE)
        self.assertEqual(rebuilt[0].path, expected["path"])
        self.assertEqual(rebuilt[0].created_at_utc, expected["created_at_utc"])
        self.assertEqual(rebuilt[0].source_refs, expected["source_refs"])
        self.assertEqual(rebuilt[0].refs, expected["refs"])

    def test_recovery_repairs_weakened_receipt_index_lineage(self) -> None:
        result = ingest_broker_read_receipt(
            self.source,
            engine=self.engine,
            receipt_root=self.import_root,
            artifact_store=self.store,
        )
        with immediate_state_core_session(self.engine) as session:
            index = session.get(ReceiptIndex, result.receipt_id)
            self.assertIsNotNone(index)
            index.source_refs = [result.receipt_ref]
            index.refs = [str(self.source)]
            session.add(index)
        before = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.import_root,
            artifact_store=self.store,
        )
        self.assertIn(
            "manifest_receipt_index_missing_or_stale",
            {finding.code for finding in before.findings},
        )
        recovery = recover_capital_imports(
            engine=self.engine,
            receipt_root=self.import_root,
            artifact_store=self.store,
        )
        self.assertTrue(recovery.after.ok, recovery.after)

    def test_daily_brief_publishes_manifested_import_lineage(self) -> None:
        result = run_daily_change_brief(
            portfolio_receipt=self.source,
            engine=self.engine,
            broker_import_receipt_root=self.import_root,
            state_core_receipt_root=self.root / "receipts" / "state-core",
            brief_receipt_root=self.root / "receipts" / "daily-change-brief",
            markdown_path=self.root / "daily-change-brief.md",
        )
        self.assertEqual(result.status, "baseline")
        batch = read_all(ImportBatch, engine=self.engine)[0]
        manifest = read_all(ReceiptManifest, engine=self.engine)[0]
        self.assertEqual(result.capital_import_batch_id, batch.batch_id)
        self.assertEqual(result.capital_import_manifest_id, manifest.manifest_id)
        self.assertEqual(result.capital_import_receipt_ref, manifest.receipt_ref)
        proposal = next(
            item
            for item in read_all(Proposal, engine=self.engine)
            if item.proposal_id == result.proposal_id
        )
        self.assertEqual(
            proposal.evidence["capital_import_batch_id"],
            result.capital_import_batch_id,
        )
        self.assertEqual(
            proposal.evidence["capital_import_manifest_id"],
            result.capital_import_manifest_id,
        )
        brief = json.loads(Path(result.receipt_ref).read_text(encoding="utf-8"))
        self.assertEqual(
            brief["capital_import_batch_id"],
            result.capital_import_batch_id,
        )
        self.assertEqual(
            brief["capital_import_manifest_id"],
            result.capital_import_manifest_id,
        )
        self.assertEqual(
            brief["capital_import_receipt_ref"],
            result.capital_import_receipt_ref,
        )


if __name__ == "__main__":
    unittest.main()
