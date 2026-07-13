from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "docs" / "architecture" / "system-catalog.yml"
REQUIRED_SYSTEM_FIELDS = {
    "id",
    "name",
    "status",
    "summary",
    "docs",
    "runtime_roots",
    "mature_posture",
    "checks",
    "upgrade_trigger",
}
ALLOWED_STATUS = {
    "canonical",
    "current",
    "thin",
    "scaffolded",
    "legacy",
    "planned",
    "archived",
}


def _catalog() -> dict:
    return yaml.safe_load(CATALOG.read_text(encoding="utf-8"))


def _task_names() -> set[str]:
    data = yaml.safe_load((ROOT / "Taskfile.yml").read_text(encoding="utf-8")) or {}
    return set((data.get("tasks") or {}).keys())


def _unittest_target_path(target: str) -> Path | None:
    if target.startswith("tests.") and "/" not in target:
        return ROOT / f"{target.replace('.', '/')}.py"
    if target.startswith("tests/") and target.endswith(".py"):
        return ROOT / target
    return None


class SystemCatalogTest(unittest.TestCase):
    def test_catalog_shape_is_complete(self) -> None:
        catalog = _catalog()
        self.assertEqual(catalog["schema"], "finharness.system_catalog.v3")
        self.assertEqual(catalog["status"], "current")
        self.assertEqual(set(catalog["allowed_statuses"]), ALLOWED_STATUS)
        self.assertEqual(
            catalog["fact_ownership"],
            {
                "system_ownership_and_lifecycle": "docs/architecture/system-catalog.yml",
                "verified_engineering_debt": "docs/governance/debt-register.json",
                "implementation_sequence": "docs/architecture/finharness-evolution-roadmap.md",
            },
        )
        self.assertEqual(
            catalog["documentation"]["update_command"],
            "task docs:generate-current-views",
        )
        self.assertGreaterEqual(len(catalog["systems"]), 10)
        ids = [system["id"] for system in catalog["systems"]]
        self.assertEqual(len(ids), len(set(ids)))
        for system in catalog["systems"]:
            with self.subTest(system=system.get("id")):
                self.assertEqual(set(system), REQUIRED_SYSTEM_FIELDS)
                self.assertIn(system["status"], ALLOWED_STATUS)
                for field in ("id", "name", "summary", "mature_posture", "upgrade_trigger"):
                    self.assertTrue(str(system[field]).strip())
                self.assertTrue(system["docs"])
                self.assertTrue(system["runtime_roots"])
                self.assertTrue(system["checks"])

    def test_required_architecture_statuses(self) -> None:
        systems = {system["id"]: system for system in _catalog()["systems"]}
        expected = {
            "execution_kernel": "canonical",
            "capital_action_intent": "legacy",
            "paper_validation_runtime": "legacy",
            "external_data_mature_wheels": "thin",
            "agent_cognition_runtime": "current",
            "archived_live_trading_legacy": "archived",
        }
        self.assertTrue(set(expected).issubset(systems))
        for system_id, status in expected.items():
            with self.subTest(system=system_id):
                self.assertEqual(status, systems[system_id]["status"])

    def test_high_risk_statuses_match_current_docs(self) -> None:
        system_map = (ROOT / "docs" / "architecture" / "system-map.md").read_text(encoding="utf-8")
        module_map = (ROOT / "docs" / "architecture" / "module-map.md").read_text(encoding="utf-8")
        capital_layers = (ROOT / "docs" / "architecture" / "capital-os-layering.md").read_text(
            encoding="utf-8"
        )

        required_system_map_claims = (
            "Capital Action Intent (legacy",
            "Paper Validation Runtime (legacy",
            "Execution Kernel (canonical",
            "Agent Cognition Runtime / Agent Operating Cycle v0.1 (current AUT2)",
        )
        required_module_rows = (
            "| Capital Action Intent | `legacy` |",
            "| Paper Validation Runtime | `legacy` |",
            "| Execution Kernel | `canonical` |",
            "| Agent Cognition Runtime / Work Orchestrator | `current` |",
        )
        for claim in required_system_map_claims:
            with self.subTest(system_map_claim=claim):
                self.assertIn(claim, system_map)
        for row in required_module_rows:
            with self.subTest(module_map_row=row):
                self.assertIn(row, module_map)
        self.assertIn("system lifecycle/status", capital_layers)
        self.assertIn("Agent Operating Cycle v0.1 / AUT2 foundation (15/15)", capital_layers)

    def test_catalog_paths_exist(self) -> None:
        catalog = _catalog()
        missing: list[str] = []
        for system in catalog["systems"]:
            for path_text in [*system["docs"], *system["runtime_roots"]]:
                path = ROOT / path_text.rstrip("/")
                if not path.exists():
                    missing.append(f"{system['id']} references missing path {path_text}")
        self.assertEqual([], missing)

    def test_task_checks_reference_live_tasks(self) -> None:
        tasks = _task_names()
        catalog = _catalog()
        missing: list[str] = []
        for system in catalog["systems"]:
            for check in system["checks"]:
                if not check.startswith("task "):
                    continue
                task_name = check.split()[1]
                if task_name not in tasks:
                    missing.append(f"{system['id']} references missing task {task_name}")
        self.assertEqual([], missing)

    def test_unittest_checks_reference_existing_tests(self) -> None:
        catalog = _catalog()
        missing: list[str] = []
        prefix = "uv run python -m unittest "
        for system in catalog["systems"]:
            for check in system["checks"]:
                if not check.startswith(prefix):
                    continue
                for target in check.removeprefix(prefix).split():
                    path = _unittest_target_path(target)
                    if path is not None and not path.exists():
                        missing.append(
                            f"{system['id']} references missing unittest target {target}"
                        )
        self.assertEqual([], missing)


if __name__ == "__main__":
    unittest.main()
