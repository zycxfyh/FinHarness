"""LangGraph workflow for the third-layer SEC EDGAR events slice."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from finharness.events import (
    DEFAULT_FORMS,
    DEFAULT_UNIVERSE,
    EventSourceSpec,
    build_event_quality,
    context_symbols_from_universe,
    fetch_sec_edgar_raw_payloads,
    filing_symbols_from_universe,
    normalize_sec_edgar_records,
    normalize_symbol,
    persist_event_bundle,
)


class EventsGraphState(TypedDict, total=False):
    universe: list[str]
    forms: list[str]
    per_symbol_limit: int
    timeout: float
    linked_market_snapshot_refs: list[str]
    linked_indicator_snapshot_refs: list[str]
    source: dict[str, Any]
    raw_payloads: dict[str, dict[str, Any]]
    records: list[dict[str, Any]]
    quality: dict[str, Any]
    lineage: dict[str, Any]
    snapshot: dict[str, Any]
    receipt: dict[str, Any]
    consumer_handoff: dict[str, Any]
    review_hook: dict[str, Any]
    final: dict[str, Any]


def source_config_node(state: EventsGraphState) -> EventsGraphState:
    universe = [normalize_symbol(symbol) for symbol in state.get("universe", DEFAULT_UNIVERSE)]
    filing_symbols = filing_symbols_from_universe(universe)
    context_symbols = context_symbols_from_universe(universe)
    forms = state.get("forms", DEFAULT_FORMS)
    source = EventSourceSpec(
        fetch_config={
            "universe": universe,
            "filing_symbols": filing_symbols,
            "context_symbols": context_symbols,
            "forms": forms,
            "per_symbol_limit": state.get("per_symbol_limit", 40),
            "linked_market_snapshot_refs": state.get("linked_market_snapshot_refs", []),
            "linked_indicator_snapshot_refs": state.get("linked_indicator_snapshot_refs", []),
        }
    )
    return {
        "universe": universe,
        "forms": forms,
        "source": source.model_dump(mode="json"),
    }


def fetch_sec_edgar_node(state: EventsGraphState) -> EventsGraphState:
    raw_payloads = fetch_sec_edgar_raw_payloads(
        universe=state["universe"],
        timeout=state.get("timeout", 20.0),
    )
    return {"raw_payloads": raw_payloads}


def normalize_filings_node(state: EventsGraphState) -> EventsGraphState:
    records = normalize_sec_edgar_records(
        state["raw_payloads"],
        forms=state.get("forms", DEFAULT_FORMS),
        per_symbol_limit=state.get("per_symbol_limit", 40),
    )
    return {"records": [record.model_dump(mode="json") for record in records]}


def quality_node(state: EventsGraphState) -> EventsGraphState:
    records = normalize_sec_edgar_records(
        state["raw_payloads"],
        forms=state.get("forms", DEFAULT_FORMS),
        per_symbol_limit=state.get("per_symbol_limit", 40),
    )
    quality = build_event_quality(records)
    return {"quality": quality.model_dump(mode="json")}


def lineage_node(state: EventsGraphState) -> EventsGraphState:
    return {
        "lineage": {
            "status": "pending_persist",
            "note": "hashes and refs are finalized in snapshot/receipt persistence",
        }
    }


def snapshot_node(state: EventsGraphState) -> EventsGraphState:
    records = normalize_sec_edgar_records(
        state["raw_payloads"],
        forms=state.get("forms", DEFAULT_FORMS),
        per_symbol_limit=state.get("per_symbol_limit", 40),
    )
    source = EventSourceSpec(**state["source"])
    bundle = persist_event_bundle(
        source=source,
        raw_payloads=state["raw_payloads"],
        records=records,
        universe=state["universe"],
        filing_symbols=filing_symbols_from_universe(state["universe"]),
        context_symbols=context_symbols_from_universe(state["universe"]),
        linked_market_snapshot_refs=state.get("linked_market_snapshot_refs", []),
        linked_indicator_snapshot_refs=state.get("linked_indicator_snapshot_refs", []),
    )
    return {
        "snapshot": bundle.snapshot.model_dump(mode="json"),
        "receipt": bundle.receipt.model_dump(mode="json"),
        "lineage": bundle.lineage.model_dump(mode="json"),
        "quality": bundle.quality.model_dump(mode="json"),
    }


def receipt_node(state: EventsGraphState) -> EventsGraphState:
    return {
        "receipt": state["receipt"],
    }


def consumer_handoff_node(state: EventsGraphState) -> EventsGraphState:
    snapshot = state["snapshot"]
    return {
        "consumer_handoff": {
            "consumer": "daily_virtual_training_review",
            "event_count": snapshot["event_count"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "allowed_outputs": [
                "human review questions",
                "hypothesis candidates",
                "watch items",
            ],
            "forbidden_outputs": [
                "orders",
                "position changes",
                "execution permission",
            ],
        }
    }


def review_hook_node(state: EventsGraphState) -> EventsGraphState:
    snapshot = state["snapshot"]
    return {
        "review_hook": {
            "status": "open",
            "questions": snapshot["review_questions"],
            "next_review": "daily virtual training review",
            "promote_to": [
                "docs/reviews/",
                "docs/lessons/",
                "hypothesis candidates",
            ],
        }
    }


def final_node(state: EventsGraphState) -> EventsGraphState:
    snapshot = state["snapshot"]
    return {
        "final": {
            "workflow": "langgraph_events_sec_edgar_v1",
            "universe": snapshot["universe"],
            "filing_symbols": snapshot["filing_symbols"],
            "context_symbols": snapshot["context_symbols"],
            "event_count": snapshot["event_count"],
            "execution_allowed": snapshot["execution_allowed"],
            "quality_ok": snapshot["quality"]["ok"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "review_questions": snapshot["review_questions"],
            "consumer_handoff": state["consumer_handoff"],
            "review_hook": state["review_hook"],
        }
    }


def build_events_graph():
    graph = StateGraph(EventsGraphState)
    graph.add_node("source_config", source_config_node)
    graph.add_node("fetch_sec_edgar", fetch_sec_edgar_node)
    graph.add_node("normalize_filings", normalize_filings_node)
    graph.add_node("quality", quality_node)
    graph.add_node("lineage", lineage_node)
    graph.add_node("snapshot", snapshot_node)
    graph.add_node("receipt", receipt_node)
    graph.add_node("consumer_handoff", consumer_handoff_node)
    graph.add_node("review_hook", review_hook_node)
    graph.add_node("final", final_node)
    graph.add_edge(START, "source_config")
    graph.add_edge("source_config", "fetch_sec_edgar")
    graph.add_edge("fetch_sec_edgar", "normalize_filings")
    graph.add_edge("normalize_filings", "quality")
    graph.add_edge("quality", "lineage")
    graph.add_edge("lineage", "snapshot")
    graph.add_edge("snapshot", "receipt")
    graph.add_edge("receipt", "consumer_handoff")
    graph.add_edge("consumer_handoff", "review_hook")
    graph.add_edge("review_hook", "final")
    graph.add_edge("final", END)
    return graph.compile()


events_graph = build_events_graph()


def run_events_graph(
    *,
    universe: list[str] | None = None,
    forms: list[str] | None = None,
    per_symbol_limit: int = 40,
    timeout: float = 20.0,
    linked_market_snapshot_refs: list[str] | None = None,
    linked_indicator_snapshot_refs: list[str] | None = None,
) -> dict[str, Any]:
    result = events_graph.invoke(
        {
            "universe": universe or DEFAULT_UNIVERSE,
            "forms": forms or DEFAULT_FORMS,
            "per_symbol_limit": per_symbol_limit,
            "timeout": timeout,
            "linked_market_snapshot_refs": linked_market_snapshot_refs or [],
            "linked_indicator_snapshot_refs": linked_indicator_snapshot_refs or [],
        }
    )
    return dict(result)
