# Events Layer: Institutional Practices

Date: 2026-06-01

Purpose: understand how top traders, funds, and institutional platforms handle
market-moving events, then adapt the useful pattern to FinHarness.

## Core Point

The Events layer is not a news summary layer.

Institutional event handling is closer to:

```text
source monitoring
-> event detection
-> entity mapping
-> event classification
-> novelty / relevance / confidence scoring
-> timestamp alignment
-> market reaction measurement
-> workflow routing
-> evidence receipt
```

For FinHarness, Events should become the third evidence layer after:

```text
market data
-> indicators
-> events
```

Events describe what happened in the outside world. They do not authorize
trades.

## What Top Institutions Care About

### 1. Speed

For systematic and event-driven desks, seconds can matter.

Bloomberg Event-Driven Feeds and LSEG/Reuters Machine Readable News both
position their products around real-time, machine-readable, low-latency event
and news delivery for trading, pricing, risk, and quant workflows.

Institutional lesson:

```text
events must arrive as machine-readable data, not only human-readable articles
```

FinHarness adaptation:

```text
Start slower and safer:
  batch / polling first
  near-real-time later
  websocket only after quality and review are stable
```

### 2. Structure

Top systems do not only store raw headlines.

They attach structure:

```text
event_id
source
published_at
received_at
entity
instrument
event_type
topic
sentiment
novelty
relevance
confidence
source_rank
raw_ref
parsed_ref
```

Bloomberg describes event-driven feeds as highly structured, machine-readable
data. LSEG describes Machine Readable News with sentiment, relevance, novelty,
and metadata. RavenPack similarly focuses on entity and event detection,
sentiment, relevance, and novelty.

Institutional lesson:

```text
unstructured text becomes useful only after entity/event normalization
```

FinHarness adaptation:

```text
Create EventSnapshot and EventReceipt before trying to make event signals.
```

### 3. Entity Mapping

The hard part is not only finding a headline.

The hard part is mapping it correctly:

```text
company name -> ticker / instrument
person -> company / political office / account
filing -> issuer / form type / fiscal period
macro release -> country / indicator / release time
crypto event -> token / chain / exchange / contract
```

Institutional platforms use identifiers such as FIGI, RIC, ticker, CIK, ISIN,
exchange codes, and internal instrument masters.

Institutional lesson:

```text
wrong entity mapping creates false events
```

FinHarness adaptation:

```text
Events layer depends on future reference-data / instrument-master work.
Until then, keep mapping confidence explicit.
```

### 4. Novelty And Deduplication

One real event can create many articles, reposts, summaries, and social posts.

Institutional systems score or cluster:

```text
is this the first report?
is it an update?
is it a duplicate?
does it change the known fact pattern?
is the source reliable?
```

Institutional lesson:

```text
without novelty and deduplication, the system overreacts to repetition
```

FinHarness adaptation:

```text
EventQuality should include duplicate_cluster_id, novelty_score, and stale flag.
```

### 5. Event Type Taxonomy

Top desks think in event types, not just "news".

Common event families:

```text
earnings
guidance
M&A
buyback / dividend / split
management change
product launch / recall
lawsuit / investigation
regulatory action
macro release
central bank speech / decision
geopolitical shock
large holder / insider filing
analyst rating / target change
social-media catalyst
crypto listing / delisting
funding / liquidation / exploit / hack
```

Institutional lesson:

```text
each event type has a different trading half-life, risk profile, and evidence need
```

FinHarness adaptation:

```text
Do not build one generic "news sentiment" feature.
Build typed event families gradually.
```

### 6. Calendar Awareness

Professional workflows separate scheduled from unscheduled events:

```text
scheduled:
  earnings, CPI, FOMC, Fed speeches, unlocks, economic releases

unscheduled:
  breaking news, lawsuits, hacks, resignations, geopolitical shocks
```

Scheduled events require preparation before release.
Unscheduled events require detection and containment.

Institutional lesson:

```text
pre-event state and post-event reaction are different workflows
```

FinHarness adaptation:

```text
Events layer should support:
  calendar watch
  breaking event detection
  post-event reaction measurement
```

### 7. Market Reaction Measurement

Top traders do not stop at "event happened".

They ask:

```text
what did price do before the event?
what did price do immediately after?
what did volume/liquidity/spread do?
was the move already priced in?
did related assets react?
did volatility expand or compress?
```

Institutional lesson:

```text
events need to be aligned with market data and indicators
```

FinHarness adaptation:

```text
EventSnapshot should link to MarketDataSnapshot and IndicatorSnapshot where
possible.
```

