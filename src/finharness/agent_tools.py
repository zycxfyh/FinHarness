"""OpenAI Agents SDK tools for the FinHarness lab."""

from __future__ import annotations

import json

from agents import Agent, function_tool

from finharness.data_entry import fetch_openbb_quote, fetch_yfinance_history
from finharness.finance_graph import run_finance_graph
from finharness.metrics import summarize


@function_tool
def get_quote_snapshot(symbol: str) -> dict[str, object]:
    """Get a quote snapshot through OpenBB's yfinance provider."""
    quote = fetch_openbb_quote(symbol)
    return quote.__dict__


@function_tool
def get_historical_risk_metrics(symbol: str, start: str, end: str) -> dict[str, object]:
    """Fetch yfinance/Yahoo Finance history and compute core risk metrics."""
    history = fetch_yfinance_history(symbol, start, end)
    metrics = summarize(history["close"].astype(float).tolist())
    return {
        "symbol": symbol,
        "start": start,
        "end": end,
        "rows": len(history),
        "data_source": "yfinance/Yahoo Finance, not TradingView/TV",
        "metrics": metrics.__dict__,
    }


@function_tool
def run_finance_graph_workflow(symbol: str, start: str, end: str) -> dict[str, object]:
    """Run the LangGraph finance workflow: data entry, Backtrader baseline, and risk eval."""
    return run_finance_graph(symbol=symbol, start=start, end=end)


@function_tool
def evaluate_latest_risk_note() -> dict[str, object]:
    """Run promptfoo assertions against the latest generated risk note."""
    return run_finance_graph()["eval"]


finance_research_agent = Agent(
    name="Finance Research Harness Agent",
    instructions=(
        "Use tools to fetch data, run backtests, and evaluate risk notes. "
        "Always state that outputs are for education, not investment advice. "
        "Always disclose that the current history source is yfinance/Yahoo Finance, "
        "not TradingView/TV."
    ),
    tools=[
        get_quote_snapshot,
        get_historical_risk_metrics,
        run_finance_graph_workflow,
        evaluate_latest_risk_note,
    ],
)


def tool_names() -> list[str]:
    return [
        get_quote_snapshot.name,
        get_historical_risk_metrics.name,
        run_finance_graph_workflow.name,
        evaluate_latest_risk_note.name,
    ]


def describe_agent() -> str:
    return json.dumps(
        {
            "agent": finance_research_agent.name,
            "tools": tool_names(),
        },
        indent=2,
        sort_keys=True,
    )
