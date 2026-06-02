# Module: Market Data

Status: active
Owner: FinHarness
Layer: 1 - Information / market data
Last updated: 2026-06-01

## Purpose

The market data module turns external price and quote sources into auditable
first-layer evidence for the rest of FinHarness.

Its job is not to predict or trade. Its job is to answer:

```text
What data did we fetch?
From where?
When?
How was it normalized?
What quality checks ran?
Where is the receipt?
```

## Current Responsibilities

```text
fetch quote snapshots through OpenBB yfinance provider
fetch OHLCV history through yfinance/Yahoo Finance
fetch close matrices for research/trade graph workflows
normalize OHLCV into a local contract
convert OHLCV into NautilusTrader Bar objects
write Nautilus ParquetDataCatalog data
write raw and normalized payload references
write MarketDataSnapshot, MarketDataLineage, MarketDataQuality, and DataReceipt
```

## Non-Goals

```text
no trading decisions
no signal generation
no execution authorization
no homemade market-data vendor
no exchange matching or broker accounting
no claim that yfinance data is institution-grade
```

## Inputs

Current inputs:

```text
symbol
universe
date range
period
provider fetch config
OpenBB quote provider output
yfinance OHLCV / close output
```

Important source objects:

```text
SourceSpec
fetch_config
raw_payload
```

## Outputs

Current outputs:

```text
MarketDataSnapshot
MarketDataQuality
MarketDataLineage
DataReceipt
normalized OHLCV JSON
raw payload JSON
optional Nautilus ParquetDataCatalog write
close matrix for vectorbt research
```

Downstream consumers:

```text
Indicator layer
Backtrader baseline
vectorbt research screen
LangGraph finance workflow
LangGraph paper trade workflow
risk notes
future event/interpretation/proposal layers
```

## Current Implementation

Important files:

```text
src/finharness/market_data.py
src/finharness/market_data_graph.py
src/finharness/data_entry.py
src/finharness/workflow.py
src/finharness/trade_graph.py
tests/test_market_data.py
tests/test_market_data_graph.py
```

Runtime artifacts:

```text
data/raw/market-data/
data/normalized/market-data/
data/catalog/nautilus/
data/receipts/market-data/
data/cache/
```

Tasks:

```text
task data:entry
task market-data:graph
task workflow:data-entry
task test
task check
```

## Mature Wheels / External Systems

```text
OpenBB:
  quote snapshot through yfinance provider.

yfinance:
  current Yahoo Finance OHLCV and close matrix source.

NautilusTrader:
  Bar, BarType, and ParquetDataCatalog.

Pydantic:
  typed governance objects.
```

## Quality / Lineage / Receipt

Quality checks currently include:

```text
required columns
row count
duplicate timestamps
null counts
staleness hook
non-positive OHLC flags
high-below-low flag
```

Lineage currently records:

```text
provider
upstream source
asset class
dataset
access method
wheel and wheel version
fetch config
raw hash
normalized hash
transform version
raw ref
normalized ref
catalog ref
```

Receipt object:

```text
DataReceipt
```

## Upgrade Log

### 2026-05-31: Eight-Layer Market Data Slice

Why:

```text
The project needed a first-layer data boundary that was more serious than a
temporary DataFrame.
```

What changed:

```text
Added MarketDataSnapshot, MarketDataQuality, MarketDataLineage, DataReceipt,
SourceSpec, raw/normalized payload refs, hash lineage, and Nautilus Bar/catalog
write path.
```

Evidence:

```text
tests/test_market_data.py
task check passed
docs/notes/eight-layer-wheel-integration.md
```

Risks:

```text
yfinance is convenient but not an institutional data vendor.
OpenBB historical yfinance provider path previously had local conversion issues.
Quality checks are still basic.
```

Next:

```text
Add provider mismatch checks.
Add exchange/session calendar awareness.
Add corporate-action policy.
Add spread/liquidity quality flags before execution-oriented workflows.
```

### 2026-06-01: Independent Market Data LangGraph

Why:

```text
The first layer needed the same strict graph shape as the Events layer instead
of being hidden inside the broader data-entry workflow.
```

What changed:

```text
Added market_data_graph.py with:
  source_config -> fetch_market_data -> normalize_ohlcv -> quality -> lineage
  -> snapshot -> receipt -> consumer_handoff -> review_hook -> final.

Added CLI/task and graph tests.
```

Evidence:

```text
src/finharness/market_data_graph.py
scripts/run_market_data_graph.py
tests/test_market_data_graph.py
task market-data:graph
```

## Open Risks

```text
yfinance data may be delayed, revised, incomplete, or provider-dependent.
No official instrument master yet.
No multi-provider reconciliation yet.
No market-session/calendar gate yet.
No robust corporate-action policy yet.
```

## Next Upgrades

```text
1. Add provider mismatch checks for same symbol/date across available sources.
2. Add instrument master and symbol metadata.
3. Add session/calendar state.
4. Add liquidity/spread snapshot support for execution-adjacent workflows.
5. Add a market-data proposal before bringing in a paid/provider API.
```