### 8. Human Review And Source Skepticism

News is noisy.

Social feeds are noisier.

For discretionary top traders, the edge is often not reading one post quickly.
It is knowing:

```text
who matters?
which source moves markets?
what is already consensus?
what is rumor?
what is actionable?
what is illegal/material nonpublic information risk?
```

Institutional lesson:

```text
source ranking and compliance boundaries matter
```

FinHarness adaptation:

```text
Do not auto-trade social events.
Use events to create hypotheses or alerts, then route to proposal/risk gate.
```

## Source Families For FinHarness

### Tier 1: Official / Primary Sources

Best for correctness and audit:

```text
SEC EDGAR:
  8-K, 10-K, 10-Q, 13F, insider filings, company facts.

Federal Reserve / FRED:
  macro series and official releases.

Exchange / issuer pages:
  corporate actions, listings, delistings.

Company investor relations:
  earnings releases, presentations, transcripts where available.

Exchange APIs:
  crypto listing/delisting, funding, open interest, liquidation where available.
```

### Tier 2: Licensed Institutional Feeds

Best for speed and structure:

```text
Bloomberg Event-Driven Feeds
LSEG / Reuters Machine Readable News
RavenPack
Dow Jones / Factiva
AlphaSense
```

These are institution-grade but often expensive and license-heavy.

### Tier 3: Public / Social / Alternative

Best for early weak signals, worst for noise:

```text
X filtered streams
official company accounts
government accounts
exchange accounts
top investor accounts
crypto project accounts
GitHub / Discord / forums where legally and ethically usable
```

FinHarness should treat these as hypothesis inputs, not evidence of truth.

## Recommended FinHarness Events Layer

### Objects

```text
EventSourceSpec
EventRecord
EventEntity
EventQuality
EventLineage
EventSnapshot
EventReceipt
```

### EventRecord Minimum Fields

```text
event_id
event_type
source
provider
raw_id
headline_or_title
summary
published_at
received_at
entities
instruments
source_url
raw_ref
parsed_ref
```

### EventQuality Minimum Fields

```text
mapping_confidence
source_rank
duplicate_cluster_id
novelty_score
stale
missing_fields
parse_errors
license_boundary
```

### EventLineage Minimum Fields

```text
provider
endpoint
fetch_config
fetched_at
raw_hash
parsed_hash
transform_version
license
```

### Permission Boundary

```text
EventSnapshot.execution_allowed = false
```

Events can create:

```text
alerts
hypotheses
research tasks
proposal candidates
review questions
```

Events cannot create:

```text
orders
position changes
execution permission
```

## MVP Recommendation

Do not start with Bloomberg/LSEG/RavenPack.

Start with official/public sources:

```text
1. SEC EDGAR recent filings for a small US equity watchlist.
2. FRED/Fed release calendar for macro events.
3. X filtered stream only for a tiny allowlisted account list, later.
4. OKX/Binance exchange announcements for crypto events, later.
```

First vertical slice:

```text
watchlist: AAPL, MSFT, NVDA, SPY, QQQ
source: SEC EDGAR submissions API
event types: 8-K, 10-Q, 10-K
output: EventSnapshot + EventReceipt
link: MarketDataSnapshot / IndicatorSnapshot by symbol and date
consumer: human review only
```

This gives FinHarness a clean third layer without rushing into noisy social
monitoring.

## Sources

- Bloomberg Event-Driven Feeds:
  https://www.bloomberg.com/professional/products/data/enterprise-catalog/event-driven-feeds/
- Bloomberg real-time events data:
  https://www.bloomberg.com/professional/insights/press-announcement/bloomberg-elevates-front-office-efficiency-with-real-time-events-data/
- LSEG Machine Readable News:
  https://www.lseg.com/en/data-analytics/financial-news-services/machine-readable-news
- Reuters News Feed Direct overview:
  https://share.refinitiv.com/assets/elektron/news-feed-direct-overview.pdf
- RavenPack via WRDS:
  https://wrds-www.wharton.upenn.edu/pages/about/data-vendors/ravenpack/
- SEC EDGAR APIs:
  https://www.sec.gov/edgar/sec-api-documentation
- Federal Reserve / FRED API:
  https://www.federalreserve.gov/data/data-download-fred-information.htm
- Federal Reserve statistical release calendar:
  https://www.federalreserve.gov/econresdata/releaseschedule.htm
- NYSE corporate actions:
  https://www.nyse.com/market-data/corporate-actions
- X API filtered stream:
  https://docs.x.com/x-api/posts/filtered-stream/introduction
