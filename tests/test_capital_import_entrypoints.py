# ruff: noqa: E501
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from finharness.artifact_store import LocalArtifactStore
from finharness.capital_import_recovery import audit_capital_imports, recover_capital_imports
from finharness.capital_import_registry import (
    PRODUCTION_CAPITAL_IMPORT_ADAPTERS,
    PRODUCTION_CAPITAL_IMPORT_EXPOSURES,
    PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS,
    registry_projection,
)
from finharness.daily_change_brief import run_daily_change_brief
from finharness.project_paths import ROOT
from finharness.statecore.models import (
    Account,
    ImportBatch,
    ImportDomainHead,
    Position,
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
class CapitalImportEntrypointInventoryTest(unittest.TestCase):
    def test_registry_has_exact_current_production_kinds(self) -> None:
        self.assertEqual(
            PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS,
            frozenset({"personal_finance_export", "beancount_ledger", "broker_read"}),
        )
        self.assertEqual(len(PRODUCTION_CAPITAL_IMPORT_ADAPTERS), 3)
        self.assertTrue(PRODUCTION_CAPITAL_IMPORT_EXPOSURES)
        self.assertFalse(
            {
                exposure.exposure_kind
                for exposure in PRODUCTION_CAPITAL_IMPORT_EXPOSURES
            }
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

    def test_synthetic_direct_importer_is_rejected(self) -> None:
        checker = _load_checker()
        source = '''
from finharness.statecore.models import Snapshot
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
'''
        findings = checker.find_generic_write_bypasses(
            source,
            registered_source_kinds=PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS,
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["code"], "unregistered_production_capital_import")
        self.assertEqual(findings[0]["function"], "ingest_synthetic_import")
        self.assertEqual(findings[0]["writers"], ["upsert_records"])
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

    def test_legacy_broker_evidence_index_is_not_an_import_mirror(self) -> None:
        # Generic upsert_records rejects broker_read ReceiptIndex — it's a
        # production source kind now guarded by the registry-bound store.
        with self.assertRaisesRegex(StateCoreStoreError, "materialize_import_batch"):
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
        # History compat: legacy broker_read ReceiptIndex inserted via
        # low-level Session is still readable and audit does not delete it.
        from sqlmodel import Session

        with Session(self.engine) as session:
            legacy = ReceiptIndex(
                receipt_id="receipt_legacy_history",
                kind="broker_read",
                path="legacy-broker.json",
                created_at_utc="2025-01-01T00:00:00+00:00",
            )
            session.add(legacy)
            session.commit()
            session.refresh(legacy)
        # Verify readable
        with Session(self.engine) as session:
            found = session.get(ReceiptIndex, "receipt_legacy_history")
            self.assertIsNotNone(found)
            self.assertEqual(found.kind, "broker_read")  # type: ignore[union-attr]
        # Audit does not remove it
        report = audit_capital_imports(
            engine=self.engine,
            receipt_root=self.import_root,
            artifact_store=self.store,
        )
        self.assertTrue(report.ok, report)
        self.assertEqual(report.findings, ())

    def test_prepared_failure_replays_through_current_path_contract(self) -> None:
        with patch(
            "finharness.statecore.snapshot_ingest.materialize_import_batch",
            side_effect=StateCoreStoreError("injected materialization failure"),
        ), self.assertRaisesRegex(StateCoreStoreError, "injected"):
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
        self.assertFalse(recovery.after.ok)
        self.assertIn(
            "import_domain_head_missing",
            {finding.code for finding in recovery.after.findings},
        )
        self.assertEqual(read_all(ImportDomainHead, engine=self.engine), [])
        self.assertEqual(read_all(Account, engine=self.engine), [])
        self.assertEqual(read_all(Position, engine=self.engine), [])

    def test_missing_import_index_rebuilds_with_materialized_marker(self) -> None:
        result = ingest_broker_read_receipt(
            self.source,
            engine=self.engine,
            receipt_root=self.import_root,
            artifact_store=self.store,
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
        self.assertEqual(result.capital_import_receipt_id, manifest.receipt_id)
        self.assertEqual(result.capital_import_receipt_ref, manifest.receipt_ref)

        proposal = next(
            item
            for item in read_all(Proposal, engine=self.engine)
            if item.proposal_id == result.proposal_id
        )
        self.assertEqual(
            proposal.evidence["capital_import_receipt_id"],
            result.capital_import_receipt_id,
        )
        self.assertEqual(
            proposal.evidence["capital_import_receipt_ref"],
            result.capital_import_receipt_ref,
        )
        brief = json.loads(Path(result.receipt_ref).read_text(encoding="utf-8"))
        self.assertEqual(
            brief["capital_import_receipt_id"],
            result.capital_import_receipt_id,
        )
        self.assertEqual(
            brief["capital_import_receipt_ref"],
            result.capital_import_receipt_ref,
        )
if __name__ == "__main__":
    unittest.main()

class SyntheticFullRepositoryValidatorTest(unittest.TestCase):
    """Part D: synthetic temp repo with unregistered surfaces must fail full validator."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        src_dir = self.root / "src"
        shutil.copytree(ROOT / "src", src_dir, dirs_exist_ok=True)
        scripts_dir = self.root / "scripts"
        shutil.copytree(ROOT / "scripts", scripts_dir, dirs_exist_ok=True)
        gov_dir = self.root / "docs" / "governance"
        gov_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(
            ROOT / "docs" / "governance" / "capital-import-entrypoints.json",
            gov_dir / "capital-import-entrypoints.json",
        )
        shutil.copy2(ROOT / "Taskfile.yml", self.root / "Taskfile.yml")
        shutil.copy2(ROOT / "pyproject.toml", self.root / "pyproject.toml")
        synth_dir = self.root / "src" / "finharness"
        synth_dir.mkdir(parents=True, exist_ok=True)
        (synth_dir / "__init__.py").write_text("", encoding="utf-8")
        (synth_dir / "synthetic_capital_surface.py").write_text("""\
from finharness.statecore.snapshot_ingest import ingest_broker_read_receipt
from finharness.statecore.models import Snapshot
from finharness.statecore.store import upsert_records

router = type("Router", (), {"post": staticmethod(lambda *a, **kw: lambda f: f)})()
app = type("App", (), {"tool": staticmethod(lambda f: f)})()
tool = lambda f: f  # noqa: E731
def import_capital_snapshot(path, *, engine):
    return ingest_broker_read_receipt(path, engine=engine)
def direct_registered_marker_write(*, engine):
    upsert_records(
        [
            Snapshot(
                snapshot_id="synthetic",
                kind="portfolio",
                as_of_utc="2026-07-19T00:00:00+00:00",
                payload={"source": "broker_read"},
            )
        ],
        engine=engine,
    )
@router.post("/capital/import")
def import_capital_api(path, *, engine):
    return ingest_broker_read_receipt(path, engine=engine)
@tool
def import_capital_tool(path, *, engine):
    return ingest_broker_read_receipt(path, engine=engine)
""", encoding="utf-8")
        (self.root / "scripts" / "import_synthetic_capital.py").write_text("""\
from finharness.synthetic_capital_surface import import_capital_snapshot

def main():
    import_capital_snapshot("/dev/null", engine=None)
""", encoding="utf-8")
        tf = self.root / "Taskfile.yml"
        tf.write_text(tf.read_text(encoding="utf-8") + "\n  synthetic:capital-import:\n    cmds:\n      - python scripts/import_synthetic_capital.py\n", encoding="utf-8")

    def test_full_validator_rejects_all_unregistered_surfaces(self) -> None:
        checker = _load_checker()
        report = checker.validate_capital_import_entrypoints(
            root=self.root,
            projection_path=self.root / "docs" / "governance" / "capital-import-entrypoints.json",
        )
        self.assertFalse(report["ok"], f"should reject: {report}")
        codes = {f["code"] for f in report["findings"]}
        expected = {
            "unregistered_function_capital_import_exposure",
            "unregistered_script_capital_import_exposure",
            "unregistered_task_capital_import_exposure",
            "unregistered_api_capital_import_exposure",
            "unregistered_agent_capital_import_exposure",
            "registered_production_import_generic_write",
        }
        missing = expected - codes
        self.assertEqual(missing, set(), f"missing: {missing}")
class AdapterContractReachableHelperTest(unittest.TestCase):
    """Part D6: reachable helper write detected, module-wide calls rejected."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "src" / "finharness").mkdir(parents=True, exist_ok=True)
        (self.root / "src" / "finharness" / "__init__.py").write_text("", encoding="utf-8")

    def test_reachable_helper_generic_write_is_detected(self) -> None:
        (self.root / "src" / "finharness" / "example_adapter.py").write_text("""\
from finharness.statecore.store import upsert_records

def ingest_example(path, *, engine):
    return _persist(path, engine)

def _persist(path, engine):
    upsert_records([], engine=engine)
""", encoding="utf-8")
        checker = _load_checker()
        findings = checker._adapter_contract_findings(
            type("FakeSpec", (), {
                "adapter_id": "fake", "module": "finharness.example_adapter",
                "symbol": "ingest_example", "result_type": "FakeResult",
            })(),
            root=self.root,
        )
        codes = {f["code"] for f in findings}
        self.assertIn("adapter_direct_generic_write", codes, f"not detected: {findings}")

    def test_module_wide_calls_dont_satisfy_adapter_contract(self) -> None:
        (self.root / "src" / "finharness" / "example_adapter2.py").write_text("""\
from finharness.import_provenance import prepare_import
from finharness.statecore.store import materialize_import_batch

def ingest_example(path, *, engine):
    return None

def unrelated():
    prepare_import(source_kind="test", source_id="x",
                   source_content=b"", source_sha256="a"*64,
                   adapter_version="v1", coverage_mode="full",
                   record_counts={}, snapshot_id="s", receipt_id="r",
                   receipt_root=".", receipt_ref="r", artifact_store=None,
                   receipt_payload={}, created_at_utc="", completeness_status="complete",
                   time_semantics={}, findings=[], covered_domains=[],
                   corporate_action_status="not_applicable")
    materialize_import_batch([], source="test", batch=None, manifest=None,
                             artifact_store=None, engine=None)
""", encoding="utf-8")
        checker = _load_checker()
        findings = checker._adapter_contract_findings(
            type("FakeSpec2", (), {
                "adapter_id": "fake2", "module": "finharness.example_adapter2",
                "symbol": "ingest_example", "result_type": "FakeResult2",
            })(),
            root=self.root,
        )
        codes = {f["code"] for f in findings}
        self.assertIn("adapter_missing_canonical_envelope", codes, f"should not pass: {findings}")
