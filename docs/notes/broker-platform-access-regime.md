# Broker And Trading Platform Access Regime

Date: 2026-05-27

Purpose: compare major brokers and trading platforms from a China-mainland
resident perspective, starting from market scale and then checking practical
access, tax, funding, and risk.

This is research, not legal, tax, or investment advice.

## Executive Summary

Market-share logic alone is not enough.

The largest brokers are not necessarily usable by a China-mainland resident.
The most usable platforms are not necessarily safest for long-term wealth.

Practical split:

```text
Long-term regulated securities exposure:
  QDII / domestic cross-border ETFs
  Stock Connect / Hong Kong market access
  Interactive Brokers, if eligible and funding/tax path is sustainable

API / Web4 / agent-control experiments:
  OKX / Binance / Bybit / Coinbase-style crypto venues
  Use demo or tiny capital; treat synthetic stock products as derivatives,
  not ownership of real shares.
```

## Market-Scale Tiers

### Tier 1: US Retail And Institutional Brokerage Giants

```text
Charles Schwab
Fidelity
Interactive Brokers
E*TRADE / Morgan Stanley
Robinhood
```

Observations:

```text
Schwab and Fidelity are enormous US wealth/brokerage platforms, but mainly
serve US or selected international clients.

Interactive Brokers is the most globally oriented of the US-listed brokers and
is therefore the most important one to investigate for non-US residents.

Robinhood is large in US retail but structurally US-resident focused.
```

### Tier 2: International / Asia-Friendly Online Brokers

```text
Firstrade
Futu / moomoo
Tiger Brokers
Saxo
```

Observations:

```text
These may be easier from a Chinese-language UX perspective, but current
mainland-China onboarding policy must be verified at the time of application.
Regulatory pressure can change access quickly.
```

### Tier 3: Crypto / Derivatives / Tokenized Exposure Platforms

```text
Binance
OKX
Bybit
Coinbase
Kraken
```

Observations:

```text
These are strong for API access, crypto liquidity, perpetuals, and agent
experiments. They are not substitutes for regulated securities custody.
```

CoinGecko's 2025 Q1 report ranked Binance as the largest centralized exchange
by spot volume share, with Bybit and Coinbase following. OKX was also in the
top group of global exchanges.

## China-Mainland Constraint Layer

For a China-mainland resident, the bottleneck is usually not software.

The bottlenecks are:

```text
1. KYC eligibility
2. legal residence and tax residence
3. bank account and proof of address
4. source of funds
5. foreign exchange usage restrictions
6. broker/platform regional policy
7. ongoing account review / freeze risk
```

Important China-side constraint:

```text
The personal annual FX quota and individual purchase of foreign currency are
not a free route for offshore securities investment.
```

SAFE materials for personal FX purchase include restrictions that purchased
foreign exchange must not be used for overseas securities investment, overseas
property purchase, investment-type insurance, and other non-open capital-account
items.

## Traditional Broker Comparison

### Interactive Brokers

Scale:

```text
Global broker; strong multi-market access; widely used by professional and
international investors.
```

Why it matters:

```text
If there is one overseas broker to study seriously first, it is IBKR.
```

Likely strengths:

```text
Global market access
Professional trading infrastructure
API support
Multi-currency support
Low-cost execution
Tax documentation workflow for non-US clients
```

Typical onboarding requirements:

```text
Identity document
Proof of residential address
Tax residency information
Employment / financial profile
W-8BEN for non-US beneficial owner status
Funding account in the applicant's own name
```

Tax basics for non-US persons:

```text
W-8BEN establishes foreign status.
US-source dividends are generally subject to withholding tax, often 30% unless
a treaty reduces it.
Capital gains for nonresident aliens are usually not taxed by the US unless
special conditions apply, but local tax obligations may still exist.
US estate tax exposure can matter for direct US situs assets.
```

Open questions before action:

```text
Does IBKR currently accept your exact residency profile?
Can you provide acceptable proof of address?
Can you fund from a compliant bank path?
How will you handle tax reporting?
```

Decision:

```text
Primary candidate for a real overseas securities account, but only if KYC,
funding, and tax paths are clean.
```

### Charles Schwab International

Scale:

```text
One of the largest US brokerage/wealth platforms.
```

Why it matters:

```text
Huge platform, strong US-market access, but not necessarily easy for China-
mainland residents.
```

Known structure:

```text
Schwab One International is the relevant international account product.
Some international accounts historically require a meaningful minimum opening
deposit, commonly referenced as USD 25,000.
```

Typical onboarding:

```text
International account application
Identity and address proof
W-8BEN for non-US persons
Country eligibility check
Bank funding
```

