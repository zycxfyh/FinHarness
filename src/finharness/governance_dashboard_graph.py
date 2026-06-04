"""LangGraph wrapper for the FinHarness governance dashboard."""

from __future__ import annotations

from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from finharness.governance_dashboard import (
    build_governance_dashboard,
    write_governance_dashboard_outputs,
)
from finharness.repo_intelligence import ROOT


class GovernanceDashboardGraphState(TypedDict, total=False):
    root: str
    run_checks: bool
    dashboard: dict[str, Any]
    outputs: dict[str, str]
    final: dict[str, Any]


def _root(state: GovernanceDashboardGraphState) -> Path:
    return Path(state.get("root") or ROOT)


def dashboard_node(
    state: GovernanceDashboardGraphState,
) -> GovernanceDashboardGraphState:
    dashboard = build_governance_dashboard(
        root=_root(state),
        run_checks=state.get("run_checks", False),
    )
    return {"dashboard": dashboard}


def output_node(state: GovernanceDashboardGraphState) -> GovernanceDashboardGraphState:
    outputs = write_governance_dashboard_outputs(state["dashboard"], root=_root(state))
    return {"outputs": outputs, "final": {**state["dashboard"], "outputs": outputs}}


def build_governance_dashboard_graph():
    graph = StateGraph(GovernanceDashboardGraphState)
    graph.add_node("dashboard", dashboard_node)
    graph.add_node("output", output_node)
    graph.add_edge(START, "dashboard")
    graph.add_edge("dashboard", "output")
    graph.add_edge("output", END)
    return graph.compile()


def run_governance_dashboard_graph(
    *,
    root: str | None = None,
    run_checks: bool = False,
) -> GovernanceDashboardGraphState:
    initial: GovernanceDashboardGraphState = {"run_checks": run_checks}
    if root:
        initial["root"] = root
    return build_governance_dashboard_graph().invoke(initial)
