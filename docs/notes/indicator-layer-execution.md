# Indicator Layer Execution

Date: 2026-05-31

Purpose: define and deliver the second layer of FinHarness: indicator processing
over first-layer market-data snapshots.

## 1. Initiation

Original request:

```text
Build the second layer, the indicator layer. This layer should call indicator
libraries to process first-layer information/data, and should follow a serious
task execution lifecycle.
```

Task charter:

```text
Background:
  First-layer market data now creates MarketDataSnapshot, Lineage, Quality, and
  DataReceipt objects.

Goal:
  Add a second-layer indicator pipeline that consumes first-layer market data
  and produces auditable indicator features.

Success criteria:
  Use a mature indicator/research library when available.
  Do not let indicator output authorize execution.
  Link indicator receipts back to the first-layer market-data snapshot.
  Persist output and receipt artifacts.
  Cover quality flags, lineage, and tests.
  Pass project checks.

In scope:
  TA-Lib-backed SMA, MACD, RSI, and Bollinger Bands.
  pandas-ta-backed ATR.
  IndicatorSpec, IndicatorQuality, IndicatorLineage, IndicatorSnapshot,
  IndicatorReceipt.
  Integration into the existing data-entry workflow.

Out of scope:
  Adding new production dependencies without approval.
  Treating hand-rolled Squeeze/SMC experiments as institution-grade indicators.
  Execution decisions from indicator output alone.

Assumptions:
  vectorbt is the installed mature indicator wheel.
  ta, stockstats, and finta are not installed.
  CCXT remains optional until dependency approval.
```

Checkpoint:

```text
Requirement is clear enough for an engineering slice:
first-layer market data -> library-backed indicators -> quality/lineage/receipt.
```

## 2. Planning

WBS:

```text
1. Inspect available indicator libraries and current indicator code.
2. Define indicator governance models.
3. Implement vectorbt core indicator computation.
4. Link indicator lineage to MarketDataSnapshot.
5. Persist normalized indicator payload and receipt.
6. Integrate into run_data_entry_workflow.
7. Add unit tests.
8. Run lint/test/check and fix issues.
9. Document delivery and next gaps.
```

Method:

```text
Small iterative slice.
Use mature wheels first.
Keep FinHarness as governance and orchestration only.
```

Quality plan:

```text
Tests must verify:
  vectorbt owns the indicator specs.
  latest-row nulls fail quality.
  indicator receipt links to first-layer snapshot.
  indicator output never allows execution.
```

## 3. Preparation

Environment facts:

```text
Installed:
  vectorbt 1.0.0
  TA-Lib 0.6.8
  pandas-ta 0.4.71b0

Not installed:
  ta
  stockstats
  finta
```

Decision:

```text
Use TA-Lib and pandas-ta as the primary indicator wheels.
Keep vectorbt as a research/backtest wheel.
Leave current hand-written MACD/Squeeze/SMC modules as experimental feature
scripts until they are replaced by or reconciled with mature libraries.
```

## 4. Execution

Implemented:

```text
src/finharness/indicator_layer.py
```

Core objects:

```text
IndicatorSpec
IndicatorQuality
IndicatorLineage
IndicatorSnapshot
IndicatorReceipt
```

Library-backed indicators:

```text
TA-Lib.SMA
TA-Lib.MACD
TA-Lib.RSI
TA-Lib.BBANDS
pandas-ta.ATR
```

Workflow:

```text
MarketDataSnapshot / OHLCV history
-> compute_vectorbt_core_indicators
-> IndicatorQuality
-> IndicatorLineage
-> IndicatorSnapshot
-> IndicatorReceipt
```

Integrated into:

```text
src/finharness/workflow.py
```

The data-entry workflow now returns:

```text
market_data_snapshot
data_receipt_path
nautilus_catalog_ref
indicator_snapshot
indicator_receipt_path
```

## 5. Monitoring And Control

Quality checks:

```text
row count
feature count
warmup null counts
latest null features
infinite numeric values
```

Execution guard:

```text
IndicatorSnapshot.execution_allowed = false
```

This preserves the boundary:

```text
Indicators describe market state.
They do not authorize trades.
```

## 6. Closing

Deliverables:

```text
src/finharness/indicator_layer.py
tests/test_indicator_layer.py
docs/notes/indicator-layer-execution.md
workflow.py integration
```

Acceptance evidence:

```text
task check
```

## 7. Documentation

This document records:

```text
task charter
scope
method
implemented artifacts
quality controls
next gaps
```

The receipt files are runtime artifacts under:

```text
data/normalized/indicators/
data/receipts/indicators/
```

## 8. Retrospective

What worked:

```text
The first-layer MarketDataSnapshot made second-layer lineage easy.
TA-Lib/pandas-ta give mature indicator math without local formula ownership.
Pydantic receipts keep the layer auditable.
```

What remains:

```text
Replace or explicitly label current hand-written Squeeze/SMC as experimental.
Add a library-backed ATR/ADX/volume indicator group.
Add provider mismatch and indicator drift checks.
Add a formal FeatureStore/Catalog only after snapshots and receipts stabilize.
```

Process improvement:

```text
Every new layer should follow the same pattern:
library does domain work;
FinHarness records Source/Spec, Quality, Lineage, Snapshot, Receipt, and
permission boundary.
```
