"""LangGraph workflow that bundles the first four FinHarness evidence layers."""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from finharness.daily_evidence import (
    DailyEvidenceReceipt,
    persist_daily_evidence_receipt,
    write_daily_evidence_review,
)
from finharness.events import DEFAULT_FORMS, DEFAULT_UNIVERSE, context_symbols_from_universe
from finharness.events_graph import run_events_graph
from finharness.indicator_graph import run_indicator_graph
from finharness.interpretation_graph import run_interpretation_graph
from finharness.market_data_graph import run_market_data_graph


class DailyEvidenceGraphState(TypedDict, total=False):
    universe: list[str]
    market_symbols: list[str]
    start: str
    end: str
    forms: list[str]
    per_symbol_limit: int
    max_records: int
    ma_fast: int
    ma_slow: int
    source: dict[str, Any]
    market_data_results: list[dict[str, Any]]
    indicator_results: list[dict[str, Any]]
    events_result: dict[str, Any]
    interpretation_result: dict[str, Any]
    quality_gate: dict[str, Any]
    evidence_bundle: dict[str, Any]
    snapshot: dict[str, Any]
    receipt: dict[str, Any]
    review_hook: dict[str, Any]
    final: dict[str, Any]


def _refs(results: list[dict[str, Any]], snapshot_key: str, id_key: str) -> list[str]:
    refs = []
    for result in results:
        snapshot = result.get(snapshot_key) or {}
        ref = snapshot.get("payload_ref") or snapshot.get(id_key)
        if ref:
            refs.append(str(ref))
    return refs


def _quality_ok(results: list[dict[str, Any]]) -> bool:
    return all(bool(result.get("final", {}).get("quality_ok")) for result in results)


def _route_quality(state: DailyEvidenceGraphState) -> str:
    return "continue" if state["quality_gate"]["ok"] else "failed"


def _route_events_quality(state: DailyEvidenceGraphState) -> str:
    if not state["quality_gate"]["ok"]:
        return "failed"
    if state["quality_gate"].get("event_count", 0) == 0:
        return "empty"
    return "continue"


def _market_snapshot_refs(state: DailyEvidenceGraphState) -> list[str]:
    return _refs(state.get("market_data_results", []), "snapshot", "snapshot_id")


def _indicator_snapshot_refs(state: DailyEvidenceGraphState) -> list[str]:
    return _refs(state.get("indicator_results", []), "snapshot", "indicator_snapshot_id")


def _layer_summaries(state: DailyEvidenceGraphState) -> dict[str, Any]:
    return {
        "market_data": [result.get("final", {}) for result in state.get("market_data_results", [])],
        "indicators": [result.get("final", {}) for result in state.get("indicator_results", [])],
        "events": (state.get("events_result") or {}).get("final"),
        "interpretation": (state.get("interpretation_result") or {}).get("final"),
    }


def _layer_quality(state: DailyEvidenceGraphState) -> dict[str, bool]:
    layer_quality = {
        "market_data": _quality_ok(state.get("market_data_results", [])),
        "indicators": _quality_ok(state.get("indicator_results", [])),
    }
    if state.get("events_result"):
        layer_quality["events"] = bool(state["events_result"]["final"].get("quality_ok"))
    if state.get("interpretation_result"):
        layer_quality["interpretation"] = bool(
            state["interpretation_result"]["final"].get("quality_ok")
        )
    return layer_quality


