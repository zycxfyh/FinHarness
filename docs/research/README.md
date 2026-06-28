# Research Asset Library

Date: 2026-06-28
Status: current cite-only reference

FinHarness research assets are reusable contracts and references. They may be
selected into evidence, proposal, review, or Agent explanation context, but they
do not execute strategies, compute portfolio accounting, claim compliance, or
authorize live trading.

## Asset Types

```text
StrategySpec:
  reusable strategy contract and non-claim boundary

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

## Current Runtime Boundary

The typed loader lives in:

```text
src/finharness/research_assets.py
tests/test_research_assets.py
```

The policy is always:

```text
asset policy = cite_only
missing asset ids = reported, not silently erased
execution_allowed = false
```

Research assets can support proposal/review explanations and evidence
attachments. They must not become instructions, broker commands, live-trading
approval, or a substitute for human review.

## Using Assets From Code

```python
from finharness.research_assets import resolve_research_assets

selection = resolve_research_assets(
    research_asset_ids=[
        "strategy.trend_following.v0",
        "math.validation.walk_forward.v0",
    ],
)
context = selection.context_for_layer("L5")
assert context["policy"] == "cite_only"
assert context["execution_allowed"] is False
```

`LayerRef` still accepts the older L1-L10 asset labels for compatibility with
existing JSON assets. That compatibility does not make the retired ten-layer
workflow current again; Capital OS remains the mainline architecture.
