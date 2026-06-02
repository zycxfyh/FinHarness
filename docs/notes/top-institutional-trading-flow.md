# Top Institutional Trading Flow

Date: 2026-05-31

Purpose: compress how top financial institutions turn market views into
controlled trades, then map that process back into FinHarness.

This is operating-model research, not investment advice.

## Bottom Line

Top institutions do not treat trading as one action.

They separate the lifecycle:

```text
Mandate
-> data and market state
-> research / signal / pricing
-> portfolio construction
-> pre-trade risk and compliance
-> order plan
-> execution venue / broker / EMS / OMS
-> post-trade capture and reconciliation
-> performance, attribution, and TCA
-> review and model/process improvement
```

The important lesson for FinHarness:

```text
The trade is only one step. The product is the controlled workflow around it.
```

## What The Best Firms Seem To Have In Common

Public descriptions from BlackRock, J.P. Morgan, Goldman Sachs, Bridgewater,
and QuantConnect point to the same shape:

```text
shared data language
portfolio-aware research
pre-trade analytics
risk and compliance checks
controlled execution
post-trade analytics
audit trail and feedback
```

Examples:

- BlackRock Aladdin emphasizes portfolio risk, performance, scenario analysis,
  compliance, oversight, and a whole-portfolio operating platform.
- J.P. Morgan Markets Execute combines market analytics, liquidity access,
  execution workflows, pre-trade, real-time, and post-trade transaction cost
  analytics.
- Goldman Sachs Marquee exposes institutional market insights, analytics,
  execution capabilities, data services, APIs, pre-trade analytics, portfolio
  analytics, and post-trade analytics.
- Bridgewater describes its process as fundamental, systematic, repeatable,
  tested against reality, and continuously improved.
- QuantConnect / LEAN is useful as a public engine reference because it joins
  research, backtesting, optimization, and live trading in one modular system.

## Institutional Flow, Expanded

### 1. Mandate

Question:

```text
Whose capital is this, and what are we allowed to do?
```

Artifacts:

```text
client mandate
investment policy
allowed instruments
leverage limits
liquidity constraints
benchmark
tax / regulatory constraints
approval authority
```

FinHarness equivalent:

```text
mode = research | paper | demo | live-read | live-write
capital_scope = educational / paper unless explicitly changed
allowed_symbols
allowed_venues
max_notional
human_approval_required
```

### 2. Data And Market State

Question:

```text
What facts does the system trust right now?
```

Artifacts:

```text
instrument master
market data snapshot
corporate actions
calendar/session state
positions
cash
open orders
fills
fees
source lineage
timestamps
```

FinHarness equivalent:

```text
yfinance/OpenBB/venue market snapshot
broker account read
open order read
receipt with source and timestamp
```

Missing next:

```text
instrument master
source-quality flags
market-session awareness
corporate-action policy
```

### 3. Research / Signal / Pricing

Question:

```text
Why might this trade have positive expected value, and when is that belief false?
```

Artifacts:

```text
hypothesis
data window
feature/signal
backtest or pricing model
expected return
risk estimate
failure mode
disconfirming evidence
```

FinHarness equivalent:

```text
vectorbt trend screen
Backtrader baseline
indicator snapshots
written thesis and invalidation
```

Hard rule:

```text
Signals describe market state. They never authorize execution.
```

### 4. Portfolio Construction

Question:

```text
What should the portfolio own after this decision?
```

Artifacts:

```text
target weights
position size
cash impact
gross/net exposure
concentration
correlation/crowding
hedges
liquidity budget
```

FinHarness equivalent today:

```text
single selected candidate
fixed small quantity
max notional budget
```

Missing next:

```text
portfolio object
position-aware sizing
exposure limits
cash and buying-power normalization
```

### 5. Pre-Trade Risk And Compliance

Question:

```text
Is this order allowed before it touches the market?
```

Checks:

```text
mandate allowed
instrument allowed
venue allowed
account active
no unexpected open orders
notional within budget
drawdown/cooldown guard clear
liquidity and spread acceptable
leverage/margin acceptable
human approval present if needed
```

FinHarness equivalent:

```text
TradingState guard
Alpaca account status
open-orders-before check
budget check
execute flag default false
```

Missing next:

```text
typed risk-limit config
liquidity/spread gate
session/calendar gate
explicit approval receipt
```

### 6. Order Plan

Question:

```text
What exact order should be sent, and why this execution method?
```

Artifacts:

