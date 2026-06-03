# Review: Research Asset ID Handoff

Date: 2026-06-02
Status: implemented-mvp
Related proposal: /root/projects/finharness/docs/proposals/2026-06-02-research-asset-id-handoff.md
Related receipt:
- /root/projects/finharness/data/receipts/cognitive-graph/20260602T171407Z-research-asset-id-handoff.json
- /root/projects/finharness/data/receipts/engineering-delivery/20260602T171609Z-research-asset-id-handoff-mvp.json
Related module: src/finharness/ten_layer_graph.py

## Summary

Asset id handoff is implemented as a cite-only orchestration feature. The
top-level graph resolves requested asset ids, passes a compact context into
L5-L10, records layer-filtered refs in `SourceSpec.config`, and reports selected
and missing ids in final output.

## Expected

```text
asset ids can be supplied to the ten-layer graph and CLI
L5-L10 source configs record layer-filtered asset refs
missing ids are visible
asset context never enables execution
focused and full checks pass
```

## Actual

```text
resolve_research_assets and compact_research_asset_context added
ten_layer_graph gained a research_assets node and final research_asset_refs
L5-L10 graph runners accept research_asset_context
L5-L10 source_config nodes write compact context into SourceSpec.config
CLI accepts --asset-id, --strategy-spec-id, --method-spec-id, --reference-card-id
tests cover resolver, handoff, final reporting, and source config recording
```

## Evidence

```text
PYTHONPATH=src uv run ruff check ...
  All checks passed.

PYTHONPATH=src uv run python -m unittest tests.test_research_assets tests.test_ten_layer_graph tests.test_research_asset_handoff
  Ran 11 tests; OK.

PYTHONPATH=src uv run python scripts/run_ten_layer_graph.py --run-layers 10 --asset-id strategy.trend_following.v0 --asset-id math.validation.walk_forward.v0 --asset-id reference.provider.alpaca_paper_adapter.v0 --asset-id missing.asset.v0
  final.research_asset_refs includes selected ids, missing.asset.v0, and execution_allowed=false.

rg "research_asset_context|strategy.trend|walk_forward|alpaca|missing.asset" data/normalized data/receipts
  found L5-L10 receipt/payload refs carrying research_asset_context.

task test
  Ran 109 tests; OK.

task check
  Rust tests passed, ruff passed, Python tests passed, experiment passed, eval smoke passed.
```

## Classification

architecture handoff

## Root Causes / Conditions

Research assets needed to become callable references in ten-layer runs, but
they must stay outside execution authority. The correct insertion point is
`SourceSpec.config` and final orchestration summary, not strategy records or
order objects.

## Lessons

External references should enter the evidence chain as cite-only lineage first.
Only after that boundary is stable should layer-specific behavior consume more
detail from the assets.

## Actions

```text
keep asset policy cite_only
keep StrategySpec/MathMethodSpec/ReferenceCard non-executing
consider future explicit Lineage.asset_refs after SourceSpec.config stabilizes
```
