"""LangGraph workflow for the second-layer indicator slice."""

from __future__ import annotations

from typing import Any, TypedDict

import pandas as pd
from langgraph.graph import END, START, StateGraph

from finharness.indicator_layer import (
    IndicatorSpec,
    build_indicator_quality,
    build_indicator_snapshot,
    clean_feature_row,
    compute_library_core_indicators,
)
from finharness.market_data import MarketDataSnapshot
from finharness.market_data_graph import run_market_data_graph


class IndicatorGraphState(TypedDict, total=False):
    symbol: str
    start: str
    end: str
    ma_fast: int
    ma_slow: int
    source: dict[str, Any]
    market_data: dict[str, Any]
    market_data_snapshot: dict[str, Any]
    history_records: list[dict[str, Any]]
    features: dict[str, Any]
    feature_records: list[dict[str, Any]]
    quality: dict[str, Any]
    lineage: dict[str, Any]
    snapshot: dict[str, Any]
    receipt: dict[str, Any]
    consumer_handoff: dict[str, Any]
    review_hook: dict[str, Any]
    final: dict[str, Any]


def _history_from_records(records: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(records)
    frame["date"] = pd.to_datetime(frame["date"])
    return frame


def source_config_node(state: IndicatorGraphState) -> IndicatorGraphState:
    return {
        "symbol": state.get("symbol", "SPY").upper(),
        "start": state.get("start", "2025-01-01"),
        "end": state.get("end", "2025-06-30"),
        "ma_fast": state.get("ma_fast", 20),
        "ma_slow": state.get("ma_slow", 50),
        "source": {
            "provider": "TA-Lib + pandas-ta",
            "input_layer": "market_data_graph",
            "dataset": "core_technical_indicators",
        },
    }


def load_market_data_node(state: IndicatorGraphState) -> IndicatorGraphState:
    if state.get("market_data_snapshot") and state.get("history_records"):
        return {
            "market_data": {
                "workflow": "langgraph_market_data_v1",
                "symbol": state["symbol"],
                "reused": True,
            },
            "history_records": state["history_records"],
            "market_data_snapshot": state["market_data_snapshot"],
        }
    market_data = run_market_data_graph(
        symbol=state["symbol"],
        start=state["start"],
        end=state["end"],
        write_catalog=False,
    )
    return {
        "market_data": market_data["final"],
        "history_records": market_data["normalized_records"],
        "market_data_snapshot": market_data["snapshot"],
    }


def compute_indicators_node(state: IndicatorGraphState) -> IndicatorGraphState:
    history = _history_from_records(state["history_records"])
    feature_frame, specs = compute_library_core_indicators(
        history,
        ma_fast=state["ma_fast"],
        ma_slow=state["ma_slow"],
    )
    latest = feature_frame.iloc[-1]
    return {
        "features": {
            "latest": clean_feature_row(latest),
            "indicator_specs": [spec.model_dump(mode="json") for spec in specs],
        },
        "feature_records": feature_frame.to_dict(orient="records"),
    }


def quality_node(state: IndicatorGraphState) -> IndicatorGraphState:
    feature_frame = pd.DataFrame(state["feature_records"])
    quality = build_indicator_quality(feature_frame)
    return {"quality": quality.model_dump(mode="json")}


def lineage_node(state: IndicatorGraphState) -> IndicatorGraphState:
    return {
        "lineage": {
            "status": "pending_persist",
            "input_market_data_snapshot_id": state["market_data_snapshot"]["snapshot_id"],
            "note": "indicator output hash/ref is finalized in snapshot/receipt persistence",
        }
    }


def snapshot_node(state: IndicatorGraphState) -> IndicatorGraphState:
    history = _history_from_records(state["history_records"])
    market_data_snapshot = MarketDataSnapshot.model_validate(state["market_data_snapshot"])
    feature_frame = pd.DataFrame(state["feature_records"])
    indicator_specs = [
        IndicatorSpec.model_validate(spec) for spec in state["features"]["indicator_specs"]
    ]
    receipt = build_indicator_snapshot(
        symbol=state["symbol"],
        history=history,
        market_data_snapshot=market_data_snapshot,
        ma_fast=state["ma_fast"],
        ma_slow=state["ma_slow"],
        feature_frame=feature_frame,
        indicator_specs=indicator_specs,
    )
    return {
        "snapshot": receipt.snapshot.model_dump(mode="json"),
        "receipt": receipt.model_dump(mode="json"),
        "lineage": receipt.snapshot.lineage.model_dump(mode="json"),
        "quality": receipt.snapshot.quality.model_dump(mode="json"),
    }


def receipt_node(state: IndicatorGraphState) -> IndicatorGraphState:
    return {"receipt": state["receipt"]}


def consumer_handoff_node(state: IndicatorGraphState) -> IndicatorGraphState:
    snapshot = state["snapshot"]
    return {
        "consumer_handoff": {
            "consumer": "events_interpretation_research_review",
            "symbol": snapshot["symbol"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "allowed_outputs": ["feature evidence", "hypothesis input", "review evidence"],
            "forbidden_outputs": ["orders", "position changes", "execution permission"],
        }
    }


def review_hook_node(state: IndicatorGraphState) -> IndicatorGraphState:
    return {
        "review_hook": {
            "status": "open",
            "questions": [
                "Are latest indicator values fully formed after warmup windows?",
                "Which feature states are worth watching next?",
                "Do indicators agree or conflict with market/event evidence?",
            ],
            "next_review": "daily evidence review",
        }
    }


def final_node(state: IndicatorGraphState) -> IndicatorGraphState:
    snapshot = state["snapshot"]
    return {
        "final": {
            "workflow": "langgraph_indicators_v1",
            "symbol": state["symbol"],
            "input_market_data_snapshot_id": state["market_data_snapshot"]["snapshot_id"],
            "indicator_snapshot_id": snapshot["indicator_snapshot_id"],
            "quality_ok": snapshot["quality"]["ok"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "execution_allowed": snapshot["execution_allowed"],
            "consumer_handoff": state["consumer_handoff"],
            "review_hook": state["review_hook"],
        }
    }


def build_indicator_graph():
    graph = StateGraph(IndicatorGraphState)
    graph.add_node("source_config", source_config_node)
    graph.add_node("load_market_data", load_market_data_node)
    graph.add_node("compute_indicators", compute_indicators_node)
    graph.add_node("quality", quality_node)
    graph.add_node("lineage", lineage_node)
    graph.add_node("snapshot", snapshot_node)
    graph.add_node("receipt", receipt_node)
    graph.add_node("consumer_handoff", consumer_handoff_node)
    graph.add_node("review_hook", review_hook_node)
    graph.add_node("final", final_node)
    graph.add_edge(START, "source_config")
    graph.add_edge("source_config", "load_market_data")
    graph.add_edge("load_market_data", "compute_indicators")
    graph.add_edge("compute_indicators", "quality")
    graph.add_edge("quality", "lineage")
    graph.add_edge("lineage", "snapshot")
    graph.add_edge("snapshot", "receipt")
    graph.add_edge("receipt", "consumer_handoff")
    graph.add_edge("consumer_handoff", "review_hook")
    graph.add_edge("review_hook", "final")
    graph.add_edge("final", END)
    return graph.compile()


indicator_graph = build_indicator_graph()


def run_indicator_graph(
    *,
    symbol: str = "SPY",
    start: str = "2025-01-01",
    end: str = "2025-06-30",
    ma_fast: int = 20,
    ma_slow: int = 50,
    market_data_snapshot: dict[str, Any] | None = None,
    history_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "symbol": symbol,
        "start": start,
        "end": end,
        "ma_fast": ma_fast,
        "ma_slow": ma_slow,
    }
    if market_data_snapshot is not None:
        payload["market_data_snapshot"] = market_data_snapshot
    if history_records is not None:
        payload["history_records"] = history_records
    result = indicator_graph.invoke(payload)
    return dict(result)
