from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml
from scripts.sync_current_docs import BEGIN, END, check, expected_outputs


def _catalog() -> dict:
    return {
        "schema": "finharness.system_catalog.v3",
        "status": "current",
        "allowed_statuses": ["current"],
        "fact_ownership": {},
        "documentation": {
            "navigation": {
                "entrypoints": ["README.md"],
                "historical_roots": ["docs/archive"],
            }
        },
        "systems": [
            {
                "id": "example",
                "name": "Example",
                "status": "current",
                "summary": "Example current system.",
                "docs": ["README.md"],
                "runtime_roots": ["README.md"],
                "mature_posture": "Locally owned.",
                "checks": ["task docs:current-check"],
                "upgrade_trigger": "Measured pressure.",
            }
        ],
    }


def _inventory() -> dict:
    return {
        "schema": "finharness.attestation_consumer_inventory.v1",
        "baseline_sha": "abc",
        "scope": {"source_roots": ["src"], "scan_terms": ["Attestation"]},
        "summary": {
            "total_consumers": 1,
            "by_role": {"schema_model": 1},
            "by_disposition": {"preserve": 1},
            "high_or_critical_count": 1,
        },
        "consumers": [
            {
                "consumer_id": "ATT-CONS-001",
                "path": "src/model.py",
                "symbol": "Attestation",
                "role": "schema_model",
                "decision_semantics": "historical_evidence",
                "version_binding": "proposal_id_only",
                "risk": "high",
                "disposition": "preserve",
                "target_owner": "historical evidence",
            }
        ],
        "exclusions": [],
        "unclassified_hits": [],
    }


class CurrentDocGenerationTest(unittest.TestCase):
    def _root(self) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / "docs" / "architecture").mkdir(parents=True)
        (root / "docs" / "governance").mkdir(parents=True)
        (root / "docs" / "audits").mkdir(parents=True)
        (root / "README.md").write_text("# Root\n", encoding="utf-8")
        (root / "docs" / "architecture" / "system-catalog.yml").write_text(
            yaml.safe_dump(_catalog(), sort_keys=False), encoding="utf-8"
        )
        marker_doc = f"# View\n\n{BEGIN}\nstale\n{END}\n"
        (root / "docs" / "architecture" / "framework-index.md").write_text(
            marker_doc, encoding="utf-8"
        )
        (root / "docs" / "architecture" / "module-map.md").write_text(
            marker_doc, encoding="utf-8"
        )
        (root / "docs" / "governance" / "attestation-consumers.json").write_text(
            json.dumps(_inventory()), encoding="utf-8"
        )
        (root / "docs" / "audits" / "attestation-consumer-inventory.md").write_text(
            "stale", encoding="utf-8"
        )
        for path, content in expected_outputs(root).items():
            path.write_text(content, encoding="utf-8")
        return temp, root

    def test_repository_views_are_current(self) -> None:
        self.assertEqual([], check())

    def test_json_change_makes_attestation_markdown_stale(self) -> None:
        temp, root = self._root()
        try:
            source = root / "docs" / "governance" / "attestation-consumers.json"
            data = json.loads(source.read_text(encoding="utf-8"))
            data["baseline_sha"] = "changed"
            source.write_text(json.dumps(data), encoding="utf-8")
            self.assertTrue(
                any("attestation-consumer-inventory.md is stale" in item for item in check(root))
            )
        finally:
            temp.cleanup()

    def test_navigation_rejects_missing_reachable_document(self) -> None:
        temp, root = self._root()
        try:
            (root / "README.md").write_text("[Missing](docs/missing.md)\n", encoding="utf-8")
            self.assertTrue(
                any("links missing path docs/missing.md" in item for item in check(root))
            )
        finally:
            temp.cleanup()


if __name__ == "__main__":
    unittest.main()
