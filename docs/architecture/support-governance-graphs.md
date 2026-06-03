# Architecture: Support Governance Graphs

Date: 2026-06-03
Status: active support positioning

## Summary

FinHarness has one primary ten-layer domain chain and two high-priority support
governance graphs:

```text
cognitive_graph
engineering_delivery_graph
```

The archived `finance_graph` and `trade_graph` are no longer active workflow
entrypoints. They live under `docs/archive/legacy-graphs/` as historical
references.

## Cognitive Graph Positioning

Purpose:

```text
turn raw thinking into durable project knowledge before implementation
```

Use it when:

```text
researching a new layer or institutional practice
turning a vague idea into a proposal
capturing why a direction matters
creating review and lesson placeholders before implementation
preserving a receipt for project memory
```

Do not use it to:

```text
claim implementation is complete
run tests
authorize financial execution
replace engineering delivery evidence
```

Path:

```text
source_config is implicit in run_cognitive_project_flow input
-> capture_idea
-> synthesize_note
-> draft_proposal
-> implementation_plan
-> review
-> lesson
-> receipt
-> final
```

Artifacts:

```text
ideas/<date>-<slug>.md
docs/notes/<date>-<slug>-workflow-note.md
docs/proposals/<date>-<slug>.md
docs/reviews/<date>-<slug>.md
docs/lessons/<date>-<slug>.md
data/receipts/cognitive-graph/<stamp>-<slug>.json
```

Authority boundary:

```text
The cognitive graph creates project knowledge artifacts only.
It does not prove code works and does not close delivery.
```

Current implementation:

```text
src/finharness/cognitive_graph.py
scripts/run_cognitive_flow.py
task workflow:cognitive
```

## Engineering Delivery Graph Positioning

Purpose:

```text
turn implementation evidence into a delivery receipt and review
```

Use it when:

```text
sealing a new layer or major workflow
auditing whether changed files match the stated scope
checking whether docs and tests were updated
recording pass/fail command evidence
creating an engineering delivery receipt
classifying remaining debt explicitly
```

Do not use it to:

```text
perform code mutations
replace tests
pretend missing checks passed
authorize financial execution
replace the ten-layer domain chain
```

Path:

```text
source_config
-> intake
-> goal_definition
-> scope_boundary
-> change_classification
-> design_gate
   -> failed route: quality_gate -> failed_receipt
   -> continue route:
      implementation_plan
      -> work_breakdown
      -> execute_changes
      -> local_checks
      -> quality_gate
         -> failed route: failed_receipt
         -> continue route: docs_update -> receipt
-> review_hook
-> lesson_capture
-> final
```

Key gates:

```text
design_gate:
  requires goal, scope, non_goals, and proposal_ref for high-risk change types

quality_gate:
  requires changed_files, docs_updated, and passing_checks
```

Artifacts:

```text
data/receipts/engineering-delivery/<stamp>-<slug>.json
docs/reviews/<date>-<slug>-engineering-delivery.md
```

Authority boundary:

```text
The engineering delivery graph audits delivery evidence.
It does not mutate code and does not authorize financial execution.
```

Current implementation:

```text
src/finharness/engineering_delivery_graph.py
scripts/run_engineering_delivery_graph.py
task workflow:engineering-delivery
```

## Relationship Between The Two

```text
cognitive_graph answers:
  What is the idea, why does it matter, and what should be proposed?

engineering_delivery_graph answers:
  Was the proposed engineering work actually delivered with evidence?
```

Recommended lifecycle:

```text
new idea / layer / architecture question
-> workflow:cognitive
-> implementation work
-> focused tests and task checks
-> workflow:engineering-delivery
-> module docs / review / lesson updates
```

## Archive Decision

Archived on 2026-06-03:

```text
docs/archive/legacy-graphs/finance_graph.py
docs/archive/legacy-graphs/trade_graph.py
docs/archive/legacy-graphs/run_institutional_paper_trade.py
```

Reason:

```text
finance_graph mixed legacy data-entry and risk-note evaluation in a wrapper
that is no longer the authoritative domain chain.

trade_graph mixed research, risk, paper execution, and receipt behavior in one
experiment after Layers 7-10 split those responsibilities into governed modules.
```

Current stance:

```text
Keep these archived graphs as design history.
Do not expose them through Taskfile, agent tools, active scripts, or tests.
```
