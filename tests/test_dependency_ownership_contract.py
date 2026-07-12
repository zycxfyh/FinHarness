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
        """Empty paper group is intentionally empty — verifier passes with status=current."""
        from scripts.verify_debt_register import _dependency_grouping

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            m = dict(self.manifest, status="current")
            _setup_minimal_project(tmp_root, m)
            result = _dependency_grouping(tmp_root)
            self.assertTrue(result, "Empty paper group must not block closure")

    def test_security_group_empty_should_not_fail(self) -> None:
        """Empty security group is intentionally empty — verifier passes."""
        from scripts.verify_debt_register import _dependency_grouping

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            m = dict(self.manifest, status="current")
            _setup_minimal_project(tmp_root, m)
            result = _dependency_grouping(tmp_root)
            self.assertTrue(result)

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

    def test_recommended_group_must_match_declared_group(self) -> None:
        from scripts.verify_debt_register import _dependency_grouping

        modified = []
        for entry in self.manifest["entries"]:
            entry = dict(entry)
            if entry["distribution"] == "yfinance":
                entry["recommended_group"] = "research"
            modified.append(entry)
        bad = dict(self.manifest, status="current", entries=modified)

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            _setup_minimal_project(tmp_root, bad)
            self.assertFalse(_dependency_grouping(tmp_root))


def _setup_minimal_project(tmp_root: Path, manifest: dict) -> None:
    """Create minimal project files needed by the verifier."""
    # pyproject.toml
    pyproject = (tmp_root / "pyproject.toml")
    pyproject_text = """[project]
name = "finharness"
dependencies = [
    "fastapi>=0.137.1",
    "keyring>=25.7.0",
    "opentelemetry-api>=1.42.1",
    "opentelemetry-sdk>=1.42.1",
    "pandas>=2.2.0",
    "pydantic-settings>=2.14.2",
    "sqlmodel>=0.0.38",
    "structlog>=26.1.0",
    "uvicorn[standard]>=0.40.0",
    "uuid6>=2025.0.1",
]

[dependency-groups]
dev = [
    "httpx>=0.28.1",
    "mypy>=2.1.0",
    "pytest>=9.0.3",
    "ruff>=0.15.14",
]
data = [
    "beancount>=3.2.3",
    "beanquery>=0.2.0",
    "nautilus-trader>=1.227.0",
    "pandera>=0.20",
    "yfinance>=0.2.60",
]
research = [
    "backtrader>=1.9.78.123",
    "quantstats>=0.0.81",
    "riskfolio-lib>=7.2.1",
    "scipy>=1.17.1",
    "vectorbt>=1.0.0",
]
agent = [
    "langgraph>=1.2.1",
    "openai-agents>=0.6.1",
]
eval = ["deepeval>=3.7.0"]
paper = []
security = []
"""
    pyproject.write_text(pyproject_text)

    taskfile = tmp_root / "Taskfile.yml"
    taskfile.write_text(
        "tasks:\n"
        "  deps:probe-base:\n"
        "  deps:probe-data:\n"
        "  deps:probe-research:\n"
        "  deps:probe-agent:\n"
        "  deps:probe-eval:\n"
        "  deps:probe-all:\n"
    )

    scripts = tmp_root / "scripts"
    scripts.mkdir()
    (scripts / "probe_base_runtime.py").write_text("")
    (scripts / "probe_dependency_group.py").write_text("")

    workflow = tmp_root / ".github" / "workflows"
    workflow.mkdir(parents=True)
    (workflow / "dependency-profiles.yml").write_text(
        "profile: [base, data, research, agent, eval]\n"
    )

    # Manifest
    manifest_dir = tmp_root / "docs" / "governance"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (manifest_dir / "dependency-consumers.json").write_text(json.dumps(manifest))


if __name__ == "__main__":
    unittest.main()
