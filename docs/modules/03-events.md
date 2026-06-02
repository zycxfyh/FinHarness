# Module: Events

Status: active MVP
Owner: FinHarness
Layer: 3 - Events / information events
Last updated: 2026-06-01

## Purpose

The events module turns external world events into auditable, structured
evidence for research and review workflows.

It answers:

```text
What happened?
Where did we learn it?
When was it published and received?
Which entity/instrument does it affect?
How novel, reliable, and actionable is it?
What evidence and lineage prove the event record?
```

## Current Responsibilities

Current MVP responsibilities:

```text
ingest SEC EDGAR submissions API payloads for the Magnificent Seven
parse raw filing payloads into EventRecord objects
map events to entities and instruments
score quality and mapping confidence
write EventSnapshot, EventLineage, EventQuality, and EventReceipt
route events to human review questions
```

## Non-Goals

```text
no trade authorization
no social-media auto-trading
no claim that event sentiment is alpha
no use of material nonpublic information
no broad web scraping without license and source review
no replacement for market data, indicators, or risk gates
```

## Inputs

Planned inputs:

```text
watchlist
entity/instrument mapping
source configuration
SEC EDGAR submissions API
official filings or release APIs later
licensed news feeds later
public/social feeds later
MarketDataSnapshot refs
IndicatorSnapshot refs
```

## Outputs

Planned outputs:

```text
EventRecord
EventSnapshot
EventQuality
EventLineage
EventReceipt
raw event payload refs
parsed event payload refs
alerts or hypothesis candidates
human review questions
```

Downstream consumers:

```text
Interpretation layer
Hypothesis layer
Proposal layer
Review/reporting workflows
Human training workflow
```

Runtime artifacts:

```text
data/raw/events/sec-edgar/
data/normalized/events/sec-edgar/
data/receipts/events/
```

Current implementation:

```text
src/finharness/events.py
src/finharness/events_graph.py
scripts/run_events_snapshot.py
tests/test_events.py
```

Tasks:

```text
task events:snapshot
task test
```

## Mature Wheels / External Systems

Initial public/official sources:

```text
SEC EDGAR APIs
Federal Reserve / FRED APIs
exchange corporate action or announcement sources
X filtered stream later, only for allowlisted accounts and clear license bounds
```

Institutional references:

```text
Bloomberg Event-Driven Feeds
LSEG / Reuters Machine Readable News
RavenPack
AlphaSense
```

## Quality / Lineage / Receipt Strategy

Quality should include:

```text
source availability
timestamp freshness
missing fields
parse errors
entity mapping confidence
duplicate cluster id
novelty score
source rank
license boundary
```

Lineage should include:

```text
provider
endpoint/source URL
fetched_at
published_at
received_at
raw hash
parsed hash
transform version
license
linked market/indicator snapshot refs
```

Receipt object:

```text
EventReceipt
```

Permission boundary:

```text
EventSnapshot.execution_allowed = false
```

## Proposed First Slice

```text
source:
  SEC EDGAR submissions API

watchlist:
  AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, SPY, QQQ

filing issuers:
  AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA

market context:
  SPY, QQQ

event types:
  8-K, 10-Q, 10-K

workflow:
  fetch recent filings
  normalize into EventRecord
  write EventSnapshot + EventReceipt
  link by symbol/date to existing MarketDataSnapshot and IndicatorSnapshot
  human review only
```

SPY and QQQ are included as market context assets. They are not company filing
issuers in the SEC EDGAR slice.

## Upgrade Log

### 2026-06-01: Events Layer Institutional Scan

Why:

```text
After market data and indicators, FinHarness needs a third evidence layer for
external market-moving events.
```

What changed:

```text
Added proposed module document and institutional practice scan.
```

Evidence:

```text
docs/notes/2026-06-01-events-layer-institutional-practices.md
```

Risks:

```text
news/social feeds are noisy
entity mapping can be wrong
deduplication is required before interpretation
licensed sources have usage constraints
events may be overinterpreted as trade signals
```

Next:

```text
Write a proposal before implementation.
Build SEC EDGAR recent-filings MVP.
Add EventSnapshot/EventReceipt tests.
Keep execution permission disabled.
```

### 2026-06-01: SEC EDGAR Events MVP

Why:

```text
The first two evidence layers were active. The project needed a third layer to
turn official external events into auditable event snapshots for daily virtual
training.
```

What changed:

```text
Added EventSourceSpec, EventEntity, EventRecord, EventQuality, EventLineage,
EventSnapshot, EventReceipt, and EventBundle.
Added SEC EDGAR submissions fetch/normalize/persist path.
Added LangGraph events subgraph:
  source_config -> fetch_sec_edgar -> normalize_filings -> quality -> lineage
  -> snapshot -> receipt -> consumer_handoff -> review_hook -> final.
Added CLI and Taskfile entry.
```

Evidence:

```text
src/finharness/events.py
src/finharness/events_graph.py
scripts/run_events_snapshot.py
tests/test_events.py
task events:snapshot
```

Risks:

```text
CIK mapping is static.
Current quality checks are basic.
No multi-source event reconciliation yet.
No market/indicator cross-linking yet.
```

Next:

```text
Run for three trading days.
Add market/indicator snapshot refs to daily review.
Add deduplication and novelty scoring after real output is reviewed.
```

## Open Risks

```text
No instrument master yet.
No official CIK/ticker mapping yet.
No deduplication model yet.
No event taxonomy implementation yet.
No provider/license abstraction yet.
```

## Next Upgrades

```text
1. Create proposal for Magnificent Seven + SPY/QQQ SEC EDGAR events MVP.
2. Add EventRecord/EventSnapshot/EventReceipt models.
3. Add CIK/ticker mapping for a tiny watchlist.
4. Add recent-filings ingestion.
5. Add tests and workflow integration.
```
