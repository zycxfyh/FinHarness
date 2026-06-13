"""LangGraph workflow for tenth-layer post-trade reconciliation."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from finharness.execution import ExecutionSnapshot
from finharness.execution_graph import run_execution_graph
from finharness.post_trade import (
    PostTradeContext,
    PostTradeSourceSpec,
    build_cost_estimates,
    build_post_trade_bundle_from_execution_snapshot,
    build_post_trade_exceptions,
    build_post_trade_quality,
    build_reconciliations,
    final_post_trade_status,
)
from finharness.research_assets import compact_research_asset_context
from finharness.trading_state_store import (
    trading_state_path,
    update_from_post_trade_snapshot,
)


class PostTradeGraphState(TypedDict, total=False):
    universe: list[str]
    forms: list[str]
    max_records: int
    max_hypotheses: int
    symbols: list[str]
    risk_context: dict[str, Any]
    execution_context: dict[str, Any]
    execution_snapshot: dict[str, Any]
    post_trade_context: dict[str, Any]
    research_asset_context: dict[str, Any]
    source: dict[str, Any]
    lineage_check: dict[str, Any]
    lifecycle_classification: dict[str, Any]
    reconciliations: list[dict[str, Any]]
    cost_estimates: list[dict[str, Any]]
    settlement_awareness: dict[str, Any]
    exceptions: list[dict[str, Any]]
    performance_handoff: dict[str, Any]
    quality: dict[str, Any]
    lineage: dict[str, Any]
    snapshot: dict[str, Any]
    receipt: dict[str, Any]
    review_hook: dict[str, Any]
    final: dict[str, Any]
    fake_fill_mode: str
    trading_state_path: str
    trading_state: dict[str, Any]


def source_config_node(state: PostTradeGraphState) -> PostTradeGraphState:
    context = PostTradeContext.model_validate(state.get("post_trade_context") or {})
    source = PostTradeSourceSpec(
        config={
            "settlement_cycle": context.settlement_cycle,
            "account_ref": context.account_ref,
            "performance_handoff_enabled": context.performance_handoff_enabled,
            "research_asset_context": compact_research_asset_context(
                state.get("research_asset_context"), "L10"
            ),
        }
    )
    return {
        "source": source.model_dump(mode="json"),
        "post_trade_context": context.model_dump(mode="json"),
    }


def load_execution_snapshot_node(state: PostTradeGraphState) -> PostTradeGraphState:
    if "execution_snapshot" in state:
        return {"execution_snapshot": state["execution_snapshot"]}
    result = run_execution_graph(
        universe=state.get("universe"),
        forms=state.get("forms"),
        max_records=state.get("max_records", 30),
        max_hypotheses=state.get("max_hypotheses", 10),
        symbols=state.get("symbols") or None,
        risk_context=state.get("risk_context") or {},
        execution_context=state.get("execution_context") or {},
        fake_fill_mode=state.get("fake_fill_mode", "accepted"),
        research_asset_context=state.get("research_asset_context"),
    )
    return {"execution_snapshot": result["snapshot"]}


def lineage_check_node(state: PostTradeGraphState) -> PostTradeGraphState:
    snapshot = ExecutionSnapshot.model_validate(state["execution_snapshot"])
    return {
        "lineage_check": {
            "status": "passed" if snapshot.receipt_ref else "failed",
            "execution_snapshot_id": snapshot.execution_snapshot_id,
            "execution_receipt_ref": snapshot.receipt_ref,
        }
    }


def lifecycle_classification_node(state: PostTradeGraphState) -> PostTradeGraphState:
    snapshot = ExecutionSnapshot.model_validate(state["execution_snapshot"])
    reconciliations = build_reconciliations(snapshot)
    status = final_post_trade_status(reconciliations, lineage_ok=bool(snapshot.receipt_ref))
    return {
        "lifecycle_classification": {
            "execution_final_status": snapshot.final_status,
            "post_trade_status": status,
            "reconciliation_count": len(reconciliations),
        }
    }


def fill_reconciliation_node(state: PostTradeGraphState) -> PostTradeGraphState:
    snapshot = ExecutionSnapshot.model_validate(state["execution_snapshot"])
    reconciliations = build_reconciliations(snapshot)
    return {
        "reconciliations": [item.model_dump(mode="json") for item in reconciliations]
    }


def tca_estimate_node(state: PostTradeGraphState) -> PostTradeGraphState:
    snapshot = ExecutionSnapshot.model_validate(state["execution_snapshot"])
    context = PostTradeContext.model_validate(state["post_trade_context"])
    reconciliations = build_reconciliations(snapshot)
    cost_estimates = build_cost_estimates(
        execution_snapshot=snapshot,
        context=context,
        reconciliations=reconciliations,
    )
    return {"cost_estimates": [item.model_dump(mode="json") for item in cost_estimates]}


def settlement_awareness_node(state: PostTradeGraphState) -> PostTradeGraphState:
    context = PostTradeContext.model_validate(state["post_trade_context"])
    return {
        "settlement_awareness": {
            "status": "awareness_only",
            "settlement_cycle": context.settlement_cycle,
            "no_settlement_completion_claim": True,
        }
    }


def exception_detection_node(state: PostTradeGraphState) -> PostTradeGraphState:
    snapshot = ExecutionSnapshot.model_validate(state["execution_snapshot"])
    reconciliations = build_reconciliations(snapshot)
    context = PostTradeContext.model_validate(state["post_trade_context"])
    cost_estimates = build_cost_estimates(
        execution_snapshot=snapshot,
        context=context,
        reconciliations=reconciliations,
    )
    exceptions = build_post_trade_exceptions(
        execution_snapshot=snapshot,
        reconciliations=reconciliations,
        cost_estimates=cost_estimates,
    )
    return {"exceptions": [item.model_dump(mode="json") for item in exceptions]}


def performance_handoff_node(state: PostTradeGraphState) -> PostTradeGraphState:
    status = state["lifecycle_classification"]["post_trade_status"]
    return {
        "performance_handoff": {
            "status": "available" if status == "reconciled_filled" else "withheld",
            "post_trade_status": status,
        }
    }


def quality_node(state: PostTradeGraphState) -> PostTradeGraphState:
    snapshot = ExecutionSnapshot.model_validate(state["execution_snapshot"])
    reconciliations = build_reconciliations(snapshot)
    context = PostTradeContext.model_validate(state["post_trade_context"])
    cost_estimates = build_cost_estimates(
        execution_snapshot=snapshot,
        context=context,
        reconciliations=reconciliations,
    )
    exceptions = build_post_trade_exceptions(
        execution_snapshot=snapshot,
        reconciliations=reconciliations,
        cost_estimates=cost_estimates,
    )
    quality = build_post_trade_quality(
        execution_snapshot=snapshot,
        reconciliations=reconciliations,
        cost_estimates=cost_estimates,
        exceptions=exceptions,
        lineage_complete=False,
        receipt_written=False,
    )
    return {"quality": quality.model_dump(mode="json")}


def lineage_node(state: PostTradeGraphState) -> PostTradeGraphState:
    return {
        "lineage": {
            "status": "pending_persist",
            "note": "hashes and refs are finalized in snapshot/receipt persistence",
        }
    }


def snapshot_node(state: PostTradeGraphState) -> PostTradeGraphState:
    source = PostTradeSourceSpec.model_validate(state["source"])
    execution_snapshot = ExecutionSnapshot.model_validate(state["execution_snapshot"])
    context = PostTradeContext.model_validate(state["post_trade_context"])
    bundle = build_post_trade_bundle_from_execution_snapshot(
        execution_snapshot,
        context=context,
        source=source,
    )
    return {
        "snapshot": bundle.snapshot.model_dump(mode="json"),
        "receipt": bundle.receipt.model_dump(mode="json"),
        "quality": bundle.quality.model_dump(mode="json"),
        "lineage": bundle.lineage.model_dump(mode="json"),
    }


def receipt_node(state: PostTradeGraphState) -> PostTradeGraphState:
    return {"receipt": state["receipt"]}


def persist_trading_state_node(state: PostTradeGraphState) -> PostTradeGraphState:
    """Loop 3 feedback edge: fold this run's outcome into durable state.

    Only provable facts are written (trade lifecycle completed, process
    failure occurred); win/loss stays operator-reported via
    trading_state_store.record_operator_outcome.
    """
    path = state.get("trading_state_path")
    record = update_from_post_trade_snapshot(state["snapshot"], path=path)
    return {
        "trading_state": {
            "record": record.model_dump(mode="json"),
            "path": str(trading_state_path(path)),
        }
    }


def review_hook_node(state: PostTradeGraphState) -> PostTradeGraphState:
    snapshot = state["snapshot"]
    return {
        "review_hook": {
            "status": "open",
            "questions": snapshot["review_questions"],
            "next_review": "human post-trade review before portfolio/accounting claims",
            "promote_to": ["portfolio layer", "accounting review", "performance review"],
        }
    }


def final_node(state: PostTradeGraphState) -> PostTradeGraphState:
    snapshot = state["snapshot"]
    return {
        "final": {
            "workflow": "langgraph_post_trade_v1",
            "input_execution_snapshot_id": snapshot["input_execution_snapshot_id"],
            "execution_receipt_ref": snapshot["input_execution_receipt_ref"],
            "final_status": snapshot["final_status"],
            "reconciliation_count": snapshot["reconciliation_count"],
            "cost_estimate_count": snapshot["cost_estimate_count"],
            "exception_count": snapshot["exception_count"],
            "quality_ok": snapshot["quality"]["ok"],
            "order_creation_allowed": snapshot["order_creation_allowed"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "portfolio_handoff": snapshot["portfolio_handoff"],
            "accounting_handoff": snapshot["accounting_handoff"],
            "performance_handoff": snapshot["performance_handoff"],
            "review_questions": snapshot["review_questions"],
            "review_hook": state["review_hook"],
            "trading_state": state.get("trading_state", {}),
        }
    }


def build_post_trade_graph():
    graph = StateGraph(PostTradeGraphState)
    graph.add_node("source_config", source_config_node)
    graph.add_node("load_execution_snapshot", load_execution_snapshot_node)
    graph.add_node("lineage_check", lineage_check_node)
    graph.add_node("lifecycle_classification", lifecycle_classification_node)
    graph.add_node("fill_reconciliation", fill_reconciliation_node)
    graph.add_node("tca_estimate", tca_estimate_node)
    graph.add_node("settlement_awareness", settlement_awareness_node)
    graph.add_node("exception_detection", exception_detection_node)
    graph.add_node("performance_handoff", performance_handoff_node)
    graph.add_node("quality", quality_node)
    graph.add_node("lineage", lineage_node)
    graph.add_node("snapshot", snapshot_node)
    graph.add_node("receipt", receipt_node)
    graph.add_node("persist_trading_state", persist_trading_state_node)
    graph.add_node("review_hook", review_hook_node)
    graph.add_node("final", final_node)
    graph.add_edge(START, "source_config")
    graph.add_edge("source_config", "load_execution_snapshot")
    graph.add_edge("load_execution_snapshot", "lineage_check")
    graph.add_edge("lineage_check", "lifecycle_classification")
    graph.add_edge("lifecycle_classification", "fill_reconciliation")
    graph.add_edge("fill_reconciliation", "tca_estimate")
    graph.add_edge("tca_estimate", "settlement_awareness")
    graph.add_edge("settlement_awareness", "exception_detection")
    graph.add_edge("exception_detection", "performance_handoff")
    graph.add_edge("performance_handoff", "quality")
    graph.add_edge("quality", "lineage")
    graph.add_edge("lineage", "snapshot")
    graph.add_edge("snapshot", "receipt")
    graph.add_edge("receipt", "persist_trading_state")
    graph.add_edge("persist_trading_state", "review_hook")
    graph.add_edge("review_hook", "final")
    graph.add_edge("final", END)
    return graph.compile()


post_trade_graph = build_post_trade_graph()


def run_post_trade_graph(
    *,
    universe: list[str] | None = None,
    forms: list[str] | None = None,
    max_records: int = 30,
    max_hypotheses: int = 10,
    symbols: list[str] | None = None,
    risk_context: dict[str, Any] | None = None,
    execution_context: dict[str, Any] | None = None,
    execution_snapshot: dict[str, Any] | None = None,
    post_trade_context: dict[str, Any] | None = None,
    fake_fill_mode: str = "accepted",
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
        "execution_context": execution_context or {},
        "post_trade_context": post_trade_context or {},
        "fake_fill_mode": fake_fill_mode,
        "research_asset_context": research_asset_context or {},
    }
    if execution_snapshot is not None:
        payload["execution_snapshot"] = execution_snapshot
    if trading_state_path is not None:
        payload["trading_state_path"] = trading_state_path
    result = post_trade_graph.invoke(payload)
    return dict(result)
