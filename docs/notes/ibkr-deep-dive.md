# Interactive Brokers Deep Dive

Date: 2026-05-27

Purpose: evaluate Interactive Brokers (IBKR) as the primary serious overseas
broker candidate for a China-mainland resident and as a future FinHarness API
integration target.

This is research, not legal, tax, or investment advice.

## Bottom Line

IBKR is the first broker worth deep investigation if the goal is a real overseas
securities account rather than synthetic exposure.

Why:

```text
Global market access
Professional infrastructure
Strong API ecosystem
Multi-currency account support
Commonly used by international investors
Paper trading support
Regulated securities custody, unlike crypto stock-perpetual exposure
```

But the hard parts are not technical:

```text
KYC eligibility
proof of residential address
funding from a same-name bank account
China-side FX usage restrictions
tax forms and reporting
US estate-tax exposure for large direct US holdings
```

## What IBKR Is Good For

IBKR is relevant if we want:

```text
US stocks and ETFs
Hong Kong stocks
options
futures
bonds
multi-currency cash
margin, when eligible
professional order types
API trading
paper trading
```

For our project, IBKR is useful in two tracks:

```text
Track 1: real broker feasibility study
Track 2: future regulated-broker API adapter for FinHarness
```

## Account Opening: What To Verify

Do not assume success until the live application confirms eligibility.

Minimum applicant data usually includes:

```text
legal name
date of birth
residential address
tax residency
citizenship/nationality
employment status
source of wealth / source of funds
investment experience
financial profile
trading permissions requested
```

Typical documents:

```text
identity document
proof of residential address
tax certification, usually W-8BEN for non-US persons
```

For China-mainland users, the key friction is proof of address and funding path,
not simply clicking through the application.

## Proof Of Address

IBKR's documentation and account workflow require proof of identity and proof of
address. For mainland China applicants, acceptable address evidence may include
China-specific documents in addition to common global documents, but acceptance
depends on the exact workflow and review.

Common proof-of-address categories to prepare:

```text
bank statement
utility bill
government-issued residence document
household registration / hukou style document if accepted
driver license or residence permit if it displays address
```

Action:

```text
Before applying, prepare one clean document showing your name and current
residential address in a way IBKR accepts.
```

## Tax Forms

### W-8BEN

Non-US individuals generally use IRS Form W-8BEN to certify foreign beneficial
owner status.

Practical effects:

```text
Broker knows you are not a US person for withholding purposes.
US-source dividends are withheld according to default rate or treaty claim.
Form must be kept valid and renewed when required.
```

Official IRS source:

- https://www.irs.gov/forms-pubs/about-form-w-8-ben

### US Dividend Withholding

IRS Publication 515 covers withholding for payments to nonresident aliens and
foreign persons.

Simplified:

```text
US-source dividends are commonly subject to 30% withholding unless a treaty
reduces it.
```

China tax residents may have treaty considerations, but do not assume the broker
applies a reduced rate correctly until the form workflow confirms it.

Official IRS source:

- https://www.irs.gov/publications/p515

### Capital Gains

For nonresident aliens, US taxation of capital gains is usually more limited
than dividends, but special conditions can apply, including presence in the US
for 183 days or more in the tax year.

Official IRS source:

- https://www.irs.gov/publications/p519

### Estate Tax

Hidden issue:

```text
Direct US situs assets can create US estate-tax exposure for nonresident
non-citizens.
```

This matters more after the portfolio becomes large. For early learning, it is
not the first blocker, but it should be understood before building serious
long-term holdings.

## Funding Path

IBKR funding is not the same as OKX crypto transfer.

Important principles:

```text
Deposits should come from a bank or brokerage account in your own name.
IBKR generally rejects or discourages third-party deposits.
Wire instructions vary by currency and are generated in Client Portal.
Creating a deposit notification in IBKR does not itself move money; you still
initiate the wire from your bank.
```

Official IBKR funding page notes that third-party deposits are generally
rejected because of fraud and anti-money-laundering risk.

Source:

- https://brokerage.ibkr.com/en/support/fund-my-account.php

China-mainland issue:

```text
Even if IBKR can receive a wire, China-side purchase and remittance of foreign
currency must have a compliant purpose.
The personal FX quota should not be treated as a shortcut for offshore
securities investing.
```

This is the largest real-world bottleneck for many mainland users.

## API Options

IBKR has several API families. They are powerful but heavier than OKX CLI.

### TWS API / IB Gateway

Official description:

