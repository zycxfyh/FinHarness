# LangGraph Workflow

## Purpose

LangGraph is now the orchestration layer for the finance workflow.

The OpenAI Agents SDK tool `run_finance_graph_workflow` calls this graph instead of manually chaining steps inside the tool.

## Graph Nodes

`src/finharness/finance_graph.py` defines:

- `data_entry`: runs OpenBB quote, yfinance historical data, metrics, Backtrader, and note generation.
- `risk_eval`: runs promptfoo assertions against the generated risk note.
- `final`: collects the workflow and eval outputs into a compact result.

## Run

```bash
task workflow:data-entry
```

The graph still uses Yahoo Finance/yfinance for historical prices, not TradingView/TV data.
