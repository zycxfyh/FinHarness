"""LangGraph workflow for local FinHarness repository intelligence."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

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


def build_repo_intelligence_graph():
    graph = StateGraph(RepoIntelligenceGraphState)
    graph.add_node("source", source_node)
    graph.add_node("inventory", inventory_node)
    graph.add_node("import_graph", import_graph_node)
    graph.add_node("task_graph", task_graph_node)
    graph.add_node("test_map", test_map_node)
    graph.add_node("blast_radius", blast_radius_node)
    graph.add_node("security_surface", security_surface_node)
    graph.add_node("output", output_node)
    graph.add_edge(START, "source")
    graph.add_edge("source", "inventory")
    graph.add_edge("inventory", "import_graph")
    graph.add_edge("import_graph", "task_graph")
    graph.add_edge("task_graph", "test_map")
    graph.add_edge("test_map", "blast_radius")
    graph.add_edge("blast_radius", "security_surface")
    graph.add_edge("security_surface", "output")
    graph.add_edge("output", END)
    return graph.compile()


def run_repo_intelligence_graph(
    *,
    root: str | None = None,
    changed_files: list[str] | None = None,
) -> RepoIntelligenceGraphState:
    initial: RepoIntelligenceGraphState = {}
    if root:
        initial["root"] = root
    if changed_files is not None:
        initial["changed_files"] = changed_files
    return build_repo_intelligence_graph().invoke(initial)
