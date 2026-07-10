"""AST-level transitive import boundary tests for paper validation surface.

SEC-02B: Replace string-based import checks with AST-level transitive
import graph analysis.  Must detect indirect (multi-hop) forbidden imports
that string comparison cannot catch.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PREFIXES = (
    "finharness.execution.broker",
    "finharness.execution.adapters",
    "finharness.execution.commands",
    "finharness.providers",
    "finharness.agent_runtime",
)

FORBIDDEN_EXTERNAL = (
    "httpx",
    "requests",
    "urllib",
    "socket",
    "ccxt",
    "alpaca",
)

PAPER_ROOTS = (
    "src/finharness/api/routes_paper_validation.py",
    "src/finharness/statecore/paper_accounts.py",
    "src/finharness/statecore/paper_order_tickets.py",
    "src/finharness/statecore/paper_executions.py",
)


class PaperValidationTransitiveImportBoundaryTest(unittest.TestCase):
    """Real-codebase transitive import boundary."""

    def test_no_paper_module_transitively_imports_forbidden_prefix(self) -> None:
        """No paper module directly or transitively imports forbidden modules."""
        from finharness.paper_validation_boundary_audit import (
            build_internal_import_graph,
            find_forbidden_transitive_imports,
        )

        graph = build_internal_import_graph(ROOT)
        self.assertGreater(len(graph.nodes), 0, "Import graph must not be empty")

        findings = find_forbidden_transitive_imports(
            graph,
            roots=set(PAPER_ROOTS),
            forbidden_prefixes=set(FORBIDDEN_PREFIXES),
        )
        self.assertEqual(
            findings, [],
            "Found forbidden transitive imports from paper modules:\n"
            + "\n".join(
                f"  {f.code}: {' -> '.join(f.path)}" for f in findings
            ),
        )

    def test_no_paper_module_transitively_imports_forbidden_external(self) -> None:
        """No paper module imports external network dependencies."""
        from finharness.paper_validation_boundary_audit import (
            build_internal_import_graph,
            find_forbidden_transitive_imports,
        )

        graph = build_internal_import_graph(ROOT)
        findings = find_forbidden_transitive_imports(
            graph,
            roots=set(PAPER_ROOTS),
            forbidden_prefixes=set(FORBIDDEN_EXTERNAL),
        )
        self.assertEqual(
            findings, [],
            "Found forbidden external imports from paper modules:\n"
            + "\n".join(
                f"  {f.code}: {' -> '.join(f.path)}" for f in findings
            ),
        )


class PaperValidationTransitiveNegativeFixtureTest(unittest.TestCase):
    """Negative tests: fixtures that intentionally violate the boundary."""

    def test_transitive_import_chain_is_detected(self) -> None:
        """A chain paper_root->paper_helper->execution.commands is caught."""
        from finharness.paper_validation_boundary_audit import (
            build_internal_import_graph,
            find_forbidden_transitive_imports,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            _setup_transitive_fixture(tmp_root)

            graph = build_internal_import_graph(tmp_root)
            findings = find_forbidden_transitive_imports(
                graph,
                roots={"src.paper_root"},
                forbidden_prefixes={"finharness.execution.commands"},
            )
            self.assertGreater(
                len(findings), 0,
                "Transitive import chain must be detected: "
                "paper_root -> paper_helper -> finharness.execution.commands"
            )

    def test_direct_forbidden_import_is_detected(self) -> None:
        """A direct import of a forbidden module is caught."""
        from finharness.paper_validation_boundary_audit import (
            build_internal_import_graph,
            find_forbidden_transitive_imports,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            _setup_direct_fixture(tmp_root)

            graph = build_internal_import_graph(tmp_root)
            findings = find_forbidden_transitive_imports(
                graph,
                roots={"src.paper_direct"},
                forbidden_prefixes={"finharness.execution.broker"},
            )
            self.assertEqual(len(findings), 1)
            self.assertEqual(findings[0].code, "forbidden_transitive_import")


def _setup_transitive_fixture(tmp_root: Path) -> None:
    """Create a minimal project with transitive forbidden import chain."""
    src = tmp_root / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "paper_helper.py").write_text(
        "from finharness.execution.commands import submit_order\n"
    )
    (src / "paper_root.py").write_text(
        "from src.paper_helper import submit_order\n"
    )


def _setup_direct_fixture(tmp_root: Path) -> None:
    """Create a minimal project with direct forbidden import."""
    src = tmp_root / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "paper_direct.py").write_text(
        "from finharness.execution.broker import submit_order\n"
    )


if __name__ == "__main__":
    unittest.main()
