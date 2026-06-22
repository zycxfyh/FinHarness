"""LangGraph workflow for the first-layer market data slice."""

from __future__ import annotations

from typing import Any, TypedDict

import pandas as pd
from langgraph.graph import END, START, StateGraph

from finharness.data_entry import fetch_yfinance_history
from finharness.market_data import (
    AdjustmentMode,
    MarketDataQuality,
    SourceSpec,
    adjusted_from_adjustment,
    adjustment_from_adjusted,
    build_ohlcv_snapshot_from_history,
    build_quality_report,
    package_version,
    reconcile_close,
)


class MarketDataGraphState(TypedDict, total=False):
    symbol: str
    start: str
    end: str
    adjusted: bool
    adjustment: AdjustmentMode
    second_provider: Any
    write_catalog: bool
    source: dict[str, Any]
    raw_payload: dict[str, Any]
    history_records: list[dict[str, Any]]
    normalized_records: list[dict[str, Any]]
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


def _history_to_records(history: pd.DataFrame) -> list[dict[str, Any]]:
    return history.to_dict(orient="records")


def source_config_node(state: MarketDataGraphState) -> MarketDataGraphState:
    symbol = state.get("symbol", "SPY").upper()
    adjustment = state.get("adjustment")
    if adjustment is None:
        adjustment = adjustment_from_adjusted(state.get("adjusted", True))
    adjusted = adjusted_from_adjustment(adjustment)  # keep legacy bool in lockstep.
    source = SourceSpec(
        provider="yfinance",
        upstream_source="Yahoo Finance",
        asset_class="equity",
        dataset="ohlcv_history",
        access_method="api_pull",
        wheel="yfinance",
        wheel_version=package_version("yfinance"),
        adjustment=adjustment,
    )
    return {
        "symbol": symbol,
        "start": state.get("start", "2025-01-01"),
        "end": state.get("end", "2025-06-30"),
        "adjusted": adjusted,
        "adjustment": adjustment,
        "second_provider": state.get("second_provider"),
        "write_catalog": state.get("write_catalog", True),
        "source": source.model_dump(mode="json"),
    }


def fetch_market_data_node(state: MarketDataGraphState) -> MarketDataGraphState:
    history = fetch_yfinance_history(
        state["symbol"],
        state["start"],
        state["end"],
        adjustment=state["adjustment"],
    )
    return {
        "history_records": _history_to_records(history),
        "raw_payload": {
            "symbol": state["symbol"],
            "start": state["start"],
            "end": state["end"],
            "source": "yfinance.download",
            "rows": len(history),
            "auto_adjust": state["adjusted"],
            "adjustment": state["adjustment"],
        },
    }


def normalize_ohlcv_node(state: MarketDataGraphState) -> MarketDataGraphState:
    history = _history_from_records(state["history_records"])
    normalized = history[["date", "open", "high", "low", "close", "volume"]].copy()
    return {"normalized_records": _history_to_records(normalized)}


def quality_node(state: MarketDataGraphState) -> MarketDataGraphState:
    history = _history_from_records(state["normalized_records"])
    reconciliation = reconcile_close(
        state["symbol"],
        state["start"],
        state["end"],
        primary_history=history,
        second_provider=state.get("second_provider"),
        adjustment=state["adjustment"],
    )
    quality = build_quality_report(
        history,
        required_columns=["date", "open", "high", "low", "close", "volume"],
        reconciliation=reconciliation,
    )
    return {"quality": quality.model_dump(mode="json")}


def lineage_node(state: MarketDataGraphState) -> MarketDataGraphState:
    return {
        "lineage": {
            "status": "pending_persist",
            "note": "hashes and refs are finalized in snapshot/receipt persistence",
        }
    }


def snapshot_node(state: MarketDataGraphState) -> MarketDataGraphState:
    history = _history_from_records(state["normalized_records"])
    source = SourceSpec(**state["source"])
    quality = MarketDataQuality.model_validate(state["quality"])
    receipt = build_ohlcv_snapshot_from_history(
        history,
        symbol=state["symbol"],
        source=source,
        fetch_config={
            "symbol": state["symbol"],
            "start": state["start"],
            "end": state["end"],
            "auto_adjust": state["adjusted"],
            "adjustment": state["adjustment"],
        },
        raw_payload=state["raw_payload"],
        adjusted=state["adjusted"],
        adjustment=state["adjustment"],
        quality=quality,
        write_catalog=state.get("write_catalog", True),
    )
    return {
        "snapshot": receipt.snapshot.model_dump(mode="json"),
        "receipt": receipt.model_dump(mode="json"),
        "lineage": receipt.snapshot.lineage.model_dump(mode="json"),
        "quality": receipt.snapshot.quality.model_dump(mode="json"),
    }


