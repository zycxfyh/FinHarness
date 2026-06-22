"""LangGraph workflow for eighth-layer independent risk gates.

Two build modes:

- default: non-interactive; missing human attestation simply leaves decisions
  at needs_human_review (fail-closed).
- interactive: a real LangGraph interrupt pauses the run after decisions are
  built; a human resumes with an explicit attestation, which is recorded in
  the context and the decisions are rebuilt. Approval is an event in the graph
  state, not a default.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from finharness.proposal import ProposalSnapshot
from finharness.proposal_graph import run_proposal_graph
from finharness.research_assets import compact_research_asset_context
from finharness.risk_gate import (
    RiskGateContext,
    RiskGateDecision,
    RiskGateSourceSpec,
    build_risk_gate_decisions,
    build_risk_gate_quality,
    persist_risk_gate_bundle,
)
from finharness.trading_state_store import (
    load_trading_state,
    merge_into_risk_context,
    trading_state_path,
)


class RiskGateGraphState(TypedDict, total=False):
    universe: list[str]
    forms: list[str]
    max_records: int
    max_hypotheses: int
    symbols: list[str]
    llm_enabled: bool
    hermes_root: str
    research_asset_context: dict[str, Any]
    proposal_snapshot: dict[str, Any]
    risk_context: dict[str, Any]
    trading_state_path: str
    trading_state: dict[str, Any]
    human_review_event: dict[str, Any]
    source: dict[str, Any]
    proposal_quality_check: dict[str, Any]
    mandate_check: dict[str, Any]
    instrument_permission_check: dict[str, Any]
    paper_or_live_permission_check: dict[str, Any]
    exposure_limit_check: dict[str, Any]
    concentration_check: dict[str, Any]
    liquidity_check: dict[str, Any]
    drawdown_behavior_check: dict[str, Any]
    scenario_check: dict[str, Any]
    decisions: list[dict[str, Any]]
    quality: dict[str, Any]
    lineage: dict[str, Any]
    snapshot: dict[str, Any]
    receipt: dict[str, Any]
    consumer_handoff: dict[str, Any]
    review_hook: dict[str, Any]
    final: dict[str, Any]


def load_trading_state_node(state: RiskGateGraphState) -> RiskGateGraphState:
    """Loop 3 feedback edge: persisted behavioral state is the default input.

    Explicit risk_context keys still win, so operator overrides stay possible
    and visible; everything else comes from the durable TradingStateRecord
    written back by post-trade runs.
    """
    path = state.get("trading_state_path")
    record = load_trading_state(path)
    merged = merge_into_risk_context(state.get("risk_context"), path=path)
    return {
        "risk_context": merged,
        "trading_state": {
            "record": record.model_dump(mode="json"),
            "path": str(trading_state_path(path)),
        },
    }


def source_config_node(state: RiskGateGraphState) -> RiskGateGraphState:
    llm_enabled = bool(state.get("llm_enabled", False))
    context = RiskGateContext.model_validate(state.get("risk_context") or {})
    source = RiskGateSourceSpec(
        llm_provider="hermes-agent" if llm_enabled else None,
        llm_interface="HermesRiskGateDraftProvider" if llm_enabled else None,
        llm_enabled=llm_enabled,
        hermes_root=state.get("hermes_root", "/root/projects/hermes-agent"),
        config={
            "universe": state.get("universe"),
            "forms": state.get("forms", ["8-K", "10-Q", "10-K"]),
            "max_records": state.get("max_records", 30),
            "max_hypotheses": state.get("max_hypotheses", 10),
            "symbols": state.get("symbols", []),
            "mandate_id": context.mandate_id,
            "live_execution_allowed": context.live_execution_allowed,
            "research_asset_context": compact_research_asset_context(
                state.get("research_asset_context"), "L8"
            ),
        },
    )
    return {
        "source": source.model_dump(mode="json"),
        "risk_context": context.model_dump(mode="json"),
    }


def load_proposal_snapshot_node(state: RiskGateGraphState) -> RiskGateGraphState:
    if "proposal_snapshot" in state:
        return {"proposal_snapshot": state["proposal_snapshot"]}
    result = run_proposal_graph(
        universe=state.get("universe"),
        forms=state.get("forms"),
        max_records=state.get("max_records", 30),
        max_hypotheses=state.get("max_hypotheses", 10),
        symbols=state.get("symbols") or None,
        llm_enabled=state.get("llm_enabled", False),
        hermes_root=state.get("hermes_root", "/root/projects/hermes-agent"),
        research_asset_context=state.get("research_asset_context"),
    )
    return {"proposal_snapshot": result["snapshot"]}


def proposal_quality_check_node(state: RiskGateGraphState) -> RiskGateGraphState:
    snapshot = ProposalSnapshot.model_validate(state["proposal_snapshot"])
    return {
        "proposal_quality_check": {
            "status": "passed" if snapshot.quality.ok else "failed",
            "candidate_count": snapshot.candidate_count,
        }
    }


def mandate_check_node(state: RiskGateGraphState) -> RiskGateGraphState:
    context = RiskGateContext.model_validate(state["risk_context"])
    return {
        "mandate_check": {
            "status": "passed" if context.mandate_id and context.mandate_text else "failed",
            "mandate_id": context.mandate_id,
        }
    }


def instrument_permission_check_node(state: RiskGateGraphState) -> RiskGateGraphState:
    snapshot = ProposalSnapshot.model_validate(state["proposal_snapshot"])
    context = RiskGateContext.model_validate(state["risk_context"])
    blocked = [
        candidate.proposal_id
        for candidate in snapshot.candidates
        if candidate.symbol not in context.allowed_symbols
        or candidate.action_type not in context.allowed_action_types
    ]
    return {"instrument_permission_check": {"status": "checked", "blocked": blocked}}


def paper_or_live_permission_check_node(state: RiskGateGraphState) -> RiskGateGraphState:
    context = RiskGateContext.model_validate(state["risk_context"])
    passed = context.requested_execution_mode != "live" and not context.live_execution_allowed
    return {
        "paper_or_live_permission_check": {
            "status": "passed" if passed else "failed",
            "requested_execution_mode": context.requested_execution_mode,
            "live_execution_allowed": context.live_execution_allowed,
        }
    }


def exposure_limit_check_node(state: RiskGateGraphState) -> RiskGateGraphState:
    context = RiskGateContext.model_validate(state["risk_context"])
    return {
        "exposure_limit_check": {
            "status": (
                "passed"
                if context.requested_notional <= context.max_paper_notional
                else "failed"
            ),
            "requested_notional": context.requested_notional,
            "max_paper_notional": context.max_paper_notional,
        }
    }


def concentration_check_node(state: RiskGateGraphState) -> RiskGateGraphState:
    context = RiskGateContext.model_validate(state["risk_context"])
    return {
        "concentration_check": {
            "status": (
                "passed"
                if context.requested_symbol_concentration_pct
                <= context.max_symbol_concentration_pct
                else "failed"
            ),
            "requested_symbol_concentration_pct": context.requested_symbol_concentration_pct,
            "max_symbol_concentration_pct": context.max_symbol_concentration_pct,
        }
    }


def liquidity_check_node(state: RiskGateGraphState) -> RiskGateGraphState:
    context = RiskGateContext.model_validate(state["risk_context"])
    return {
        "liquidity_check": {
            "status": "passed" if context.liquidity_evidence_present else "failed",
        }
    }


def drawdown_behavior_check_node(state: RiskGateGraphState) -> RiskGateGraphState:
    context = RiskGateContext.model_validate(state["risk_context"])
    passed = (
        context.drawdown_pct > context.hard_stop_drawdown_pct
        and context.consecutive_losses < context.hard_stop_consecutive_losses
        and not context.behavior_reset_required
    )
    return {
        "drawdown_behavior_check": {
            "status": "passed" if passed else "failed",
            "drawdown_pct": context.drawdown_pct,
            "consecutive_losses": context.consecutive_losses,
            "behavior_reset_required": context.behavior_reset_required,
        }
    }


def scenario_check_node(state: RiskGateGraphState) -> RiskGateGraphState:
    context = RiskGateContext.model_validate(state["risk_context"])
    return {
        "scenario_check": {
            "status": "passed" if context.scenario_review_present else "failed",
        }
    }


def decision_node(state: RiskGateGraphState) -> RiskGateGraphState:
    snapshot = ProposalSnapshot.model_validate(state["proposal_snapshot"])
    context = RiskGateContext.model_validate(state["risk_context"])
    decisions = build_risk_gate_decisions(
        proposal_snapshot=snapshot,
        context=context,
    )
    return {"decisions": [decision.model_dump(mode="json") for decision in decisions]}


def human_review_gate_node(state: RiskGateGraphState) -> RiskGateGraphState:
    """Interactive-only: pause for a human attestation via LangGraph interrupt.

    Resumes with {"attest": bool, "reason": str}. A positive attestation is
    written into the risk context and decisions are rebuilt so the receipt
    records both the pre- and post-attestation evidence path. Anything else
    leaves the fail-closed needs_human_review decisions untouched.
    """
    context = RiskGateContext.model_validate(state["risk_context"])
    needs_review = [
        item
        for item in state.get("decisions", [])
        if item.get("decision") == "needs_human_review"
    ]
    if context.human_review_attested or not needs_review:
        return {}
    answer = interrupt(
        {
            "question": (
                "Attest human review for these paper-review candidates? "
                "Resume with {'attest': true, 'reason': '...'} to approve."
            ),
            "pending_decisions": [
                {
                    "decision_id": item.get("decision_id"),
                    "symbol": item.get("symbol"),
                    "action_type": item.get("action_type"),
                    "blocking_reasons": item.get("blocking_reasons", []),
                }
                for item in needs_review
            ],
        }
    )
    if not (isinstance(answer, dict) and answer.get("attest") is True):
        return {}
    reason = str(answer.get("reason") or "").strip()
    if not reason:
        # An attestation without a written reason is not an attestation.
        return {}
    attested_context = context.model_copy(update={"human_review_attested": True})
    snapshot = ProposalSnapshot.model_validate(state["proposal_snapshot"])
    decisions = build_risk_gate_decisions(
        proposal_snapshot=snapshot,
        context=attested_context,
    )
    return {
        "risk_context": attested_context.model_dump(mode="json"),
        "human_review_event": {
            "attested": True,
            "reason": reason,
            "decisions_before": [item.get("decision_id") for item in needs_review],
        },
        "decisions": [decision.model_dump(mode="json") for decision in decisions],
    }


def quality_node(state: RiskGateGraphState) -> RiskGateGraphState:
    snapshot = ProposalSnapshot.model_validate(state["proposal_snapshot"])
    context = RiskGateContext.model_validate(state["risk_context"])
    decisions = [RiskGateDecision.model_validate(item) for item in state["decisions"]]
    quality = build_risk_gate_quality(
        proposal_snapshot=snapshot,
        context=context,
        decisions=decisions,
    )
    return {"quality": quality.model_dump(mode="json")}


def lineage_node(state: RiskGateGraphState) -> RiskGateGraphState:
    return {
        "lineage": {
            "status": "pending_persist",
            "note": "hashes and refs are finalized in snapshot/receipt persistence",
        }
    }


def snapshot_node(state: RiskGateGraphState) -> RiskGateGraphState:
    source = RiskGateSourceSpec(**state["source"])
    proposal_snapshot = ProposalSnapshot.model_validate(state["proposal_snapshot"])
    context = RiskGateContext.model_validate(state["risk_context"])
    decisions = [RiskGateDecision.model_validate(item) for item in state["decisions"]]
    bundle = persist_risk_gate_bundle(
        source=source,
        input_proposal_snapshot=proposal_snapshot,
        context=context,
        decisions=decisions,
    )
    return {
        "snapshot": bundle.snapshot.model_dump(mode="json"),
        "receipt": bundle.receipt.model_dump(mode="json"),
        "lineage": bundle.lineage.model_dump(mode="json"),
        "quality": bundle.quality.model_dump(mode="json"),
    }


def receipt_node(state: RiskGateGraphState) -> RiskGateGraphState:
    return {"receipt": state["receipt"]}


def consumer_handoff_node(state: RiskGateGraphState) -> RiskGateGraphState:
    snapshot = state["snapshot"]
    return {
        "consumer_handoff": {
            "consumer": "execution_review",
            "decision_count": snapshot["decision_count"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "allowed_outputs": [
                "paper review handoff",
                "blocked candidate reasons",
                "human review prompts",
            ],
            "forbidden_outputs": [
                "orders",
                "live execution approval",
                "final sizing",
                "broker instructions",
            ],
        }
    }


def review_hook_node(state: RiskGateGraphState) -> RiskGateGraphState:
    snapshot = state["snapshot"]
    return {
        "review_hook": {
            "status": "open",
            "questions": snapshot["review_questions"],
            "next_review": "human risk-gate review before any execution-layer work",
            "promote_to": ["execution layer", "docs/reviews/", "docs/lessons/"],
        }
    }


def final_node(state: RiskGateGraphState) -> RiskGateGraphState:
    snapshot = state["snapshot"]
    return {
        "final": {
            "workflow": "langgraph_risk_gate_v1",
            "input_proposal_snapshot_id": snapshot["input_proposal_snapshot_id"],
            "candidate_count": snapshot["candidate_count"],
            "decision_count": snapshot["decision_count"],
            "quality_ok": snapshot["quality"]["ok"],
            "execution_allowed": snapshot["execution_allowed"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "execution_handoff": snapshot["execution_handoff"],
            "review_questions": snapshot["review_questions"],
            "consumer_handoff": state["consumer_handoff"],
            "review_hook": state["review_hook"],
            "llm_enabled": state.get("source", {}).get("llm_enabled", False),
            "hermes_root": state.get("source", {}).get("hermes_root"),
            "trading_state": state.get("trading_state", {}),
        }
    }


def build_risk_gate_graph(*, interactive: bool = False):
    graph = StateGraph(RiskGateGraphState)
    graph.add_node("load_trading_state", load_trading_state_node)
    graph.add_node("source_config", source_config_node)
    graph.add_node("load_proposal_snapshot", load_proposal_snapshot_node)
    graph.add_node("proposal_quality_check", proposal_quality_check_node)
    graph.add_node("mandate_check", mandate_check_node)
    graph.add_node("instrument_permission_check", instrument_permission_check_node)
    graph.add_node("paper_or_live_permission_check", paper_or_live_permission_check_node)
    graph.add_node("exposure_limit_check", exposure_limit_check_node)
    graph.add_node("concentration_check", concentration_check_node)
    graph.add_node("liquidity_check", liquidity_check_node)
    graph.add_node("drawdown_behavior_check", drawdown_behavior_check_node)
    graph.add_node("scenario_check", scenario_check_node)
    graph.add_node("decision", decision_node)
    if interactive:
        graph.add_node("human_review_gate", human_review_gate_node)
    graph.add_node("quality", quality_node)
    graph.add_node("lineage", lineage_node)
    graph.add_node("snapshot", snapshot_node)
    graph.add_node("receipt", receipt_node)
    graph.add_node("consumer_handoff", consumer_handoff_node)
    graph.add_node("review_hook", review_hook_node)
    graph.add_node("final", final_node)
    graph.add_edge(START, "load_trading_state")
    graph.add_edge("load_trading_state", "source_config")
    graph.add_edge("source_config", "load_proposal_snapshot")
    graph.add_edge("load_proposal_snapshot", "proposal_quality_check")
    graph.add_edge("proposal_quality_check", "mandate_check")
    graph.add_edge("mandate_check", "instrument_permission_check")
    graph.add_edge("instrument_permission_check", "paper_or_live_permission_check")
    graph.add_edge("paper_or_live_permission_check", "exposure_limit_check")
    graph.add_edge("exposure_limit_check", "concentration_check")
    graph.add_edge("concentration_check", "liquidity_check")
    graph.add_edge("liquidity_check", "drawdown_behavior_check")
    graph.add_edge("drawdown_behavior_check", "scenario_check")
    graph.add_edge("scenario_check", "decision")
    if interactive:
        graph.add_edge("decision", "human_review_gate")
        graph.add_edge("human_review_gate", "quality")
    else:
        graph.add_edge("decision", "quality")
    graph.add_edge("quality", "lineage")
    graph.add_edge("lineage", "snapshot")
    graph.add_edge("snapshot", "receipt")
    graph.add_edge("receipt", "consumer_handoff")
    graph.add_edge("consumer_handoff", "review_hook")
    graph.add_edge("review_hook", "final")
    graph.add_edge("final", END)
    if interactive:
        return graph.compile(checkpointer=MemorySaver())
    return graph.compile()


risk_gate_graph = build_risk_gate_graph()


def run_risk_gate_graph(
    *,
    universe: list[str] | None = None,
    forms: list[str] | None = None,
    max_records: int = 30,
    max_hypotheses: int = 10,
    symbols: list[str] | None = None,
    proposal_snapshot: dict[str, Any] | None = None,
    risk_context: dict[str, Any] | None = None,
    llm_enabled: bool = False,
    hermes_root: str = "/root/projects/hermes-agent",
    research_asset_context: dict[str, Any] | None = None,
    trading_state_path: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "universe": universe,
        "forms": forms or ["8-K", "10-Q", "10-K"],
        "max_records": max_records,
        "max_hypotheses": max_hypotheses,
        "symbols": symbols or [],
        "risk_context": risk_context or {},
        "llm_enabled": llm_enabled,
        "hermes_root": hermes_root,
        "research_asset_context": research_asset_context or {},
    }
    if trading_state_path is not None:
        payload["trading_state_path"] = trading_state_path
    if proposal_snapshot is not None:
        payload["proposal_snapshot"] = proposal_snapshot
    result = risk_gate_graph.invoke(payload)
    return dict(result)


def run_risk_gate_graph_interactive(
    *,
    payload: dict[str, Any],
    thread_id: str,
    graph=None,
) -> dict[str, Any]:
    """Start an interactive risk-gate run; may pause at the human gate.

    Returns the raw state. When paused, the state contains "__interrupt__";
    resume with resume_risk_gate_graph on the same graph and thread_id.
    """
    compiled = graph or build_risk_gate_graph(interactive=True)
    config = {"configurable": {"thread_id": thread_id}}
    result = compiled.invoke(payload, config=config)
    return dict(result)


def resume_risk_gate_graph(
    *,
    graph,
    thread_id: str,
    attest: bool,
    reason: str,
) -> dict[str, Any]:
    """Resume a paused interactive run with an explicit human attestation."""
    config = {"configurable": {"thread_id": thread_id}}
    result = graph.invoke(
        Command(resume={"attest": attest, "reason": reason}), config=config
    )
    return dict(result)
