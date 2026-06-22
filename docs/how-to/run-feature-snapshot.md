# How To Run A Feature Snapshot

Use this when you want a quick indicator snapshot from real yfinance data while
keeping the output in the evidence-only lane.

## Preconditions

- Project dependencies are installed.
- Network access to yfinance is available.
- You are in `/root/projects/finharness`.

## Run One Indicator

MACD:

```bash
task feature:macd
```

Squeeze:

```bash
task feature:squeeze
```

SMC-lite:

```bash
task feature:smc
```

Override symbol and date range:

```bash
task feature:macd -- --symbol QQQ --start 2025-01-01 --end 2025-06-30
```

Expected output shape:

```text
symbol=SPY
indicator=macd
rows=121
latest_date=2025-06-27
output_path=data/features/spy_macd_snapshot.json
execution_allowed=false
```

## Run The Combined Snapshot

```bash
task feature:snapshot
```

This writes:

```text
data/features/spy_combined_indicator_snapshot.json
```

## Verify The Boundary

Open the output JSON and check:

- `symbol`
- `indicator`
- `rows`
- `latest_date`
- `source.provider`
- `source.note`
- `execution_allowed: false`

## What This Does Not Prove

- It does not prove a profitable edge.
- It does not create a proposal.
- It does not authorize an order.
- It does not bypass validation, Risk Gate, or human review.
