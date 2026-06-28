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
ALLOWED_STATUS = {"current", "thin", "planned", "archived"}


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
        self.assertEqual(catalog["schema"], "finharness.system_catalog.v1")
        self.assertEqual(catalog["status"], "current")
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
