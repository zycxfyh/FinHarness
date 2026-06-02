# Proposal: Cognitive engineering workflow

Date: 2026-06-01
Status: draft
Related idea: /root/projects/finharness/ideas/2026-06-01-cognitive-engineering-workflow.md
Related note: /root/projects/finharness/docs/notes/2026-06-01-cognitive-engineering-workflow-workflow-note.md
Related module:
Related ADR:

## Problem

FinHarness needs a repeatable way to turn important thoughts into project state
that can guide implementation and review.

## User / Workflow

The users are the future human operator, future AI agent, and any workflow that
needs to understand why a project action exists.

## Goals

```text
capture intent
produce a before-action proposal
preserve a review slot
distill a future lesson
write a receipt
```

## Non-Goals

```text
replace code implementation
pretend untested ideas are validated
create documentation ceremony
authorize financial execution
```

## Evidence

- Idea: /root/projects/finharness/ideas/2026-06-01-cognitive-engineering-workflow.md
- Note: /root/projects/finharness/docs/notes/2026-06-01-cognitive-engineering-workflow-workflow-note.md
- Project rule: AGENTS.md

## Design

Run the idea through a LangGraph workflow with explicit nodes for capture,
synthesis, proposal, implementation placeholder, review, lesson, and receipt.

## Inputs / Outputs

Typed inputs:

```text
topic
raw_thought
layer
source
```

Typed outputs:

```text
idea path
note path
proposal path
implementation plan
review path
lesson path
receipt path
```

## Quality / Lineage / Receipt

The receipt records all artifact paths and the workflow version. The proposal
keeps links back to the idea and note.

## Risks

```text
too many documents for small thoughts
generated placeholders never updated
proposal accepted without implementation evidence
```

## Success Signal

A future implementation can start from this proposal and later update the review
and lesson with real evidence.

## Review Plan

After the next implementation action, update the review with actual outcome,
evidence, surprises, and actions.
