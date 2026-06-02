# Module Governance From Top Projects

Date: 2026-06-01

Purpose: learn how top companies and open-source projects record module
evolution, major decisions, upgrade rationale, and implementation history; then
adapt the practice to FinHarness.

## Compression

Yes, serious companies and top open-source projects do this.

They usually do not call it "one md file per module", but they maintain the
same underlying system:

```text
module ownership
design proposals
decision records
change history
status tracking
review/approval process
implementation evidence
```

The mature pattern is:

```text
small changes -> normal PR / changelog / tests
significant changes -> RFC / KEP / DEP / ADR / blueprint
module history -> module README / handbook / architecture page
```

## What Top Projects Do

### Rust: RFCs

Rust uses RFCs for substantial language, library, and ecosystem changes.

Pattern:

```text
proposal before implementation
motivation and detailed design
drawbacks and alternatives
community/team review
accepted RFC becomes active
tracking issue follows implementation
```

Lesson for FinHarness:

```text
For major layer changes, write a proposal before code.
Keep implementation tracking separate from the proposal.
```

Use when:

```text
new layer
new durable schema
new execution permission model
new provider integration pattern
major workflow redesign
```

### Kubernetes: KEPs

Kubernetes uses Kubernetes Enhancement Proposals for substantial platform
changes.

Pattern:

```text
enhancement issue
proposal document
SIG ownership
motivation
goals and non-goals
implementation plan
graduation / rollout status
```

Lesson for FinHarness:

```text
Every serious module upgrade should state goals, non-goals, status, owner, and
rollout evidence.
```

Use when:

```text
moving a module from experiment -> active
adding a new lifecycle stage
changing how receipts or snapshots work
```

### Django: DEPs

Django uses Django Enhancement Proposals for large framework changes.

Pattern:

```text
proposal for framework-level change
public discussion
accepted design
reference implementation
eventual integration
```

Lesson for FinHarness:

```text
Separate the design from the reference implementation.
The first working implementation should still point back to the proposal.
```

### GitLab: Handbook, Architecture, Blueprints

GitLab operates with a public handbook and architecture decision/blueprint
processes.

Pattern:

```text
handbook-first operating model
architecture pages for shared understanding
blueprints for significant changes
maintainer/reviewer responsibilities
decision-making rules
```

Lesson for FinHarness:

```text
Docs are not afterthoughts. They are how the system remembers why it exists and
how it should change.
```

### ADRs / MADR / Cloud Architecture Guidance

Architecture Decision Records are a lightweight way to preserve the reason
behind an architectural choice.

Pattern:

```text
status
context
problem
considered options
decision
consequences
confirmation / evidence
links
```

Microsoft and Google Cloud both recommend ADR-style records for explaining
architecture choices and keeping decision history close to engineering work.

Lesson for FinHarness:

```text
Use ADRs for "why did we choose this?".
Use module logs for "how did this module evolve?".
Use ideas/think for "what could this become?".
```

## FinHarness Recommendation

Use three document types, not one giant document.

### 1. Module README

One per major layer/module.

Location:

```text
docs/modules/<module-name>.md
```

Purpose:

```text
current truth of the module
what it owns
what it does not own
inputs and outputs
important files
current maturity
upgrade log
open risks
next upgrades
```

### 2. Decision Records

One per significant decision.

Location:

```text
docs/adr/YYYY-MM-DD-short-title.md
```

Purpose:

```text
why this decision was made
what alternatives were considered
what we chose
what consequences we accept
how we will know it worked
```

### 3. Proposals / RFCs

One per major new layer or cross-cutting change.

Location:

```text
docs/proposals/YYYY-MM-DD-short-title.md
```

Purpose:

```text
before-code design for large changes
goals and non-goals
success criteria
implementation plan
rollout and test plan
```

## Proposed Module Map

Start with these module docs:

