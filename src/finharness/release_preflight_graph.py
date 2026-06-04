"""Release preflight graph for FinHarness.

This graph seals the local release decision with repo intelligence and quality
governance evidence. It is designed for pre-merge and pre-release use.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from finharness.quality_governance_graph import run_quality_governance_graph
from finharness.repo_intelligence import ROOT

WORKFLOW_VERSION = "langgraph_release_preflight_v1"


class ReleasePreflightGraphState(TypedDict, total=False):
    root: str
    run_checks: bool
    source: dict[str, Any]
    quality: dict[str, Any]
    supply_chain: dict[str, Any]
    release_gate: dict[str, Any]
    receipt_ref: str
    final: dict[str, Any]


def _root(state: ReleasePreflightGraphState) -> Path:
    return Path(state.get("root") or ROOT)


def source_node(state: ReleasePreflightGraphState) -> ReleasePreflightGraphState:
    return {
        "source": {
            "workflow": WORKFLOW_VERSION,
            "graph": "release_preflight_graph",
            "execution_allowed": False,
            "authority_boundary": (
                "This graph seals engineering release evidence; it never grants "
                "autonomous live trading permission."
            ),
        }
    }


def quality_node(state: ReleasePreflightGraphState) -> ReleasePreflightGraphState:
    quality = run_quality_governance_graph(
        root=str(_root(state)),
        run_checks=state.get("run_checks", False),
    )
    return {"quality": quality["final"]}


def supply_chain_node(state: ReleasePreflightGraphState) -> ReleasePreflightGraphState:
    root = _root(state)
    workflow_paths = [
        ".github/workflows/security.yml",
        ".github/workflows/scorecard.yml",
        ".github/workflows/fuzz.yml",
    ]
    present = [path for path in workflow_paths if (root / path).exists()]
    missing = sorted(set(workflow_paths) - set(present))
    return {
        "supply_chain": {
            "dependency_graph_expected": True,
            "dependabot_config_present": (root / ".github" / "dependabot.yml").exists(),
            "scorecard_workflow_present": (
                root / ".github" / "workflows" / "scorecard.yml"
            ).exists(),
            "codeql_workflow_present": (root / ".github" / "workflows" / "security.yml").exists(),
            "fuzz_workflow_present": (root / ".github" / "workflows" / "fuzz.yml").exists(),
            "workflow_refs_present": present,
            "missing_workflow_refs": missing,
        }
    }


def release_gate_node(state: ReleasePreflightGraphState) -> ReleasePreflightGraphState:
    quality_decision = state["quality"]["release_decision"]
    supply_chain = state["supply_chain"]
    missing = []
    if quality_decision["release_blocked"]:
        missing.append("quality_governance_pass")
    if not supply_chain["dependabot_config_present"]:
        missing.append("dependabot_config")
    if not supply_chain["scorecard_workflow_present"]:
        missing.append("scorecard_workflow")
    if not supply_chain["codeql_workflow_present"]:
        missing.append("codeql_workflow")
    if not supply_chain["fuzz_workflow_present"]:
        missing.append("fuzz_workflow")
    return {
        "release_gate": {
            "release_ready": not missing,
            "release_blocked": bool(missing),
            "missing": missing,
            "requires_human_review": quality_decision["requires_human_review"],
            "execution_allowed": False,
        }
    }


def receipt_node(state: ReleasePreflightGraphState) -> ReleasePreflightGraphState:
    receipt = {
        "workflow": WORKFLOW_VERSION,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": state["source"],
        "quality": {
            "release_decision": state["quality"]["release_decision"],
            "receipt_ref": state["quality"]["receipt_ref"],
        },
        "supply_chain": state["supply_chain"],
        "release_gate": state["release_gate"],
    }
    path = _root(state) / "data" / "receipts" / "release-preflight" / "latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"receipt_ref": str(path), "final": {**receipt, "receipt_ref": str(path)}}


def build_release_preflight_graph():
    graph = StateGraph(ReleasePreflightGraphState)
    graph.add_node("source", source_node)
    graph.add_node("quality", quality_node)
    graph.add_node("supply_chain", supply_chain_node)
    graph.add_node("release_gate", release_gate_node)
    graph.add_node("receipt", receipt_node)
    graph.add_edge(START, "source")
    graph.add_edge("source", "quality")
    graph.add_edge("quality", "supply_chain")
    graph.add_edge("supply_chain", "release_gate")
    graph.add_edge("release_gate", "receipt")
    graph.add_edge("receipt", END)
    return graph.compile()


def run_release_preflight_graph(
    *,
    root: str | None = None,
    run_checks: bool = False,
) -> ReleasePreflightGraphState:
    initial: ReleasePreflightGraphState = {"run_checks": run_checks}
    if root:
        initial["root"] = root
    return build_release_preflight_graph().invoke(initial)
