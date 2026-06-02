# Eight-Layer Wheel Integration

Date: 2026-05-31

Purpose: record how FinHarness now combines mature finance wheels across the
eight data layers while keeping local code as a thin governance layer.

## Rule

Use mature wheels for heavy finance mechanics.

FinHarness owns only:

```text
SourceSpec
MarketDataQuality
MarketDataLineage
MarketDataSnapshot
DataReceipt
permission boundaries
workflow orchestration
```

## Current Wheel Roles

```text
OpenBB:
  Broad source access for quotes, equity data, macro, fundamentals, reference,
  filings, and provider-standardized output.

yfinance:
  Current working Yahoo Finance price-history provider for OHLCV and close
  matrix ingestion.

NautilusTrader:
  Trading-domain data model and storage: Bar, BarType, and ParquetDataCatalog.

vectorbt:
  Fast vectorized research consumer.

Backtrader:
  Small event-style baseline backtest consumer.

Alpaca paper API:
  Broker/account/order state for paper execution tests.

CCXT:
  Not installed yet. Treat as the future crypto exchange source/venue adapter
  after explicit dependency approval.
```

## Layer Map

### 1. Source Layer

Implemented:

```text
SourceSpec(provider, upstream_source, asset_class, dataset, access_method, wheel)
OpenBB quote source in src/finharness/data_entry.py
yfinance OHLCV and close-matrix sources
Alpaca paper account/order source
```

Wheel owner:

```text
OpenBB for broad financial sources
yfinance for current Yahoo Finance price history
future CCXT for crypto venue breadth
```

### 2. Ingestion Layer

Implemented:

```text
API pull through OpenBB/yfinance/Alpaca
fetch_config recorded into MarketDataLineage
raw payload hash recorded into receipt
```

Wheel owner:

```text
OpenBB / yfinance perform actual fetch
FinHarness records evidence
```

Still missing:

```text
scheduled ingestion
shared retry/rate-limit policy
websocket ingestion
batch/vendor file ingestion
```

### 3. Normalization Layer

Implemented:

```text
normalize_ohlcv(...)
OHLCV contract: date, open, high, low, close, volume
Nautilus Bar conversion via ohlcv_to_nautilus_bars(...)
```

Wheel owner:

```text
OpenBB/yfinance provide provider-shaped outputs
NautilusTrader owns trading-domain Bar semantics
FinHarness maps only at the boundary
```

### 4. Quality Layer

Implemented:

```text
MarketDataQuality
missing required column checks
duplicate timestamp checks
null counts
basic OHLC sanity checks
staleness flag hook
```

Wheel owner:

```text
Pydantic validates governance objects
Nautilus validates Bar construction invariants
FinHarness records quality flags
```

Still missing:

```text
provider mismatch checks
liquidity/spread quality
full stale-data SLA
bad tick/outlier model beyond basic OHLC sanity
```

### 5. Storage Layer

Implemented:

```text
data/raw/market-data/*.json
data/normalized/market-data/*.json
data/catalog/nautilus/
data/receipts/market-data/*.json
```

Wheel owner:

```text
NautilusTrader ParquetDataCatalog owns typed market-data catalog writes
FinHarness owns receipts and hashes
```

### 6. Snapshot Layer

Implemented:

```text
MarketDataSnapshot
snapshot_id
as_of_utc
symbols
fields
timeframe
adjusted
quality
lineage
payload_ref
receipt_ref
```

Consumers now get snapshot evidence from:

```text
run_data_entry_workflow(...)
trade_graph.market_data_node(...)
```

### 7. Lineage Layer

Implemented:

```text
MarketDataLineage
provider and wheel version
fetch_config
raw_hash
normalized_hash
transform_version
raw_ref
normalized_ref
catalog_ref
```

FinHarness owns this layer because it is the evidence root.

### 8. Consumer Layer

Implemented consumers:

```text
vectorbt research screen
Backtrader baseline
risk metrics
LangGraph data workflow
LangGraph paper trade workflow
Alpaca paper account/order workflow
risk notes and JSON receipts
```

Rule:

```text
Consumers should read MarketDataSnapshot + DataReceipt evidence, not raw
provider output alone.
```

## Current Code Entry Points

```text
src/finharness/market_data.py:
  governance models, quality checks, Nautilus Bar conversion, catalog writes,
  snapshot and receipt persistence.

src/finharness/workflow.py:
  OpenBB quote + yfinance OHLCV -> MarketDataSnapshot -> Nautilus catalog ->
  Backtrader/risk note.

src/finharness/trade_graph.py:
  yfinance close matrix -> MarketDataSnapshot -> vectorbt research -> paper
  risk/execution workflow.

tests/test_market_data.py:
  quality checks, Nautilus Bar/catalog round trip, eight-layer receipt coverage.
```

## Verification

Current verified commands:

```bash
task lint
task test
```

Both pass after the eight-layer slice was added.

## Next Upgrades

1. Add an explicit `proposal` node after research and before risk.
2. Add `SourceSpec` adapters under `providers/` only when provider diversity
   grows beyond the current module.
3. Add CCXT after explicit dependency approval, then map crypto markets into the
   same `SourceSpec -> MarketDataSnapshot -> DataReceipt` contract.
4. Add provider mismatch checks by comparing OpenBB/yfinance/venue snapshots for
   the same symbol and time.
5. Add spread/liquidity quality flags before allowing execution-oriented
   workflows to proceed.