Decision:

```text
Worth checking, but likely less flexible than IBKR for a China-mainland
student with limited offshore banking infrastructure.
```

### Fidelity

Scale:

```text
Very large US brokerage and asset-management platform.
```

Practical issue:

```text
Fidelity's US retail brokerage is strongly US-resident oriented.
Opening or maintaining accounts as a non-US resident is usually constrained.
```

Decision:

```text
Study as a market leader, but low-priority for actual China-mainland resident
onboarding.
```

### Robinhood

Scale:

```text
Major US retail broker, especially among younger US investors.
```

Practical issue:

```text
Robinhood is US-resident focused. Account requirements typically include US
residential address, US tax identification, and US legal/residency status.
```

Decision:

```text
Not a realistic primary route for a China-mainland resident without genuine US
residency/tax setup.
```

### E*TRADE / Morgan Stanley

Scale:

```text
Large US brokerage under Morgan Stanley.
```

Practical issue:

```text
Primarily US-market/account infrastructure. International availability is not
the first route to study for China-mainland users.
```

Decision:

```text
Lower priority than IBKR.
```

### Firstrade

Scale:

```text
Smaller than Schwab/Fidelity/IBKR, but historically popular with international
retail users because of lower barriers and commission-free US equities/ETFs.
```

Typical onboarding:

```text
International account application
Passport or identity document
Address proof
W-8BEN
Wire funding
```

Decision:

```text
Worth checking as an alternative candidate, especially if IBKR proves too hard.
Must verify current China-mainland resident policy before relying on it.
```

### Futu / moomoo

Scale:

```text
Large China/Hong-Kong/Singapore-facing online broker ecosystem with strong UX
and Chinese-language support.
```

Practical issue:

```text
Mainland-China account opening policies have faced regulatory changes. Do not
assume historical availability still applies.
```

Decision:

```text
Good UX and strong regional relevance, but current onboarding eligibility must
be verified directly from the app/site.
```

### Tiger Brokers

Scale:

```text
Major Asia-oriented online broker with Chinese-language UX and US/HK market
features.
```

Practical issue:

```text
Similar to Futu: China-mainland user onboarding has regulatory sensitivity and
may change.
```

Decision:

```text
Worth monitoring, but not assumed available.
```

## Regulated Domestic Alternatives

### QDII / Cross-Border Mutual Funds And ETFs

What it solves:

```text
Access to overseas market beta without opening an overseas securities account.
```

Examples:

```text
Nasdaq 100 products
S&P 500 products
Hong Kong tech products
Japan / Germany / global equity products
Gold / commodity-linked products
```

Pros:

```text
More compliant for mainland investors
RMB account access
No overseas broker KYC
Useful for long-term beta exposure
```

Cons:

```text
Limited single-stock access
QDII quota constraints
Premium/discount risk
Tracking error
Trading suspension / subscription limits under stress
```

Decision:

```text
Best first layer for compliant overseas beta.
```

### Stock Connect / Hong Kong Market

What it solves:

```text
Regulated access to selected Hong Kong-listed securities through mainland
brokerage channels.
```

Main threshold:

```text
Individual investors typically need at least RMB 500,000 in securities/cash
assets to qualify for Stock Connect access.
```

Pros:

```text
Regulated channel
No overseas brokerage account needed
Access to Hong Kong-listed equities and ETFs
```

Cons:

```text
High threshold for a student
Not direct US stock access
Limited universe
Trading calendar and settlement constraints
```

Decision:

```text
Good future route after asset threshold, not likely first route now.
```

## Crypto / Derivatives Platform Comparison

### OKX

Status in our lab:

```text
Official okx CLI installed.
OAuth connected.
Live account read works.
Demo order place/cancel works.
App self-selected list reconstructed locally.
```

Strengths:

```text
Strong API/CLI/agent-skill support
Crypto liquidity
Perpetuals
Stock/ETF/commodity synthetic exposure through SWAP-style instruments
Good Web4/agent-control testing surface
```

Risks:

```text
Not real share ownership
No shareholder rights
Platform/counterparty risk
Derivative liquidation risk
Funding-rate risk
Regulatory uncertainty
Access policy may change
```

Decision:

```text
Excellent for Web4/agent experiments and small-risk synthetic exposure.
Not a replacement for regulated long-term securities custody.
```

### Binance / Bybit / Coinbase / Kraken

General notes:

```text
Binance and Bybit are major global crypto venues by volume.
Coinbase and Kraken are more regulation-forward in the US/EU context.
Feature sets differ sharply by jurisdiction.
```

China-mainland issue:

```text
Regional access, KYC, fiat on/off-ramp, and product availability can be
unstable or restricted.
```

Decision:

```text
Useful comparison set for crypto liquidity and API design.
Not first choice for regulated securities exposure.
```

## Tax Layer

### US W-8BEN

For non-US persons, W-8BEN is the standard form to certify foreign beneficial
owner status for US withholding-tax purposes.

Practical effect:

```text
Without proper documentation, withholding may be worse or account operation may
be blocked.
US-source dividends generally face withholding.
Treaty benefits depend on tax residence and treaty status.
```

### US Dividend Withholding

Baseline:

```text
US-source FDAP income such as dividends paid to nonresident aliens is generally
subject to 30% withholding unless reduced by treaty.
```

For China tax residents, the US-China treaty may reduce dividend withholding in
some cases, but broker application and treaty-claim handling must be verified.

### US Capital Gains

Broad simplified rule:

```text
Nonresident aliens are generally not taxed by the US on capital gains from US
stocks unless specific conditions apply, such as being present in the US for
183 days or more in the tax year.
```

This is not the same as saying there is no tax anywhere. Local tax reporting may
still apply.

### US Estate Tax

Important hidden risk:

```text
Direct US situs assets held by nonresident non-citizens can create US estate
tax exposure, with a much lower exemption than US citizens/residents.
```

This matters more for meaningful long-term portfolios than for tiny experiments.

## Decision Matrix

| Route | Market scale | Access realism for mainland student | Asset authenticity | API usefulness | Main risk | Priority |
| --- | --- | --- | --- | --- | --- | --- |
| IBKR | Very high global | Medium, verify KYC/funding | High | High | funding/KYC/tax | High |
| Schwab Intl | Very high US | Low-medium | High | Medium | eligibility/minimum | Medium |
| Fidelity | Very high US | Low | High | Low-medium | US-resident focus | Low |
| Robinhood | High US retail | Very low | High | Medium | US-resident focus | Low |
| Firstrade | Medium | Medium, verify current policy | High | Low-medium | policy/funding | Medium |
| Futu/moomoo | High regional | Uncertain | High if available | Medium | mainland policy | Medium |
| Tiger | High regional | Uncertain | High if available | Medium | mainland policy | Medium |
| QDII/ETF | High enough | High | Fund exposure | Low | premium/quota/tracking | Very high |
| Stock Connect | High | Low now, needs assets | High | Low | RMB 500k threshold | Future |
| OKX | High crypto | High technically | Synthetic/derivative | Very high | platform/derivative/regulatory | Lab only |

## Recommended Path For This Project

### Track A: Compliant Long-Term Exposure

Build a database of:

```text
QDII products
domestic cross-border ETFs
Hong Kong ETFs
Stock Connect candidates
```

Use this for serious long-horizon allocation research.

### Track B: Overseas Broker Feasibility

Investigate in this order:

```text
1. Interactive Brokers
2. Firstrade
3. Schwab International
4. Futu/moomoo
5. Tiger Brokers
```

For each:

```text
Can a China-mainland resident apply today?
What proof of address is accepted?
What tax forms are required?
What funding paths are acceptable?
What happens if residency changes?
What fees/minimums apply?
```

### Track C: Web4 / Agent Trading Lab

Use OKX only as:

```text
demo trading
read-only live account inspection
tiny synthetic exposure experiments after explicit approval
API control and risk-gating lab
```

Never treat it as the core lifetime wealth system.

## Source Links

Broker/platform and scale:

- Interactive Brokers: https://www.interactivebrokers.com/
- Charles Schwab International: https://international.schwab.com/
- Fidelity: https://www.fidelity.com/
- Robinhood: https://robinhood.com/
- Firstrade: https://www.firstrade.com/
- Futu: https://ir.futuholdings.com/
- UP Fintech / Tiger Brokers: https://ir.itiger.com/
- OKX agent skills: https://github.com/okx/agent-skills
- OKX CLI: https://www.npmjs.com/package/@okx_ai/okx-trade-cli
- CoinGecko reports: https://www.coingecko.com/research

Tax and regulation:

- IRS Form W-8BEN: https://www.irs.gov/forms-pubs/about-form-w-8-ben
- IRS Publication 515: https://www.irs.gov/publications/p515
- IRS Publication 519: https://www.irs.gov/publications/p519
- SAFE: https://www.safe.gov.cn/
- CSRC Stock Connect Q&A: https://www.csrc.gov.cn/
- Shanghai Stock Exchange Stock Connect: https://www.sse.com.cn/services/hkexsc/home/
- Shenzhen Stock Exchange Stock Connect: https://www.szse.cn/option/hkex/