def source_config_node(state: DailyEvidenceGraphState) -> DailyEvidenceGraphState:
    universe = [symbol.upper() for symbol in state.get("universe", DEFAULT_UNIVERSE)]
    market_symbols = state.get("market_symbols") or context_symbols_from_universe(universe)
    if not market_symbols:
        market_symbols = ["SPY"]
    return {
        "universe": universe,
        "market_symbols": [symbol.upper() for symbol in market_symbols],
        "start": state.get("start", "2025-01-01"),
        "end": state.get("end", "2025-06-30"),
        "forms": state.get("forms", DEFAULT_FORMS),
        "per_symbol_limit": state.get("per_symbol_limit", 40),
        "max_records": state.get("max_records", 30),
        "ma_fast": state.get("ma_fast", 20),
        "ma_slow": state.get("ma_slow", 50),
        "source": {
            "workflow": "daily_evidence_graph",
            "layers": ["market_data", "indicators", "events", "interpretation"],
            "execution_allowed": False,
        },
    }


def market_data_node(state: DailyEvidenceGraphState) -> DailyEvidenceGraphState:
    results = [
        run_market_data_graph(
            symbol=symbol,
            start=state["start"],
            end=state["end"],
            write_catalog=False,
        )
        for symbol in state["market_symbols"]
    ]
    return {"market_data_results": results}


def market_quality_gate_node(state: DailyEvidenceGraphState) -> DailyEvidenceGraphState:
    ok = _quality_ok(state.get("market_data_results", []))
    return {
        "quality_gate": {
            "layer": "market_data",
            "ok": ok,
            "failed_layers": [] if ok else ["market_data"],
        }
    }


def indicators_node(state: DailyEvidenceGraphState) -> DailyEvidenceGraphState:
    results = []
    for market_result in state["market_data_results"]:
        final = market_result["final"]
        results.append(
            run_indicator_graph(
                symbol=final["symbol"],
                start=state["start"],
                end=state["end"],
                ma_fast=state["ma_fast"],
                ma_slow=state["ma_slow"],
                market_data_snapshot=market_result["snapshot"],
                history_records=market_result["normalized_records"],
            )
        )
    return {"indicator_results": results}


def indicator_quality_gate_node(state: DailyEvidenceGraphState) -> DailyEvidenceGraphState:
    ok = _quality_ok(state.get("indicator_results", []))
    return {
        "quality_gate": {
            "layer": "indicators",
            "ok": ok,
            "failed_layers": [] if ok else ["indicators"],
        }
    }


def events_node(state: DailyEvidenceGraphState) -> DailyEvidenceGraphState:
    result = run_events_graph(
        universe=state["universe"],
        forms=state["forms"],
        per_symbol_limit=state["per_symbol_limit"],
        linked_market_snapshot_refs=_market_snapshot_refs(state),
        linked_indicator_snapshot_refs=_indicator_snapshot_refs(state),
    )
    return {"events_result": result}


def events_quality_gate_node(state: DailyEvidenceGraphState) -> DailyEvidenceGraphState:
    final = state["events_result"]["final"]
    ok = bool(final.get("quality_ok"))
    return {
        "quality_gate": {
            "layer": "events",
            "ok": ok,
            "event_count": final.get("event_count", 0),
            "failed_layers": [] if ok else ["events"],
        }
    }


def interpretation_node(state: DailyEvidenceGraphState) -> DailyEvidenceGraphState:
    result = run_interpretation_graph(
        universe=state["universe"],
        forms=state["forms"],
        max_records=state["max_records"],
        event_snapshot=state["events_result"]["snapshot"],
        market_snapshot_refs=_market_snapshot_refs(state),
        indicator_snapshot_refs=_indicator_snapshot_refs(state),
    )
    return {"interpretation_result": result}


def interpretation_quality_gate_node(
    state: DailyEvidenceGraphState,
) -> DailyEvidenceGraphState:
    ok = bool(state["interpretation_result"]["final"].get("quality_ok"))
    return {
        "quality_gate": {
            "layer": "interpretation",
            "ok": ok,
            "failed_layers": [] if ok else ["interpretation"],
        }
    }


