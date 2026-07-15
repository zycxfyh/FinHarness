from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from finharness.architecture_boundaries import (
    audit_architecture,
    build_canonical_import_graph,
    load_layer_matrix,
    validate_plane_model,
)

MATRIX = """\
schema: finharness.architecture_layers.v1
source_roots: [src]
layers:
  - name: statecore
    module_globs: [pkg.statecore, pkg.statecore.*]
  - name: api_frontend
    module_globs: [pkg.api, pkg.api.*]
  - name: core
    module_globs: [pkg, pkg.*]
rules:
  - id: statecore-foundation
    source_layers: [statecore]
    forbidden_target_layers: [api_frontend]
"""


class ArchitectureBoundaryTest(unittest.TestCase):
    def _repo(self, files: dict[str, str]) -> tuple[tempfile.TemporaryDirectory, Path]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        for relative, content in files.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        (root / "matrix.yml").write_text(MATRIX, encoding="utf-8")
        return temp, root

    def test_relative_imports_resolve_to_canonical_modules(self) -> None:
        temp, root = self._repo(
            {
                "src/pkg/__init__.py": "",
                "src/pkg/a.py": "from . import b\n",
                "src/pkg/b.py": "from .sub import c\n",
                "src/pkg/sub/__init__.py": "",
                "src/pkg/sub/c.py": "VALUE = 1\n",
            }
        )
        self.addCleanup(temp.cleanup)
        _, edges = build_canonical_import_graph(root, ("src",))
        pairs = {(edge.source, edge.target) for edge in edges}
        self.assertIn(("pkg.a", "pkg.b"), pairs)
        self.assertIn(("pkg.b", "pkg.sub.c"), pairs)

    def test_same_production_gate_reports_cycle(self) -> None:
        temp, root = self._repo(
            {
                "src/pkg/__init__.py": "",
                "src/pkg/a.py": "from . import b\n",
                "src/pkg/b.py": "from . import a\n",
            }
        )
        self.addCleanup(temp.cleanup)
        audit = audit_architecture(root=root, matrix_path=root / "matrix.yml")
        self.assertFalse(audit["ok"])
        self.assertEqual(audit["cycles"], [["pkg.a", "pkg.b"]])

    def test_direct_and_transitive_forbidden_paths_are_complete(self) -> None:
        temp, root = self._repo(
            {
                "src/pkg/__init__.py": "",
                "src/pkg/statecore/__init__.py": "",
                "src/pkg/statecore/direct.py": "from pkg.api import endpoint\n",
                "src/pkg/statecore/indirect.py": "from pkg import bridge\n",
                "src/pkg/bridge.py": "from pkg.api import endpoint\n",
                "src/pkg/api/__init__.py": "",
                "src/pkg/api/endpoint.py": "VALUE = 1\n",
            }
        )
        self.addCleanup(temp.cleanup)
        audit = audit_architecture(root=root, matrix_path=root / "matrix.yml")
        paths = {(item["kind"], tuple(item["path"])) for item in audit["violations"]}
        self.assertIn(
            ("direct", ("pkg.statecore.direct", "pkg.api.endpoint")),
            paths,
        )
        self.assertIn(
            ("transitive", ("pkg.statecore.indirect", "pkg.bridge", "pkg.api.endpoint")),
            paths,
        )

    def test_current_repository_passes_the_ci_gate(self) -> None:
        audit = audit_architecture()
        self.assertEqual(audit["cycles"], [])
        self.assertEqual(audit["violations"], [])
        self.assertEqual(audit["plane_count"], 8)
        self.assertGreater(audit["plane_dependency_edges"], 0)
        self.assertTrue(audit["ok"])

    def test_canonical_plane_model_is_complete_and_horizontal_assurance_is_separate(
        self,
    ) -> None:
        matrix = load_layer_matrix()
        planes = {plane["name"]: plane for plane in matrix["plane_model"]["planes"]}
        self.assertEqual(
            set(planes),
            {
                "truth",
                "knowledge",
                "judgment",
                "control",
                "agent",
                "action-learning",
                "product",
                "assurance",
            },
        )
        self.assertEqual(
            {name: plane["depends_on"] for name, plane in planes.items()},
            {
                "truth": [],
                "knowledge": [],
                "control": ["truth"],
                "judgment": ["truth", "knowledge", "control"],
                "agent": ["truth", "knowledge", "judgment", "control"],
                "action-learning": [
                    "truth",
                    "knowledge",
                    "judgment",
                    "control",
                    "agent",
                ],
                "product": [
                    "truth",
                    "knowledge",
                    "judgment",
                    "control",
                    "agent",
                    "action-learning",
                ],
                "assurance": [],
            },
        )
        self.assertEqual(planes["assurance"]["kind"], "horizontal")
        self.assertEqual(planes["assurance"]["depends_on"], [])
        self.assertEqual(
            set(planes["assurance"]["supports"]),
            set(planes) - {"assurance"},
        )

    def test_reverse_plane_dependency_is_rejected(self) -> None:
        model = copy.deepcopy(load_layer_matrix()["plane_model"])
        planes = {plane["name"]: plane for plane in model["planes"]}
        planes["truth"]["depends_on"] = ["product"]
        with self.assertRaisesRegex(ValueError, "reverse dependency truth -> product"):
            validate_plane_model(model)

    def test_duplicate_plane_ownership_is_rejected(self) -> None:
        model = copy.deepcopy(load_layer_matrix()["plane_model"])
        planes = {plane["name"]: plane for plane in model["planes"]}
        planes["knowledge"]["owned_objects"].append("CapitalStateVersion")
        with self.assertRaisesRegex(
            ValueError,
            "owned object CapitalStateVersion has multiple planes: truth, knowledge",
        ):
            validate_plane_model(model)

    def test_plane_vocabulary_is_shared_by_current_architecture_docs(self) -> None:
        paths = (
            "docs/adr/2026-07-16-finharness-plane-model-and-dependency-direction.md",
            "docs/architecture/capital-os-layering.md",
            "docs/architecture/module-map.md",
            "docs/architecture/finharness-evolution-roadmap.md",
        )
        for relative in paths:
            with self.subTest(path=relative):
                text = (Path(__file__).resolve().parents[1] / relative).read_text(
                    encoding="utf-8"
                )
                self.assertIn("Canonical plane model", text)
                self.assertIn("Truth", text)
                self.assertIn("Knowledge", text)
                self.assertIn("Judgment", text)
                self.assertIn("Control", text)
                self.assertIn("Agent", text)
                self.assertIn("Action/Learning", text)
                self.assertIn("Product", text)
                self.assertIn("Assurance", text)


if __name__ == "__main__":
    unittest.main()
