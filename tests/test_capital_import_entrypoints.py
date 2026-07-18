from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path
from types import ModuleType

from finharness.capital_import_registry import (
    PRODUCTION_CAPITAL_IMPORT_ADAPTERS,
    PRODUCTION_CAPITAL_IMPORT_EXPOSURES,
    PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS,
    registry_projection,
)
from finharness.project_paths import ROOT


def _load_checker() -> ModuleType:
    path = ROOT / "scripts" / "check_capital_import_entrypoints.py"
    spec = importlib.util.spec_from_file_location("check_capital_import_entrypoints", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load checker: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


if __name__ == "__main__":
    unittest.main()
