"""OpenAI Agents SDK tools for the FinHarness lab."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from agents import Agent, function_tool

from finharness.data_entry import fetch_quote_snapshot, fetch_yfinance_history
from finharness.metrics import summarize

ROOT = Path(__file__).resolve().parents[2]
LATEST_RISK_NOTE = ROOT / "data" / "cache" / "latest_risk_note.txt"
DEFAULT_RISK_NOTE = """Not investment advice.

This educational risk note uses yfinance/Yahoo Finance history and not TradingView/TV data.
Historical metrics do not guarantee future returns.

Max drawdown and volatility can change when market regimes, liquidity, or data freshness change.
Transaction costs, slippage, taxes, and venue constraints must be reviewed before any paper
or live use.
"""


@function_tool
def get_quote_snapshot(symbol: str) -> dict[str, object]:
    """Get a quote snapshot through the default available data provider."""
    quote = fetch_quote_snapshot(symbol)
    return quote.__dict__


@function_tool
def get_historical_risk_metrics(symbol: str, start: str, end: str) -> dict[str, object]:
    """Fetch yfinance/Yahoo Finance history and compute core risk metrics."""
    return historical_risk_metrics_payload(symbol=symbol, start=start, end=end)


def historical_risk_metrics_payload(symbol: str, start: str, end: str) -> dict[str, object]:
    """Build the historical risk metrics payload behind the Agents SDK adapter."""
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
def evaluate_latest_risk_note() -> dict[str, object]:
    """Run promptfoo assertions against the latest generated risk note."""
    return evaluate_latest_risk_note_payload()


def evaluate_latest_risk_note_payload(timeout_seconds: float = 60.0) -> dict[str, object]:
    """Run promptfoo assertions with a bounded subprocess timeout."""
    if not LATEST_RISK_NOTE.exists():
        LATEST_RISK_NOTE.parent.mkdir(parents=True, exist_ok=True)
        LATEST_RISK_NOTE.write_text(DEFAULT_RISK_NOTE, encoding="utf-8")

    command = [
        "pnpm",
        "exec",
        "promptfoo",
        "eval",
        "-c",
        "evals/promptfoo/risk-note.yaml",
        "--no-cache",
    ]
    try:
        result = subprocess.run(  # noqa: S603 -- fixed local promptfoo command, shell disabled.
            command,
            cwd=ROOT,
            env={
                **dict(os.environ),
                "PROMPTFOO_DISABLE_TELEMETRY": "1",
                "PROMPTFOO_DISABLE_UPDATE": "1",
            },
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "returncode": None,
            "stdout_tail": str(exc.output or "")[-2000:],
            "stderr_tail": f"promptfoo timed out after {timeout_seconds} seconds",
        }
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
    }


finance_research_agent = Agent(
    name="Finance Research Harness Agent",
    instructions=(
        "Use tools to fetch data, run backtests, and evaluate risk notes. "
        "Always state that outputs are for education, not investment advice. "
        "Always disclose that the current default data source is yfinance/Yahoo Finance, "
        "not TradingView/TV, and that optional providers are evidence sources only."
    ),
    tools=[
        get_quote_snapshot,
        get_historical_risk_metrics,
        evaluate_latest_risk_note,
    ],
)


def tool_names() -> list[str]:
    return [
        get_quote_snapshot.name,
        get_historical_risk_metrics.name,
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
