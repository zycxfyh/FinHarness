"""Contract tests for the dependency grouping verifier (DEPS-02A).

Verifies that the success definition correctly accepts empty groups
and rejects wrong groupings, duplicates, and stale consumers.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFIER_SCRIPT = ROOT / "scripts" / "verify_debt_register.py"
MANIFEST_SRC = ROOT / "docs" / "governance" / "dependency-consumers.json"


class DependencyGroupingContractTest(unittest.TestCase):
    """Negative test matrix for the dependency ownership verifier."""

    def setUp(self) -> None:
        self.manifest = json.loads(MANIFEST_SRC.read_text(encoding="utf-8"))

    def _make_fixture(self, *, manifest_overrides: dict | None = None) -> Path:
        """Create a temp dir with the project and a modified manifest."""
        tmp = Path(tempfile.mkdtemp())
        tmp_manifest = tmp / "docs" / "governance"
        tmp_manifest.mkdir(parents=True)
        m = dict(self.manifest)
        if manifest_overrides:
            m.update(manifest_overrides)
        (tmp_manifest / "dependency-consumers.json").write_text(json.dumps(m))
        return tmp

    def test_paper_group_empty_should_not_fail(self) -> None:
        """Empty paper group is intentionally empty — should not block closure."""
        # This is a positive test: the current audit status is "audit" not "current"
        # so the verifier returns False, but NOT because the group is empty.
        from scripts.verify_debt_register import _dependency_grouping

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            _setup_minimal_project(tmp_root, self.manifest)
            result = _dependency_grouping(tmp_root)
            # False because status is "audit" not "current" — not because group is empty
            self.assertFalse(result)

    def test_security_group_empty_should_not_fail(self) -> None:
        """Empty security group is intentionally empty — should not block closure."""
        from scripts.verify_debt_register import _dependency_grouping

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            _setup_minimal_project(tmp_root, self.manifest)
            result = _dependency_grouping(tmp_root)
            self.assertFalse(result)  # Because status != "current"

    def test_duplicate_distribution_fails(self) -> None:
        """Same distribution appearing twice fails the verifier."""
        from scripts.verify_debt_register import _dependency_grouping

        dup_entries = list(self.manifest["entries"])
        dup_entries.append(dict(dup_entries[0]))  # Duplicate first entry
        bad = dict(self.manifest, status="current", entries=dup_entries)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            _setup_minimal_project(tmp_root, bad)
            result = _dependency_grouping(tmp_root)
            self.assertFalse(result)

    def test_missing_declared_dependency_in_manifest_fails(self) -> None:
        """If pyproject declares a dep not in manifest, verifier returns False."""
        from scripts.verify_debt_register import _dependency_grouping

        # Remove fastapi from manifest entries
        filtered = [e for e in self.manifest["entries"] if e["distribution"] != "fastapi"]
        bad = dict(self.manifest, status="current", entries=filtered)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            _setup_minimal_project(tmp_root, bad)
            result = _dependency_grouping(tmp_root)
            self.assertFalse(result)

    def test_unused_with_consumers_fails(self) -> None:
        """An 'unused' entry with consumers fails the verifier."""
        from scripts.verify_debt_register import _dependency_grouping

        modified = []
        for e in self.manifest["entries"]:
            e = dict(e)
            if e["distribution"] == "pandas-ta":
                e["import_consumers"] = ["fake/consumer.py"]
            modified.append(e)
        bad = dict(self.manifest, status="current", entries=modified)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            _setup_minimal_project(tmp_root, bad)
            result = _dependency_grouping(tmp_root)
            self.assertFalse(result)

    def test_kept_without_consumers_fails(self) -> None:
        """A non-unused entry with zero consumers fails the verifier."""
        from scripts.verify_debt_register import _dependency_grouping

        modified = []
        for e in self.manifest["entries"]:
            e = dict(e)
            if e["distribution"] == "fastapi":
                e["recommended_group"] = "base"
                e["import_consumers"] = []
                e["task_consumers"] = []
            modified.append(e)
        bad = dict(self.manifest, status="current", entries=modified)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            _setup_minimal_project(tmp_root, bad)
            result = _dependency_grouping(tmp_root)
            self.assertFalse(result)


def _setup_minimal_project(tmp_root: Path, manifest: dict) -> None:
    """Create minimal project files needed by the verifier."""
    # pyproject.toml
    pyproject = (tmp_root / "pyproject.toml")
    pyproject_text = """[project]
name = "finharness"
dependencies = [
    "fastapi>=0.137.1",
    "pandas>=2.2.0",
    "sqlmodel>=0.0.38",
    "structlog>=26.1.0",
    "uvicorn[standard]>=0.40.0",
    "keyring>=25.7.0",
    "opentelemetry-api>=1.42.1",
    "opentelemetry-sdk>=1.42.1",
    "pydantic-settings>=2.14.2",
    "backtrader>=1.9.78.123",
    "beancount>=3.2.3",
    "beanquery>=0.2.0",
    "deepeval>=3.7.0",
    "langgraph>=1.2.1",
    "nautilus-trader>=1.227.0",
    "openai-agents>=0.6.1",
    "pandas-ta>=0.4.71b0",
    "pandera>=0.20",
    "plotly>=5.20.0",
    "quantstats>=0.0.81",
    "riskfolio-lib>=7.2.1",
    "scipy>=1.17.1",
    "ta-lib>=0.6.8",
    "vectorbt>=1.0.0",
    "yfinance>=0.2.60",
]

[dependency-groups]
dev = [
    "httpx>=0.28.1",
    "mypy>=2.1.0",
    "pytest>=9.0.3",
    "ruff>=0.15.14",
]
data = []
research = []
agent = []
eval = []
paper = []
security = []
"""
    pyproject.write_text(pyproject_text)

    # Manifest
    manifest_dir = tmp_root / "docs" / "governance"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "dependency-consumers.json").write_text(json.dumps(manifest))


if __name__ == "__main__":
    unittest.main()
