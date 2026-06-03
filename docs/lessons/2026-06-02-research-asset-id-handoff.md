# Lesson: Research Asset ID Handoff

Date: 2026-06-02
Status: active
Source reviews:
- /root/projects/finharness/docs/reviews/2026-06-02-research-asset-id-handoff.md
Source ideas:
- /root/projects/finharness/ideas/2026-06-02-research-asset-id-handoff.md
Affected modules:
- ten-layer graph
- research assets
- L5-L10 graphs

## Lesson

Research assets should enter the ten-layer chain as cite-only lineage before
they influence layer behavior.

## Why It Matters

Asset ids answer "what did this run cite?" They do not answer "is this trade
allowed?" Keeping that distinction explicit prevents StrategySpec from becoming
a hidden signal engine, MathMethodSpec from becoming an unverified calculation
engine, and ReferenceCard from becoming a compliance claim.

## Evidence

```text
ten_layer_graph resolves asset ids through a research_assets node.
L5-L10 source configs receive layer-filtered research_asset_context.
final.research_asset_refs reports selected ids, missing ids, and execution_allowed=false.
focused tests, task test, and task check passed.
```

## Rule / Heuristic

For future research-asset integrations:

```text
asset id in final summary
-> asset id in SourceSpec.config
-> asset id in receipt lineage
-> only then consider layer-specific behavior
```

Never let an asset id bypass Proposal, Risk Gate, Execution, or Post-Trade
permission boundaries.

## Where It Should Live

```text
src/finharness/research_assets.py
src/finharness/ten_layer_graph.py
docs/research/README.md
docs/architecture/ten-layer-langgraph-map.md
tests/test_research_asset_handoff.py
```
