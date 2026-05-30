# Finance Operating Model

This document defines the minimum structure of a serious financial institution.
It is not a list of financial products. It is the operating skeleton behind
banks, investment banks, asset managers, hedge funds, brokers, and insurers.

Reference institutions:

- JPMorgan Chase: diversified bank with consumer, commercial, investment bank,
  and asset/wealth management businesses.
- Goldman Sachs: global banking, markets, and asset/wealth management.
- BlackRock: asset manager plus investment/risk technology through Aladdin.
- Bridgewater: institutional macro investing with systematic research and risk
  thinking.

## One-Sentence Model

Finance moves capital across time, risk, information, and trust.

The minimal loop:

```text
Capital -> Mandate -> Research/Pricing -> Allocation/Underwriting -> Execution
-> Risk Control -> Operations -> Reporting -> Feedback
```

If a financial system cannot explain each step, it is not yet institution-grade.

## The Minimum Institution

Every serious financial institution needs these functions:

```text
1. Capital and client mandate
2. Data and market infrastructure
3. Research and pricing
4. Portfolio / balance sheet / deal decision
5. Execution
6. Risk management
7. Operations and accounting
8. Compliance and governance
9. Reporting and client communication
10. Feedback and model improvement
```

Different institutions emphasize different parts, but the skeleton remains.

## Front, Middle, Back Office

The classic financial institution split:

```text
Front office:
  Revenue and decisions.
  Clients, sales, trading, portfolio management, investment banking, lending.

Middle office:
  Independent measurement and control.
  Risk, valuation, treasury, performance, model validation, compliance.

Back office:
  Settlement and record truth.
  Operations, accounting, reconciliation, reporting, custody, data quality.
```

This split matters because financial errors often come from mixing decision,
measurement, and recordkeeping into one uncontrolled process.

## Core Flow

### 1. Capital And Mandate

Question:

```text
Whose money is this, and what are we allowed to do with it?
```

Examples:

```text
Bank deposits
Shareholder equity
Insurance premiums
Pension fund assets
Mutual fund assets
Hedge fund capital
Private wealth accounts
Corporate advisory clients
```

Minimum artifacts:

```text
Investment policy statement
Risk tolerance
Liquidity requirement
Return objective
Legal restrictions
Fee model
Time horizon
```

If mandate is unclear, later "performance" is meaningless.

### 2. Data And Infrastructure

Question:

```text
What facts does the institution trust?
```

Data types:

```text
Market data: price, volume, order book, rates, curves, volatility
Fundamental data: financial statements, credit data, macro data
Reference data: identifiers, calendars, corporate actions, instrument metadata
Alternative data: news, web, satellite, flows, text
Internal data: positions, orders, fills, exposures, PnL, limits
```

Minimum controls:

```text
Source lineage
Timestamp
Revision handling
Missing data policy
Corporate action handling
Permission/license tracking
Audit trail
```

Bad data is not a small bug in finance. It is wrong reality.

### 3. Research And Pricing

Question:

```text
What is the asset, deal, loan, or risk worth under uncertainty?
```

Main research styles:

```text
Fundamental research
Quantitative research
Macro research
Credit research
Relative value
Event-driven research
Risk-premia research
Manager/fund research
```

Minimum output:

```text
Hypothesis
Data used
Valuation or signal
Expected return
Risk estimate
Failure mode
Time horizon
Reason to act or not act
```

Research that cannot state its failure mode is storytelling.

### 4. Decision Layer

Question:

```text
What action should be taken, at what size, under which constraints?
```

Decision forms:

```text
Approve or reject a loan
Underwrite or avoid a deal
Buy, sell, hold, hedge, or do nothing
Allocate capital across strategies
Rebalance a portfolio
Set risk limits
Change liquidity buffers
```

Minimum decision record:

```text
Decision
Rationale
Sizing
Risk impact
Expected return
Alternative considered
Approval owner
Review date
```

The institution should remember why it acted.

### 5. Execution

Question:

```text
How do we transform a decision into market or client reality?
```

Execution types:

```text
Market order execution
Algorithmic execution
Block trade
Loan origination
Bond issuance
M&A advisory process
Derivative structuring
Insurance policy issuance
Fund subscription/redemption
```

Minimum metrics:

```text
Fill price
Slippage
Spread
Market impact
Latency
Commission/fees
Failed trades
Counterparty
```

Execution is where ideas become cost.

### 6. Risk Management

Question:

```text
What can kill us, our clients, or the mandate?
```

Risk types:

```text
Market risk
Credit risk
Liquidity risk
Counterparty risk
Operational risk
Model risk
Legal/compliance risk
Concentration risk
Leverage risk
Reputation risk
```

Minimum risk tools:

```text
Exposure
Stress test
Scenario analysis
Value at risk / expected shortfall
Drawdown
Liquidity horizon
Limit monitoring
Independent valuation
Escalation process
```

Risk is not a report after the fact. It is a constraint before action.

### 7. Operations And Accounting

Question:

```text
What actually happened, and do all records agree?
```

Core operations:

```text
Trade capture
Confirmation
Clearing
Settlement
Reconciliation
Position accounting
Cash accounting
Collateral management
Corporate actions
NAV / valuation
```

Minimum truth checks:

```text
Order equals fill
Fill equals broker confirmation
Broker equals custodian
Position equals accounting book
Cash equals bank/custody record
PnL equals price and position change
```

Back office is not low-status work. It is the institution's memory.

### 8. Compliance And Governance

Question:

```text
Are we allowed to do this, and can we prove it?
```

Minimum controls:

