from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.manage_governance_inventories import (
    InventoryError,
    inspect_inventories,
    update_inventories,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _fixture_root(base: Path) -> Path:
    (base / "src").mkdir()
    (base / "src" / "consumer.py").write_text("import fastapi\n", encoding="utf-8")
    (base / "pyproject.toml").write_text(
        """[project]
dependencies = ["fastapi>=1"]
[dependency-groups]
dev = []
""",
        encoding="utf-8",
    )
    _write_json(
        base / "docs" / "governance" / "dependency-consumers.json",
        {
            "schema": "finharness.dependency_consumer_manifest.v1",
            "status": "current",
            "debt_ref": "test",
            "source_roots": ["pyproject.toml", "src"],
            "entries": [
                {
                    "distribution": "fastapi",
                    "requirement": "fastapi>=0",
                    "declared_group": "dev",
                    "recommended_group": "base",
                    "import_modules": [],
                    "import_consumers": [],
                    "task_consumers": ["api:serve"],
                    "rationale": "Manual policy judgment remains intact.",
                    "confidence": "high",
                }
            ],
        },
    )
    _write_json(
        base / "docs" / "governance" / "attestation-consumers.json",
        {
            "consumers": [
                {"role": "state_gate", "disposition": "preserve", "risk": "high"}
            ],
            "summary": {},
        },
    )
    return base


class GovernanceInventoryGenerationTest(unittest.TestCase):
    def test_repository_inventories_are_current(self) -> None:
        changes, paper_findings = inspect_inventories(REPO_ROOT)
        self.assertEqual([finding for item in changes for finding in item.findings], [])
        self.assertEqual(paper_findings, [])

    def test_check_is_read_only_and_update_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture_root(Path(tmp))
            dependency_path = root / "docs" / "governance" / "dependency-consumers.json"
            before = dependency_path.read_text(encoding="utf-8")
            changes, findings = inspect_inventories(root)
            self.assertTrue(any(change.findings for change in changes))
            self.assertEqual(findings, [])
            self.assertEqual(dependency_path.read_text(encoding="utf-8"), before)

            updated = update_inventories(root)
            self.assertEqual(len(updated), 2)
            manifest = json.loads(dependency_path.read_text(encoding="utf-8"))
            entry = manifest["entries"][0]
            self.assertEqual(entry["requirement"], "fastapi>=1")
            self.assertEqual(entry["declared_group"], "base")
            self.assertEqual(entry["import_consumers"], ["src/consumer.py"])
            self.assertEqual(entry["rationale"], "Manual policy judgment remains intact.")
            self.assertEqual(update_inventories(root), [])

    def test_new_dependency_requires_manual_policy_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = _fixture_root(Path(tmp))
            pyproject = root / "pyproject.toml"
            pyproject.write_text(
                "[project]\ndependencies = [\"fastapi>=1\", \"sqlmodel>=1\"]\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(InventoryError, "sqlmodel"):
                inspect_inventories(root)


if __name__ == "__main__":
    unittest.main()
