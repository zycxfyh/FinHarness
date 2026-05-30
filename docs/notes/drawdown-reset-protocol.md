# Drawdown Reset Protocol

Date: 2026-05-27

Purpose: prevent a bad trading session from turning into a behavior spiral.

This is an engineering control, not investment advice.

## Trigger

Enter reset mode when any of these happen:

```text
session drawdown <= -3%
or consecutive losses >= 3
or execution no longer matches the written plan
or the next trade is motivated by making the money back
```

## Immediate Action

```text
Stop opening new trades.
Cancel non-essential pending orders.
Do not increase size to recover losses.
Do not switch instruments to chase movement.
Move OKX interaction to read-only market inspection.
```

If exposure is already open, manage only according to the pre-written
invalidation or risk plan. Do not improvise a larger thesis mid-loss.

## Cooldown

Minimum reset:

```text
30 minutes after a losing trade before any new decision
rest of session off after hard-stop drawdown
next session starts in demo or read-only mode
```

## Review Template

Before trading again, write:

```text
1. What was the original thesis?
2. What invalidated it?
3. Was position size defined before entry?
4. Did I move the stop, average down, overtrade, or chase?
5. Was this a strategy loss or a behavior loss?
6. What exact rule would have blocked the bad action?
```

## OKX-Specific Reminder

Many app watchlist symbols such as `NVDAUSDT`, `OPENAIUSDT`, or `CRCLUSDT`
resolve through the OKX CLI as `*-USDT-SWAP`.

That means:

```text
not real share ownership
derivative/synthetic exposure
liquidation mechanics may apply
funding and platform rules matter
spread and liquidity can differ from the underlying stock
```

Treat these as lab instruments unless a separate, written risk plan says
otherwise.

## FinHarness Commands

```bash
task trading:reset-check
task okx:market
```

For a custom reset check:

```bash
cargo run -q -p finharness-cli -- guard \
  --drawdown-pct -4.2 \
  --consecutive-losses 3
```

Expected hard-stop output:

```text
trade_allowed=false
level=hard_stop
```