def evidence_bundle_node(state: DailyEvidenceGraphState) -> DailyEvidenceGraphState:
    return {
        "evidence_bundle": {
            "layer_summaries": _layer_summaries(state),
            "market_snapshot_refs": _market_snapshot_refs(state),
            "indicator_snapshot_refs": _indicator_snapshot_refs(state),
            "event_snapshot_ref": state["events_result"]["snapshot"]["payload_ref"],
            "interpretation_snapshot_ref": state["interpretation_result"]["snapshot"][
                "payload_ref"
            ],
            "execution_allowed": False,
        }
    }


def no_events_bundle_node(state: DailyEvidenceGraphState) -> DailyEvidenceGraphState:
    return {
        "evidence_bundle": {
            "layer_summaries": _layer_summaries(state),
            "market_snapshot_refs": _market_snapshot_refs(state),
            "indicator_snapshot_refs": _indicator_snapshot_refs(state),
            "event_snapshot_ref": state["events_result"]["snapshot"]["payload_ref"],
            "interpretation_snapshot_ref": None,
            "execution_allowed": False,
            "status": "warning",
            "notes": ["events layer produced no candidate records; interpretation skipped"],
        }
    }


def receipt_node(state: DailyEvidenceGraphState) -> DailyEvidenceGraphState:
    bundle = state["evidence_bundle"]
    receipt = persist_daily_evidence_receipt(
        universe=state["universe"],
        market_symbols=state["market_symbols"],
        layer_summaries=bundle["layer_summaries"],
        layer_quality=_layer_quality(state),
        market_snapshot_refs=bundle["market_snapshot_refs"],
        indicator_snapshot_refs=bundle["indicator_snapshot_refs"],
        event_snapshot_ref=bundle["event_snapshot_ref"],
        interpretation_snapshot_ref=bundle["interpretation_snapshot_ref"],
        status=bundle.get("status", "ok"),
        notes=bundle.get("notes"),
    )
    return {
        "snapshot": receipt.snapshot.model_dump(mode="json"),
        "receipt": receipt.model_dump(mode="json"),
    }


def failed_receipt_node(state: DailyEvidenceGraphState) -> DailyEvidenceGraphState:
    gate = state["quality_gate"]
    event_snapshot_ref = None
    interpretation_snapshot_ref = None
    if state.get("events_result"):
        event_snapshot_ref = state["events_result"].get("snapshot", {}).get("payload_ref")
    if state.get("interpretation_result"):
        interpretation_snapshot_ref = (
            state["interpretation_result"].get("snapshot", {}).get("payload_ref")
        )
    receipt = persist_daily_evidence_receipt(
        universe=state["universe"],
        market_symbols=state["market_symbols"],
        layer_summaries=_layer_summaries(state),
        layer_quality=_layer_quality(state),
        market_snapshot_refs=_market_snapshot_refs(state),
        indicator_snapshot_refs=_indicator_snapshot_refs(state),
        event_snapshot_ref=event_snapshot_ref,
        interpretation_snapshot_ref=interpretation_snapshot_ref,
        status="failed",
        notes=[f"quality gate failed at layer: {gate['layer']}"],
    )
    return {
        "snapshot": receipt.snapshot.model_dump(mode="json"),
        "receipt": receipt.model_dump(mode="json"),
    }


def review_hook_node(state: DailyEvidenceGraphState) -> DailyEvidenceGraphState:
    snapshot = state["snapshot"]
    review_ref = write_daily_evidence_review(DailyEvidenceReceipt.model_validate(state["receipt"]))
    return {
        "review_hook": {
            "status": "open",
            "questions": snapshot["review_questions"],
            "next_review": "daily virtual training review",
            "promote_to": ["docs/reviews/", "docs/lessons/", "hypotheses layer"],
            "review_ref": review_ref,
        }
    }


