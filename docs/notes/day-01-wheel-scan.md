# Day 01 Wheel Scan

## Decision

Start with the smallest loop that still teaches the real system shape:

1. `backtrader` for a local first backtest.
2. `OpenBB` as the intended finance data platform.
3. `openai-agents-python` for tool-calling agents.
4. `promptfoo` first for eval CLI, then `deepeval` for richer Python evals.

This avoids building a custom framework too early while keeping each piece understandable.

## Finance Wheels

### OpenBB

Role: finance data platform and future data gateway for agents.

Observed quickstart path:

- Upstream docs show `pip install openbb`.
- In this repo, add or sync Python packages with `uv`; do not use direct `pip`.
- CLI is available separately upstream as `openbb-cli`; install it through `uv`
  only if the project actually needs the CLI surface.
- Docs emphasize provider-backed financial data and warn that financial instruments are high risk.

How we use it:

- Treat OpenBB as the primary data abstraction once dependencies are installed.
- Keep a provider boundary in our code so we can use cached CSVs or alternative data while learning.

### Backtrader

Role: beginner-friendly backtesting engine.

Observed quickstart path:

- Upstream docs show `pip install backtrader`.
- In this repo, install or update it through `uv`.
- It is self-contained and has no mandatory external dependencies unless plotting is needed.

How we use it:

- First strategy: buy-and-hold baseline.
- Second strategy: moving-average crossover.
- Use it to learn orders, broker state, positions, and strategy lifecycle.

### vectorbt

Role: fast parameter sweeps and vectorized research.

How we use it:

- Add after a Backtrader baseline exists.
- Use it to compare many windows/assets quickly.

### FinGPT

Role: financial NLP and LLM reference project.

How we use it:

- Do not start here.
- Use later for sentiment, financial text datasets, and model-specific ideas.

## Harness Wheels

### OpenAI Agents SDK

Role: lightweight agent and tool-calling harness.

Observed quickstart path:

- Create an agent with name and instructions.
- Run it with `Runner.run`.
- Add Python functions with `@function_tool`.
- Use handoffs or agents-as-tools only after the single-agent version works.

How we use it:

- Wrap finance metrics as tools.
- Agent produces a research memo from computed facts, not from memory.
- Keep all tool outputs structured and citeable.

### promptfoo

Role: CLI-first eval and red-team harness.

Observed quickstart path:

- Requires modern Node.
- Upstream supports multiple install modes.
- In this repo, run promptfoo through `pnpm exec promptfoo ...`.
- Runs local evals and supports model comparisons, red teaming, CI checks, and security scans.

How we use it:

- First eval: reject memos that give direct investment advice.
- Second eval: require risk warnings.
- Third eval: require citation to computed facts.

### DeepEval

Role: Python-first LLM eval framework.

Observed capabilities:

- Agentic metrics such as task completion, tool correctness, goal accuracy, step efficiency, plan adherence, and tool use.
- RAG metrics such as faithfulness, answer relevancy, contextual precision/recall.
- Hallucination and JSON correctness metrics.

How we use it:

- Add when we have a repeatable Python agent run.
- Use for tool correctness and hallucination checks.

## First Build Loop

We should not begin with an autonomous trading bot.

Build this first:

1. Load or fetch daily price data.
2. Compute returns, volatility, drawdown, and Sharpe ratio.
3. Backtest buy-and-hold and a moving-average crossover.
4. Generate a research memo from those computed facts.
5. Evaluate the memo for risk, citations, and unsupported claims.
