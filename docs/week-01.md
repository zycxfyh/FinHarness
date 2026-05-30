# Week 01

## Objective

Create the smallest useful finance research loop:

1. Get price data.
2. Calculate risk and return.
3. Backtest a simple strategy.
4. Produce a short research note.
5. Evaluate the note.

## Daily Plan

### Day 1: Map the Wheels

- Read OpenBB quickstart.
- Read Backtrader quickstart.
- Read OpenAI Agents SDK examples.
- Read promptfoo or DeepEval quickstart.

Deliverable: notes in `docs/notes/`.

### Day 2: Data Pull

- Pull daily prices for `SPY`, `QQQ`, `AAPL`, and `BTC`.
- Save normalized data under `data/cache/`.
- Keep raw data out of git.

Deliverable: a reproducible script in `src/`.

### Day 3: Metrics

- Compute daily return.
- Compute annualized volatility.
- Compute max drawdown.
- Compute Sharpe ratio.

Deliverable: a table and chart.

### Day 4: Backtest

- Implement buy-and-hold.
- Implement moving-average crossover.
- Compare both on the same asset.

Deliverable: one backtest report.

### Day 5: Agent

- Wrap the metrics and backtest as tools.
- Ask an agent to write a short research memo.
- Require citations to local computed facts.

Deliverable: generated memo with traceable inputs.

### Day 6: Eval

- Test whether the memo:
  - includes risk warnings
  - avoids direct investment advice
  - cites computed data
  - does not invent unsupported claims

Deliverable: eval config and failing/passing examples.

### Day 7: Review

- Write what worked.
- Write what failed.
- Pick the next capability to deepen.