def final_node(state: DailyEvidenceGraphState) -> DailyEvidenceGraphState:
    snapshot = state["snapshot"]
    return {
        "final": {
            "workflow": "langgraph_daily_evidence_v1",
            "status": state["receipt"]["status"],
            "quality_ok": snapshot["quality"]["ok"],
            "failed_layers": snapshot["quality"]["failed_layers"],
            "daily_evidence_snapshot_id": snapshot["daily_evidence_snapshot_id"],
            "market_snapshot_refs": snapshot["lineage"]["market_snapshot_refs"],
            "indicator_snapshot_refs": snapshot["lineage"]["indicator_snapshot_refs"],
            "event_snapshot_ref": snapshot["lineage"]["event_snapshot_ref"],
            "interpretation_snapshot_ref": snapshot["lineage"]["interpretation_snapshot_ref"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "execution_allowed": snapshot["execution_allowed"],
            "review_hook": state["review_hook"],
        }
    }


def build_daily_evidence_graph():
    graph = StateGraph(DailyEvidenceGraphState)
    graph.add_node("source_config", source_config_node)
    graph.add_node("market_data", market_data_node)
    graph.add_node("market_quality_gate", market_quality_gate_node)
    graph.add_node("indicators", indicators_node)
    graph.add_node("indicator_quality_gate", indicator_quality_gate_node)
    graph.add_node("events", events_node)
    graph.add_node("events_quality_gate", events_quality_gate_node)
    graph.add_node("interpretation", interpretation_node)
    graph.add_node("interpretation_quality_gate", interpretation_quality_gate_node)
    graph.add_node("evidence_bundle", evidence_bundle_node)
    graph.add_node("no_events_bundle", no_events_bundle_node)
    graph.add_node("receipt", receipt_node)
    graph.add_node("failed_receipt", failed_receipt_node)
    graph.add_node("review_hook", review_hook_node)
    graph.add_node("final", final_node)

    graph.add_edge(START, "source_config")
    graph.add_edge("source_config", "market_data")
    graph.add_edge("market_data", "market_quality_gate")
    graph.add_conditional_edges(
        "market_quality_gate",
        _route_quality,
        {"continue": "indicators", "failed": "failed_receipt"},
    )
    graph.add_edge("indicators", "indicator_quality_gate")
    graph.add_conditional_edges(
        "indicator_quality_gate",
        _route_quality,
        {"continue": "events", "failed": "failed_receipt"},
    )
    graph.add_edge("events", "events_quality_gate")
    graph.add_conditional_edges(
        "events_quality_gate",
        _route_events_quality,
        {
            "continue": "interpretation",
            "empty": "no_events_bundle",
            "failed": "failed_receipt",
        },
    )
    graph.add_edge("interpretation", "interpretation_quality_gate")
    graph.add_conditional_edges(
        "interpretation_quality_gate",
        _route_quality,
        {"continue": "evidence_bundle", "failed": "failed_receipt"},
    )
    graph.add_edge("evidence_bundle", "receipt")
    graph.add_edge("no_events_bundle", "receipt")
    graph.add_edge("receipt", "review_hook")
    graph.add_edge("failed_receipt", "review_hook")
    graph.add_edge("review_hook", "final")
    graph.add_edge("final", END)
    return graph.compile()


daily_evidence_graph = build_daily_evidence_graph()


def run_daily_evidence_graph(
    *,
    universe: list[str] | None = None,
    market_symbols: list[str] | None = None,
    start: str = "2025-01-01",
    end: str = "2025-06-30",
    forms: list[str] | None = None,
    per_symbol_limit: int = 40,
    max_records: int = 30,
    ma_fast: int = 20,
    ma_slow: int = 50,
) -> dict[str, Any]:
    payload = {
        "universe": universe or DEFAULT_UNIVERSE,
        "market_symbols": market_symbols,
        "start": start,
        "end": end,
        "forms": forms or DEFAULT_FORMS,
        "per_symbol_limit": per_symbol_limit,
        "max_records": max_records,
        "ma_fast": ma_fast,
        "ma_slow": ma_slow,
    }
    result = daily_evidence_graph.invoke(payload)
    return dict(result)
