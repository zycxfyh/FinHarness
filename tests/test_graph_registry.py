"""Graph registry (R1) guardrails — keep the audit-as-artifact honest and discoverable.

These tests enforce that the registry stays a faithful, self-checking view of the Graph
Rationalization Audit: ids unique, fields in their closed sets, module paths real, task
consumers actually in the Taskfile, retired assets carry no active task, and the pilot
support graphs are not quietly relabelled ``keep``. A coverage test forces every source
graph module to be registered, so a new graph cannot slip in unclassified.
"""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from tests._graph_registry import (
    CONSUMER_CLASSES,
    GRAPH_NEEDED_REASONS,
    GRAPHS,
    STATUSES,
)

_ROOT = Path(__file__).resolve().parents[1]
_SRC_GRAPH_DIR = _ROOT / "src" / "finharness"


def _taskfile_tasks() -> set[str]:
    data = yaml.safe_load((_ROOT / "Taskfile.yml").read_text(encoding="utf-8")) or {}
    return set((data.get("tasks") or {}).keys())


class GraphRegistryTest(unittest.TestCase):
    def test_ids_unique(self) -> None:
        ids = [g.id for g in GRAPHS]
        self.assertEqual(len(ids), len(set(ids)), "graph asset ids must be unique")

    def test_enums_are_closed_sets(self) -> None:
        for g in GRAPHS:
            with self.subTest(graph=g.id):
                self.assertIn(g.consumer_class, CONSUMER_CLASSES, f"{g.id}: consumer_class")
                self.assertIn(g.graph_needed_reason, GRAPH_NEEDED_REASONS, f"{g.id}: reason")
                self.assertIn(g.status, STATUSES, f"{g.id}: status")
                for field in ("id", "owner", "review_due", "evidence"):
                    self.assertTrue(getattr(g, field).strip(), f"{g.id}: {field} required")

    def test_module_paths_exist(self) -> None:
        for g in GRAPHS:
            with self.subTest(graph=g.id):
                if g.consumer_class == "historical":
                    # Retired assets may have no module file (deleted). If a path is given
                    # (e.g. an archive dir), it must still exist.
                    if g.module is not None:
                        self.assertTrue((_ROOT / g.module).exists(), f"{g.id}: {g.module}")
                    continue
                self.assertIsNotNone(g.module, f"{g.id}: active asset needs a module path")
                assert g.module is not None  # for type-checkers
                self.assertTrue((_ROOT / g.module).exists(), f"{g.id}: missing {g.module}")

    def test_active_tasks_exist_in_taskfile(self) -> None:
        tasks = _taskfile_tasks()
        for g in GRAPHS:
            if g.task:
                with self.subTest(graph=g.id):
                    self.assertIn(g.task, tasks, f"{g.id}: task '{g.task}' not in Taskfile.yml")

    def test_delete_candidates_have_no_task_consumer(self) -> None:
        for g in GRAPHS:
            if g.status == "delete_candidate":
                with self.subTest(graph=g.id):
                    self.assertIsNone(
                        g.task, f"{g.id}: delete_candidate must have no active task consumer"
                    )

    def test_retired_assets_carry_no_active_task(self) -> None:
        for g in GRAPHS:
            if g.consumer_class == "historical" or g.status == "archived":
                with self.subTest(graph=g.id):
                    self.assertIsNone(g.task, f"{g.id}: archived/historical must have no task")

    def test_pilot_support_graphs_stay_downgrade_candidates(self) -> None:
        # Guard the gate's explicit concern: these must NOT be silently relabelled `keep`.
        expected = {"repo_intelligence", "quality_governance", "release_preflight"}
        by_id = {g.id: g for g in GRAPHS}
        for graph_id in expected:
            with self.subTest(graph=graph_id):
                self.assertIn(graph_id, by_id, f"{graph_id} missing from registry")
                self.assertEqual(
                    by_id[graph_id].status,
                    "downgrade_candidate",
                    f"{graph_id} must remain downgrade_candidate (registry is not a "
                    "promotion/deletion authorization)",
                )

    def test_registry_covers_every_source_graph_module(self) -> None:
        # Forcing function for audit-completeness: every src graph module must be registered,
        # so a new graph cannot enter the repo unclassified.
        registered = {g.module for g in GRAPHS if g.module}
        on_disk = {
            str(path.relative_to(_ROOT).as_posix())
            for path in _SRC_GRAPH_DIR.glob("*_graph.py")
        }
        missing = on_disk - registered
        self.assertEqual(
            missing, set(), f"source graph modules missing from the registry: {sorted(missing)}"
        )


if __name__ == "__main__":
    unittest.main()
