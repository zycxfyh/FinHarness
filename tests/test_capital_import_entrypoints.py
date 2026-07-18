from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

from sqlmodel import Session

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
        self.assertTrue(recovery.after.ok, recovery.after)
        self.assertTrue(any(action.startswith("replayed:") for action in recovery.actions))
        self.assertEqual(len(read_all(ImportBatch, engine=self.engine)), 1)
        self.assertEqual(len(read_all(ReceiptManifest, engine=self.engine)), 1)
        self.assertEqual(len(read_all(Snapshot, engine=self.engine)), 1)

    def test_missing_import_index_rebuilds_with_materialized_marker(self) -> None:
        result = ingest_broker_read_receipt(
            self.source,
            engine=self.engine,
            receipt_root=self.import_root,
            artifact_store=self.store,
        )
        with Session(self.engine) as session:
            index = session.get(ReceiptIndex, result.receipt_id)
            self.assertIsNotNone(index)
            session.delete(index)
            session.commit()

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
