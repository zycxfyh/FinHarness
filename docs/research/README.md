# Research Asset Library

Date: 2026-06-02
Status: draft MVP

FinHarness research assets sit outside the ten-layer chain. They provide
reusable contracts and references that the evidence layers may cite, but they
do not execute strategies, compute portfolio accounting, claim compliance, or
authorize live trading.

## Asset Types

```text
StrategySpec:
  reusable strategy contract for L5-L10 handoff

MathMethodSpec:
  mathematical validation, risk, cost, robustness, or attribution contract

ReferenceCard:
  external standard, mature tool, provider, broker, or exchange reference
```

## Directory Map

```text
docs/research/
  strategy-library/
  math-method-library/
  institutional-reference/
  tool-reference/
  provider-reference/

data/research/
  strategy-specs/
  method-specs/
  reference-cards/
  experiment-receipts/
```

## Ten-Layer Relationship

The top-level graph can resolve asset ids and pass a compact cite-only context
to L5-L10. This context is written into each layer's `SourceSpec.config` so the
receipt lineage can answer which strategy, method, or reference assets were
consulted.

Example:

```text
task ten-layer:graph -- \
  --asset-id strategy.trend_following.v0 \
  --asset-id math.validation.walk_forward.v0 \
  --asset-id reference.provider.alpaca_paper_adapter.v0
```

```text
L5 Hypotheses:
  may cite StrategySpec thesis and assumptions

L6 Validation:
  may cite MathMethodSpec validation contracts

L7 Proposal:
  may cite StrategySpec proposal/risk/execution constraints

L8 Risk Gate:
  may cite StrategySpec risk contracts and MathMethodSpec risk methods

L9 Execution:
  may read execution constraints after Risk Gate, paper/fake-first only

L10 Post-Trade:
  may cite review metrics and attribution MathMethodSpec assets
```

## Boundary

```text
Research assets are inputs and references.
Asset policy is cite_only.
Asset context is written to SourceSpec.config and lineage receipts.
Missing asset ids are reported, not silently erased.
The ten-layer graph remains the lifecycle orchestrator.
Risk Gate remains the independent pre-execution control.
Execution remains paper/fake-first in this MVP.
Post-Trade cannot create orders.
Asset refs never set execution_allowed=true.
```

Current typed loader:

```text
src/finharness/research_assets.py
tests/test_research_assets.py
tests/test_research_asset_handoff.py
```
