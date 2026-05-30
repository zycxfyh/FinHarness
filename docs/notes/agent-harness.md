# Agent Harness

## Current Shape

The OpenAI Agents SDK layer lives in `src/finharness/agent_tools.py`.

Registered tools:

- `get_quote_snapshot`
- `get_historical_risk_metrics`
- `run_finance_graph_workflow`
- `evaluate_latest_risk_note`

The agent is named `Finance Research Harness Agent`.

`run_finance_graph_workflow` calls the LangGraph workflow in `src/finharness/finance_graph.py`.

## Local Checks

Describe the registered agent and tools:

```bash
task agent:describe
```

Run tool-level tests without any model or API key:

```bash
task smoke
```

Run the real SDK `Runner` only when `OPENAI_API_KEY` is already present in the environment:

```bash
task agent:run
```

If `OPENAI_API_KEY` is not set, the script exits cleanly and does not attempt to read secret files.

## Safety Defaults

- The agent must state that outputs are educational and not investment advice.
- The agent must disclose that historical data currently comes from yfinance/Yahoo Finance, not TradingView/TV.
- The agent can run promptfoo risk assertions against generated notes.
