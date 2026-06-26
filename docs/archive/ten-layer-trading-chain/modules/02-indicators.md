# Module: Indicators

Status: active
Owner: FinHarness
Layer: 2 - Indicators / features
Last updated: 2026-06-01

## Purpose

The indicators module transforms first-layer market data into auditable
technical feature snapshots.

Indicators describe market state. They do not authorize execution.

## Current Responsibilities

```text
consume first-layer OHLCV / MarketDataSnapshot evidence
compute core indicators using mature indicator libraries
compute OHLCV-derived risk/return formula features
write IndicatorSnapshot, IndicatorQuality, IndicatorLineage, and IndicatorReceipt
link indicator lineage back to MarketDataSnapshot
persist normalized indicator payloads
expose indicator output to workflow consumers
```

## Non-Goals

```text
no trade authorization
no portfolio construction
no execution permission
no claim that indicators create edge by themselves
no local ownership of standard indicator math when mature libraries exist
```

## Inputs

Current inputs:

```text
normalized OHLCV history
MarketDataSnapshot
symbol
indicator parameters
```

Upstream module:

```text
01-market-data
```

## Outputs

Current outputs:

```text
IndicatorSnapshot
IndicatorQuality
IndicatorLineage
IndicatorReceipt
normalized indicator JSON payload
workflow summary fields
```

Downstream consumers:

```text
research workflows
future event/interpretation/hypothesis/proposal layers
review and reporting workflows
```

## Current Implementation

Important files:

```text
src/finharness/indicator_layer.py
src/finharness/indicator_graph.py
src/finharness/workflow.py
tests/test_indicator_layer.py
tests/test_indicator_graph.py
```

Experimental feature scripts still exist:

```text
src/finharness/indicators/
scripts/run_indicator_snapshot.py
scripts/run_macd_snapshot.py
scripts/run_smc_snapshot.py
scripts/run_squeeze_snapshot.py
tests/test_indicators.py
```

Those scripts are useful experiments, but the institution-grade indicator layer
is `src/finharness/indicator_layer.py`.

Runtime artifacts:

```text
data/normalized/indicators/
data/receipts/indicators/
data/features/
```

Tasks:

```text
task feature:macd
task feature:squeeze
task feature:smc
task feature:snapshot
task indicators:graph
task test
task check
```

## Mature Wheels / External Systems

```text
TA-Lib:
  SMA, MACD, RSI, BBANDS.

pandas-ta:
  ATR.

pandas / numpy:
  simple returns, log returns, wealth index, drawdown, drawdown duration,
  realized volatility, Sharpe-style descriptive metrics, rolling VaR/CVaR,
  skewness, and kurtosis.

vectorbt:
  research and parameter sweeps, not the primary indicator math owner.

Pydantic:
  typed governance objects.
```

## Quality / Lineage / Receipt

Quality checks currently include:

```text
row count
feature count
warmup null counts
latest null features
infinite numeric values
warmup nulls for rolling formulas
```

Lineage currently records:

```text
input MarketDataSnapshot id
input payload ref
indicator specs
library name and version
indicator params
computed_at_utc
transform version
output hash
output ref
```

Receipt object:

```text
IndicatorReceipt
```

Permission boundary:

```text
IndicatorSnapshot.execution_allowed = false
```

## Upgrade Log

### 2026-06-01: Library-Backed Indicator Layer

Why:

```text
The second layer should call indicator libraries to process first-layer market
data instead of hand-rolling standard technical indicators.
```

What changed:

```text
Installed TA-Lib and pandas-ta.
Added IndicatorSpec, IndicatorQuality, IndicatorLineage, IndicatorSnapshot, and
IndicatorReceipt.
Computed TA-Lib SMA/MACD/RSI/BBANDS and pandas-ta ATR.
Linked indicator receipts back to MarketDataSnapshot.
Integrated indicator output into run_data_entry_workflow.
```

Evidence:

```text
tests/test_indicator_layer.py
task check passed with 38 Python tests
docs/notes/indicator-layer-execution.md
```

Risks:

```text
Warmup periods create nulls by design.
Current indicator set is basic.
Experimental hand-written indicators still need classification or replacement.
Indicators can create false confidence if treated as signals.
```

Next:

```text
Add library-backed ATR/ADX/OBV/volume feature group.
Add feature drift and indicator agreement checks.
Add a feature catalog only after snapshots and receipts stabilize.
Separate experimental custom indicators from production indicator layer.
```

### 2026-06-02: Risk / Return Formula Features

Why:

```text
The project needed the core quantitative formulas to live inside the
evidence-producing indicator layer instead of remaining only in ad hoc workflow
summaries.
```

What changed:

```text
Added OHLCV-derived formula features:
  simple_return
  log_return
  wealth_index
  cumulative_return
  cumulative_log_return
  drawdown
  max_drawdown_to_date
  drawdown_duration
  rolling_mean_return_20d
  rolling_volatility_20d_annualized
  expanding_mean_return_annualized
  expanding_return_annualized
  expanding_volatility_annualized
  expanding_sharpe
  rolling_var_95_20d
  rolling_cvar_95_20d
  rolling_skew_20d
  rolling_kurtosis_20d
```

Evidence:

```text
src/finharness/indicator_layer.py
tests/test_indicator_layer.py
docs/notes/2026-06-02-formula-layer-catalog.md
```

Risks:

```text
Formula calculation is not formula validation.
Single-symbol OHLCV cannot support benchmark, factor, portfolio, or execution
metrics by itself.
Rolling formulas have warmup nulls by design.
```

Next:

```text
Add benchmark-aware formulas later:
  beta
  active_return
  tracking_error
  information_ratio
  Jensen alpha

Add factor-aware formulas in the validation layer.
Add transaction-cost formulas only after execution/fill evidence exists.
```

### 2026-06-01: Independent Indicator LangGraph

Why:

```text
The second layer needed the same strict graph shape as the Events layer instead
of being hidden inside run_data_entry_workflow.
```

What changed:

```text
Added indicator_graph.py with:
  source_config -> load_market_data -> compute_indicators -> quality -> lineage
  -> snapshot -> receipt -> consumer_handoff -> review_hook -> final.

The graph consumes MarketDataSnapshot evidence from the first-layer graph.
Added CLI/task and graph tests.
```

Evidence:

```text
src/finharness/indicator_graph.py
scripts/run_indicator_graph.py
tests/test_indicator_graph.py
task indicators:graph
```

## Open Risks

```text
Indicator output may be overinterpreted as a trade signal.
The module currently covers only a basic technical indicator set.
No feature importance, regime classification, or cross-asset indicator quality.
No formal feature-store/cross-run comparison yet.
```

## Next Upgrades

```text
1. Add ADX/OBV/volume features through TA-Lib or pandas-ta.
2. Add indicator-family grouping and parameter presets.
3. Add a quality rule for latest-row readiness per indicator family.
4. Add comparison between indicator states and later proposal outcomes.
5. Document experimental indicators as separate from library-backed indicators.
```
