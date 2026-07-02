from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "docs" / "governance" / "removal-ledger.yml"

REQUIRED_FIELDS = {
    "id",
    "target",
    "action",
    "reason",
    "replacement",
    "owner",
    "proposed_in_pr",
    "effective_pr",
    "status",
    "remove_from_current_nav",
    "checks_required",
}

CURRENT_DOC_PATHS = (
    ROOT / "README.md",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "tutorials" / "golden-path.md",
    ROOT / "docs" / "reference" / "README.md",
    ROOT / "docs" / "reference" / "commands.md",
    ROOT / "docs" / "reference" / "config-env.md",
    ROOT / "docs" / "reference" / "interfaces.md",
    ROOT / "docs" / "reference" / "receipts.md",
    ROOT / "docs" / "how-to" / "README.md",
    ROOT / "docs" / "architecture" / "capital-os-layering.md",
    ROOT / "docs" / "architecture" / "engineering-leverage-map.md",
    ROOT / "docs" / "architecture" / "framework-index.md",
    ROOT / "docs" / "architecture" / "system-map.md",
    ROOT / "docs" / "architecture" / "module-map.md",
    ROOT / "docs" / "architecture" / "documentation-fact-governance.md",
    ROOT / "docs" / "architecture" / "support-surface-registry.yml",
)


def _ledger() -> dict:
    return yaml.safe_load(LEDGER.read_text(encoding="utf-8"))


def _task_names() -> set[str]:
    data = yaml.safe_load((ROOT / "Taskfile.yml").read_text(encoding="utf-8")) or {}
    return set((data.get("tasks") or {}).keys())


def _path_exists_or_live_task(ref: str) -> bool:
    if ref.startswith("task "):
        return ref.removeprefix("task ") in _task_names()
    return (ROOT / ref).exists()


class RemovalLedgerTest(unittest.TestCase):
    def test_ledger_shape_is_complete(self) -> None:
        ledger = _ledger()
        self.assertEqual(ledger["schema"], "finharness.removal_ledger.v1")
        self.assertEqual(ledger["status"], "current")
        allowed_actions = set(ledger["allowed_actions"])
        allowed_statuses = set(ledger["allowed_statuses"])
        entries = ledger["entries"] or []
        ids = [entry["id"] for entry in entries]
        self.assertEqual(len(ids), len(set(ids)))
        for entry in entries:
            with self.subTest(entry=entry.get("id")):
                self.assertEqual(set(entry), REQUIRED_FIELDS)
                self.assertIn(entry["action"], allowed_actions)
                self.assertIn(entry["status"], allowed_statuses)
                self.assertTrue(str(entry["owner"]).strip())
                self.assertTrue(str(entry["reason"]).strip())
                self.assertTrue(entry["target"])
                self.assertTrue(entry["checks_required"])

    def test_done_delete_targets_are_absent(self) -> None:
        still_present: list[str] = []
        for entry in _ledger()["entries"] or []:
            if entry["action"] != "delete" or entry["status"] != "done":
                continue
            for target in entry["target"]:
                if (ROOT / target).exists():
                    still_present.append(f"{entry['id']} target still exists: {target}")
        self.assertEqual([], still_present)

    def test_replacements_exist_or_are_live_tasks(self) -> None:
        missing: list[str] = []
        for entry in _ledger()["entries"] or []:
            for replacement in entry["replacement"]:
                if replacement == "none":
                    continue
                if not _path_exists_or_live_task(replacement):
                    missing.append(f"{entry['id']} replacement missing: {replacement}")
        self.assertEqual([], missing)

    def test_current_docs_do_not_reference_done_delete_targets(self) -> None:
        violations: list[str] = []
        deleted_targets = {
            target
            for entry in _ledger()["entries"] or []
            if entry["action"] == "delete" and entry["status"] == "done"
            for target in entry["target"]
        }
        for path in CURRENT_DOC_PATHS:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            for target in deleted_targets:
                if target in text or Path(target).name in text:
                    violations.append(f"{path.relative_to(ROOT)} references deleted {target}")
        self.assertEqual([], violations)


if __name__ == "__main__":
    unittest.main()
