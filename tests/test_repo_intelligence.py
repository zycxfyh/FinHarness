from __future__ import annotations

import unittest

from finharness.repo_intelligence import (
    affected_systems_for_files,
    build_blast_radius,
    build_file_inventory,
    build_import_graph,
    build_test_map,
    classify_security_surface,
    infer_required_checks,
    parse_taskfile,
)


class RepoIntelligenceTest(unittest.TestCase):
    def test_import_graph_maps_core_modules(self) -> None:
        graph = build_import_graph()
        node_paths = {node["path"] for node in graph["nodes"]}
        self.assertIn("src/finharness/allocation.py", node_paths)
        self.assertIn("src/finharness/exposure.py", node_paths)
        self.assertTrue(
            any(edge["source"] == "src/finharness/allocation.py" for edge in graph["edges"])
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
        self.assertIn("decisions:scan", names)
        self.assertIn("hardening:gate", names)

    def test_blast_radius_recommends_boundary_checks(self) -> None:
        graph = build_import_graph()
        tests = build_test_map()
        blast = build_blast_radius(["src/finharness/restricted_symbols.py"], graph, tests)
        self.assertIn("task eval:redteam-boundary", blast["required_checks"])
        self.assertIn(
            "uv run python -m unittest tests/test_restricted_symbols.py",
            blast["required_checks"],
        )

    def test_authorization_boundary_requires_human_review(self) -> None:
        surface = classify_security_surface(["src/finharness/authorization.py"])
        self.assertTrue(surface["requires_human_review"])
        self.assertFalse(surface["execution_allowed"])

    def test_infer_required_checks_for_research_asset_change(self) -> None:
        checks = infer_required_checks(["data/research/strategy-specs/trend_following_v0.json"])
        self.assertIn("uv run python -m unittest tests/test_research_assets.py", checks)
        self.assertIn("task hardening:gate", checks)

    def test_system_catalog_maps_changed_files_to_systems_and_checks(self) -> None:
        systems = affected_systems_for_files(["src/finharness/ips.py"])
        ids = {system["id"] for system in systems}
        self.assertIn("ips_policy", ids)

        checks = infer_required_checks(["src/finharness/ips.py"])
        self.assertIn("uv run python -m unittest tests.test_ips", checks)
        self.assertIn("task check", checks)

    def test_catalog_governance_files_are_catalog_aware(self) -> None:
        systems = affected_systems_for_files(["docs/architecture/system-catalog.yml"])
        ids = {system["id"] for system in systems}
        self.assertIn("engineering_assurance", ids)

        graph = build_import_graph()
        tests = build_test_map()
        blast = build_blast_radius(["docs/architecture/system-catalog.yml"], graph, tests)
        self.assertIn("engineering_assurance", {item["id"] for item in blast["affected_systems"]})
        self.assertIn("task docs:current-check", blast["required_checks"])



class RepoIntelligencePruneTest(unittest.TestCase):
    def _fixture(self, root) -> None:
        from pathlib import Path

        root = Path(root)
        (root / "src" / "finharness").mkdir(parents=True)
        (root / "src" / "finharness" / "mod.py").write_text("x = 1\n", encoding="utf-8")
        (root / "README.md").write_text("# hi\n", encoding="utf-8")
        # Heavy dependency and generated-data dirs that must be pruned, not walked.
        for d in (".venv", "node_modules", "vendor", ".git", "__pycache__"):
            (root / d).mkdir()
            (root / d / "junk.py").write_text("noise = 1\n", encoding="utf-8")
        for d in ("cache", "receipts", "raw"):
            (root / "data" / d).mkdir(parents=True)
            (root / "data" / d / "generated.json").write_text("{}", encoding="utf-8")

    def test_iter_repo_files_prunes_dependency_dirs(self) -> None:
        import tempfile
        from pathlib import Path

        from finharness.repo_intelligence import _iter_repo_files

        with tempfile.TemporaryDirectory() as tmp:
            self._fixture(tmp)
            names = {p.name for p in _iter_repo_files(Path(tmp))}
            self.assertIn("mod.py", names)
            self.assertIn("README.md", names)
            self.assertNotIn("junk.py", names)  # never descended into pruned dirs
            self.assertNotIn("generated.json", names)

    def test_inventory_excludes_pruned_dirs_and_is_stable(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            self._fixture(tmp)
            paths = {item["path"] for item in build_file_inventory(root=Path(tmp))}
            self.assertEqual(paths, {"src/finharness/mod.py", "README.md"})
            # no path from a pruned dependency dir leaked into the inventory
            self.assertFalse(
                any(p.split("/")[0] in {".venv", "node_modules", "vendor", ".git"} for p in paths)
            )


if __name__ == "__main__":
    unittest.main()