```text
Know-your-customer / anti-money-laundering
Suitability
Market abuse surveillance
Restricted list
Personal trading policy
Data licensing
Model governance
Record retention
Conflicts of interest
Regulatory reporting
```

Compliance converts trust into durable permission to operate.

### 9. Reporting

Question:

```text
What should clients, managers, regulators, and risk owners know?
```

Report types:

```text
Performance
Risk exposure
Attribution
Fees
Holdings
Liquidity
Compliance exceptions
Operational breaks
Client commentary
Regulatory filings
```

Minimum standard:

```text
Accurate
Timely
Auditable
Decision-relevant
Consistent with mandate
```

Reporting is not decoration. It is accountability.

### 10. Feedback And Improvement

Question:

```text
What did reality teach us?
```

Feedback loops:

```text
Research hit rate
Forecast error
Backtest vs live performance
Execution cost drift
Risk limit breaches
Operational breaks
Client redemptions
Regulatory issues
Model decay
```

Minimum improvement loop:

```text
Record decision -> Observe outcome -> Attribute cause -> Update model/process
```

Institutions survive by learning before losses become fatal.

## Institution Types

### Bank

Core machine:

```text
Funding -> Lending/investment -> Interest income -> Credit loss control -> Capital management
```

Important metrics:

```text
Net interest margin
Loan losses
Capital ratio
Liquidity coverage
Deposit stability
Return on equity
```

### Investment Bank

Core machine:

```text
Client need -> Advisory/underwriting/market access -> Execution -> Fee/spread
```

Important metrics:

```text
Advisory fees
Underwriting volume
Trading revenue
Client franchise
Risk-weighted assets
League table share
```

### Asset Manager

Core machine:

```text
Client mandate -> Portfolio process -> Risk-adjusted return -> Fees -> Retention
```

Important metrics:

```text
Assets under management
Net flows
Investment performance
Fee rate
Operating margin
Retention
```

### Hedge Fund

Core machine:

```text
Research edge -> Portfolio construction -> Risk control -> Alpha -> Incentive fees
```

Important metrics:

```text
Sharpe
Drawdown
Capacity
Correlation
Hit rate
Liquidity
Alpha decay
```

### Broker / Exchange / Market Maker

Core machine:

```text
Order flow -> Matching/liquidity -> Execution quality -> Spread/fee
```

Important metrics:

```text
Volume
Spread
Latency
Fill rate
Market share
Operational uptime
Regulatory incidents
```

### Insurer

Core machine:

```text
Premium -> Underwriting -> Float investment -> Claims -> Reserves
```

Important metrics:

```text
Combined ratio
Loss ratio
Reserve adequacy
Investment yield
Solvency
Policy retention
```

## What Top Institutions Teach

### JPMorgan Chase

Lesson:

```text
Scale finance is an integrated balance-sheet, client, risk, and operations
machine.
```

Its public reporting separates major businesses such as Consumer & Community
Banking, Commercial & Investment Bank, Asset & Wealth Management, and Corporate.
That reflects the reality that banking, markets, payments, lending, and wealth
are connected through capital, clients, risk, and operations.

### Goldman Sachs

Lesson:

```text
Institutional finance combines advisory, markets, asset management, and risk
intermediation.
```

Its structure shows the front-office engines clearly: banking, markets, and
asset/wealth management. The common substrate is client trust, pricing, risk,
execution, and balance-sheet discipline.

### BlackRock

Lesson:

```text
Modern asset management is investment process plus risk technology plus
distribution.
```

BlackRock's Aladdin platform is important conceptually: serious finance needs a
shared operating system for data, risk, portfolios, and reporting. This is close
to what our FinHarness should become in miniature.

### Bridgewater

Lesson:

```text
Research process, systematic thinking, and portfolio construction are the core
assets of an institutional investor.
```

Bridgewater is useful as a mental model because it emphasizes understanding
economic machines, turning beliefs into systems, and stress-testing views
against reality.

## Minimum Version For FinHarness

Our project should first implement a tiny institutional loop:

```text
Data -> Research hypothesis -> Backtest -> Risk -> Decision note -> Eval -> Report
```

Current state:

```text
Data:
  OpenBB quote
  yfinance historical prices

Research:
  basic moving-average hypothesis

Backtest:
  Backtrader

Risk:
  drawdown and simple risk summary

Eval:
  promptfoo risk-note checks

Agent:
  LangGraph workflow
  Hermes tool bridge
```

Next minimum additions:

```text
1. Instrument master: symbol metadata and source lineage
2. Research note format: hypothesis, data, risk, failure mode
3. Portfolio object: position, cash, exposure, PnL
4. Risk limits: max drawdown, concentration, liquidity, leverage
5. Experiment ledger: every run has parameters, output, timestamp, source
6. Report generator: human-readable investment memo
```

## The Smallest Serious Workflow

Use this as the first institution-grade workflow:

```text
1. Define mandate:
   Educational research only. No investment advice.

2. Select instrument:
   Example: SPY.

3. Validate data:
   Source, date range, missing values, corporate actions.

4. State hypothesis:
   Example: 20-day trend filter may reduce drawdown.

5. Run backtest:
   Include transaction cost assumption.

6. Measure risk:
   Return, volatility, drawdown, exposure, turnover.

7. Compare baseline:
   Strategy vs buy-and-hold.

8. Write decision note:
   What happened, why it might be false, what to test next.

9. Run eval:
   Check disclaimers, risk language, no overclaiming.

10. Save artifact:
   Data path, config, outputs, timestamp.
```

If we can do this cleanly, we have the seed of an institutional research system.

