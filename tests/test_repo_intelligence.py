from __future__ import annotations

import unittest

from finharness.repo_intelligence import (
    build_blast_radius,
    build_file_inventory,
    build_import_graph,
    build_test_map,
    classify_security_surface,
    infer_required_checks,
    parse_taskfile,
)
from finharness.repo_intelligence_graph import run_repo_intelligence_graph


class RepoIntelligenceTest(unittest.TestCase):
    def test_import_graph_maps_core_modules(self) -> None:
        graph = build_import_graph()
        node_paths = {node["path"] for node in graph["nodes"]}
        self.assertIn("src/finharness/ten_layer_graph.py", node_paths)
        self.assertIn("src/finharness/risk_gate/__init__.py", node_paths)
        self.assertTrue(
            any(edge["source"] == "src/finharness/ten_layer_graph.py" for edge in graph["edges"])
        )

    def test_inventory_excludes_secrets_and_runtime_receipts(self) -> None:
        inventory = build_file_inventory()
        paths = {item["path"] for item in inventory}
        self.assertNotIn(".env.alpaca", paths)
        self.assertFalse(any(path.startswith("data/receipts/") for path in paths))

    def test_taskfile_parser_finds_core_tasks(self) -> None:
        task_graph = parse_taskfile()
        names = {task["name"] for task in task_graph["tasks"]}
        self.assertIn("check", names)
        self.assertIn("ten-layer:graph", names)
        self.assertIn("hardening:gate", names)

    def test_blast_radius_recommends_risk_checks(self) -> None:
        graph = build_import_graph()
        tests = build_test_map()
        blast = build_blast_radius(["src/finharness/risk_gate/__init__.py"], graph, tests)
        self.assertIn("task eval:redteam-boundary", blast["required_checks"])
        self.assertIn("uv run python -m unittest tests/test_risk_gate.py", blast["required_checks"])

    def test_execution_boundary_requires_human_review(self) -> None:
        surface = classify_security_surface(["src/finharness/execution/__init__.py"])
        self.assertTrue(surface["requires_human_review"])
        self.assertFalse(surface["execution_allowed"])

    def test_infer_required_checks_for_research_asset_change(self) -> None:
        checks = infer_required_checks(["data/research/strategy-specs/trend_following_v0.json"])
        self.assertIn("uv run python -m unittest tests/test_research_assets.py", checks)
        self.assertIn("task hardening:gate", checks)

    def test_repo_intelligence_graph_outputs_final_decision_context(self) -> None:
        result = run_repo_intelligence_graph(
            changed_files=["src/finharness/execution/__init__.py"]
        )
        final = result["final"]
        self.assertEqual(final["source"]["graph"], "repo_intelligence_graph")
        self.assertFalse(final["execution_allowed"])
        self.assertTrue(final["security_surface"]["requires_human_review"])
        self.assertIn("outputs", final)


if __name__ == "__main__":
    unittest.main()
