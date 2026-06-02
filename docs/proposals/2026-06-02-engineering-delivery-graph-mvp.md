# Proposal: Engineering Delivery Graph MVP

Date: 2026-06-02
Status: implemented MVP
Related idea:
Related module: docs/modules/engineering-delivery.md
Related ADR:

## Problem

FinHarness has a Cognitive Graph for idea capture and a Daily Evidence Graph
for financial evidence, but it needs a separate workflow for engineering
delivery itself.

Without this graph, substantial changes can drift from:

```text
idea
-> discussion
-> code
-> "looks done"
```

instead of moving through:

```text
goal
-> scope
-> proposal gate
-> implementation evidence
-> local checks
-> docs
-> receipt
-> review
```

## User / Workflow

The users are the human operator, future AI agents, and future maintainers who
need to understand whether an engineering task was actually delivered.

## Goals

```text
create a strict Engineering Delivery Graph
keep it separate from Finance Graph and Trade Graph
record scope, non-goals, files, docs, checks, receipt, and review
fail when required delivery evidence is missing
use it to audit this implementation after tests
keep execution permission disabled
```

## Non-Goals

```text
no financial execution
no broker/exchange action
no replacement for Cognitive Graph
no replacement for Daily Evidence Graph
no automatic CI/release approval
no claim that passing tests proves architecture is correct
```

## Evidence

Project context:

```text
AGENTS.md:
  substantial goals should bind to explicit workflows with gates, receipts,
  reviews, and completion evidence.

docs/proposals/2026-06-01-cognitive-engineering-workflow.md:
  Cognitive Graph already captures ideas and proposal artifacts.

docs/proposals/2026-06-02-daily-evidence-graph-mvp.md:
  Daily Evidence Graph already composes financial evidence layers.
```

## Design

The MVP graph is a deterministic LangGraph workflow:

```text
source_config
-> intake
-> goal_definition
-> scope_boundary
-> change_classification
-> design_gate
-> implementation_plan
-> work_breakdown
-> execute_changes
-> local_checks
-> quality_gate
-> docs_update
-> receipt
-> review_hook
-> lesson_capture
-> final
```

Failure route:

```text
design_gate or quality_gate failed
-> failed_receipt
-> review_hook
-> lesson_capture
-> final
```

The graph does not edit files. It audits delivery evidence supplied by the
caller and writes receipt/review artifacts.

## Inputs / Outputs

Typed inputs:

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

Typed outputs:

```text
snapshot
receipt
review_ref
final
remaining_debt
```

## Quality / Lineage / Receipt

Quality gates require:

```text
goal
scope
non_goals
proposal_ref for substantial workflow/layer/architecture changes
changed_files
docs_updated
passing checks
```

Lineage records:

```text
source_ref
proposal_ref
module_refs
transform_version
```

Receipt path:

```text
data/receipts/engineering-delivery/
```

Review path:

```text
docs/reviews/YYYY-MM-DD-*-engineering-delivery.md
```

## Risks

```text
caller-supplied check evidence can be inaccurate
review hooks can become stale if not read
passing local checks are not design proof
the graph can become ceremony if used for tiny tasks
```

## Success Signal

```text
task workflow:engineering-delivery
```

can produce:

```text
quality_ok=true
status=pass
receipt_ref
review_ref
execution_allowed=false
remaining_debt=[]
```

and tests cover both pass and missing-evidence failure routes.

## Review Plan

After implementation, run the graph against this delivery itself using actual
changed-file, doc, and test evidence. Keep the generated engineering review as
the first self-audit artifact.
