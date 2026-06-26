# Interpretation Layer: Institutional Practices

Date: 2026-06-01

Purpose: understand how top institutions and traders turn structured events
into meaning, impact paths, risks, and scenarios without jumping directly to
trade execution.

## Core Point

The Interpretation layer is not:

```text
event -> AI summary -> bullish/bearish -> trade
```

The institutional pattern is closer to:

```text
event evidence
-> entity and business context
-> affected drivers
-> time horizon
-> market expectation / surprise
-> risk factor exposure
-> scenario analysis
-> disconfirming evidence
-> interpretation snapshot
-> hypothesis candidate
```

Interpretation answers:

```text
What might this event mean?
Through which mechanism could it matter?
What is already known or priced?
What would prove this interpretation wrong?
What should be watched next?
```

It does not answer:

```text
Should we place an order?
```

## What Top Institutions Care About

### 1. Meaning Is Contextual

The same event can mean different things depending on:

```text
company baseline
sector regime
market expectations
valuation
positioning
liquidity
macro environment
portfolio exposure
time horizon
```

Example:

```text
An 8-K about guidance can be bullish if expectations were too low, bearish if
the market already priced perfection, or irrelevant if the disclosure was
already known.
```

Institutional lesson:

```text
interpretation must compare event content with prior context
```

FinHarness adaptation:

```text
InterpretationSnapshot must link back to:
  EventSnapshot
  MarketDataSnapshot
  IndicatorSnapshot
  prior interpretation/review notes where available
```

### 2. Separate Claim, Evidence, And Inference

Analyst-grade interpretation separates:

```text
claim:
  what the system thinks the event might imply

evidence:
  specific filing/event/market data used

inference:
  reasoning path between evidence and claim

confidence:
  how strong the interpretation is

counterevidence:
  what weakens or falsifies it
```

Institutional lesson:

```text
do not mix source truth with analyst inference
```

FinHarness adaptation:

```text
InterpretationRecord should store claim/evidence/inference separately.
```

### 3. Interpret Impact Paths, Not Just Sentiment

Professional interpretation asks "how could this matter?"

Common impact paths:

```text
revenue
margin
capex
cash flow
balance sheet
regulatory risk
competitive position
management credibility
AI/data-center demand
consumer demand
macro sensitivity
multiple/valuation
liquidity/positioning
```

This is more useful than a single sentiment score.

Institutional lesson:

```text
sentiment is weak unless attached to a business or market mechanism
```

FinHarness adaptation:

```text
Use impact_path tags before sentiment labels.
```

### 4. Interpret Time Horizon

Top traders separate:

```text
intraday catalyst
multi-day repricing
earnings-cycle thesis update
long-term fundamental change
portfolio risk update
```

The same event can be:

```text
short-term noisy
medium-term material
long-term irrelevant
```

Institutional lesson:

```text
meaning depends on horizon
```

FinHarness adaptation:

```text
InterpretationRecord should include horizon:
  intraday | days | weeks | quarters | long_term
```

### 5. Scenario And What-If Thinking

BlackRock Aladdin, MSCI Barra, and similar institutional systems emphasize
scenario analysis, stress tests, risk decomposition, and what-if analysis.

Interpretation is not only "what happened"; it is:

```text
if this interpretation is right, what exposures are affected?
if this interpretation is wrong, where is the downside?
what scenario would make this event matter more?
what scenario would make it fade?
```

Institutional lesson:

```text
interpretation should produce scenarios, not certainty
```

FinHarness adaptation:

```text
InterpretationSnapshot should include base/bull/bear or confirm/fade scenarios.
```

### 6. Risk Factor And Portfolio Context

MSCI Barra and BlackRock Aladdin show the institutional norm: interpret
investment information through risk factors, exposures, sectors, and portfolio
context.

For FinHarness:

```text
NVDA event:
  may affect AI capex basket, semiconductors, QQQ, mega-cap growth, momentum.

AAPL event:
  may affect consumer hardware, China exposure, services margin, buyback
  expectations.

META event:
  may affect ads, AI capex, regulation, metaverse spend, margin.
```

Institutional lesson:

```text
single-name interpretation should also ask which baskets and risk factors move
```

FinHarness adaptation:

```text
Add affected_exposures:
  single_name
  sector
  basket
  index_context
  macro_factor
```

### 7. Analyst Productivity Tools Still Preserve Source Links

S&P Capital IQ Pro, FactSet, AlphaSense, and LSEG products increasingly use AI
or NLP to summarize filings, transcripts, news, and research, but their value is
not just text generation. The durable value is:

