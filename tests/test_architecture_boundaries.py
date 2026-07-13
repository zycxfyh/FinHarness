from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from finharness.architecture_boundaries import (
    audit_architecture,
    build_canonical_import_graph,
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
        self.assertTrue(audit["ok"])


if __name__ == "__main__":
    unittest.main()
