from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "architecture" / "support-surface-registry.yml"

REQUIRED_FIELDS = {
    "id",
    "type",
    "status",
    "owner",
    "source_of_truth",
    "depends_on",
    "review_due",
    "staleness_policy",
    "machine_checked",
}

REQUIRED_SURFACE_IDS = {
    "product-north-star",
    "capital-os-layering",
    "system-map",
    "module-map",
    "interface-reference",
    "system-catalog",
    "support-surface-registry",
    "removal-ledger",
    "agent-runtime-reference",
    "receipt-reference",
    "policy-registry",
    "graph-registry",
}

CURRENT_FACT_PATHS = {
    "docs/product-north-star.md",
    "docs/architecture/capital-os-layering.md",
    "docs/architecture/system-map.md",
    "docs/architecture/module-map.md",
    "docs/reference/interfaces.md",
    "docs/architecture/system-catalog.yml",
}


def _registry() -> dict:
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


def _as_path(path_text: str) -> Path:
    return ROOT / path_text.rstrip("/")


class SupportSurfaceRegistryTest(unittest.TestCase):
    def test_registry_shape_is_complete(self) -> None:
        registry = _registry()
        self.assertEqual(registry["schema"], "finharness.support_surface_registry.v1")
        self.assertEqual(registry["status"], "current")
        self.assertGreaterEqual(len(registry["surfaces"]), len(REQUIRED_SURFACE_IDS))
        allowed_statuses = set(registry["allowed_statuses"])
        ids = [surface["id"] for surface in registry["surfaces"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(REQUIRED_SURFACE_IDS.issubset(ids))
        for surface in registry["surfaces"]:
            with self.subTest(surface=surface.get("id")):
                self.assertEqual(set(surface), REQUIRED_FIELDS)
                self.assertIn(surface["status"], allowed_statuses)
                self.assertTrue(str(surface["owner"]).strip())
                self.assertTrue(str(surface["type"]).strip())
                self.assertTrue(str(surface["staleness_policy"]).strip())
                self.assertIsInstance(surface["machine_checked"], bool)

    def test_registered_paths_exist(self) -> None:
        missing: list[str] = []
        for surface in _registry()["surfaces"]:
            paths = [surface["source_of_truth"], *surface["depends_on"]]
            for path_text in paths:
                if not _as_path(path_text).exists():
                    missing.append(f"{surface['id']} references missing path {path_text}")
        self.assertEqual([], missing)

    def test_current_fact_docs_are_registered(self) -> None:
        registered = {surface["source_of_truth"] for surface in _registry()["surfaces"]}
        self.assertTrue(CURRENT_FACT_PATHS.issubset(registered))

    def test_active_surfaces_have_future_review_due_dates(self) -> None:
        today = date(2026, 7, 2)
        overdue: list[str] = []
        active_statuses = {"current", "reference", "planned", "downgrade_candidate"}
        for surface in _registry()["surfaces"]:
            if surface["status"] not in active_statuses:
                continue
            due = date.fromisoformat(surface["review_due"])
            if due < today:
                overdue.append(f"{surface['id']} review_due is past: {surface['review_due']}")
        self.assertEqual([], overdue)


if __name__ == "__main__":
    unittest.main()
