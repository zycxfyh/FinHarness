"""repo_intelligence linear-contract regression (post R2 downgrade).

Originally the R2 *evidence* pilot (PR #44) that proved the graph-shaped path was
reproducible by a plain linear composition. After the downgrade shipped (#46),
``run_repo_intelligence_graph`` *is* that linear composition, so this file now serves
as the contract regression: it pins the public runner to the canonical node order /
state threading and to the full output contract, guarding against a future change
that silently reorders, drops, or mis-threads a stage.

It compares the public runner against an independent reference composition of the same
node functions (kept here on purpose, not imported from the module, so the test is a
genuine independent check). Only ``generated_at`` and the per-root path prefix are
normalized away; every semantic contract field must match.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from finharness.repo_intelligence_graph import (
    blast_radius_node,
    import_graph_node,
    inventory_node,
    output_node,
    run_repo_intelligence_graph,
    security_surface_node,
    source_node,
    task_graph_node,
    test_map_node,
)

# The node functions in the exact order the compiled graph wires its edges:
# source -> inventory -> import_graph -> task_graph -> test_map -> blast_radius
# -> security_surface -> output.
_LINEAR_NODES = (
    source_node,
    inventory_node,
    import_graph_node,
    task_graph_node,
    test_map_node,
    blast_radius_node,
    security_surface_node,
    output_node,
)


def _run_linear(*, root: str, changed_files: list[str]) -> dict:
    """Plain linear composition: thread state through the nodes with dict-merge.

    This mirrors LangGraph's default channel merge for a plain ``TypedDict`` state
    (no custom reducers): each node returns a partial update that is merged last-
    writer-wins, which is exactly ``state.update(node(state))``.
    """
    state: dict = {"root": root, "changed_files": list(changed_files)}
    for node in _LINEAR_NODES:
        state.update(node(state))
    return state


def _normalize(final: dict, root: str) -> dict:
    """Drop the wall-clock field and the per-root path prefix; keep every contract field.

    The two paths run against two isolated roots (so neither run's written outputs
    pollute the other's file inventory), so the only differences are the wall-clock
    ``generated_at`` and the absolute ``outputs`` paths' root prefix. Everything else
    is a semantic field and must match.
    """
    normalized = dict(final)
    normalized.pop("generated_at", None)
    outputs = normalized.get("outputs")
    if isinstance(outputs, dict):
        normalized["outputs"] = {
            key: str(value).replace(root, "<root>") for key, value in outputs.items()
        }
    return normalized


class RepoIntelligenceDowngradeEvidenceTest(unittest.TestCase):
    def _fixture(self, root: Path) -> None:
        (root / "src" / "finharness").mkdir(parents=True)
        (root / "src" / "finharness" / "mod.py").write_text(
            "import finharness.other\nx = 1\n", encoding="utf-8"
        )
        (root / "src" / "finharness" / "other.py").write_text("y = 2\n", encoding="utf-8")
        (root / "README.md").write_text("# fixture\n", encoding="utf-8")
        (root / "tests").mkdir()
        (root / "tests" / "test_mod.py").write_text(
            "import finharness.mod\n", encoding="utf-8"
        )
        # parse_taskfile needs a Taskfile.yml to return task_count.
        (root / "Taskfile.yml").write_text(
            "tasks:\n  build:\n    desc: build it\n", encoding="utf-8"
        )

    def test_graph_output_is_linearly_reproducible(self) -> None:
        # Two isolated roots: each run writes its outputs into its own root, so neither
        # run's generated files leak into the other's file inventory.
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            root_a, root_b = Path(tmp_a), Path(tmp_b)
            self._fixture(root_a)
            self._fixture(root_b)
            changed_files = ["src/finharness/mod.py"]

            graph_final = run_repo_intelligence_graph(
                root=str(root_a), changed_files=changed_files
            )["final"]
            linear_final = _run_linear(root=str(root_b), changed_files=changed_files)["final"]

            # Sanity: the run actually produced the full contract, not an empty stub.
            self.assertEqual(graph_final["source"]["graph"], "repo_intelligence_graph")
            self.assertFalse(graph_final["execution_allowed"])
            self.assertIn("outputs", graph_final)

            # Core evidence: every semantic contract field is identical across the two
            # paths (only generated_at and the per-root path prefix are allowed to differ).
            self.assertEqual(
                _normalize(graph_final, str(root_a)),
                _normalize(linear_final, str(root_b)),
            )

    def test_each_threaded_field_survives_linear_composition(self) -> None:
        """Guards against a mis-threaded linear runner silently dropping a field."""
        with tempfile.TemporaryDirectory() as tmp_a, tempfile.TemporaryDirectory() as tmp_b:
            root_a, root_b = Path(tmp_a), Path(tmp_b)
            self._fixture(root_a)
            self._fixture(root_b)
            changed_files = ["src/finharness/mod.py"]

            graph_state = run_repo_intelligence_graph(
                root=str(root_a), changed_files=changed_files
            )
            linear_state = _run_linear(root=str(root_b), changed_files=changed_files)

            # Root-relative / root-independent fields must match field-for-field. (outputs
            # holds absolute paths and is covered, normalized, by the test above.)
            for key in (
                "source",
                "file_inventory",
                "import_graph",
                "task_graph",
                "test_map",
                "blast_radius",
                "security_surface",
                "mermaid",
            ):
                self.assertEqual(
                    graph_state[key], linear_state[key], f"field {key!r} diverged"
                )


if __name__ == "__main__":
    unittest.main()
