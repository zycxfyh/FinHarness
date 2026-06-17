"""Reusable finance workflow for CLI and agent tools."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from finharness.backtrader_runner import BacktraderSummary, run_moving_average_backtest
from finharness.data_entry import (
    QuoteSnapshot,
    fetch_quote_snapshot,
    fetch_yfinance_history,
    write_history_csv,
)
from finharness.indicator_layer import build_indicator_snapshot
from finharness.market_data import SourceSpec, build_ohlcv_snapshot_from_history, package_version
from finharness.metrics import RiskReturnSummary, summarize

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "data" / "cache"


def pct(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2%}"


def build_risk_note(
    symbol: str,
    quote: QuoteSnapshot,
    metrics: RiskReturnSummary,
    backtest: BacktraderSummary,
) -> str:
    lines = [
        f"# {symbol} Data Entry Risk Note",
        "",
        (
            f"Data sources: {quote.provider} for quote; yfinance package/Yahoo Finance for "
            "historical prices. This is not TradingView/TV data."
        ),
        "",
        "Not investment advice. This note is for engineering and financial education only.",
        "Backtest results do not guarantee future returns.",
        "",
        "## Quote Snapshot",
        f"- Symbol: {quote.symbol}",
        f"- Name: {quote.name}",
        f"- Exchange: {quote.exchange}",
        f"- Last/indicative price: {quote.last_price}",
        f"- Previous close: {quote.previous_close}",
        f"- Currency: {quote.currency}",
        "",
        "## Historical Risk Metrics",
        f"- Total return: {pct(metrics.total_return)}",
        f"- Annualized volatility: {pct(metrics.annualized_volatility)}",
        f"- Max drawdown: {pct(metrics.max_drawdown)}",
        f"- Sharpe ratio: {metrics.sharpe_ratio}",
        "",
        "## Backtrader Baseline",
        f"- Strategy: {backtest.strategy}",
        f"- Start value: {backtest.start_value:.2f}",
        f"- End value: {backtest.end_value:.2f}",
        f"- Strategy total return: {pct(backtest.total_return)}",
        "",
        "## Risk Checklist",
        "- Data may be delayed, adjusted, incomplete, or provider-dependent.",
        "- A simple moving-average strategy is not a trading system.",
        (
            "- Transaction costs, slippage, taxes, liquidity, and survivorship bias are not "
            "modeled here."
        ),
        "- Any real capital decision requires independent research and risk controls.",
    ]
    return "\n".join(lines) + "\n"


def run_data_entry_workflow(
    symbol: str = "SPY",
    start: str = "2025-01-01",
    end: str = "2025-06-30",
    fast: int = 20,
    slow: int = 50,
) -> dict[str, object]:
    CACHE.mkdir(parents=True, exist_ok=True)

    quote = fetch_quote_snapshot(symbol)
    adjustment = "auto_adjust"
    history = fetch_yfinance_history(symbol, start, end, adjustment=adjustment)
    data_receipt = build_ohlcv_snapshot_from_history(
        history,
        symbol=symbol,
        source=SourceSpec(
            provider="yfinance",
            upstream_source="Yahoo Finance",
            asset_class="equity",
            dataset="ohlcv_history",
            access_method="api_pull",
            wheel="yfinance",
            wheel_version=package_version("yfinance"),
            adjustment=adjustment,
        ),
        fetch_config={
            "symbol": symbol,
            "start": start,
            "end": end,
            "auto_adjust": True,
            "adjustment": adjustment,
        },
        raw_payload={
            "symbol": symbol,
            "start": start,
            "end": end,
            "source": "yfinance.download",
            "rows": len(history),
        },
        adjusted=True,
        adjustment=adjustment,
    )
    indicator_receipt = build_indicator_snapshot(
        symbol=symbol,
        history=history,
        market_data_snapshot=data_receipt.snapshot,
    )
    history_path = CACHE / f"{symbol.lower()}_history.csv"
    write_history_csv(history, history_path)

    metrics = summarize(history["close"].astype(float).tolist())
    backtest = run_moving_average_backtest(history, fast=fast, slow=slow)
    risk_note = build_risk_note(symbol, quote, metrics, backtest)

    note_path = CACHE / "latest_risk_note.txt"
    summary_path = CACHE / "latest_summary.json"
    note_path.write_text(risk_note, encoding="utf-8")

    summary: dict[str, object] = {
        "symbol": symbol,
        "start": start,
        "end": end,
        "history_rows": len(history),
        "history_path": str(history_path.relative_to(ROOT)),
        "risk_note_path": str(note_path.relative_to(ROOT)),
        "data_sources": [
            f"{quote.provider} for quote",
            "yfinance package/Yahoo Finance for historical prices",
        ],
        "not_data_source": "TradingView/TV",
        "market_data_snapshot": data_receipt.snapshot.model_dump(mode="json"),
        "data_receipt_path": data_receipt.snapshot.receipt_ref,
        "nautilus_catalog_ref": data_receipt.snapshot.lineage.catalog_ref,
        "indicator_snapshot": indicator_receipt.snapshot.model_dump(mode="json"),
        "indicator_receipt_path": indicator_receipt.snapshot.receipt_ref,
        "backtest": asdict(backtest),
        "metrics": asdict(metrics),
        "quote": asdict(quote),
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary
