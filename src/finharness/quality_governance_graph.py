"""LangGraph workflow for FinHarness quality governance.

The graph collects quality evidence and makes a release-style decision. It does
not replace the underlying tools; Taskfile, unit tests, scanners, and evals stay
the authoritative executors.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from finharness.repo_intelligence import ROOT
from finharness.repo_intelligence_graph import run_repo_intelligence_graph

WORKFLOW_VERSION = "langgraph_quality_governance_v1"

DEFAULT_CHECKS = [
    {"name": "task check", "command": ["task", "check"], "required": True},
    {
        "name": "task hardening:gate",
        "command": ["task", "hardening:gate"],
        "required": True,
    },
    {
        "name": "task eval:redteam-boundary",
        "command": ["task", "eval:redteam-boundary"],
        "required": True,
    },
]


class QualityGovernanceGraphState(TypedDict, total=False):
    root: str
    run_checks: bool
    checks: list[dict[str, Any]]
    source: dict[str, Any]
    repo_intelligence: dict[str, Any]
    check_results: list[dict[str, Any]]
    security_gate: dict[str, Any]
    redteam_gate: dict[str, Any]
    release_decision: dict[str, Any]
    receipt_ref: str
    final: dict[str, Any]


def _root(state: QualityGovernanceGraphState) -> Path:
    return Path(state.get("root") or ROOT)


def source_node(state: QualityGovernanceGraphState) -> QualityGovernanceGraphState:
    return {
        "source": {
            "workflow": WORKFLOW_VERSION,
            "graph": "quality_governance_graph",
            "execution_allowed": False,
            "authority_boundary": (
                "This graph gates engineering quality; it does not approve live trading."
            ),
        }
    }


def repo_intelligence_node(
    state: QualityGovernanceGraphState,
) -> QualityGovernanceGraphState:
    result = run_repo_intelligence_graph(root=str(_root(state)))
    return {"repo_intelligence": result["final"]}


def _run_command(command: list[str], *, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        text=True,
        capture_output=True,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout_tail": completed.stdout.splitlines()[-20:],
        "stderr_tail": completed.stderr.splitlines()[-20:],
    }


def checks_node(state: QualityGovernanceGraphState) -> QualityGovernanceGraphState:
    configured = state.get("checks") or DEFAULT_CHECKS
    results: list[dict[str, Any]] = []
    if state.get("run_checks", False):
        for check in configured:
            run = _run_command(list(check["command"]), cwd=_root(state))
            results.append(
                {
                    "name": check["name"],
                    "required": bool(check.get("required", True)),
                    "status": "passed" if run["returncode"] == 0 else "failed",
                    "returncode": run["returncode"],
                    "command": run["command"],
                    "stdout_tail": run["stdout_tail"],
                    "stderr_tail": run["stderr_tail"],
                }
            )
    else:
        for check in configured:
            results.append(
                {
                    "name": check["name"],
                    "required": bool(check.get("required", True)),
                    "status": check.get("status", "not_run"),
                    "returncode": check.get("returncode"),
                    "command": check.get("command", []),
                }
            )
    return {"check_results": results}


def security_gate_node(state: QualityGovernanceGraphState) -> QualityGovernanceGraphState:
    check_results = state["check_results"]
    hardening = next(
        (item for item in check_results if item["name"] == "task hardening:gate"),
        None,
    )
    security_ok = bool(hardening and hardening["status"] == "passed")
    return {
        "security_gate": {
            "ok": security_ok,
            "required": True,
            "evidence": hardening["name"] if hardening else "missing hardening gate",
        }
    }


def redteam_gate_node(state: QualityGovernanceGraphState) -> QualityGovernanceGraphState:
    check_results = state["check_results"]
    redteam = next(
        (item for item in check_results if item["name"] == "task eval:redteam-boundary"),
        None,
    )
    redteam_ok = bool(redteam and redteam["status"] == "passed")
    return {
        "redteam_gate": {
            "ok": redteam_ok,
            "required": True,
            "evidence": redteam["name"] if redteam else "missing redteam eval",
        }
    }


def decision_node(state: QualityGovernanceGraphState) -> QualityGovernanceGraphState:
    failed_required = [
        item["name"]
        for item in state["check_results"]
        if item.get("required", True) and item["status"] != "passed"
    ]
    human_review = state["repo_intelligence"]["security_surface"][
        "requires_human_review"
    ]
    release_blocked = bool(failed_required)
    decision = "blocked" if release_blocked else "human_review" if human_review else "passed"
    return {
        "release_decision": {
            "decision": decision,
            "release_blocked": release_blocked,
            "failed_required_checks": failed_required,
            "requires_human_review": human_review,
            "execution_allowed": False,
        }
    }


def receipt_node(state: QualityGovernanceGraphState) -> QualityGovernanceGraphState:
    root = _root(state)
    receipt = {
        "workflow": WORKFLOW_VERSION,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": state["source"],
        "repo_intelligence": {
            "inventory_summary": state["repo_intelligence"]["inventory_summary"],
            "blast_radius": state["repo_intelligence"]["blast_radius"],
            "security_surface": state["repo_intelligence"]["security_surface"],
        },
        "check_results": state["check_results"],
        "security_gate": state["security_gate"],
        "redteam_gate": state["redteam_gate"],
        "release_decision": state["release_decision"],
    }
    path = root / "data" / "receipts" / "quality-governance" / "latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"receipt_ref": str(path), "final": {**receipt, "receipt_ref": str(path)}}


def build_quality_governance_graph():
    graph = StateGraph(QualityGovernanceGraphState)
    graph.add_node("source", source_node)
    graph.add_node("repo_intelligence", repo_intelligence_node)
    graph.add_node("checks", checks_node)
    graph.add_node("security_gate", security_gate_node)
    graph.add_node("redteam_gate", redteam_gate_node)
    graph.add_node("decision", decision_node)
    graph.add_node("receipt", receipt_node)
    graph.add_edge(START, "source")
    graph.add_edge("source", "repo_intelligence")
    graph.add_edge("repo_intelligence", "checks")
    graph.add_edge("checks", "security_gate")
    graph.add_edge("security_gate", "redteam_gate")
    graph.add_edge("redteam_gate", "decision")
    graph.add_edge("decision", "receipt")
    graph.add_edge("receipt", END)
    return graph.compile()


def run_quality_governance_graph(
    *,
    root: str | None = None,
    run_checks: bool = False,
    checks: list[dict[str, Any]] | None = None,
) -> QualityGovernanceGraphState:
    initial: QualityGovernanceGraphState = {"run_checks": run_checks}
    if root:
        initial["root"] = root
    if checks is not None:
        initial["checks"] = checks
    return build_quality_governance_graph().invoke(initial)
