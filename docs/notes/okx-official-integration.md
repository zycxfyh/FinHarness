# OKX Official Agent Integration

Date: 2026-05-26

Goal: integrate OKX without hand-rolling exchange auth, order, and account
logic when the official OKX agent tooling already exists.

## Security Incident

An OKX API key/secret was shown in chat via screenshot.

Action required:

```text
Revoke that API key immediately.
Do not reuse it.
Create a fresh key only after deciding the integration mode.
```

Recommended first setup:

```text
No withdrawal permission
Read-only where possible
Demo trading before live trading
IP allowlist for any API-key profile
Human approval before every write/trade operation
```

Never store real OKX credentials in this repository.
Do not paste API keys into chat.

## Official Wheel

OKX has an official GitHub organization and an official agent-skills repo.

Sources:

- https://github.com/okx
- https://github.com/okx/agent-skills
- https://www.npmjs.com/package/@okx_ai/okx-trade-cli

The official repo describes `agent-skills` as plug-and-play AI agent skills for
OKX. The skills route an AI agent to the official `okx` CLI rather than forcing
each project to wire REST APIs manually.

Current package registry entry observed:

```text
name: @okx_ai/okx-trade-cli
version: 1.3.5
bin: okx
license: MIT
```

Local CLI observed on 2026-05-27:

```text
okx version: 1.3.5
pilot: installed
public market commands work without reading account credentials
```

## What The Official Skills Cover

From `okx/agent-skills`:

```text
okx-cex-auth:
  OAuth login / API-key setup / auth helper.

okx-cex-market:
  Public market data: tickers, order books, candles, funding, OI,
  instruments, screeners, and technical indicators. No credentials required.

okx-cex-portfolio:
  Account balances, positions, PnL, fees, account config, transfers.
  Requires credentials.

okx-cex-trade:
  Spot, perpetual swap, futures, options, event contracts, TP/SL, TWAP,
  iceberg, conditional/OCO orders. Requires credentials.

okx-cex-bot:
  Grid and DCA bots. Requires credentials.

okx-cex-earn:
  Earn products. Requires credentials.

okx-cex-smartmoney:
  Smart-money analytics. Requires credentials.

okx-sentiment-tracker:
  News, sentiment, trending coins, market mood.
```

This is closer to our Web4 direction than a raw REST wrapper:

```text
Agent -> official skill instructions -> okx CLI -> OKX
```

## Integration Decision

Do not maintain a custom OKX REST client now.

Use the official CLI as the primary OKX tool surface:

```text
Market data:
  okx market ...

Portfolio/account:
  okx account ...

Trading:
  okx spot/swap/futures/options ...
```

Our harness should add:

```text
permission boundaries
demo/live mode checks
human approval gates
logging
evals
reporting
research workflows
```

OKX should own:

```text
auth
API signing
endpoint mapping
CLI command semantics
exchange-specific edge cases
```

## Safe Adoption Phases

### Phase 0: No Secrets, Public Market Only

Install official CLI only after explicit approval:

```bash
pnpm add -g @okx_ai/okx-trade-cli
```

For one-off public market checks, prefer an ephemeral `pnpm dlx` invocation
when it works for the command being tested, so we do not add a global tool
before the integration mode is settled.

Then test public data:

```bash
okx market ticker BTC-USDT --json
okx market candles BTC-USDT --bar 1D --limit 30 --json
okx market orderbook BTC-USDT --sz 5 --json
```

No API key required.

### Phase 1: Agent Reads Market Data

Connect only read-only market commands into FinHarness/Hermes.

Allowed:

```text
Ticker
Candles
Order book
Funding rate
Open interest
Instruments
Indicators
Market filters
```

Blocked:

```text
Account
Transfer
Order placement
Bots
Earn
```

### Phase 2: Demo Account Read

Use official auth/config flow.

Preferred for an end user:

```bash
okx config init
```

or OAuth flow if using the official auth skill.

Run only demo/read commands:

```bash
okx --demo account balance
okx --demo account positions
```

### Phase 3: Demo Trading With Approval

Only after explicit human approval:

```text
Agent proposes order
Risk check runs
Human confirms exact command
Command executes in demo mode
Result is logged
```

### Phase 4: Live Read-Only

Only after:

```text
Fresh key
IP whitelist
No withdrawal permission
Read-only permission
No trade permission
Audit logging
```

### Phase 5: Live Trading

Not now.

Prerequisites:

```text
Position limits
Loss limits
Order size limits
Kill switch
Human confirmation
Experiment ledger
Post-trade reconciliation
Security review
```

## How This Fits FinHarness

FinHarness should treat OKX as a new data/execution adapter:

```text
Data adapter:
  OKX market ticker/candles/funding/OI

Portfolio adapter:
  OKX account balance/positions, read-only first

Execution adapter:
  OKX demo order commands, gated

Risk adapter:
  pre-trade checks and post-trade reconciliation
```

Minimum workflow:

```text
OKX market data -> strategy hypothesis -> backtest -> risk report -> eval
```

Do not begin with live trading.

## Hermes Integration

Hermes can call the official CLI through a narrow tool wrapper.

First safe wrapper:

```text
run_okx_market_command
```

Allowed commands:

```text
okx market ticker
okx market candles
okx market orderbook
okx market funding-rate
okx market open-interest
okx market instruments
okx market filter
```

Blocked commands:

```text
okx account
okx spot
okx swap
okx futures
okx options
okx bot
okx earn
okx config
okx auth
```

This gives the agent market intelligence without account risk.

## Local Wrapper

FinHarness has an OKX wrapper:

```text
src/finharness/okx_cli.py
scripts/okx_market_snapshot.py
scripts/okx_live_status.py
crates/finharness-cli (Rust)
task okx:market
task okx:live-status
task okx:live-read
task okx:demo
task okx:live-write
```

Read-only commands are allowlisted for market, account, spot, swap, futures,
and option modules. Live write commands are connected for account, spot, swap,
futures, and option modules, but require both:

```text
task okx:live-write
FINHARNESS_OKX_ENABLE_LIVE_MUTATIONS=1
```

The wrapper still blocks earn, bot, event, smartmoney, setup, pilot, skill, and
upgrade modules. It also does not expose `okx config show`, because local CLI
profile configuration can include sensitive account setup details.

The goal is to make the real execution path available without making accidental
or stress-driven execution easy.

Watchlist symbols reconstructed from the OKX app may be compact names such as
`NVDAUSDT`. The local wrapper now tries both:

```text
NVDA-USDT
NVDA-USDT-SWAP
```

For stock-like app symbols, the working instrument is often the `*-USDT-SWAP`
variant. Treat this as derivative/synthetic exposure, not equity ownership.

## Behavioral Drawdown Guard

After large drawdown or several consecutive losses, FinHarness should move
from execution mode into review mode.

Local guard:

```text
src/finharness/trading_guard.py
crates/finharness-cli (Rust guard command)
task trading:reset-check
```

Default hard stops:

```text
daily/session drawdown <= -3%
or consecutive losses >= 3
```

Default caution:

```text
daily/session drawdown <= -1.5%
or consecutive losses >= 2
or no written thesis
or less than 30 minutes since a losing trade
```

These defaults are engineering guardrails, not investment advice. Tune them
before any real-capital workflow.

## Key Takeaway

The official OKX project is not just an SDK. It is already an Agent-facing
exchange tool layer.

Therefore:

```text
Use official OKX CLI and skills.
Do not hand-roll auth/signing/order logic now.
Build our value in permissioning, evals, reports, risk, and workflow.
```
