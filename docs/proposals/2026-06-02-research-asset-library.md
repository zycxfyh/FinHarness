# Proposal: Research Asset Library

Date: 2026-06-02
Status: implemented-mvp
Related idea: /root/projects/finharness/ideas/2026-06-02-research-asset-library.md
Related note: /root/projects/finharness/docs/notes/2026-06-02-research-asset-library-workflow-note.md
Related module: docs/research/README.md
Related ADR:

## Problem

FinHarness has a ten-layer evidence chain, but reusable research knowledge is
still scattered across notes and layer-specific modules. Strategy ideas,
mathematical validation contracts, and references to mature tools or external
providers need a durable asset boundary that the ten-layer graph can cite
without becoming a homemade strategy engine or live execution system.

## User / Workflow

The users are the future human operator, future AI agent, and ten-layer
workflows that need to know which strategy contract, mathematical method, or
external reference applies to a layer output.

## Goals

```text
create lightweight StrategySpec assets
create lightweight MathMethodSpec assets
create lightweight ReferenceCard assets
load and validate those assets with typed Python contracts
document how the assets feed L5-L10 without authorizing execution
seal the implementation with engineering_delivery_graph evidence
```

## Non-Goals

```text
create a local strategy engine
create a local mathematical optimization engine
claim institutional compliance
connect new broker, exchange, or live trading behavior
change ten_layer_graph execution behavior in this MVP
```

## Evidence

- Idea: /root/projects/finharness/ideas/2026-06-02-research-asset-library.md
- Note: /root/projects/finharness/docs/notes/2026-06-02-research-asset-library-workflow-note.md
- Architecture map: docs/architecture/ten-layer-langgraph-map.md
- Project rule: CONTEXT.md

## Design

Create a research asset library outside the ten-layer chain:

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

The typed loader validates the asset shapes and returns an inventory summary.
It does not execute strategies, call mature libraries, connect providers, or
authorize orders.

Initial asset families:

```text
StrategySpec:
  trend_following_v0
  mean_reversion_v0
  event_reaction_v0

MathMethodSpec:
  no_lookahead_validation_v0
  walk_forward_validation_v0
  drawdown_risk_v0
  transaction_cost_analysis_v0
  parameter_robustness_v0
  return_attribution_v0

ReferenceCard:
  vectorbt
  Riskfolio-Lib
  OpenBB
  NautilusTrader
  QuantConnect LEAN
  Microsoft Qlib
  GIPS-style performance presentation
  FINRA-style best execution boundary
  Alpaca paper adapter
  OKX read/write gate
```

## Inputs / Outputs

Typed inputs are JSON files under `data/research`. Typed outputs are Pydantic
models and catalog summaries:

```text
StrategySpec
MathMethodSpec
ReferenceCard
ResearchAssetCatalog.summary()
```

Ten-layer handoff:

```text
L5 Hypotheses may cite StrategySpec thesis and assumptions.
L6 Validation may cite MathMethodSpec validation contracts.
L7 Proposal may cite StrategySpec proposal/risk/execution constraints.
L8 Risk Gate may cite StrategySpec and MathMethodSpec risk boundaries.
L9 Execution may read approved constraints only after Risk Gate.
L10 Post-Trade may cite review metrics and attribution methods.
```

## Quality / Lineage / Receipt

Quality gates:

```text
sample catalog loads successfully
known layer refs are enforced
unknown live-write integration status is rejected
all sample assets declare no_execution_authority
```

Lineage:

```text
cognitive_graph creates the idea/proposal trail
engineering_delivery_graph records changed files, docs, checks, and lessons
```

## Risks

```text
assets become stale if not referenced by future ten-layer runs
ReferenceCards may be mistaken for compliance claims
StrategySpecs may be mistaken for trading signals
MathMethodSpecs may be mistaken for implemented calculations
```

## Success Signal

Future ten-layer work can point to a StrategySpec, MathMethodSpec, or
ReferenceCard by id and know what it may learn, what it must not claim, and
which layer boundary owns the decision.

## Review Plan

Run focused tests for the asset loader, then run the standard project check.
Use engineering_delivery_graph to write the delivery receipt and update the
review with concrete evidence.
