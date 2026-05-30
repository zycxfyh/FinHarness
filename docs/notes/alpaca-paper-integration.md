# Alpaca Paper Trading Integration

Date: 2026-05-27

Purpose: evaluate Alpaca paper trading as a regulated-broker-style US equity API
sandbox for FinHarness.

This is research and engineering setup, not investment advice.

## Why Alpaca Matters

Alpaca is a better fit than OKX for testing US stock/ETF broker-style workflows:

```text
US equities / ETFs API shape
paper trading account
orders, positions, account, assets
API-key authentication
clear paper vs live endpoints
good fit for agent-controlled trading harnesses
```

It does not solve China-mainland real-money brokerage access by itself.
But it is excellent for learning and system design.

## Security

Do not paste Alpaca API key or secret into chat.
Do not commit credentials.

Use environment variables:

```bash
export ALPACA_API_KEY_ID="..."
export ALPACA_API_SECRET_KEY="..."
export ALPACA_PAPER=1
```

The screenshot shows personal account data. Treat future screenshots carefully.

## Official API Shape

Paper trading base URL:

```text
https://paper-api.alpaca.markets
```

Live trading base URL:

```text
https://api.alpaca.markets
```

Main paper endpoints:

```text
GET /v2/account
GET /v2/account/configurations
PATCH /v2/account/configurations
GET /v2/positions
GET /v2/orders
POST /v2/orders
DELETE /v2/orders/{order_id}
GET /v2/assets
GET /v2/options/contracts
GET /v2/account/activities
```

Auth headers:

```text
APCA-API-KEY-ID
APCA-API-SECRET-KEY
```

Alpaca documentation notes that paper accounts use different API keys from live
accounts. The paper and live API specifications are the same, but the base URL
and credentials differ. In most cases their docs suggest setting:

```bash
APCA_API_BASE_URL=https://paper-api.alpaca.markets
```

Our local scripts use `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY` so the
variable names are explicit and do not collide with other tools.

## How To Configure Locally

### Step 1: Generate Paper API Keys

In Alpaca Dashboard:

```text
Paper Trading account -> API -> Generate / Regenerate keys
```

Do not paste the key or secret into chat.

### Step 2: Export Environment Variables

For the current WSL shell:

```bash
export ALPACA_API_KEY_ID="your_paper_key_id"
export ALPACA_API_SECRET_KEY="your_paper_secret_key"
export ALPACA_PAPER=1
```

Optional Alpaca-compatible variable:

```bash
export APCA_API_BASE_URL="https://paper-api.alpaca.markets"
```

### Step 3: Verify Read-Only Access

```bash
task alpaca:paper-check
```

Expected result:

```text
status
cash
portfolio_value
buying_power
positions_count
open_orders_count
```

### Step 4: Keep Secrets Out Of Git

Do not create a committed `.env` with real keys.

If you want persistent local config, use a private shell/session secret manager
or an ignored local file loaded manually. Do not commit it.

## Safe Adoption Phases

### Phase 0: Read-Only Paper Check

```text
Fetch account.
Fetch positions.
Fetch open orders.
No order placement.
```

### Phase 1: Paper Place/Cancel

```text
Place tiny notional limit order far from market.
Confirm order appears.
Cancel immediately.
Confirm no open order remains.
```

### Phase 2: Paper Capability Surface

Commands:

```bash
task alpaca:paper-capabilities
task alpaca:paper-config-dry-run
task alpaca:paper-config-experiment
task alpaca:paper-assets
task alpaca:paper-crypto-assets
task alpaca:paper-option-contracts
```

Paper experiment config:

```text
suspend_trade=false
no_shorting=false
fractional_trading=true
max_margin_multiplier=4
max_options_trading_level=3
disable_overnight_trading=false
trade_confirm_email=all
dtbp_check=both
pdt_check=both
```

This is for paper experimentation only. Live endpoint support remains
intentionally absent.

### Phase 3: FinHarness Adapter

Add:

```text
BrokerAccount
BrokerPosition
BrokerOrder
BrokerFill
PaperExecutionAdapter
```

### Phase 4: Agent Harness

Only after adapter and tests:

```text
Agent proposes order.
Risk check runs.
Human approves exact order.
Paper order executes.
Ledger records result.
```

### Phase 5: Live

Not now.

Prerequisites:

```text
legal/tax eligibility
funding path
loss limits
human approval
security review
paper track record
```

## Alpaca vs OKX vs IBKR

```text
Alpaca:
  best for US equity API paper trading and agent workflow testing.

OKX:
  best for crypto/derivative API control and Web4 exchange experiments.

IBKR:
  best long-term serious regulated broker candidate, but heavier onboarding and API.
```

## Next Step

Run:

```bash
task alpaca:paper-check
```

after setting:

```bash
ALPACA_API_KEY_ID
ALPACA_API_SECRET_KEY
```

No credentials are stored by the project.

## Source Links

- https://docs.alpaca.markets/
- https://docs.alpaca.markets/docs/about-paper-trading
- https://docs.alpaca.markets/us/docs/getting-started-with-trading-api
- https://docs.alpaca.markets/us/docs/authentication
- https://docs.alpaca.markets/reference/getaccount-1
- https://docs.alpaca.markets/reference/getallopenpositions-1
- https://docs.alpaca.markets/reference/postorder
- https://github.com/alpacahq/alpaca-py
