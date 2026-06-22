# Config And Environment Reference

This page lists known configuration and environment variables used by
FinHarness. It is a reference, not setup instructions.

Never commit real secrets. Do not print or paste credentials into docs, receipts,
reviews, or chat.

## Local Template

The repository includes `.env.example` with an Alpaca paper template:

```text
ALPACA_API_KEY_ID=
ALPACA_API_SECRET_KEY=
ALPACA_PAPER=1
```

Copy only the section you need into a private ignored file, such as
`.env.alpaca`.

## Variables

| Variable | Used by | Purpose | Safety note |
| --- | --- | --- | --- |
| `ALPACA_API_KEY_ID` | `finharness.alpaca_client` | Alpaca API key id. | Secret. Keep out of git and logs. |
| `ALPACA_API_SECRET_KEY` | `finharness.alpaca_client` | Alpaca API secret. | Secret. Keep out of git and logs. |
| `ALPACA_PAPER` | Alpaca scripts/client | Select paper mode. | Keep paper mode for experiments. |
| `ALPACA_TEST_SYMBOL` | `scripts/alpaca_paper_order_cycle.py` | Override tiny paper test symbol. | Paper-only helper. |
| `ALPACA_TEST_QTY` | `scripts/alpaca_paper_order_cycle.py` | Override tiny paper test quantity. | Paper-only helper. |
| `OPENAI_API_KEY` | `task agent:run`, agent scripts | Enables the real OpenAI agent runner. | Secret; optional for most local docs path. |
| `FINHARNESS_TRADING_STATE_PATH` | `finharness.trading_state_store` | Override persisted behavior-state file. | Use carefully; changing state path changes guard inputs. |
| `FINHARNESS_SEC_USER_AGENT` | `finharness.events` | SEC EDGAR user-agent override. | Use a truthful user agent for EDGAR access. |
| `FINHARNESS_OKX_LIVE_WRITE_ARMED` | `finharness.okx_cli` | Hard kill-switch for OKX live writes. | Defaults closed. Live write needs this and the mutation env gate. |
| `FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS` | `finharness.okx_cli` | Enables live OKX mutating commands after other gates. | Defaults closed. Does not bypass attestation, thesis, cap, or receipt. |
| `PYTHONPATH` | `Taskfile.yml` | Points tasks at `src`. | Project task config. |
| `PROMPTFOO_DISABLE_TELEMETRY` | `Taskfile.yml` | Disables promptfoo telemetry in task runs. | Project task config. |
| `PROMPTFOO_DISABLE_UPDATE` | `Taskfile.yml` | Disables promptfoo update checks in task runs. | Project task config. |

## Live-Write Boundary

OKX live writes require all of the following:

- `FINHARNESS_OKX_LIVE_WRITE_ARMED=1`
- `FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS=1`
- command routed through `task okx:live-write`
- written thesis via `--thesis`
- `--attester` and `--reason`
- bounded notional under the governed ceiling; `--max-notional` is only a
  per-request tightening limit
- behavior guard allowing the request
- interactive confirmation unless `--yes` is used

These env vars only open a gate for reviewable execution. They do not authorize
autonomous trading.
