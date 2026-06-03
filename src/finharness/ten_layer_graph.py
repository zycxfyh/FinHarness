"""Top-level LangGraph orchestrator for the ten FinHarness layers.

The orchestrator can run the full domain chain, or reuse supplied snapshots and
run only selected layers. It coordinates layers; individual layer modules own
their contracts and receipts.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from finharness.events_graph import run_events_graph
from finharness.execution_graph import run_execution_graph
from finharness.hypotheses_graph import run_hypotheses_graph
from finharness.indicator_graph import run_indicator_graph
from finharness.interpretation_graph import run_interpretation_graph
from finharness.market_data_graph import run_market_data_graph
from finharness.post_trade_graph import run_post_trade_graph
from finharness.proposal_graph import run_proposal_graph
from finharness.research_assets import resolve_research_assets
from finharness.risk_gate_graph import run_risk_gate_graph
from finharness.validation_graph import run_validation_graph

WORKFLOW_VERSION = "langgraph_ten_layer_orchestrator_v1"

LAYER_KEYS = {
    1: "market_data",
    2: "indicators",
    3: "events",
    4: "interpretation",
    5: "hypotheses",
    6: "validation",
    7: "proposal",
    8: "risk_gate",
    9: "execution",
    10: "post_trade",
}

SNAPSHOT_KEYS = {
    1: "market_data_snapshot",
    2: "indicator_snapshot",
    3: "event_snapshot",
    4: "interpretation_snapshot",
    5: "hypothesis_snapshot",
    6: "validation_snapshot",
    7: "proposal_snapshot",
    8: "risk_gate_snapshot",
    9: "execution_snapshot",
    10: "post_trade_snapshot",
}


class TenLayerGraphState(TypedDict, total=False):
    symbol: str
    start: str
    end: str
    adjusted: bool
    write_catalog: bool
    ma_fast: int
    ma_slow: int
    universe: list[str]
    forms: list[str]
    max_records: int
    max_hypotheses: int
    symbols: list[str]
    risk_context: dict[str, Any]
    execution_context: dict[str, Any]
    post_trade_context: dict[str, Any]
    fake_fill_mode: str
    llm_enabled: bool
    hermes_root: str
    research_asset_ids: list[str]
    strategy_spec_ids: list[str]
    method_spec_ids: list[str]
    reference_card_ids: list[str]
    research_asset_policy: str
    research_asset_context: dict[str, Any]
    run_layers: list[int | str]
    reuse_policy: str
    layer_status: dict[str, dict[str, Any]]
    market_data_snapshot: dict[str, Any]
    indicator_snapshot: dict[str, Any]
    event_snapshot: dict[str, Any]
    interpretation_snapshot: dict[str, Any]
    hypothesis_snapshot: dict[str, Any]
    validation_snapshot: dict[str, Any]
    proposal_snapshot: dict[str, Any]
    risk_gate_snapshot: dict[str, Any]
    execution_snapshot: dict[str, Any]
    post_trade_snapshot: dict[str, Any]
    market_data_final: dict[str, Any]
    indicator_final: dict[str, Any]
    event_final: dict[str, Any]
    interpretation_final: dict[str, Any]
    hypothesis_final: dict[str, Any]
    validation_final: dict[str, Any]
    proposal_final: dict[str, Any]
    risk_gate_final: dict[str, Any]
    execution_final: dict[str, Any]
    post_trade_final: dict[str, Any]
    final: dict[str, Any]


def _run_layer_set(state: TenLayerGraphState) -> set[int]:
    raw = state.get("run_layers")
    if not raw:
        return set(LAYER_KEYS)
    selected: set[int] = set()
    name_to_layer = {value: key for key, value in LAYER_KEYS.items()}
    for item in raw:
        if isinstance(item, int):
            selected.add(item)
            continue
        text = str(item).strip().lower().replace("-", "_")
        if text.isdigit():
            selected.add(int(text))
        elif text in name_to_layer:
            selected.add(name_to_layer[text])
    return {layer for layer in selected if layer in LAYER_KEYS}


def _should_run(state: TenLayerGraphState, layer: int) -> bool:
    return layer in _run_layer_set(state)


def _snapshot_ref(snapshot: dict[str, Any] | None) -> str | None:
    if not snapshot:
        return None
    return (
        snapshot.get("payload_ref")
        or snapshot.get("receipt_ref")
        or snapshot.get("normalized_ref")
        or snapshot.get("snapshot_id")
    )


def _status(
    state: TenLayerGraphState,
    *,
    layer: int,
    status: str,
    detail: str,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    layer_status = dict(state.get("layer_status") or {})
    key = LAYER_KEYS[layer]
    layer_status[key] = {
        "layer": layer,
        "status": status,
        "detail": detail,
        "snapshot_ref": _snapshot_ref(snapshot),
    }
    return layer_status


def _universe(state: TenLayerGraphState) -> list[str] | None:
    return state.get("universe") or state.get("symbols")


def _refs(*snapshots: dict[str, Any] | None) -> list[str]:
    return [ref for ref in (_snapshot_ref(snapshot) for snapshot in snapshots) if ref]


def research_assets_node(state: TenLayerGraphState) -> TenLayerGraphState:
    selection = resolve_research_assets(
        research_asset_ids=state.get("research_asset_ids"),
        strategy_spec_ids=state.get("strategy_spec_ids"),
        method_spec_ids=state.get("method_spec_ids"),
        reference_card_ids=state.get("reference_card_ids"),
        policy="cite_only",
    )
    return {
        "research_asset_context": selection.model_dump(mode="json"),
        "research_asset_policy": selection.policy,
    }


def market_data_node(state: TenLayerGraphState) -> TenLayerGraphState:
    existing = state.get("market_data_snapshot")
    if not _should_run(state, 1):
        return {
            "layer_status": _status(
                state,
                layer=1,
                status="reused" if existing else "skipped",
                detail="market data snapshot supplied" if existing else "not requested",
                snapshot=existing,
            )
        }
    result = run_market_data_graph(
        symbol=state.get("symbol", "SPY"),
        start=state.get("start", "2025-01-01"),
        end=state.get("end", "2025-06-30"),
        adjusted=state.get("adjusted", False),
        write_catalog=state.get("write_catalog", True),
    )
    snapshot = result["snapshot"]
    return {
        "market_data_snapshot": snapshot,
        "market_data_final": result["final"],
        "layer_status": _status(
            state, layer=1, status="ran", detail="market_data_graph", snapshot=snapshot
        ),
    }


def indicator_node(state: TenLayerGraphState) -> TenLayerGraphState:
    existing = state.get("indicator_snapshot")
    if not _should_run(state, 2):
        return {
            "layer_status": _status(
                state,
                layer=2,
                status="reused" if existing else "skipped",
                detail="indicator snapshot supplied" if existing else "not requested",
                snapshot=existing,
            )
        }
    result = run_indicator_graph(
        symbol=state.get("symbol", "SPY"),
        start=state.get("start", "2025-01-01"),
        end=state.get("end", "2025-06-30"),
        ma_fast=state.get("ma_fast", 20),
        ma_slow=state.get("ma_slow", 50),
        market_data_snapshot=state.get("market_data_snapshot"),
    )
    snapshot = result["snapshot"]
    return {
        "indicator_snapshot": snapshot,
        "indicator_final": result["final"],
        "layer_status": _status(
            state, layer=2, status="ran", detail="indicator_graph", snapshot=snapshot
        ),
    }


def events_node(state: TenLayerGraphState) -> TenLayerGraphState:
    existing = state.get("event_snapshot")
    if not _should_run(state, 3):
        return {
            "layer_status": _status(
                state,
                layer=3,
                status="reused" if existing else "skipped",
                detail="event snapshot supplied" if existing else "not requested",
                snapshot=existing,
            )
        }
    result = run_events_graph(
        universe=_universe(state),
        forms=state.get("forms"),
        per_symbol_limit=state.get("max_records", 30),
        linked_market_snapshot_refs=_refs(state.get("market_data_snapshot")),
        linked_indicator_snapshot_refs=_refs(state.get("indicator_snapshot")),
    )
    snapshot = result["snapshot"]
    return {
        "event_snapshot": snapshot,
        "event_final": result["final"],
        "layer_status": _status(
            state, layer=3, status="ran", detail="events_graph", snapshot=snapshot
        ),
    }


def interpretation_node(state: TenLayerGraphState) -> TenLayerGraphState:
    existing = state.get("interpretation_snapshot")
    if not _should_run(state, 4):
        return {
            "layer_status": _status(
                state,
                layer=4,
                status="reused" if existing else "skipped",
                detail="interpretation snapshot supplied" if existing else "not requested",
                snapshot=existing,
            )
        }
    result = run_interpretation_graph(
        universe=_universe(state),
        forms=state.get("forms"),
        max_records=state.get("max_records", 30),
        event_snapshot=state.get("event_snapshot"),
        market_snapshot_refs=_refs(state.get("market_data_snapshot")),
        indicator_snapshot_refs=_refs(state.get("indicator_snapshot")),
    )
    snapshot = result["snapshot"]
    return {
        "interpretation_snapshot": snapshot,
        "interpretation_final": result["final"],
        "layer_status": _status(
            state,
            layer=4,
            status="ran",
            detail="interpretation_graph",
            snapshot=snapshot,
        ),
    }


def hypotheses_node(state: TenLayerGraphState) -> TenLayerGraphState:
    existing = state.get("hypothesis_snapshot")
    if not _should_run(state, 5):
        return {
            "layer_status": _status(
                state,
                layer=5,
                status="reused" if existing else "skipped",
                detail="hypothesis snapshot supplied" if existing else "not requested",
                snapshot=existing,
            )
        }
    result = run_hypotheses_graph(
        universe=_universe(state),
        forms=state.get("forms"),
        max_records=state.get("max_records", 30),
        max_hypotheses=state.get("max_hypotheses", 10),
        symbols=state.get("symbols"),
        interpretation_snapshot=state.get("interpretation_snapshot"),
        llm_enabled=state.get("llm_enabled", False),
        hermes_root=state.get("hermes_root", "/root/projects/hermes-agent"),
        research_asset_context=state.get("research_asset_context"),
    )
    snapshot = result["snapshot"]
    return {
        "hypothesis_snapshot": snapshot,
        "hypothesis_final": result["final"],
        "layer_status": _status(
            state, layer=5, status="ran", detail="hypotheses_graph", snapshot=snapshot
        ),
    }


def validation_node(state: TenLayerGraphState) -> TenLayerGraphState:
    existing = state.get("validation_snapshot")
    if not _should_run(state, 6):
        return {
            "layer_status": _status(
                state,
                layer=6,
                status="reused" if existing else "skipped",
                detail="validation snapshot supplied" if existing else "not requested",
                snapshot=existing,
            )
        }
    result = run_validation_graph(
        universe=_universe(state),
        forms=state.get("forms"),
        max_records=state.get("max_records", 30),
        max_hypotheses=state.get("max_hypotheses", 10),
        symbols=state.get("symbols"),
        hypothesis_snapshot=state.get("hypothesis_snapshot"),
        llm_enabled=state.get("llm_enabled", False),
        hermes_root=state.get("hermes_root", "/root/projects/hermes-agent"),
        research_asset_context=state.get("research_asset_context"),
    )
    snapshot = result["snapshot"]
    return {
        "validation_snapshot": snapshot,
        "validation_final": result["final"],
        "layer_status": _status(
            state, layer=6, status="ran", detail="validation_graph", snapshot=snapshot
        ),
    }


def proposal_node(state: TenLayerGraphState) -> TenLayerGraphState:
    existing = state.get("proposal_snapshot")
    if not _should_run(state, 7):
        return {
            "layer_status": _status(
                state,
                layer=7,
                status="reused" if existing else "skipped",
                detail="proposal snapshot supplied" if existing else "not requested",
                snapshot=existing,
            )
        }
    result = run_proposal_graph(
        universe=_universe(state),
        forms=state.get("forms"),
        max_records=state.get("max_records", 30),
        max_hypotheses=state.get("max_hypotheses", 10),
        symbols=state.get("symbols"),
        validation_snapshot=state.get("validation_snapshot"),
        llm_enabled=state.get("llm_enabled", False),
        hermes_root=state.get("hermes_root", "/root/projects/hermes-agent"),
        research_asset_context=state.get("research_asset_context"),
    )
    snapshot = result["snapshot"]
    return {
        "proposal_snapshot": snapshot,
        "proposal_final": result["final"],
        "layer_status": _status(
            state, layer=7, status="ran", detail="proposal_graph", snapshot=snapshot
        ),
    }


def risk_gate_node(state: TenLayerGraphState) -> TenLayerGraphState:
    existing = state.get("risk_gate_snapshot")
    if not _should_run(state, 8):
        return {
            "layer_status": _status(
                state,
                layer=8,
                status="reused" if existing else "skipped",
                detail="risk gate snapshot supplied" if existing else "not requested",
                snapshot=existing,
            )
        }
    result = run_risk_gate_graph(
        universe=_universe(state),
        forms=state.get("forms"),
        max_records=state.get("max_records", 30),
        max_hypotheses=state.get("max_hypotheses", 10),
        symbols=state.get("symbols"),
        proposal_snapshot=state.get("proposal_snapshot"),
        risk_context=state.get("risk_context"),
        llm_enabled=state.get("llm_enabled", False),
        hermes_root=state.get("hermes_root", "/root/projects/hermes-agent"),
        research_asset_context=state.get("research_asset_context"),
    )
    snapshot = result["snapshot"]
    return {
        "risk_gate_snapshot": snapshot,
        "risk_gate_final": result["final"],
        "layer_status": _status(
            state, layer=8, status="ran", detail="risk_gate_graph", snapshot=snapshot
        ),
    }


def execution_node(state: TenLayerGraphState) -> TenLayerGraphState:
    existing = state.get("execution_snapshot")
    if not _should_run(state, 9):
        return {
            "layer_status": _status(
                state,
                layer=9,
                status="reused" if existing else "skipped",
                detail="execution snapshot supplied" if existing else "not requested",
                snapshot=existing,
            )
        }
    result = run_execution_graph(
        universe=_universe(state),
        forms=state.get("forms"),
        max_records=state.get("max_records", 30),
        max_hypotheses=state.get("max_hypotheses", 10),
        symbols=state.get("symbols"),
        risk_gate_snapshot=state.get("risk_gate_snapshot"),
        risk_context=state.get("risk_context"),
        execution_context=state.get("execution_context"),
        fake_fill_mode=state.get("fake_fill_mode", "accepted"),
        research_asset_context=state.get("research_asset_context"),
    )
    snapshot = result["snapshot"]
    return {
        "execution_snapshot": snapshot,
        "execution_final": result["final"],
        "layer_status": _status(
            state, layer=9, status="ran", detail="execution_graph", snapshot=snapshot
        ),
    }


def post_trade_node(state: TenLayerGraphState) -> TenLayerGraphState:
    existing = state.get("post_trade_snapshot")
    if not _should_run(state, 10):
        return {
            "layer_status": _status(
                state,
                layer=10,
                status="reused" if existing else "skipped",
                detail="post-trade snapshot supplied" if existing else "not requested",
                snapshot=existing,
            )
        }
    result = run_post_trade_graph(
        universe=_universe(state),
        forms=state.get("forms"),
        max_records=state.get("max_records", 30),
        max_hypotheses=state.get("max_hypotheses", 10),
        symbols=state.get("symbols"),
        risk_context=state.get("risk_context"),
        execution_context=state.get("execution_context"),
        execution_snapshot=state.get("execution_snapshot"),
        post_trade_context=state.get("post_trade_context"),
        fake_fill_mode=state.get("fake_fill_mode", "accepted"),
        research_asset_context=state.get("research_asset_context"),
    )
    snapshot = result["snapshot"]
    return {
        "post_trade_snapshot": snapshot,
        "post_trade_final": result["final"],
        "layer_status": _status(
            state, layer=10, status="ran", detail="post_trade_graph", snapshot=snapshot
        ),
    }


def final_node(state: TenLayerGraphState) -> TenLayerGraphState:
    snapshots = {
        LAYER_KEYS[layer]: _snapshot_ref(state.get(snapshot_key))
        for layer, snapshot_key in SNAPSHOT_KEYS.items()
    }
    layer_status = state.get("layer_status") or {}
    research_asset_context = state.get("research_asset_context") or {}
    return {
        "final": {
            "workflow": WORKFLOW_VERSION,
            "reuse_policy": state.get(
                "reuse_policy",
                "run selected layers; reuse supplied snapshots",
            ),
            "requested_run_layers": sorted(_run_layer_set(state)),
            "layer_status": layer_status,
            "snapshot_refs": snapshots,
            "research_asset_policy": state.get("research_asset_policy", "cite_only"),
            "research_asset_refs": {
                "strategy_ids": [
                    item["id"]
                    for item in research_asset_context.get("strategy_specs", [])
                ],
                "method_ids": [
                    item["id"] for item in research_asset_context.get("method_specs", [])
                ],
                "reference_ids": [
                    item["id"]
                    for item in research_asset_context.get("reference_cards", [])
                ],
                "missing_ids": research_asset_context.get("missing_ids", []),
                "execution_allowed": False,
            },
            "terminal_layer": "post_trade"
            if snapshots.get("post_trade")
            else "execution"
            if snapshots.get("execution")
            else None,
            "terminal_status": (state.get("post_trade_snapshot") or {}).get("final_status")
            or (state.get("execution_snapshot") or {}).get("final_status"),
            "order_creation_allowed": (state.get("post_trade_snapshot") or {}).get(
                "order_creation_allowed", False
            ),
            "execution_allowed": (state.get("execution_snapshot") or {}).get(
                "execution_allowed", False
            ),
        }
    }


def build_ten_layer_graph():
    graph = StateGraph(TenLayerGraphState)
    graph.add_node("research_assets", research_assets_node)
    graph.add_node("market_data", market_data_node)
    graph.add_node("indicators", indicator_node)
    graph.add_node("events", events_node)
    graph.add_node("interpretation", interpretation_node)
    graph.add_node("hypotheses", hypotheses_node)
    graph.add_node("validation", validation_node)
    graph.add_node("proposal", proposal_node)
    graph.add_node("risk_gate", risk_gate_node)
    graph.add_node("execution", execution_node)
    graph.add_node("post_trade", post_trade_node)
    graph.add_node("final", final_node)
    graph.add_edge(START, "research_assets")
    graph.add_edge("research_assets", "market_data")
    graph.add_edge("market_data", "indicators")
    graph.add_edge("indicators", "events")
    graph.add_edge("events", "interpretation")
    graph.add_edge("interpretation", "hypotheses")
    graph.add_edge("hypotheses", "validation")
    graph.add_edge("validation", "proposal")
    graph.add_edge("proposal", "risk_gate")
    graph.add_edge("risk_gate", "execution")
    graph.add_edge("execution", "post_trade")
    graph.add_edge("post_trade", "final")
    graph.add_edge("final", END)
    return graph.compile()


ten_layer_graph = build_ten_layer_graph()


def run_ten_layer_graph(
    *,
    symbol: str = "SPY",
    start: str = "2025-01-01",
    end: str = "2025-06-30",
    universe: list[str] | None = None,
    forms: list[str] | None = None,
    max_records: int = 30,
    max_hypotheses: int = 10,
    symbols: list[str] | None = None,
    run_layers: list[int | str] | None = None,
    risk_context: dict[str, Any] | None = None,
    execution_context: dict[str, Any] | None = None,
    post_trade_context: dict[str, Any] | None = None,
    fake_fill_mode: str = "accepted",
    research_asset_ids: list[str] | None = None,
    strategy_spec_ids: list[str] | None = None,
    method_spec_ids: list[str] | None = None,
    reference_card_ids: list[str] | None = None,
    snapshots: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "symbol": symbol,
        "start": start,
        "end": end,
        "universe": universe,
        "forms": forms,
        "max_records": max_records,
        "max_hypotheses": max_hypotheses,
        "symbols": symbols or [],
        "run_layers": run_layers or list(LAYER_KEYS),
        "risk_context": risk_context or {},
        "execution_context": execution_context or {},
        "post_trade_context": post_trade_context or {},
        "fake_fill_mode": fake_fill_mode,
        "research_asset_ids": research_asset_ids or [],
        "strategy_spec_ids": strategy_spec_ids or [],
        "method_spec_ids": method_spec_ids or [],
        "reference_card_ids": reference_card_ids or [],
        "research_asset_policy": "cite_only",
    }
    for key, value in (snapshots or {}).items():
        if key in set(SNAPSHOT_KEYS.values()):
            payload[key] = value
    result = ten_layer_graph.invoke(payload)
    return dict(result)
