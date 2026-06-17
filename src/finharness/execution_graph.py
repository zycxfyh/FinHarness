"""LangGraph workflow for ninth-layer paper execution lifecycle control."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from finharness.execution import (
    NAUTILUS_PAPER_ADAPTER_NAME,
    ExecutionContext,
    ExecutionIntent,
    ExecutionOrderRequest,
    ExecutionSourceSpec,
    FakePaperExecutionAdapter,
    authorization_for_execution_context,
    blocked_event,
    build_execution_intents,
    build_order_requests,
    collect_execution_events,
    persist_execution_bundle,
)
from finharness.research_assets import compact_research_asset_context
from finharness.risk_gate import RiskGateSnapshot
from finharness.risk_gate_graph import run_risk_gate_graph


class ExecutionGraphState(TypedDict, total=False):
    universe: list[str]
    forms: list[str]
    max_records: int
    max_hypotheses: int
    symbols: list[str]
    risk_gate_snapshot: dict[str, Any]
    risk_context: dict[str, Any]
    execution_context: dict[str, Any]
    research_asset_context: dict[str, Any]
    source: dict[str, Any]
    allowed_decisions: list[dict[str, Any]]
    intents: list[dict[str, Any]]
    adapter_permission_check: dict[str, Any]
    pre_submit_check: dict[str, Any]
    idempotency: dict[str, Any]
    order_requests: list[dict[str, Any]]
    events: list[dict[str, Any]]
    cancel_or_reconcile: dict[str, Any]
    quality: dict[str, Any]
    lineage: dict[str, Any]
    snapshot: dict[str, Any]
    receipt: dict[str, Any]
    review_hook: dict[str, Any]
    final: dict[str, Any]
    execution_adapter: str
    fake_fill_mode: str


def graph_adapter_name(state: ExecutionGraphState, context: ExecutionContext) -> str:
    if context.requested_mode == "dry_run":
        return "dry_run"
    if state.get("execution_adapter") == "fake":
        return "fake_paper_adapter"
    return NAUTILUS_PAPER_ADAPTER_NAME


def graph_execution_adapter(state: ExecutionGraphState):
    if state.get("execution_adapter") == "fake":
        return FakePaperExecutionAdapter(
            fill_mode=state.get("fake_fill_mode", "accepted")  # type: ignore[arg-type]
        )
    return None


def source_config_node(state: ExecutionGraphState) -> ExecutionGraphState:
    context = ExecutionContext.model_validate(state.get("execution_context") or {})
    adapter_name = graph_adapter_name(state, context)
    source = ExecutionSourceSpec(
        adapter_name=adapter_name,
        adapter_mode=context.requested_mode,
        config={
            "execution_adapter": state.get("execution_adapter", "nautilus"),
            "operator_execute": context.operator_execute,
            "live_execution_allowed": context.live_execution_allowed,
            "operator_id": context.operator_id,
            "account_id": context.account_id,
            "authorization_scope": context.authorization_scope,
            "routing_policy": context.routing_policy,
            "research_asset_context": compact_research_asset_context(
                state.get("research_asset_context"), "L9"
            ),
        },
    )
    return {
        "source": source.model_dump(mode="json"),
        "execution_context": context.model_dump(mode="json"),
    }


def load_risk_gate_snapshot_node(state: ExecutionGraphState) -> ExecutionGraphState:
    if "risk_gate_snapshot" in state:
        return {"risk_gate_snapshot": state["risk_gate_snapshot"]}
    result = run_risk_gate_graph(
        universe=state.get("universe"),
        forms=state.get("forms"),
        max_records=state.get("max_records", 30),
        max_hypotheses=state.get("max_hypotheses", 10),
        symbols=state.get("symbols") or None,
        risk_context=state.get("risk_context") or {},
        research_asset_context=state.get("research_asset_context"),
    )
    return {"risk_gate_snapshot": result["snapshot"]}


def select_allowed_decisions_node(state: ExecutionGraphState) -> ExecutionGraphState:
    snapshot = RiskGateSnapshot.model_validate(state["risk_gate_snapshot"])
    allowed = [
        decision
        for decision in snapshot.decisions
        if decision.decision == "approved_for_paper_review"
        and decision.paper_review_allowed
        and not decision.live_execution_allowed
    ]
    return {"allowed_decisions": [decision.model_dump(mode="json") for decision in allowed]}


def build_execution_intent_node(state: ExecutionGraphState) -> ExecutionGraphState:
    snapshot = RiskGateSnapshot.model_validate(state["risk_gate_snapshot"])
    context = ExecutionContext.model_validate(state["execution_context"])
    intents = build_execution_intents(risk_gate_snapshot=snapshot, context=context)
    return {"intents": [intent.model_dump(mode="json") for intent in intents]}


def adapter_permission_check_node(state: ExecutionGraphState) -> ExecutionGraphState:
    context = ExecutionContext.model_validate(state["execution_context"])
    passed = context.requested_mode != "live" and not context.live_execution_allowed
    return {
        "adapter_permission_check": {
            "status": "passed" if passed else "failed",
            "requested_mode": context.requested_mode,
            "live_execution_allowed": context.live_execution_allowed,
            "operator_execute": context.operator_execute,
        }
    }


def pre_submit_check_node(state: ExecutionGraphState) -> ExecutionGraphState:
    context = ExecutionContext.model_validate(state["execution_context"])
    passed = (
        bool(state.get("intents"))
        and context.human_review_attested
        and 0 < context.requested_quantity <= context.max_order_quantity
        and authorization_for_execution_context(context).allowed
    )
    return {
        "pre_submit_check": {
            "status": "passed" if passed else "failed",
            "human_review_attested": context.human_review_attested,
            "requested_quantity": context.requested_quantity,
            "max_order_quantity": context.max_order_quantity,
            "intent_count": len(state.get("intents", [])),
            "authorization_allowed": authorization_for_execution_context(context).allowed,
        }
    }


def derive_idempotency_key_node(state: ExecutionGraphState) -> ExecutionGraphState:
    snapshot = RiskGateSnapshot.model_validate(state["risk_gate_snapshot"])
    context = ExecutionContext.model_validate(state["execution_context"])
    source = ExecutionSourceSpec.model_validate(state["source"])
    intents = [ExecutionIntent.model_validate(item) for item in state.get("intents", [])]
    requests = build_order_requests(
        risk_gate_snapshot=snapshot,
        context=context,
        source=source,
        intents=intents,
    )
    return {
        "idempotency": {
            "keys": [request.idempotency_key for request in requests],
            "client_order_ids": [request.client_order_id for request in requests],
        }
    }


def stage_order_request_node(state: ExecutionGraphState) -> ExecutionGraphState:
    snapshot = RiskGateSnapshot.model_validate(state["risk_gate_snapshot"])
    context = ExecutionContext.model_validate(state["execution_context"])
    source = ExecutionSourceSpec.model_validate(state["source"])
    intents = [ExecutionIntent.model_validate(item) for item in state.get("intents", [])]
    requests = build_order_requests(
        risk_gate_snapshot=snapshot,
        context=context,
        source=source,
        intents=intents,
    )
    return {"order_requests": [request.model_dump(mode="json") for request in requests]}


def submit_or_dry_run_node(state: ExecutionGraphState) -> ExecutionGraphState:
    context = ExecutionContext.model_validate(state["execution_context"])
    requests = [
        ExecutionOrderRequest.model_validate(item) for item in state.get("order_requests", [])
    ]
    if context.requested_mode == "live":
        events = [blocked_event("live execution is blocked in Layer 9 MVP")]
    else:
        events = collect_execution_events(
            context=context,
            order_requests=requests,
            adapter=graph_execution_adapter(state),
        )
    return {"events": [item.model_dump(mode="json") for item in events]}


def collect_execution_events_node(state: ExecutionGraphState) -> ExecutionGraphState:
    return {"events": state.get("events", [])}


def cancel_or_reconcile_node(state: ExecutionGraphState) -> ExecutionGraphState:
    statuses = [event["status"] for event in state.get("events", [])]
    return {
        "cancel_or_reconcile": {
            "cancel_requested": "cancel_requested" in statuses,
            "terminal": any(
                status in statuses for status in ["filled", "canceled", "rejected"]
            ),
            "statuses": statuses,
        }
    }


def quality_node(state: ExecutionGraphState) -> ExecutionGraphState:
    return {
        "quality": {
            "status": "pending_persist",
            "note": "quality is finalized in snapshot persistence",
        }
    }


def lineage_node(state: ExecutionGraphState) -> ExecutionGraphState:
    return {
        "lineage": {
            "status": "pending_persist",
            "note": "hashes and refs are finalized in snapshot/receipt persistence",
        }
    }


def snapshot_node(state: ExecutionGraphState) -> ExecutionGraphState:
    source = ExecutionSourceSpec.model_validate(state["source"])
    risk_gate_snapshot = RiskGateSnapshot.model_validate(state["risk_gate_snapshot"])
    context = ExecutionContext.model_validate(state["execution_context"])
    intents = [ExecutionIntent.model_validate(item) for item in state.get("intents", [])]
    order_requests = [
        ExecutionOrderRequest.model_validate(item) for item in state.get("order_requests", [])
    ]
    if context.requested_mode == "live":
        events = [blocked_event("live execution is blocked in Layer 9 MVP")]
    else:
        events = collect_execution_events(
            context=context,
            order_requests=order_requests,
            adapter=graph_execution_adapter(state),
        )
    if context.requested_mode != "live" and not intents and not events:
        events = [blocked_event("no approved Risk Gate decisions available")]
    elif context.requested_mode != "live" and intents and not order_requests and not events:
        authorization = authorization_for_execution_context(context)
        reason = (
            "authorization blocked order request: "
            + "; ".join(authorization.blocking_reasons)
            if not authorization.allowed
            else "pre-submit checks blocked order request"
        )
        events = [blocked_event(reason)]
    elif context.requested_mode != "live" and intents and not order_requests and not events:
        events = [blocked_event("pre-submit checks blocked order request")]
    bundle = persist_execution_bundle(
        source=source,
        input_risk_gate_snapshot=risk_gate_snapshot,
        context=context,
        intents=intents,
        order_requests=order_requests,
        events=events,
    )
    return {
        "snapshot": bundle.snapshot.model_dump(mode="json"),
        "receipt": bundle.receipt.model_dump(mode="json"),
        "quality": bundle.quality.model_dump(mode="json"),
        "lineage": bundle.lineage.model_dump(mode="json"),
    }


def receipt_node(state: ExecutionGraphState) -> ExecutionGraphState:
    return {"receipt": state["receipt"]}


def review_hook_node(state: ExecutionGraphState) -> ExecutionGraphState:
    snapshot = state["snapshot"]
    return {
        "review_hook": {
            "status": "open",
            "questions": snapshot["review_questions"],
            "next_review": "human execution review before any live execution discussion",
            "promote_to": ["post-trade layer", "docs/reviews/", "docs/lessons/"],
        }
    }


def final_node(state: ExecutionGraphState) -> ExecutionGraphState:
    snapshot = state["snapshot"]
    return {
        "final": {
            "workflow": "langgraph_execution_v1",
            "input_risk_gate_snapshot_id": snapshot["input_risk_gate_snapshot_id"],
            "mode": snapshot["mode"],
            "intent_count": snapshot["intent_count"],
            "order_request_count": snapshot["order_request_count"],
            "event_count": snapshot["event_count"],
            "final_status": snapshot["final_status"],
            "quality_ok": snapshot["quality"]["ok"],
            "execution_allowed": snapshot["execution_allowed"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "post_trade_handoff": snapshot["post_trade_handoff"],
            "review_questions": snapshot["review_questions"],
            "review_hook": state["review_hook"],
        }
    }


def build_execution_graph():
    graph = StateGraph(ExecutionGraphState)
    graph.add_node("source_config", source_config_node)
    graph.add_node("load_risk_gate_snapshot", load_risk_gate_snapshot_node)
    graph.add_node("select_allowed_decisions", select_allowed_decisions_node)
    graph.add_node("build_execution_intent", build_execution_intent_node)
    graph.add_node("adapter_permission_check", adapter_permission_check_node)
    graph.add_node("pre_submit_check", pre_submit_check_node)
    graph.add_node("derive_idempotency_key", derive_idempotency_key_node)
    graph.add_node("stage_order_request", stage_order_request_node)
    graph.add_node("submit_or_dry_run", submit_or_dry_run_node)
    graph.add_node("collect_execution_events", collect_execution_events_node)
    graph.add_node("cancel_or_reconcile", cancel_or_reconcile_node)
    graph.add_node("quality", quality_node)
    graph.add_node("lineage", lineage_node)
    graph.add_node("snapshot", snapshot_node)
    graph.add_node("receipt", receipt_node)
    graph.add_node("review_hook", review_hook_node)
    graph.add_node("final", final_node)
    graph.add_edge(START, "source_config")
    graph.add_edge("source_config", "load_risk_gate_snapshot")
    graph.add_edge("load_risk_gate_snapshot", "select_allowed_decisions")
    graph.add_edge("select_allowed_decisions", "build_execution_intent")
    graph.add_edge("build_execution_intent", "adapter_permission_check")
    graph.add_edge("adapter_permission_check", "pre_submit_check")
    graph.add_edge("pre_submit_check", "derive_idempotency_key")
    graph.add_edge("derive_idempotency_key", "stage_order_request")
    graph.add_edge("stage_order_request", "submit_or_dry_run")
    graph.add_edge("submit_or_dry_run", "collect_execution_events")
    graph.add_edge("collect_execution_events", "cancel_or_reconcile")
    graph.add_edge("cancel_or_reconcile", "quality")
    graph.add_edge("quality", "lineage")
    graph.add_edge("lineage", "snapshot")
    graph.add_edge("snapshot", "receipt")
    graph.add_edge("receipt", "review_hook")
    graph.add_edge("review_hook", "final")
    graph.add_edge("final", END)
    return graph.compile()


execution_graph = build_execution_graph()


def run_execution_graph(
    *,
    universe: list[str] | None = None,
    forms: list[str] | None = None,
    max_records: int = 30,
    max_hypotheses: int = 10,
    symbols: list[str] | None = None,
    risk_gate_snapshot: dict[str, Any] | None = None,
    risk_context: dict[str, Any] | None = None,
    execution_context: dict[str, Any] | None = None,
    execution_adapter: str = "nautilus",
    fake_fill_mode: str = "accepted",
    research_asset_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "universe": universe,
        "forms": forms or ["8-K", "10-Q", "10-K"],
        "max_records": max_records,
        "max_hypotheses": max_hypotheses,
        "symbols": symbols or [],
        "risk_context": risk_context or {},
        "execution_context": execution_context or {},
        "execution_adapter": execution_adapter,
        "fake_fill_mode": fake_fill_mode,
        "research_asset_context": research_asset_context or {},
    }
    if risk_gate_snapshot is not None:
        payload["risk_gate_snapshot"] = risk_gate_snapshot
    result = execution_graph.invoke(payload)
    return dict(result)
