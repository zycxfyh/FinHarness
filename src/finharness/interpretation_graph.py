"""LangGraph workflow for fourth-layer source-backed interpretation."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from finharness.events import EventRecord, EventSnapshot
from finharness.events_graph import run_events_graph
from finharness.interpretation import (
    InterpretationSourceSpec,
    build_interpretation_quality,
    extract_candidate_events,
    interpret_event_record,
    persist_interpretation_bundle,
)


class InterpretationGraphState(TypedDict, total=False):
    universe: list[str]
    forms: list[str]
    max_records: int
    market_snapshot_refs: list[str]
    indicator_snapshot_refs: list[str]
    event_snapshot: dict[str, Any]
    source: dict[str, Any]
    candidate_events: list[dict[str, Any]]
    interpreted_records: list[dict[str, Any]]
    scenarios: dict[str, Any]
    counterevidence: dict[str, Any]
    quality: dict[str, Any]
    lineage: dict[str, Any]
    snapshot: dict[str, Any]
    receipt: dict[str, Any]
    consumer_handoff: dict[str, Any]
    review_hook: dict[str, Any]
    final: dict[str, Any]


def source_config_node(state: InterpretationGraphState) -> InterpretationGraphState:
    source = InterpretationSourceSpec(
        config={
            "universe": state.get("universe"),
            "forms": state.get("forms", ["8-K", "10-Q", "10-K"]),
            "max_records": state.get("max_records", 30),
            "market_snapshot_refs": state.get("market_snapshot_refs", []),
            "indicator_snapshot_refs": state.get("indicator_snapshot_refs", []),
        }
    )
    return {"source": source.model_dump(mode="json")}


def load_event_snapshot_node(state: InterpretationGraphState) -> InterpretationGraphState:
    if "event_snapshot" in state:
        return {"event_snapshot": state["event_snapshot"]}
    result = run_events_graph(
        universe=state.get("universe"),
        forms=state.get("forms"),
        per_symbol_limit=40,
        linked_market_snapshot_refs=state.get("market_snapshot_refs", []),
        linked_indicator_snapshot_refs=state.get("indicator_snapshot_refs", []),
    )
    return {"event_snapshot": result["snapshot"]}


def extract_candidate_events_node(
    state: InterpretationGraphState,
) -> InterpretationGraphState:
    snapshot = EventSnapshot.model_validate(state["event_snapshot"])
    candidates = extract_candidate_events(
        snapshot,
        event_types=state.get("forms", ["8-K", "10-Q", "10-K"]),
        max_records=state.get("max_records", 30),
    )
    return {"candidate_events": [record.model_dump(mode="json") for record in candidates]}


def interpret_impact_paths_node(
    state: InterpretationGraphState,
) -> InterpretationGraphState:
    records = [
        interpret_event_record(EventRecord.model_validate(record))
        for record in state["candidate_events"]
    ]
    return {"interpreted_records": [record.model_dump(mode="json") for record in records]}


def build_scenarios_node(state: InterpretationGraphState) -> InterpretationGraphState:
    return {
        "scenarios": {
            "status": "built",
            "record_count": len(state["interpreted_records"]),
        }
    }


def check_counterevidence_node(state: InterpretationGraphState) -> InterpretationGraphState:
    missing = [
        record["interpretation_id"]
        for record in state["interpreted_records"]
        if not record.get("counterevidence")
    ]
    return {"counterevidence": {"status": "checked", "missing": missing}}


def quality_node(state: InterpretationGraphState) -> InterpretationGraphState:
    from finharness.interpretation import InterpretationRecord

    records = [
        InterpretationRecord.model_validate(record) for record in state["interpreted_records"]
    ]
    quality = build_interpretation_quality(records)
    return {"quality": quality.model_dump(mode="json")}


def lineage_node(state: InterpretationGraphState) -> InterpretationGraphState:
    return {
        "lineage": {
            "status": "pending_persist",
            "note": "hashes and refs are finalized in snapshot/receipt persistence",
        }
    }


def snapshot_node(state: InterpretationGraphState) -> InterpretationGraphState:
    from finharness.interpretation import InterpretationRecord

    event_snapshot = EventSnapshot.model_validate(state["event_snapshot"])
    source = InterpretationSourceSpec(**state["source"])
    records = [
        InterpretationRecord.model_validate(record) for record in state["interpreted_records"]
    ]
    bundle = persist_interpretation_bundle(
        source=source,
        input_event_snapshot=event_snapshot,
        records=records,
        market_snapshot_refs=state.get("market_snapshot_refs", []),
        indicator_snapshot_refs=state.get("indicator_snapshot_refs", []),
    )
    return {
        "snapshot": bundle.snapshot.model_dump(mode="json"),
        "receipt": bundle.receipt.model_dump(mode="json"),
        "lineage": bundle.lineage.model_dump(mode="json"),
        "quality": bundle.quality.model_dump(mode="json"),
    }


def receipt_node(state: InterpretationGraphState) -> InterpretationGraphState:
    return {"receipt": state["receipt"]}


def consumer_handoff_node(state: InterpretationGraphState) -> InterpretationGraphState:
    snapshot = state["snapshot"]
    return {
        "consumer_handoff": {
            "consumer": "hypothesis_review_risk_note",
            "record_count": snapshot["record_count"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "allowed_outputs": [
                "watch questions",
                "hypothesis candidates",
                "risk review prompts",
            ],
            "forbidden_outputs": [
                "orders",
                "position sizing",
                "broker instructions",
                "execution permission",
            ],
        }
    }


def review_hook_node(state: InterpretationGraphState) -> InterpretationGraphState:
    snapshot = state["snapshot"]
    return {
        "review_hook": {
            "status": "open",
            "questions": snapshot["review_questions"],
            "next_review": "human interpretation review before hypothesis promotion",
            "promote_to": ["docs/reviews/", "docs/lessons/", "hypothesis candidates"],
        }
    }


def final_node(state: InterpretationGraphState) -> InterpretationGraphState:
    snapshot = state["snapshot"]
    return {
        "final": {
            "workflow": "langgraph_interpretation_v1",
            "input_event_snapshot_id": snapshot["input_event_snapshot_id"],
            "record_count": snapshot["record_count"],
            "quality_ok": snapshot["quality"]["ok"],
            "execution_allowed": snapshot["execution_allowed"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "hypothesis_candidates": snapshot["hypothesis_candidates"],
            "review_questions": snapshot["review_questions"],
            "consumer_handoff": state["consumer_handoff"],
            "review_hook": state["review_hook"],
        }
    }


def build_interpretation_graph():
    graph = StateGraph(InterpretationGraphState)
    graph.add_node("source_config", source_config_node)
    graph.add_node("load_event_snapshot", load_event_snapshot_node)
    graph.add_node("extract_candidate_events", extract_candidate_events_node)
    graph.add_node("interpret_impact_paths", interpret_impact_paths_node)
    graph.add_node("build_scenarios", build_scenarios_node)
    graph.add_node("check_counterevidence", check_counterevidence_node)
    graph.add_node("quality", quality_node)
    graph.add_node("lineage", lineage_node)
    graph.add_node("snapshot", snapshot_node)
    graph.add_node("receipt", receipt_node)
    graph.add_node("consumer_handoff", consumer_handoff_node)
    graph.add_node("review_hook", review_hook_node)
    graph.add_node("final", final_node)
    graph.add_edge(START, "source_config")
    graph.add_edge("source_config", "load_event_snapshot")
    graph.add_edge("load_event_snapshot", "extract_candidate_events")
    graph.add_edge("extract_candidate_events", "interpret_impact_paths")
    graph.add_edge("interpret_impact_paths", "build_scenarios")
    graph.add_edge("build_scenarios", "check_counterevidence")
    graph.add_edge("check_counterevidence", "quality")
    graph.add_edge("quality", "lineage")
    graph.add_edge("lineage", "snapshot")
    graph.add_edge("snapshot", "receipt")
    graph.add_edge("receipt", "consumer_handoff")
    graph.add_edge("consumer_handoff", "review_hook")
    graph.add_edge("review_hook", "final")
    graph.add_edge("final", END)
    return graph.compile()


interpretation_graph = build_interpretation_graph()


def run_interpretation_graph(
    *,
    universe: list[str] | None = None,
    forms: list[str] | None = None,
    max_records: int = 30,
    event_snapshot: dict[str, Any] | None = None,
    market_snapshot_refs: list[str] | None = None,
    indicator_snapshot_refs: list[str] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "universe": universe,
        "forms": forms or ["8-K", "10-Q", "10-K"],
        "max_records": max_records,
        "market_snapshot_refs": market_snapshot_refs or [],
        "indicator_snapshot_refs": indicator_snapshot_refs or [],
    }
    if event_snapshot is not None:
        payload["event_snapshot"] = event_snapshot
    result = interpretation_graph.invoke(payload)
    return dict(result)
