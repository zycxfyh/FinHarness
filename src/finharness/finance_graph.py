"""LangGraph workflow for finance data entry and risk evaluation."""

from __future__ import annotations

import subprocess
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from finharness.workflow import ROOT, run_data_entry_workflow


class FinanceGraphState(TypedDict, total=False):
    symbol: str
    start: str
    end: str
    fast: int
    slow: int
    workflow: dict[str, Any]
    eval: dict[str, Any]
    final: dict[str, Any]


def data_entry_node(state: FinanceGraphState) -> FinanceGraphState:
    summary = run_data_entry_workflow(
        symbol=state.get("symbol", "SPY"),
        start=state.get("start", "2025-01-01"),
        end=state.get("end", "2025-06-30"),
        fast=state.get("fast", 20),
        slow=state.get("slow", 50),
    )
    return {"workflow": summary}


def risk_eval_node(state: FinanceGraphState) -> FinanceGraphState:
    result = subprocess.run(
        [
            "pnpm",
            "exec",
            "promptfoo",
            "eval",
            "-c",
            "evals/promptfoo/risk-note.yaml",
            "--no-cache",
        ],
        cwd=ROOT,
        env={
            **dict(__import__("os").environ),
            "PROMPTFOO_DISABLE_TELEMETRY": "1",
            "PROMPTFOO_DISABLE_UPDATE": "1",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "eval": {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout_tail": result.stdout[-2000:],
            "stderr_tail": result.stderr[-2000:],
        }
    }


def final_node(state: FinanceGraphState) -> FinanceGraphState:
    workflow = state.get("workflow", {})
    risk_eval = state.get("eval", {})
    return {
        "final": {
            "symbol": workflow.get("symbol", state.get("symbol", "SPY")),
            "history_rows": workflow.get("history_rows"),
            "risk_note_path": workflow.get("risk_note_path"),
            "backtest": workflow.get("backtest"),
            "metrics": workflow.get("metrics"),
            "eval_ok": risk_eval.get("ok", False),
            "data_sources": workflow.get("data_sources"),
            "not_data_source": workflow.get("not_data_source"),
        }
    }


def build_finance_graph():
    graph = StateGraph(FinanceGraphState)
    graph.add_node("data_entry", data_entry_node)
    graph.add_node("risk_eval", risk_eval_node)
    graph.add_node("final", final_node)
    graph.add_edge(START, "data_entry")
    graph.add_edge("data_entry", "risk_eval")
    graph.add_edge("risk_eval", "final")
    graph.add_edge("final", END)
    return graph.compile()


finance_graph = build_finance_graph()


def run_finance_graph(
    symbol: str = "SPY",
    start: str = "2025-01-01",
    end: str = "2025-06-30",
    fast: int = 20,
    slow: int = 50,
) -> dict[str, Any]:
    result = finance_graph.invoke(
        {
            "symbol": symbol,
            "start": start,
            "end": end,
            "fast": fast,
            "slow": slow,
        }
    )
    return dict(result)

