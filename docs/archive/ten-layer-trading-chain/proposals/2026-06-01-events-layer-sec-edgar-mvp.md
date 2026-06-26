# Proposal: Events Layer SEC EDGAR MVP

Date: 2026-06-01
Status: implemented MVP
Related idea:
Related module: docs/modules/03-events.md
Related ADR:

## Problem

FinHarness has market data and indicator evidence, but it does not yet have a
structured layer for external events. Without an Events layer, the workflow can
describe price state but cannot cleanly answer what happened in the outside
world, when we learned it, and how it should enter review or hypothesis
generation.

## User / Workflow

The first user is the human operator doing daily virtual trading practice before
real-capital training resumes.

The workflow is:

```text
market data snapshot
-> indicator snapshot
-> event snapshot
-> human review
-> hypothesis/proposal later
```

## Goals

```text
build the third evidence layer
start with official and auditable event data
keep the symbol universe small enough for manual review
link events to market/indicator state by symbol and date
write EventSnapshot and EventReceipt
keep execution permission disabled
```

## Non-Goals

```text
no social media monitoring
no low-latency breaking news trading
no licensed Bloomberg/LSEG/RavenPack integration yet
no automatic event sentiment trading
no broker/exchange execution
no claim that filings create alpha by themselves
```

## Universe

Primary company filing issuers:

```text
AAPL
MSFT
GOOGL
AMZN
NVDA
META
TSLA
```

Market context assets:

```text
SPY
QQQ
```

SPY and QQQ are included for market context and reaction comparison. They are
not treated as company filing issuers in the EDGAR slice.

## Event Source

First source:

```text
SEC EDGAR submissions API
```

First event types:

```text
8-K
10-Q
10-K
```

Why this source:

```text
official
auditable
stable enough for a first slice
entity mapping is manageable
filing type gives natural event taxonomy
easy to preserve raw and parsed payload refs
```

## Data Structures

### EventSourceSpec

```text
provider
endpoint
access_method
license
fetch_config
```

### EventEntity

```text
entity_id
entity_type
name
ticker
cik
mapping_confidence
```

### EventRecord

```text
event_id
event_type
source
provider
raw_id
title
summary
published_at
received_at
entities
instruments
source_url
raw_ref
parsed_ref
```

### EventQuality

```text
record_count
missing_fields
parse_errors
duplicate_count
stale_count
mapping_confidence_min
license_boundary
execution_allowed
```

### EventLineage

```text
provider
endpoint
fetched_at
fetch_config
raw_hash
parsed_hash
transform_version
license
linked_market_snapshot_refs
linked_indicator_snapshot_refs
```

### EventSnapshot

```text
snapshot_id
as_of
universe
event_count
records
quality
lineage
execution_allowed
receipt_ref
```

### EventReceipt

```text
receipt_id
created_at
snapshot_id
source
universe
raw_refs
parsed_refs
quality
lineage
status
```

## Implementation Steps

### Step 1: Static Watchlist And Mapping

Create a tiny CIK/ticker mapping for:

```text
AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA
```

Keep SPY and QQQ as context-only symbols.

Success:

```text
mapping is explicit, reviewable, and tested
```

### Step 2: Fetch Raw EDGAR Submissions

Fetch recent submissions per CIK.

Persist raw payloads under:

```text
data/raw/events/sec-edgar/
```

Success:

```text
raw payload exists
raw hash is recorded
fetch config is recorded
```

### Step 3: Normalize Event Records

Convert recent filings into EventRecord objects.

Filter first version to:

```text
8-K
10-Q
10-K
```

Persist parsed payloads under:

```text
data/normalized/events/sec-edgar/
```

Success:

```text
each filing has ticker, CIK, form type, filing date, accession number, and URL
```

### Step 4: Quality And Lineage

Generate EventQuality and EventLineage.

Success:

```text
missing fields and parse errors are visible
execution_allowed is false
raw and parsed hashes exist
```

### Step 5: EventSnapshot And EventReceipt

Write:

```text
EventSnapshot
EventReceipt
```

Receipt location:

```text
data/receipts/events/
```

Success:

```text
the run can be reviewed from receipt alone
```

### Step 6: Workflow Integration

Expose an events workflow that can later be called from LangGraph:

```text
run_events_workflow(...)
```

Add a script/task:

```text
scripts/run_events_snapshot.py
task events:snapshot
```

Success:

```text
one command produces event snapshot + receipt for the nine-symbol universe
```

### Step 7: Daily Virtual Training Use

Use output for human review only:

```text
what filings appeared?
what market/indicator state existed around them?
what should be watched tomorrow?
did the event create a hypothesis?
```

Success:

```text
events create review questions, not orders
```

## Quality / Lineage / Receipt

The first implementation must preserve:

```text
raw SEC payload
normalized EventRecord payload
hashes
fetch time
source URL
CIK/ticker mapping
quality flags
receipt path
```

## Risks

```text
SPY/QQQ do not map to company filings
CIK/ticker mapping can go stale
EDGAR timestamps and form semantics need careful handling
filing existence does not imply trade relevance
AI summaries may overinterpret legal filings
```

## Success Signal

```text
task events:snapshot produces a valid EventSnapshot and EventReceipt
tests cover mapping, normalization, quality, and receipt writing
execution_allowed is always false
daily virtual review can use the event output without reading raw EDGAR JSON
```

## Review Plan

After the first implementation:

```text
run the workflow for three trading days
review event records manually
compare event timing with market/indicator snapshots
promote durable lessons into docs/modules/03-events.md
```

## Implementation Evidence

Implemented files:

```text
src/finharness/events.py
src/finharness/events_graph.py
scripts/run_events_snapshot.py
tests/test_events.py
```

Implemented LangGraph node order:

```text
source_config
-> fetch_sec_edgar
-> normalize_filings
-> quality
-> lineage
-> snapshot
-> receipt
-> consumer_handoff
-> review_hook
-> final
```

Verified commands:

```text
uv run ruff check src/finharness/events.py src/finharness/events_graph.py scripts/run_events_snapshot.py tests/test_events.py
PYTHONPATH=src uv run python -m unittest tests.test_events
task events:snapshot
```

First real run:

```text
workflow: langgraph_events_sec_edgar_v1
universe: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA, SPY, QQQ
filing_symbols: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA
context_symbols: SPY, QQQ
event_count: 30
execution_allowed: false
quality_ok: true
consumer_handoff: daily_virtual_training_review
review_hook: open
receipt_ref: data/receipts/events/receipt_evs_20260601T130036Z_12316548.json
```
