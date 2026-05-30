# Wheel Status

## Connected

| Wheel | Status | Notes |
| --- | --- | --- |
| Backtrader | Connected | Installed in `.venv`; smoke backtest runs through `task smoke`. |
| vectorbt | Connected | Installed in `.venv`; intended owner of fast vectorized strategy research and parameter sweeps. |
| NautilusTrader | Connected | Installed in `.venv`; intended owner of serious event-driven simulation and backtest/live parity. |
| Riskfolio-Lib | Connected | Installed in `.venv`; intended owner of portfolio construction and optimization. |
| QuantStats | Connected | Installed in `.venv`; intended owner of strategy return diagnostics and tear sheets. |
| OpenAI Agents SDK | Connected | Imports `Agent`, `Runner`, and `function_tool`. API-key runs are intentionally deferred. |
| DeepEval | Connected | Imports `LLMTestCase`; full model-judged evals deferred until keys/models are configured. |
| OpenBB | Partially connected | App imports and `equity.price.quote(..., provider="yfinance")` works. Historical price endpoints currently fail with `KeyError: 'date'` through the yfinance provider. |
| promptfoo | Connected | CLI works after approving `better-sqlite3` build scripts; local echo eval configured. |

## Known Issue

OpenBB historical price calls using the yfinance provider currently fail:

```text
OpenBBError [Unexpected Error] -> KeyError -> 'date'
```

Direct `yfinance.download(...)` works, so the short-term plan is:

1. Use OpenBB for working provider-backed endpoints such as quotes, metadata, indexes, macro sources, and SEC/FRED-style data.
2. Use direct yfinance for price history until the provider conversion issue is resolved upstream or locally isolated.
3. Do not patch third-party source until we have a minimal reproducible issue.
