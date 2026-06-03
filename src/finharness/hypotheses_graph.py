"""LangGraph workflow for fifth-layer falsifiable hypotheses."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from finharness.hypotheses import (
    HermesHypothesisDraftProvider,
    HypothesisRecord,
    HypothesisSourceSpec,
    build_hypothesis_quality,
    formulate_hypothesis_record,
    persist_hypothesis_bundle,
    select_hypothesis_candidates,
)
from finharness.interpretation import InterpretationRecord, InterpretationSnapshot
from finharness.interpretation_graph import run_interpretation_graph
from finharness.research_assets import compact_research_asset_context


class HypothesesGraphState(TypedDict, total=False):
    universe: list[str]
    forms: list[str]
    max_records: int
    max_hypotheses: int
    symbols: list[str]
    llm_enabled: bool
    hermes_root: str
    research_asset_context: dict[str, Any]
    interpretation_snapshot: dict[str, Any]
    source: dict[str, Any]
    candidate_interpretations: list[dict[str, Any]]
    hypothesis_records: list[dict[str, Any]]
    disconfirming_evidence: dict[str, Any]
    validation_plan: dict[str, Any]
    quality: dict[str, Any]
    lineage: dict[str, Any]
    snapshot: dict[str, Any]
    receipt: dict[str, Any]
    consumer_handoff: dict[str, Any]
    review_hook: dict[str, Any]
    final: dict[str, Any]


def source_config_node(state: HypothesesGraphState) -> HypothesesGraphState:
    llm_enabled = bool(state.get("llm_enabled", False))
    source = HypothesisSourceSpec(
        llm_provider="hermes-agent" if llm_enabled else None,
        llm_interface="HermesHypothesisDraftProvider" if llm_enabled else None,
        llm_enabled=llm_enabled,
        hermes_root=state.get("hermes_root", "/root/projects/hermes-agent"),
        config={
            "universe": state.get("universe"),
            "forms": state.get("forms", ["8-K", "10-Q", "10-K"]),
            "max_records": state.get("max_records", 30),
            "max_hypotheses": state.get("max_hypotheses", 10),
            "symbols": state.get("symbols", []),
            "research_asset_context": compact_research_asset_context(
                state.get("research_asset_context"), "L5"
            ),
        },
    )
    return {"source": source.model_dump(mode="json")}


def load_interpretation_snapshot_node(state: HypothesesGraphState) -> HypothesesGraphState:
    if "interpretation_snapshot" in state:
        return {"interpretation_snapshot": state["interpretation_snapshot"]}
    result = run_interpretation_graph(
        universe=state.get("universe"),
        forms=state.get("forms"),
        max_records=state.get("max_records", 30),
    )
    return {"interpretation_snapshot": result["snapshot"]}


def select_hypothesis_candidates_node(state: HypothesesGraphState) -> HypothesesGraphState:
    snapshot = InterpretationSnapshot.model_validate(state["interpretation_snapshot"])
    candidates = select_hypothesis_candidates(
        snapshot,
        max_hypotheses=state.get("max_hypotheses", 10),
        symbols=state.get("symbols") or None,
    )
    return {
        "candidate_interpretations": [
            record.model_dump(mode="json") for record in candidates
        ]
    }


def formulate_hypotheses_node(state: HypothesesGraphState) -> HypothesesGraphState:
    llm_enabled = bool(state.get("llm_enabled", False))
    provider = (
        HermesHypothesisDraftProvider(
            hermes_root=state.get("hermes_root", "/root/projects/hermes-agent")
        )
        if llm_enabled
        else None
    )
    records = [
        formulate_hypothesis_record(
            InterpretationRecord.model_validate(record),
            draft_provider=provider,
        )
        for record in state["candidate_interpretations"]
    ]
    return {"hypothesis_records": [record.model_dump(mode="json") for record in records]}


def attach_disconfirming_evidence_node(
    state: HypothesesGraphState,
) -> HypothesesGraphState:
    missing = [
        record["hypothesis_id"]
        for record in state["hypothesis_records"]
        if not record.get("disconfirming_observations")
    ]
    return {
        "disconfirming_evidence": {
            "status": "checked",
            "missing": missing,
        }
    }


def attach_validation_plan_node(state: HypothesesGraphState) -> HypothesesGraphState:
    missing = [
        record["hypothesis_id"]
        for record in state["hypothesis_records"]
        if not record.get("validation_plan")
    ]
    return {
        "validation_plan": {
            "status": "checked",
            "missing": missing,
        }
    }


def quality_node(state: HypothesesGraphState) -> HypothesesGraphState:
    records = [
        HypothesisRecord.model_validate(record) for record in state["hypothesis_records"]
    ]
    quality = build_hypothesis_quality(records)
    return {"quality": quality.model_dump(mode="json")}


def lineage_node(state: HypothesesGraphState) -> HypothesesGraphState:
    return {
        "lineage": {
            "status": "pending_persist",
            "note": "hashes and refs are finalized in snapshot/receipt persistence",
        }
    }


def snapshot_node(state: HypothesesGraphState) -> HypothesesGraphState:
    snapshot = InterpretationSnapshot.model_validate(state["interpretation_snapshot"])
    source = HypothesisSourceSpec(**state["source"])
    records = [
        HypothesisRecord.model_validate(record) for record in state["hypothesis_records"]
    ]
    bundle = persist_hypothesis_bundle(
        source=source,
        input_interpretation_snapshot=snapshot,
        records=records,
    )
    return {
        "snapshot": bundle.snapshot.model_dump(mode="json"),
        "receipt": bundle.receipt.model_dump(mode="json"),
        "lineage": bundle.lineage.model_dump(mode="json"),
        "quality": bundle.quality.model_dump(mode="json"),
    }


def receipt_node(state: HypothesesGraphState) -> HypothesesGraphState:
    return {"receipt": state["receipt"]}


def consumer_handoff_node(state: HypothesesGraphState) -> HypothesesGraphState:
    snapshot = state["snapshot"]
    return {
        "consumer_handoff": {
            "consumer": "validation_layer",
            "record_count": snapshot["record_count"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "allowed_outputs": [
                "validation plans",
                "watch questions",
                "human review prompts",
                "hypothesis candidates for validation",
            ],
            "forbidden_outputs": [
                "orders",
                "position sizing",
                "broker instructions",
                "execution permission",
                "trade recommendation",
            ],
        }
    }


def review_hook_node(state: HypothesesGraphState) -> HypothesesGraphState:
    snapshot = state["snapshot"]
    return {
        "review_hook": {
            "status": "open",
            "questions": snapshot["review_questions"],
            "next_review": "human hypothesis review before validation promotion",
            "promote_to": ["validation layer", "docs/reviews/", "docs/lessons/"],
        }
    }


def final_node(state: HypothesesGraphState) -> HypothesesGraphState:
    snapshot = state["snapshot"]
    return {
        "final": {
            "workflow": "langgraph_hypotheses_v1",
            "input_interpretation_snapshot_id": (
                snapshot["input_interpretation_snapshot_id"]
            ),
            "record_count": snapshot["record_count"],
            "quality_ok": snapshot["quality"]["ok"],
            "execution_allowed": snapshot["execution_allowed"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "validation_handoff": snapshot["validation_handoff"],
            "review_questions": snapshot["review_questions"],
            "consumer_handoff": state["consumer_handoff"],
            "review_hook": state["review_hook"],
            "llm_enabled": state.get("source", {}).get("llm_enabled", False),
            "hermes_root": state.get("source", {}).get("hermes_root"),
        }
    }


def build_hypotheses_graph():
    graph = StateGraph(HypothesesGraphState)
    graph.add_node("source_config", source_config_node)
    graph.add_node("load_interpretation_snapshot", load_interpretation_snapshot_node)
    graph.add_node("select_hypothesis_candidates", select_hypothesis_candidates_node)
    graph.add_node("formulate_hypotheses", formulate_hypotheses_node)
    graph.add_node("attach_disconfirming_evidence", attach_disconfirming_evidence_node)
    graph.add_node("attach_validation_plan", attach_validation_plan_node)
    graph.add_node("quality", quality_node)
    graph.add_node("lineage", lineage_node)
    graph.add_node("snapshot", snapshot_node)
    graph.add_node("receipt", receipt_node)
    graph.add_node("consumer_handoff", consumer_handoff_node)
    graph.add_node("review_hook", review_hook_node)
    graph.add_node("final", final_node)
    graph.add_edge(START, "source_config")
    graph.add_edge("source_config", "load_interpretation_snapshot")
    graph.add_edge("load_interpretation_snapshot", "select_hypothesis_candidates")
    graph.add_edge("select_hypothesis_candidates", "formulate_hypotheses")
    graph.add_edge("formulate_hypotheses", "attach_disconfirming_evidence")
    graph.add_edge("attach_disconfirming_evidence", "attach_validation_plan")
    graph.add_edge("attach_validation_plan", "quality")
    graph.add_edge("quality", "lineage")
    graph.add_edge("lineage", "snapshot")
    graph.add_edge("snapshot", "receipt")
    graph.add_edge("receipt", "consumer_handoff")
    graph.add_edge("consumer_handoff", "review_hook")
    graph.add_edge("review_hook", "final")
    graph.add_edge("final", END)
    return graph.compile()


hypotheses_graph = build_hypotheses_graph()


def run_hypotheses_graph(
    *,
    universe: list[str] | None = None,
    forms: list[str] | None = None,
    max_records: int = 30,
    max_hypotheses: int = 10,
    symbols: list[str] | None = None,
    interpretation_snapshot: dict[str, Any] | None = None,
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
    if interpretation_snapshot is not None:
        payload["interpretation_snapshot"] = interpretation_snapshot
    result = hypotheses_graph.invoke(payload)
    return dict(result)
