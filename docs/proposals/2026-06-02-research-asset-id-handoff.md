# Proposal: Research Asset ID Handoff

Date: 2026-06-02
Status: implemented-mvp
Related idea: /root/projects/finharness/ideas/2026-06-02-research-asset-id-handoff.md
Related note: /root/projects/finharness/docs/notes/2026-06-02-research-asset-id-handoff-workflow-note.md
Related module: src/finharness/ten_layer_graph.py
Related ADR:

## Problem

Research assets exist as StrategySpec, MathMethodSpec, and ReferenceCard files,
but the ten-layer graph needs a governed way to cite them during L5-L10 runs.
The system should record which assets were consulted without turning those
assets into strategy logic, math engines, compliance claims, or order authority.

## User / Workflow

The user runs the ten-layer orchestrator with asset ids. L5-L10 source configs
record a compact cite-only `research_asset_context`, and final output reports
selected ids plus missing ids.

## Goals

```text
resolve asset ids before the ten-layer chain runs
pass cite-only asset context to L5-L10
write layer-filtered asset refs into SourceSpec.config
report selected and missing ids in ten_layer_graph final output
keep execution_allowed false for asset context
expose CLI flags for asset ids
test resolver, source config handoff, final reporting, and no-execution boundary
```

## Non-Goals

```text
generate trading signals from StrategySpec
run mathematical calculations from MathMethodSpec
claim compliance from ReferenceCard
skip Risk Gate because an asset was cited
authorize paper or live orders from asset ids
```

## Design

Add a `research_assets` node at the start of `ten_layer_graph`:

```text
START
-> research_assets
-> market_data
...
-> post_trade
-> final
```

The node resolves:

```text
research_asset_ids
strategy_spec_ids
method_spec_ids
reference_card_ids
```

into a cite-only `ResearchAssetSelection`. L5-L10 receive the same selection
and compact it by layer before writing it into `SourceSpec.config`.

## Inputs / Outputs

CLI example:

```text
task ten-layer:graph -- \
  --asset-id strategy.trend_following.v0 \
  --asset-id math.validation.walk_forward.v0 \
  --asset-id reference.provider.alpaca_paper_adapter.v0
```

Final output includes:

```text
research_asset_policy: cite_only
research_asset_refs:
  strategy_ids
  method_ids
  reference_ids
  missing_ids
  execution_allowed: false
```

## Quality / Lineage / Receipt

Quality evidence should show:

```text
resolver splits ids by asset type
missing ids are reported
L5-L10 source configs record layer-filtered refs
CLI final output reports refs
asset context never grants execution authority
task test and task check pass
```

## Risks

```text
asset refs may be mistaken for trading permission
missing ids may be ignored by users if only shown in final output
future implementations may overuse StrategySpec content as strategy code
```

## Success Signal

Receipts from L5-L10 runs can answer which StrategySpec, MathMethodSpec, and
ReferenceCard ids were cited, while order creation and execution authority
remain controlled only by Proposal, Risk Gate, Execution, and Post-Trade.