```text
The TWS API is a TCP socket protocol connecting to Trader Workstation or IB
Gateway.
IBKR provides code systems including Python, Java, C++, C#, and Visual Basic.
```

Practical meaning:

```text
You need TWS or IB Gateway running.
You log into that app.
Your Python process connects locally to the socket.
For trading, API settings must allow socket clients and not be read-only.
```

Pros:

```text
Mature
Widely used
Supports trading, market data, portfolio, orders
Paper account support
Good for desktop/workstation automation
```

Cons:

```text
Requires running TWS or IB Gateway
Interactive login / 2FA workflow
Not as clean as OKX CLI for headless Web4 agents
Market data subscriptions and pacing rules matter
Complex callback/event model
```

Official source:

- https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/
- https://interactivebrokers.github.io/

### Client Portal / Web API

Official description:

```text
IBKR is merging web-based API products into a comprehensive IBKR Web API using
OAuth 2.0, while existing Client Portal Web API endpoints continue.
```

Pros:

```text
HTTP/Web API shape is easier for modern apps.
Portfolio and account data can be exposed through web endpoints.
```

Cons:

```text
Authentication/session model can be cumbersome.
Active IBKR account required.
For personal users, it is not as smooth as a simple exchange API key.
```

Official source:

- https://www.interactivebrokers.com/campus/ibkr-api-page/webapi-doc/
- https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/

## How IBKR Compares To OKX

```text
IBKR:
  real securities custody
  regulated brokerage model
  stronger for long-term ownership
  heavier KYC/funding/tax/API setup

OKX:
  easy API/CLI/agent integration
  strong demo and crypto derivative testing
  synthetic exposure for stock-like products
  not real stock ownership
  higher platform/regulatory/derivative risk
```

They solve different problems.

Use:

```text
IBKR for serious regulated-market infrastructure.
OKX for Web4/control-chain experiments and small synthetic exposure tests.
```

## FinHarness Integration Plan

Do not start with live trading.

### Phase 0: Research Only

```text
Document account eligibility.
Document funding paths.
Document tax form requirements.
Map IBKR API families.
```

### Phase 1: Paper Trading Adapter

If an IBKR account is opened:

```text
Create IBKR paper account.
Install IB Gateway or TWS.
Install Python API client.
Connect read-only first.
Fetch account summary, positions, and contract details.
```

### Phase 2: Data Adapter

```text
Fetch delayed or subscribed market data.
Normalize into FinHarness bars/ticks.
Compare against yfinance/OpenBB/OKX.
```

### Phase 3: Order Adapter

```text
Paper only.
Limit orders only.
Human approval required.
Order log required.
Cancel/reconcile after every test.
```

### Phase 4: Live Trading

Not now.

Prerequisites:

```text
funding path proven compliant
tax consequences understood
paper-trading adapter stable
position limits
loss limits
human approval
ledger/reconciliation
security review
```

## Step-By-Step Feasibility Checklist

Before applying:

```text
1. Do you have a valid identity document?
2. Do you have acceptable proof of mainland residential address?
3. Can you truthfully complete tax residency and W-8BEN information?
4. Can you explain source of funds?
5. Do you have a same-name bank account that can remit funds legally?
6. Are you comfortable with dividend withholding and tax reporting?
7. Do you understand US estate-tax exposure for large portfolios?
8. Do you need market-data subscriptions?
9. Are you opening for learning, long-term investment, or active trading?
```

If any answer is unclear, do not rush the application.

## Practical Recommendation

For the user right now:

```text
Do not treat IBKR as a quick trading toy.
Treat it as the serious regulated-broker track.
Continue using OKX for API/control experiments.
Use QDII/domestic ETFs for compliant overseas beta research.
Investigate IBKR slowly and truthfully, especially funding and address proof.
```

The highest-value next action:

```text
Create an IBKR feasibility table with your exact personal constraints:
  documents available
  address proof available
  bank/funding path
  tax residency
  target assets
  API need
```

## Source Links

IBKR:

- https://www.interactivebrokers.com/
- https://brokerage.ibkr.com/en/support/fund-my-account.php
- https://brokerage.ibkr.com/en/general/what-you-need-ff.php
- https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/
- https://www.interactivebrokers.com/campus/ibkr-api-page/webapi-doc/
- https://www.interactivebrokers.com/campus/ibkr-api-page/cpapi-v1/
- https://interactivebrokers.github.io/

Tax:

- https://www.irs.gov/forms-pubs/about-form-w-8-ben
- https://www.irs.gov/publications/p515
- https://www.irs.gov/publications/p519

China-side constraints:

- https://www.safe.gov.cn/

