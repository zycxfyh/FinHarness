"""Structural contract test: verify test runner wiring in Taskfile and pytest manifest.

Does NOT run the test suite — validates structure only.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TASKFILE = ROOT / "Taskfile.yml"
MANIFEST = ROOT / "tests" / "pytest-only.txt"
PYTEST_RUNNER = ROOT / "scripts" / "run_pytest_manifest.py"
MARKER = "# finharness-test-runner: pytest"

# ── helpers ──────────────────────────────────────────────────────────────────


def _tasks() -> dict:
    data = yaml.safe_load(TASKFILE.read_text(encoding="utf-8")) or {}
    return data.get("tasks") or {}


def _task_names() -> set[str]:
    return set(_tasks().keys())


def _task_cmds(name: str) -> list:
    """Return the cmds list for a task (empty list if absent)."""
    return list(_tasks().get(name, {}).get("cmds") or [])


def _refs_from_cmds(cmds: list) -> set[str]:
    """Extract bare task references from a task's cmds (strings and dicts)."""
    refs: set[str] = set()
    for item in cmds:
        if isinstance(item, dict) and "task" in item:
            refs.add(item["task"])
    return refs


def _manifest_entries() -> list[str]:
    raw = MANIFEST.read_text(encoding="utf-8")
    lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def _files_with_marker() -> set[str]:
    found: set[str] = set()
    for py_file in sorted((ROOT / "tests").glob("*.py")):
        first = py_file.read_text(encoding="utf-8").split("\n")[0].strip()
        if MARKER in first:
            found.add(str(py_file.relative_to(ROOT)))
    return found


# ── test class ────────────────────────────────────────────────────────────────


class TestRunnerContractTest(unittest.TestCase):
    """Verify structural wiring of test runners, manifest, and gate tasks."""

    # ── Taskfile task presence ─────────────────────────────────────────────

    def test_required_tasks_exist(self) -> None:
        names = _task_names()
        for required in ("test:compile", "test:unittest", "test:pytest", "test:all", "test"):
            with self.subTest(task=required):
                self.assertIn(required, names, f"Task '{required}' missing from Taskfile")

    def test_check_fast_exists(self) -> None:
        self.assertIn("check:fast", _task_names())

    def test_pytest_runner_reports_slowest_tests(self) -> None:
        runner = PYTEST_RUNNER.read_text(encoding="utf-8")
        self.assertIn('"--durations=20"', runner)
        self.assertIn('"--durations-min=0.05"', runner)

    # ── Delegation / wiring ────────────────────────────────────────────────

    def test_task_test_delegates_to_test_all(self) -> None:
        cmds = _task_cmds("test")
        refs = _refs_from_cmds(cmds)
        self.assertIn(
            "test:all",
            refs,
            "`task test` must delegate to `task: test:all`",
        )

    def test_test_all_includes_all_three_runners(self) -> None:
        refs = _refs_from_cmds(_task_cmds("test:all"))
        for runner in ("test:compile", "test:unittest", "test:pytest"):
            with self.subTest(task_ref=runner):
                self.assertIn(
                    runner,
                    refs,
                    f"`test:all` must include `task: {runner}`",
                )

    def test_check_fast_consumes_test_all(self) -> None:
        refs = _refs_from_cmds(_task_cmds("check:fast"))
        self.assertIn(
            "test:all",
            refs,
            "`check:fast` must consume `task: test:all` (not just old `task: test`)",
        )

    # ── Manifest shape ─────────────────────────────────────────────────────

    def test_manifest_exists_and_is_non_empty(self) -> None:
        self.assertTrue(MANIFEST.is_file(), "tests/pytest-only.txt not found")
        entries = _manifest_entries()
        self.assertTrue(entries, "tests/pytest-only.txt is empty — fail closed")

    def test_manifest_has_no_duplicates(self) -> None:
        entries = _manifest_entries()
        self.assertEqual(
            len(entries),
            len(set(entries)),
            f"Duplicate entries in pytest-only manifest: {entries}",
        )

    def test_manifest_all_files_exist(self) -> None:
        for entry in _manifest_entries():
            with self.subTest(entry=entry):
                path = ROOT / entry
                self.assertTrue(path.is_file(), f"Manifest entry does not exist: {entry}")
                # Security: all entries under tests/
                try:
                    path.resolve().relative_to((ROOT / "tests").resolve())
                except ValueError:
                    self.fail(f"Manifest entry outside tests/: {entry}")

    # ── Marker ↔ manifest consistency ──────────────────────────────────────

    def test_all_marker_files_appear_in_manifest(self) -> None:
        marker_files = _files_with_marker()
        manifest = set(_manifest_entries())
        for f in marker_files:
            with self.subTest(file=f):
                self.assertIn(
                    f,
                    manifest,
                    f"File with '{MARKER}' marker must appear in pytest-only manifest: {f}",
                )

    def test_all_manifest_files_have_marker(self) -> None:
        marker_files = _files_with_marker()
        for entry in _manifest_entries():
            with self.subTest(entry=entry):
                self.assertIn(
                    entry,
                    marker_files,
                    f"Manifest entry must contain '{MARKER}' marker: {entry}",
                )

    # ── Known file presence/absence ────────────────────────────────────────

    def test_known_pytest_files_in_manifest(self) -> None:
        manifest = set(_manifest_entries())
        for required in (
            "tests/test_agent_work_loop_models.py",
            "tests/test_agent_cognition_flow.py",
            "tests/test_capital_truth_contract.py",
            "tests/test_decision_ontology.py",
        ):
            with self.subTest(file=required):
                self.assertIn(required, manifest)

    def test_unittest_sentinel_not_in_manifest(self) -> None:
        manifest = set(_manifest_entries())
        self.assertNotIn("tests/test_unittest_runner_sentinel.py", manifest)

    def test_pytest_sentinel_in_manifest(self) -> None:
        manifest = set(_manifest_entries())
        self.assertIn("tests/test_pytest_runner_sentinel.py", manifest)
