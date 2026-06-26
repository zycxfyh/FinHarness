"""Linear pipeline for local FinHarness repository intelligence.

Downgraded from a LangGraph ``StateGraph`` in R2: the eight stages form a pure
linear chain with no branching, conditionals, parallelism, or cycles, so graph
orchestration added nothing here (proved by the linear-equivalence evidence,
PR #44 / ``test_repo_intelligence_downgrade_evidence``). The public API
``run_repo_intelligence_graph`` keeps its name, signature, and return shape so
consumers and the output contract are unchanged.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from finharness.repo_intelligence import (
    ROOT,
    build_blast_radius,
    build_file_inventory,
    build_import_graph,
    build_test_map,
    classify_security_surface,
    git_changed_files,
    parse_taskfile,
    render_mermaid,
    write_repo_intelligence_outputs,
)

# Retained verbatim for output-contract stability across the R2 downgrade: the
# receipt/report carries this string and consumers read it. Renaming would change the
# output contract and is deliberately out of scope here.
WORKFLOW_VERSION = "langgraph_repo_intelligence_v1"


class RepoIntelligenceGraphState(TypedDict, total=False):
    root: str
    changed_files: list[str]
    source: dict[str, Any]
    file_inventory: list[dict[str, Any]]
    import_graph: dict[str, Any]
    task_graph: dict[str, Any]
    test_map: dict[str, Any]
    blast_radius: dict[str, Any]
    security_surface: dict[str, Any]
    mermaid: str
    outputs: dict[str, str]
    final: dict[str, Any]


def _root(state: RepoIntelligenceGraphState) -> Path:
    return Path(state.get("root") or ROOT)


def source_node(state: RepoIntelligenceGraphState) -> RepoIntelligenceGraphState:
    return {
        "source": {
            "workflow": WORKFLOW_VERSION,
            "graph": "repo_intelligence_graph",
            "execution_allowed": False,
            "authority_boundary": (
                "This graph inspects repository structure and recommends checks; "
                "it does not authorize trading or release."
            ),
        }
    }


def inventory_node(state: RepoIntelligenceGraphState) -> RepoIntelligenceGraphState:
    return {"file_inventory": build_file_inventory(_root(state))}


def import_graph_node(state: RepoIntelligenceGraphState) -> RepoIntelligenceGraphState:
    return {"import_graph": build_import_graph(_root(state))}


def task_graph_node(state: RepoIntelligenceGraphState) -> RepoIntelligenceGraphState:
    return {"task_graph": parse_taskfile(_root(state))}


def test_map_node(state: RepoIntelligenceGraphState) -> RepoIntelligenceGraphState:
    return {"test_map": build_test_map(_root(state))}


def blast_radius_node(state: RepoIntelligenceGraphState) -> RepoIntelligenceGraphState:
    changed_files = state.get("changed_files") or git_changed_files(_root(state))
    return {
        "changed_files": changed_files,
        "blast_radius": build_blast_radius(
            changed_files,
            state["import_graph"],
            state["test_map"],
        ),
    }


def security_surface_node(state: RepoIntelligenceGraphState) -> RepoIntelligenceGraphState:
    return {
        "security_surface": classify_security_surface(state.get("changed_files") or []),
        "mermaid": render_mermaid(state["import_graph"]),
    }


def output_node(state: RepoIntelligenceGraphState) -> RepoIntelligenceGraphState:
    inventory = state["file_inventory"]
    by_role: dict[str, int] = {}
    total_lines = 0
    for item in inventory:
        role = str(item["role"])
        by_role[role] = by_role.get(role, 0) + 1
        total_lines += int(item["line_count"])
    final = {
        "workflow": WORKFLOW_VERSION,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": state["source"],
        "inventory_summary": {
            "file_count": len(inventory),
            "total_lines": total_lines,
            "by_role": dict(sorted(by_role.items())),
        },
        "import_graph_summary": {
            "nodes": len(state["import_graph"]["nodes"]),
            "edges": len(state["import_graph"]["edges"]),
        },
        "task_count": state["task_graph"]["task_count"],
        "test_count": state["test_map"]["test_count"],
        "blast_radius": state["blast_radius"],
        "security_surface": state["security_surface"],
        "mermaid": state["mermaid"],
        "execution_allowed": False,
    }
    outputs = write_repo_intelligence_outputs(
        {
            **final,
            "file_inventory": state["file_inventory"],
            "import_graph": state["import_graph"],
            "task_graph": state["task_graph"],
            "test_map": state["test_map"],
        },
        root=_root(state),
    )
    return {"outputs": outputs, "final": {**final, "outputs": outputs}}


# The stages in execution order. Each node returns a partial state update that is
# merged last-writer-wins — exactly what LangGraph did for this plain TypedDict state.
_PIPELINE = (
    source_node,
    inventory_node,
    import_graph_node,
    task_graph_node,
    test_map_node,
    blast_radius_node,
    security_surface_node,
    output_node,
)


def run_repo_intelligence_graph(
    *,
    root: str | None = None,
    changed_files: list[str] | None = None,
) -> RepoIntelligenceGraphState:
    state: RepoIntelligenceGraphState = {}
    if root:
        state["root"] = root
    if changed_files is not None:
        state["changed_files"] = changed_files
    for stage in _PIPELINE:
        state.update(stage(state))
    return state
