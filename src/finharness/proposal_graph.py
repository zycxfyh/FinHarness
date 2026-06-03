"""LangGraph workflow for seventh-layer structured proposals."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from finharness.proposal import (
    HermesProposalDraftProvider,
    ProposalCandidate,
    ProposalSourceSpec,
    build_proposal_candidates,
    build_proposal_quality,
    persist_proposal_bundle,
)
from finharness.research_assets import compact_research_asset_context
from finharness.validation import ValidationSnapshot
from finharness.validation_graph import run_validation_graph


class ProposalGraphState(TypedDict, total=False):
    universe: list[str]
    forms: list[str]
    max_records: int
    max_hypotheses: int
    symbols: list[str]
    llm_enabled: bool
    hermes_root: str
    research_asset_context: dict[str, Any]
    validation_snapshot: dict[str, Any]
    source: dict[str, Any]
    proposal_candidates: list[dict[str, Any]]
    evidence_summary: dict[str, Any]
    portfolio_role: dict[str, Any]
    invalidation_triggers: dict[str, Any]
    constraints: dict[str, Any]
    alternatives: dict[str, Any]
    risk_gate_handoff: dict[str, Any]
    quality: dict[str, Any]
    lineage: dict[str, Any]
    snapshot: dict[str, Any]
    receipt: dict[str, Any]
    consumer_handoff: dict[str, Any]
    review_hook: dict[str, Any]
    final: dict[str, Any]


def source_config_node(state: ProposalGraphState) -> ProposalGraphState:
    llm_enabled = bool(state.get("llm_enabled", False))
    source = ProposalSourceSpec(
        llm_provider="hermes-agent" if llm_enabled else None,
        llm_interface="HermesProposalDraftProvider" if llm_enabled else None,
        llm_enabled=llm_enabled,
        hermes_root=state.get("hermes_root", "/root/projects/hermes-agent"),
        config={
            "universe": state.get("universe"),
            "forms": state.get("forms", ["8-K", "10-Q", "10-K"]),
            "max_records": state.get("max_records", 30),
            "max_hypotheses": state.get("max_hypotheses", 10),
            "symbols": state.get("symbols", []),
            "research_asset_context": compact_research_asset_context(
                state.get("research_asset_context"), "L7"
            ),
        },
    )
    return {"source": source.model_dump(mode="json")}


def load_validation_snapshot_node(state: ProposalGraphState) -> ProposalGraphState:
    if "validation_snapshot" in state:
        return {"validation_snapshot": state["validation_snapshot"]}
    result = run_validation_graph(
        universe=state.get("universe"),
        forms=state.get("forms"),
        max_records=state.get("max_records", 30),
        max_hypotheses=state.get("max_hypotheses", 10),
        symbols=state.get("symbols") or None,
        llm_enabled=state.get("llm_enabled", False),
        hermes_root=state.get("hermes_root", "/root/projects/hermes-agent"),
        research_asset_context=state.get("research_asset_context"),
    )
    return {"validation_snapshot": result["snapshot"]}


def select_proposal_candidates_node(state: ProposalGraphState) -> ProposalGraphState:
    snapshot = ValidationSnapshot.model_validate(state["validation_snapshot"])
    provider = (
        HermesProposalDraftProvider(
            hermes_root=state.get("hermes_root", "/root/projects/hermes-agent")
        )
        if state.get("llm_enabled", False)
        else None
    )
    candidates = build_proposal_candidates(
        validation_snapshot=snapshot,
        draft_provider=provider,
    )
    return {
        "proposal_candidates": [
            candidate.model_dump(mode="json") for candidate in candidates
        ]
    }


def build_evidence_summary_node(state: ProposalGraphState) -> ProposalGraphState:
    return {
        "evidence_summary": {
            "status": "built",
            "candidate_count": len(state["proposal_candidates"]),
        }
    }


def assign_portfolio_role_node(state: ProposalGraphState) -> ProposalGraphState:
    missing = [
        candidate["proposal_id"]
        for candidate in state["proposal_candidates"]
        if not candidate.get("portfolio_role")
    ]
    return {"portfolio_role": {"status": "checked", "missing": missing}}


def attach_invalidation_triggers_node(state: ProposalGraphState) -> ProposalGraphState:
    missing = [
        candidate["proposal_id"]
        for candidate in state["proposal_candidates"]
        if not candidate.get("invalidation_triggers")
    ]
    return {"invalidation_triggers": {"status": "checked", "missing": missing}}


def attach_constraints_node(state: ProposalGraphState) -> ProposalGraphState:
    missing = [
        candidate["proposal_id"]
        for candidate in state["proposal_candidates"]
        if not candidate.get("constraint_notes")
    ]
    return {"constraints": {"status": "checked", "missing": missing}}


def attach_alternatives_node(state: ProposalGraphState) -> ProposalGraphState:
    missing = [
        candidate["proposal_id"]
        for candidate in state["proposal_candidates"]
        if not candidate.get("alternatives_considered") or not candidate.get("do_nothing_case")
    ]
    return {"alternatives": {"status": "checked", "missing": missing}}


def build_risk_gate_handoff_node(state: ProposalGraphState) -> ProposalGraphState:
    missing = [
        candidate["proposal_id"]
        for candidate in state["proposal_candidates"]
        if not candidate.get("risk_gate_request", {}).get("required_checks")
    ]
    return {"risk_gate_handoff": {"status": "checked", "missing": missing}}


def quality_node(state: ProposalGraphState) -> ProposalGraphState:
    validation_snapshot = ValidationSnapshot.model_validate(state["validation_snapshot"])
    candidates = [
        ProposalCandidate.model_validate(candidate)
        for candidate in state["proposal_candidates"]
    ]
    quality = build_proposal_quality(
        validation_snapshot=validation_snapshot,
        candidates=candidates,
    )
    return {"quality": quality.model_dump(mode="json")}


def lineage_node(state: ProposalGraphState) -> ProposalGraphState:
    return {
        "lineage": {
            "status": "pending_persist",
            "note": "hashes and refs are finalized in snapshot/receipt persistence",
        }
    }


def snapshot_node(state: ProposalGraphState) -> ProposalGraphState:
    validation_snapshot = ValidationSnapshot.model_validate(state["validation_snapshot"])
    source = ProposalSourceSpec(**state["source"])
    candidates = [
        ProposalCandidate.model_validate(candidate)
        for candidate in state["proposal_candidates"]
    ]
    bundle = persist_proposal_bundle(
        source=source,
        input_validation_snapshot=validation_snapshot,
        candidates=candidates,
    )
    return {
        "snapshot": bundle.snapshot.model_dump(mode="json"),
        "receipt": bundle.receipt.model_dump(mode="json"),
        "lineage": bundle.lineage.model_dump(mode="json"),
        "quality": bundle.quality.model_dump(mode="json"),
    }


def receipt_node(state: ProposalGraphState) -> ProposalGraphState:
    return {"receipt": state["receipt"]}


def consumer_handoff_node(state: ProposalGraphState) -> ProposalGraphState:
    snapshot = state["snapshot"]
    return {
        "consumer_handoff": {
            "consumer": "risk_gate",
            "candidate_count": snapshot["candidate_count"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "allowed_outputs": [
                "risk gate review request",
                "proposal rejection reasons",
                "human review prompts",
            ],
            "forbidden_outputs": [
                "orders",
                "final sizing",
                "broker instructions",
                "execution permission",
                "trade approval",
            ],
        }
    }


def review_hook_node(state: ProposalGraphState) -> ProposalGraphState:
    snapshot = state["snapshot"]
    return {
        "review_hook": {
            "status": "open",
            "questions": snapshot["review_questions"],
            "next_review": "human proposal review before risk gate promotion",
            "promote_to": ["risk gate", "docs/reviews/", "docs/lessons/"],
        }
    }


def final_node(state: ProposalGraphState) -> ProposalGraphState:
    snapshot = state["snapshot"]
    return {
        "final": {
            "workflow": "langgraph_proposal_v1",
            "input_validation_snapshot_id": snapshot["input_validation_snapshot_id"],
            "candidate_count": snapshot["candidate_count"],
            "quality_ok": snapshot["quality"]["ok"],
            "execution_allowed": snapshot["execution_allowed"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "risk_gate_handoff": snapshot["risk_gate_handoff"],
            "review_questions": snapshot["review_questions"],
            "consumer_handoff": state["consumer_handoff"],
            "review_hook": state["review_hook"],
            "llm_enabled": state.get("source", {}).get("llm_enabled", False),
            "hermes_root": state.get("source", {}).get("hermes_root"),
        }
    }


def build_proposal_graph():
    graph = StateGraph(ProposalGraphState)
    graph.add_node("source_config", source_config_node)
    graph.add_node("load_validation_snapshot", load_validation_snapshot_node)
    graph.add_node("select_proposal_candidates", select_proposal_candidates_node)
    graph.add_node("build_evidence_summary", build_evidence_summary_node)
    graph.add_node("assign_portfolio_role", assign_portfolio_role_node)
    graph.add_node("attach_invalidation_triggers", attach_invalidation_triggers_node)
    graph.add_node("attach_constraints", attach_constraints_node)
    graph.add_node("attach_alternatives", attach_alternatives_node)
    graph.add_node("build_risk_gate_handoff", build_risk_gate_handoff_node)
    graph.add_node("quality", quality_node)
    graph.add_node("lineage", lineage_node)
    graph.add_node("snapshot", snapshot_node)
    graph.add_node("receipt", receipt_node)
    graph.add_node("consumer_handoff", consumer_handoff_node)
    graph.add_node("review_hook", review_hook_node)
    graph.add_node("final", final_node)
    graph.add_edge(START, "source_config")
    graph.add_edge("source_config", "load_validation_snapshot")
    graph.add_edge("load_validation_snapshot", "select_proposal_candidates")
    graph.add_edge("select_proposal_candidates", "build_evidence_summary")
    graph.add_edge("build_evidence_summary", "assign_portfolio_role")
    graph.add_edge("assign_portfolio_role", "attach_invalidation_triggers")
    graph.add_edge("attach_invalidation_triggers", "attach_constraints")
    graph.add_edge("attach_constraints", "attach_alternatives")
    graph.add_edge("attach_alternatives", "build_risk_gate_handoff")
    graph.add_edge("build_risk_gate_handoff", "quality")
    graph.add_edge("quality", "lineage")
    graph.add_edge("lineage", "snapshot")
    graph.add_edge("snapshot", "receipt")
    graph.add_edge("receipt", "consumer_handoff")
    graph.add_edge("consumer_handoff", "review_hook")
    graph.add_edge("review_hook", "final")
    graph.add_edge("final", END)
    return graph.compile()


proposal_graph = build_proposal_graph()


def run_proposal_graph(
    *,
    universe: list[str] | None = None,
    forms: list[str] | None = None,
    max_records: int = 30,
    max_hypotheses: int = 10,
    symbols: list[str] | None = None,
    validation_snapshot: dict[str, Any] | None = None,
    llm_enabled: bool = False,
    hermes_root: str = "/root/projects/hermes-agent",
    research_asset_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "universe": universe,
        "forms": forms or ["8-K", "10-Q", "10-K"],
        "max_records": max_records,
        "max_hypotheses": max_hypotheses,
        "symbols": symbols or [],
        "llm_enabled": llm_enabled,
        "hermes_root": hermes_root,
        "research_asset_context": research_asset_context or {},
    }
    if validation_snapshot is not None:
        payload["validation_snapshot"] = validation_snapshot
    result = proposal_graph.invoke(payload)
    return dict(result)