```text
docs/modules/01-market-data.md
docs/modules/02-indicators.md
docs/modules/03-events.md
docs/modules/04-interpretation.md
docs/modules/05-hypotheses.md
docs/modules/06-validation.md
docs/modules/07-proposals.md
docs/modules/08-risk-gates.md
docs/modules/09-execution.md
docs/modules/10-review-learning.md
docs/modules/idea-evolution.md
```

The first two can be filled immediately because they already exist in code.

The remaining docs can begin as stubs with:

```text
status: planned
current implementation: none
next vertical slice
risks
```

## Module Document Template

```text
# Module: <Name>

Status:
Owner:
Layer:
Last updated:

## Purpose

What problem does this module solve?

## Current Responsibilities

What does it own?

## Non-Goals

What must it not do?

## Inputs

Typed input objects and upstream sources.

## Outputs

Typed output objects and downstream consumers.

## Current Implementation

Important files, tasks, tests, and runtime artifacts.

## Mature Wheels / External Systems

Which mature projects own heavy domain work?

## Quality / Lineage / Receipt

How the module proves what happened.

## Upgrade Log

### YYYY-MM-DD: <Upgrade Title>

Why:
What changed:
Evidence:
Risks:
Next:

## Open Risks

Known weaknesses and failure modes.

## Next Upgrades

Small next steps.
```

## ADR Template

```text
# ADR: <Title>

Date:
Status: proposed | accepted | superseded | rejected
Deciders:

## Context

What problem or force made a decision necessary?

## Decision

What are we choosing?

## Considered Options

1. Option A
2. Option B
3. Option C

## Consequences

Positive:
Negative:
Neutral:

## Confirmation

What evidence will show this decision is working?

## Links

Related module docs, ideas, code, tests, receipts.
```

## Proposal Template

```text
# Proposal: <Title>

Date:
Status: draft | accepted | implemented | rejected
Layer:

## Summary

One-paragraph proposal.

## Motivation

Why now?

## Goals

What must be true?

## Non-Goals

What is intentionally excluded?

## Design

Typed inputs, outputs, workflows, storage, receipts.

## Alternatives

What else did we consider?

## Rollout Plan

Small vertical slices.

## Test Plan

Focused tests and project checks.

## Risks

What could go wrong?

## Open Questions

What remains unknown?
```

## Operating Rule

Do not document everything with the same weight.

Use:

```text
idea:
  early thought or hypothesis.

think:
  first-principles reasoning.

note:
  research or implementation summary.

module doc:
  current module truth and upgrade log.

ADR:
  one important decision and its rationale.

proposal:
  before-code plan for a substantial new layer/change.
```

## Immediate Next Step

Create:

```text
docs/modules/01-market-data.md
docs/modules/02-indicators.md
docs/adr/2026-06-01-use-module-docs-and-adrs.md
```

Then update `AGENTS.md` to require module docs and ADRs for substantial
module/layer upgrades.

## Sources

- Rust RFCs:
  https://github.com/rust-lang/rfcs
- Rust RFC merge procedure:
  https://forge.rust-lang.org/lang/rfc-merge-procedure.html
- Kubernetes Enhancement Proposals:
  https://www.kubernetes.dev/resources/keps/
- GitLab architecture handbook:
  https://handbook.gitlab.com/handbook/engineering/architecture/
- GitLab decision making:
  https://docs.gitlab.com/charts/architecture/decision-making/
- GitLab Dedicated architecture blueprints:
  https://handbook.gitlab.com/handbook/engineering/infrastructure-platforms/gitlab-dedicated/
- ADR overview:
  https://adr.github.io/
- MADR decisions and templates:
  https://adr.github.io/madr/decisions/
- Microsoft ADR guidance:
  https://learn.microsoft.com/en-ie/azure/well-architected/architect-role/architecture-decision-record
- Google Cloud ADR overview:
  https://docs.cloud.google.com/architecture/architecture-decision-records