```text
source aggregation
document intelligence
search
topic/sentiment organization
workflow integration
source-backed summaries
```

Institutional lesson:

```text
AI interpretation must remain source-grounded
```

FinHarness adaptation:

```text
Every interpretation claim must cite EventRecord ids and payload refs.
```

### 8. Top Traders Use Interpretation To Ask Better Questions

Good discretionary traders do not treat a first interpretation as a final
decision.

They use it to ask:

```text
What matters here?
What is consensus missing?
What is already priced?
What would I need to see next?
Where could I be wrong?
What is the cleanest way to observe confirmation?
```

Institutional lesson:

```text
interpretation should create watch questions and hypotheses, not orders
```

FinHarness adaptation:

```text
Interpretation can hand off to Hypotheses.
It cannot hand off to Execution.
```

## Recommended FinHarness Interpretation Layer

### Inputs

```text
EventSnapshot
MarketDataSnapshot refs
IndicatorSnapshot refs
watchlist context
prior reviews / lessons where available
```

### Objects

```text
InterpretationSourceSpec
InterpretationRecord
InterpretationQuality
InterpretationLineage
InterpretationSnapshot
InterpretationReceipt
```

### InterpretationRecord Minimum Fields

```text
interpretation_id
event_ids
symbol
claim
evidence_refs
inference
impact_paths
affected_exposures
horizon
sentiment_label
confidence
counterevidence
watch_questions
scenario_base
scenario_bull
scenario_bear
created_at
```

### Quality Checks

```text
source_backed:
  every claim links to event ids or data refs

counterevidence_present:
  interpretation includes at least one way it could be wrong

no_execution_language:
  blocks buy/sell/order/position-sizing instructions

horizon_present:
  impact time horizon is explicit

confidence_bounded:
  confidence is within a defined scale

claim_evidence_separation:
  source facts and inference are not mixed
```

### Permission Boundary

```text
InterpretationSnapshot.execution_allowed = false
```

Allowed outputs:

```text
watch questions
hypothesis candidates
risk notes
review prompts
```

Forbidden outputs:

```text
orders
position sizing
execution permission
broker instructions
```

## First FinHarness Slice

Do not start with open-ended LLM interpretation of every filing.

Start with structured, rule-guided interpretation of SEC filing events:

```text
input:
  EventSnapshot from SEC EDGAR MVP

universe:
  AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA
  SPY, QQQ as context only

event types:
  8-K, 10-Q, 10-K

output:
  InterpretationSnapshot
  InterpretationReceipt
  watch questions
  hypothesis candidates
```

First interpretation taxonomy:

```text
event_materiality:
  low | medium | high | unknown

impact_path:
  revenue | margin | capex | cash_flow | balance_sheet | regulation |
  management | competition | valuation | liquidity | index_context

horizon:
  intraday | days | weeks | quarters | long_term

stance:
  positive | negative | mixed | neutral | unknown
```

## MVP Workflow

```text
START
-> source_config
-> load_event_snapshot
-> extract_candidate_events
-> interpret_impact_paths
-> build_scenarios
-> check_counterevidence
-> quality
-> lineage
-> snapshot
-> receipt
-> consumer_handoff
-> review_hook
-> END
```

## What Not To Build Yet

```text
no autonomous analyst agent
no buy/sell recommendation
no price target generation
no valuation model
no transcript-wide open-ended summarizer
no social-media interpretation
```

## Sources

- BlackRock Aladdin Risk:
  https://www.blackrock.com/aladdin/products/aladdin-risk.page
- BlackRock Aladdin risk manager view:
  https://www.blackrock.com/aladdin/benefits/risk-managers
- MSCI Barra Models:
  https://app2.msci.com/products/analytics/models/
- MSCI BarraOne:
  https://www.msci.com/data-and-analytics/portfolio-management/barra-one
- FactSet Event-Driven Data:
  https://www.factset.com/solutions/data/event-driven-data
- FactSet AI-powered Portfolio Commentary:
  https://investor.factset.com/news-releases/news-release-details/factset-introduces-ai-powered-portfolio-commentary
- S&P Capital IQ Pro GenAI Document Intelligence:
  https://press.spglobal.com/2024-11-12-S-P-Global-Transforms-S-P-Capital-IQ-Pro-Experience-with-the-Launch-of-New-Generative-AI-Powered-Capabilities
- LSEG StarMine Financial Modelling:
  https://www.lseg.com/en/data-analytics/products/starmine-financial-modelling
