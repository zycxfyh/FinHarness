# Formula Layer Catalog

Date: 2026-06-02

## Purpose

Define where common quantitative finance formulas belong in FinHarness.

The key distinction:

```text
formula calculation != formula validation != formula-driven execution
```

## Layer Placement

### Layer 2: Indicators / Features

Layer 2 computes descriptive formulas from evidence.

Implemented first:

```text
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

Implemented in:

```text
src/finharness/indicator_layer.py
```

These formulas are evidence features only.

They do not prove edge.

They do not authorize execution.

### Layer 5: Hypotheses

Layer 5 uses formulas to state testable claims.

Example:

```text
If post-filing volatility expansion is meaningful, then realized volatility,
drawdown behavior, and SPY/QQQ context should confirm or disconfirm the claim
over the stated horizon.
```

Layer 5 does not decide whether the formula is useful.

### Layer 6: Validation

Layer 6 tests whether a formula or hypothesis has research value.

Future validation formulas:

```text
factor regression
alpha t-stat
p-value
confidence interval
walk-forward performance
out-of-sample stability
bootstrap confidence bands
probabilistic Sharpe ratio
deflated Sharpe ratio
parameter sensitivity
event study abnormal return
```

### Layer 8: Risk Gate

Layer 8 owns formula-driven risk permission.

Future risk gate formulas:

```text
Kelly fraction
fractional Kelly
volatility targeting
max position limit
max loss limit
portfolio heat
margin / leverage utilization
liquidity-adjusted position cap
```

Kelly can be computed as a metric earlier, but it cannot affect position size
until the risk gate.

### Layer 9 / 10: Execution And Review

Execution and review need real order and fill data.

Future formulas:

```text
slippage
spread cost
market impact
implementation shortfall
arrival price performance
VWAP/TWAP participation analysis
post-trade attribution
```

## Not Yet Implemented In Layer 2

These require benchmark, portfolio, factor, or execution context:

```text
active_return:
  needs benchmark returns

tracking_error:
  needs portfolio and benchmark returns

information_ratio:
  needs active return and tracking error

beta:
  needs market benchmark returns

Jensen alpha:
  needs beta, benchmark, and risk-free rate

factor exposure:
  needs factor returns

turnover:
  needs portfolio weights or position changes

transaction cost:
  needs order/fill/spread/slippage data
```

## Design Rule

Add formulas only when the layer has the required evidence.

Do not create fake precision by calculating portfolio, factor, or execution
metrics from single-symbol OHLCV alone.
