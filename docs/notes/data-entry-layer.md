# Data Entry Layer

## Current Sources

This workflow does not use TradingView/TV data.

Current data paths:

- Quote snapshot: OpenBB `equity.price.quote(..., provider="yfinance")`
- Historical OHLCV: direct `yfinance.download(...)`
- Implied upstream source: Yahoo Finance through the yfinance ecosystem

OpenBB remains the preferred higher-level platform, but its yfinance historical price endpoint currently fails locally with `KeyError: 'date'`. Until that provider conversion issue is isolated, historical prices are fetched directly through yfinance and normalized in `src/finharness/data_entry.py`.

## Workflow

Run:

```bash
task workflow:data-entry
```

It performs:

1. Fetch quote via OpenBB.
2. Fetch historical OHLCV via yfinance.
3. Save normalized data to `data/cache/spy_history.csv`.
4. Run a Backtrader moving-average baseline.
5. Generate `data/cache/latest_risk_note.txt`.
6. Run promptfoo risk-disclosure assertions against the generated note.

## Risk Eval

The promptfoo eval checks that the generated note includes:

- not investment advice
- no guarantee of future returns
- max drawdown
- non-TradingView data-source disclosure
- transaction-cost warning