def receipt_node(state: MarketDataGraphState) -> MarketDataGraphState:
    return {"receipt": state["receipt"]}


def consumer_handoff_node(state: MarketDataGraphState) -> MarketDataGraphState:
    snapshot = state["snapshot"]
    return {
        "consumer_handoff": {
            "consumer": "indicator_layer_research_review",
            "symbols": snapshot["symbols"],
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "allowed_outputs": ["indicator input", "risk metrics input", "review evidence"],
            "forbidden_outputs": ["orders", "position changes", "execution permission"],
        }
    }


def review_hook_node(state: MarketDataGraphState) -> MarketDataGraphState:
    return {
        "review_hook": {
            "status": "open",
            "questions": [
                "Is the latest bar fresh enough for today's review?",
                "Are there missing, duplicate, or invalid OHLCV records?",
                "Does this market data snapshot match the intended symbol and date range?",
            ],
            "next_review": "daily evidence review",
        }
    }


def final_node(state: MarketDataGraphState) -> MarketDataGraphState:
    snapshot = state["snapshot"]
    return {
        "final": {
            "workflow": "langgraph_market_data_v1",
            "symbol": state["symbol"],
            "start": state["start"],
            "end": state["end"],
            "row_count": snapshot["quality"]["row_count"],
            "quality_ok": snapshot["quality"]["ok"],
            "quality_notes": snapshot["quality"].get("notes", []),
            "adjustment": snapshot["lineage"]["fetch_config"].get("adjustment"),
            "reconciliation": snapshot["quality"].get("reconciliation"),
            "data_bias_controls": snapshot["lineage"].get("data_bias_controls", []),
            "payload_ref": snapshot["payload_ref"],
            "receipt_ref": snapshot["receipt_ref"],
            "execution_allowed": False,
            "consumer_handoff": state["consumer_handoff"],
            "review_hook": state["review_hook"],
        }
    }


def build_market_data_graph():
    graph = StateGraph(MarketDataGraphState)
    graph.add_node("source_config", source_config_node)
    graph.add_node("fetch_market_data", fetch_market_data_node)
    graph.add_node("normalize_ohlcv", normalize_ohlcv_node)
    graph.add_node("quality", quality_node)
    graph.add_node("lineage", lineage_node)
    graph.add_node("snapshot", snapshot_node)
    graph.add_node("receipt", receipt_node)
    graph.add_node("consumer_handoff", consumer_handoff_node)
    graph.add_node("review_hook", review_hook_node)
    graph.add_node("final", final_node)
    graph.add_edge(START, "source_config")
    graph.add_edge("source_config", "fetch_market_data")
    graph.add_edge("fetch_market_data", "normalize_ohlcv")
    graph.add_edge("normalize_ohlcv", "quality")
    graph.add_edge("quality", "lineage")
    graph.add_edge("lineage", "snapshot")
    graph.add_edge("snapshot", "receipt")
    graph.add_edge("receipt", "consumer_handoff")
    graph.add_edge("consumer_handoff", "review_hook")
    graph.add_edge("review_hook", "final")
    graph.add_edge("final", END)
    return graph.compile()


market_data_graph = build_market_data_graph()


def run_market_data_graph(
    *,
    symbol: str = "SPY",
    start: str = "2025-01-01",
    end: str = "2025-06-30",
    adjusted: bool = True,
    adjustment: str | None = None,
    second_provider: Any | None = None,
    write_catalog: bool = True,
) -> dict[str, Any]:
    result = market_data_graph.invoke(
        {
            "symbol": symbol,
            "start": start,
            "end": end,
            "adjusted": adjusted,
            "adjustment": adjustment,
            "second_provider": second_provider,
            "write_catalog": write_catalog,
        }
    )
    return dict(result)