```text
symbol
side
quantity / notional
order type
limit price or algo instructions
time in force
execution benchmark
cancel/replace rule
expected cost
invalidation
client order id
```

FinHarness equivalent:

```text
paper limit buy
price near latest close
immediate cancel after acceptance
client_order_id
thesis and invalidation
```

This is intentionally not yet a production execution algorithm.

### 7. Execution

Question:

```text
How does the order enter the market or broker system?
```

Institutional layers:

```text
OMS: order intent, approvals, allocations, audit
EMS: venue routing, execution tools, algos, liquidity
broker/exchange: actual order handling and fills
```

FinHarness equivalent:

```text
official broker/exchange adapter
paper/demo first
live-write behind explicit gates only
```

Hard rule:

```text
FinHarness should not become a homemade OMS, EMS, matching engine, margin
engine, or broker accounting system.
```

### 8. Post-Trade Capture And Reconciliation

Question:

```text
What actually happened?
```

Artifacts:

```text
order status
fills
average price
fees
remaining quantity
positions after
cash after
open orders after
cancel status
exceptions
```

FinHarness equivalent:

```text
fetch order
cancel order
open-orders-after check
JSON receipt
```

Missing next:

```text
fills ledger
positions-after snapshot
cash-after snapshot
exception taxonomy
```

### 9. Performance, Attribution, And TCA

Question:

```text
Did the trade and strategy behave as expected?
```

Artifacts:

```text
PnL
drawdown
slippage
spread cost
market impact
fees
benchmark comparison
factor/sector attribution
hit rate
turnover
```

FinHarness equivalent today:

```text
vectorbt return/drawdown
basic receipt
```

Missing next:

```text
QuantStats-style report
transaction cost analysis
post-trade review template
strategy vs benchmark ledger
```

### 10. Review And Improvement

Question:

```text
What should change in the system before the next decision?
```

Artifacts:

```text
research review
trade review
risk exception review
model drift review
data-quality review
process change log
```

FinHarness equivalent:

```text
receipt-first workflow
ideas backlog
docs/think notes
tests around guards and workflows
```

## FinHarness Target Flow

Near-term controlled loop:

```text
1. Read mandate config.
2. Read market data and account state.
3. Generate research candidates using mature wheels.
4. Build a typed proposal.
5. Run portfolio, behavioral, account, and venue risk gates.
6. Build an order plan.
7. Preview order.
8. Execute only in paper/demo unless live-write is explicitly enabled.
9. Reconcile order/account state.
10. Write receipt.
11. Generate review report.
```

The current `src/finharness/trade_graph.py` already has:

```text
market_data
research
account
risk_gate
order_plan
execution
receipt
final
```

So the next serious upgrade is not "make it smarter". It is:

```text
make each boundary typed, auditable, and harder to bypass.
```

## Recommended Next Build Step

Add a proposal object before `risk_gate`.

Minimum schema:

```text
proposal_id
mode
strategy_id
symbol
side
quantity_or_notional
horizon
thesis
invalidation
data_sources
research_metrics
portfolio_impact
known_limitations
created_at_utc
```

Then change the graph to:

```text
market_data
-> research
-> account
-> proposal
-> risk_gate
-> order_plan
-> execution
-> receipt
-> final
```

Why this matters:

```text
Institutions do not let raw research output become an order. They turn it into
a controlled proposal, then pass that proposal through independent gates.
```

## Sources

- BlackRock Aladdin Risk:
  https://www.blackrock.com/aladdin/products/aladdin-risk
- BlackRock Aladdin whole-portfolio platform note:
  https://www.blackrock.com/aladdin/the-instrument-of-change-empowering-scalability-and-growth
- J.P. Morgan Markets Execute:
  https://markets.jpmorgan.com/pricing-and-execution/execute
- Goldman Sachs Marquee history:
  https://www.goldmansachs.com/our-firm/history/moments/2014-marquee
- Goldman Sachs institutional-grade solutions / Marquee:
  https://www.goldmansachs.com/what-we-do/ficc-and-equities/custody-solutions/our-solutions/institutional-grade-solutions
- Goldman Sachs systematic trading strategies:
  https://www.goldmansachs.com/what-we-do/ficc-and-equities/systematic-trading-strategies
- Bridgewater:
  https://www.bridgewater.com/
- Bridgewater FAQ:
  https://www.bridgewater.com/working-at-bridgewater/faqs
- QuantConnect / LEAN:
  https://www.quantconnect.com/
  https://www.quantconnect.com/docs/v2/lean-engine/getting-started
