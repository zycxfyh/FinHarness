# How To Do A Safe Paper-Trade Review

> Archived workflow note (2026-06-28): the Alpaca paper/live-trading workflow
> described here is no longer a current mainline how-to. The related code moved
> to `experiments/archive/live_trading_legacy/`, and current `Taskfile.yml` does
> not expose `alpaca:*` tasks.

Use this only for paper-broker workflow validation. The goal is to exercise
receipt, thesis, guard, order, cancel, and reconciliation shape without live
capital at risk.

## Preconditions

- Alpaca paper credentials are configured privately.
- `ALPACA_PAPER=1`.
- You are in `/root/projects/finharness`.
- You have a written thesis and know this is not alpha validation.

## Dry-Run The Strategy Order Script

The Taskfile entry executes by default. To dry-run the same script directly:

```bash
uv run python scripts/alpaca_paper_strategy_order.py --symbol AAPL --qty 1
```

Expected behavior:

- pulls account and latest paper-market data;
- builds a written test thesis;
- evaluates `trading_guard`;
- writes a receipt;
- does not place the paper order because `--execute` is absent.

## Execute The Paper Workflow

```bash
task alpaca:paper-strategy-order
```

This routes to:

```bash
uv run python scripts/alpaca_paper_strategy_order.py --execute
```

The script places a deliberately non-marketable paper limit order, fetches it,
cancels it, checks open orders, and writes a receipt under:

```text
data/receipts/alpaca-paper/
```

## Stop Conditions

Stop and review if:

- the guard returns `trade_allowed=false`;
- the order fills unexpectedly;
- open orders remain after cancel;
- account state is blocked;
- the script returns non-zero;
- the receipt says `workflow_passed=false`.

## Safety Boundary

- This is paper only.
- The live Alpaca endpoint is intentionally not wired.
- Paper success does not authorize live trading.
- A broker receipt is process evidence, not proof of best execution or alpha.
