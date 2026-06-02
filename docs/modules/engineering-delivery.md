# Module: Engineering Delivery

Status: implemented MVP
Owner: FinHarness
Layer: cross-cutting engineering governance
Last updated: 2026-06-02

## Purpose

The Engineering Delivery module turns selected ideas, proposals, and user goals
into auditable engineering delivery evidence.

It answers:

```text
What was the engineering goal?
What scope and non-goals governed the work?
Was a proposal required?
Which files changed?
Which docs were updated?
Which checks passed or failed?
What receipt and review evidence exists?
```

It does not answer:

```text
Should we trade?
Is a financial hypothesis valid?
Is a generated idea true?
Is the project production-ready?
```

## Current Responsibilities

Implemented MVP responsibilities:

```text
consume a project goal and delivery evidence
classify substantial changes that require proposal evidence
run design and quality gates
write EngineeringDelivery receipt JSON
write engineering review draft
report remaining delivery debt
keep execution permission disabled
```

## Non-Goals

```text
no financial execution
no broker or exchange action
no replacement for Cognitive Graph
no replacement for Daily Evidence Graph
no automatic code editing
no CI or release authorization
no claim that passing tests proves design correctness
```

## Inputs

Current inputs:

```text
goal
source_ref
proposal_ref
module_refs
change_type
scope
non_goals
success_criteria
planned_files
changed_files
docs_updated
checks
lessons
```

## Outputs

Current outputs:

```text
EngineeringDeliverySnapshot
EngineeringDeliveryReceipt
engineering review draft
final workflow summary
remaining_debt
```

Runtime artifacts:

```text
data/receipts/engineering-delivery/
docs/reviews/YYYY-MM-DD-*-engineering-delivery.md
```

Task:

```text
task workflow:engineering-delivery
```

## Relationship To Other Graphs

```text
Cognitive Graph:
  captures and evolves ideas, notes, proposals, reviews, and lessons.

Engineering Delivery Graph:
  audits whether a selected idea/proposal was delivered with scope, files,
  checks, docs, receipt, review, and remaining-debt evidence.

Daily Evidence Graph:
  runs the first four financial evidence layers.

Future Financial Decision Operating Graph:
  will compose financial subgraphs after later layers exist.
```

Short version:

```text
Cognitive Graph thinks clearly.
Engineering Delivery Graph delivers and audits.
Daily Evidence Graph runs business evidence.
```

## Quality / Lineage / Receipt Strategy

Quality gate requires:

```text
goal present
scope present
non_goals present
proposal_ref present for substantial changes
changed_files present
docs_updated present
at least one check recorded
all checks passed
```

Lineage records:

```text
source_ref
proposal_ref
module_refs
transform_version
```

Permission boundary:

```text
execution_allowed = false
```

## Important Files

```text
src/finharness/engineering_delivery_graph.py
scripts/run_engineering_delivery_graph.py
tests/test_engineering_delivery_graph.py
docs/proposals/2026-06-02-engineering-delivery-graph-mvp.md
```

## Upgrade Log

### 2026-06-02: Engineering Delivery Graph MVP

Why:

FinHarness needed a graph for project delivery itself. Cognitive Graph could
preserve ideas, and Daily Evidence Graph could run financial evidence, but the
project lacked a strict flow for turning a selected idea into implementation,
tests, docs, receipts, and review.

What changed:

```text
Added engineering_delivery_graph.py
Added run_engineering_delivery_graph.py
Added workflow:engineering-delivery task
Added tests for pass and failed evidence gates
Added module and proposal documentation
```

Result:

The first version can audit this project delivery flow without authorizing any
financial or release action.

## Open Risks

```text
checks are recorded as supplied evidence rather than executed by the graph
review draft is generated, not externally approved
lesson capture is a structured placeholder only
no durable checkpointing beyond receipt/review files yet
```

## Next Upgrades

```text
1. Add command execution evidence capture for selected safe local checks.
2. Link Cognitive Graph proposals directly into Engineering Delivery runs.
3. Add a module-doc upgrade-log verifier.
4. Add optional human approval interrupt for architecture changes.
5. Add delivery metrics: lead time, failed gate rate, review follow-up rate.
```
