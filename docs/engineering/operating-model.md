# FinHarness Operating Model

> Status: current planning draft (2026-07-05). Scope: engineering / product
> delivery discipline. This document defines how FinHarness should move from one
> capability slice to the next without mixing roadmap, runtime, frontend, data,
> agent, and review work in the same PR.

## Core Loop

FinHarness should advance through a repeatable operating loop:

```text
strategy
-> shaping
-> RFC / pitch
-> architecture review
-> implementation slice
-> verification matrix
-> product surface review
-> release gate
-> operation / metrics
-> retrospective
```

The point is not ceremony. The point is to keep work bounded while the product
expands from governance artifacts into a user-visible Capital Workbench.

## Strategic Direction

Current strategy:

- Build an AI-native Personal Capital Workbench.
- Unblock the next layer by making data source, freshness, quality, coverage,
  and gaps visible.
- Defer high-consequence live capital actions, automated allocation, complex
  multi-account production deployment, and broad frontend rewrites until the
  data, research, scenario, paper review, and agent task layers are mature.

Current maturity reading:

```text
governance capability > data product capability > research product capability
> agent workflow capability > frontend workbench capability
```

That ordering determines the next slices.

## Shaping Rule

Every capability slice starts as a short shape note or mini-RFC before coding.
Unshaped ideas stay in shaping; they do not become implementation.

Minimum shape:

```text
Problem:
Current Repo Truth:
User-Visible Outcome:
Thin Slice:
No-Gos:
Risks / Rabbit Holes:
Acceptance:
```

For C2/C3 work, use the full [mini-RFC template](../templates/mini-rfc.md).

## PR Constitution

Every PR description, mini-RFC, or release decision must be able to answer:

| Check | Required answer |
| --- | --- |
| Product Claim | Which user capability does this advance? |
| Layer | Which L0-L8 Capital Workbench layer owns it? |
| Thin Slice | What is the smallest mergeable scope? |
| No-Gos | What is explicitly out of scope for this PR? |
| State Change | Does it change DB, receipts, API, or runtime behavior? |
| Data Flow | Where does data come from and where does it go? |
| Invariants | Which conditions must never be broken? |
| Tests | Which happy-path, stale, replay, bad-input, drift, and boundary cases are covered? |
| Docs | Which current docs, catalogs, maps, or templates changed? |
| Product Surface | What can the user now see, compare, validate, understand, or review? |
| Merge Decision | Merge now, keep draft, split, request changes, or abandon? |

Progress is not PR count. Progress is what became visible, comparable,
validated, traceable, or learnable.

## PR Type Boundaries

Each PR has one primary type:

| Type | May change | Must not mix in |
| --- | --- | --- |
| docs | Roadmap, architecture, operating model, current docs | Runtime code |
| model | SQLModel / schema / migration / receipt shape | Frontend or agent workflows |
| api | Routes, OpenAPI, service wiring | Large model/workflow changes |
| data | Connectors, catalog, quality, freshness | Scenario, paper, or agent layers |
| cockpit | UI pages and read surfaces | Large data model changes |
| agent | AgentTask, ToolRun, workflow artifacts | Data-foundation rewrites |
| paper | Paper state, performance review, paper learning | Live capital actions |
| security | Hardening, redlines, CI, dependency posture | Product feature work |

If a PR needs two primary types, split it unless the release manager explicitly
accepts the coupling.

## Verification Matrix

Each capability PR should fill the relevant rows:

| Layer | Questions |
| --- | --- |
| Unit | Do individual functions, value objects, and validators hold? |
| Integration | Do model, service, receipt, API, and storage agree? |
| Contract | Are OpenAPI, schema, docs, and allowlists synchronized? |
| Boundary | Do stale, replay, bad input, missing source, marker, and drift cases fail safely? |
| Migration | Can existing local state upgrade or remain readable? |
| Data Quality | Are stale, biased, incomplete, or future-leaking data surfaced as gaps? |
| Agent | Are profile bypass, unavailable tools, oversized outputs, and missing evidence handled? |
| Frontend | Does the page show state, gaps, errors, and review status clearly? |
| Security | Do secret scan, dependency scan, fuzz, redteam, and governance checks still pass where relevant? |

## Product Surface Review

Before release, answer these five questions:

```text
What can the user see now?
What can the user compare now?
What can the user validate now?
What can the user understand now?
What can the user review or learn from now?
```

If the answer is only "more receipt, gate, non-claim, or review object", the PR
is governance expansion, not product progress. Governance remains required, but
the roadmap headline should be a workbench capability.

## Release Gate

Every merge decision should be explicit:

```text
Merge decision:
- merge now
- keep draft
- split PR
- request changes
- abandon

Reason:
- product value
- boundary safety
- test confidence
- future maintainability
```

## Operating Metrics

Track these as lightweight project health signals:

- PR lead time.
- PR size by files, lines, and systems touched.
- Test failure count.
- Post-merge fix count.
- Docs drift count.
- OpenAPI drift count.
- Stale data incidents.
- Paper replay rejection count.
- Agent tool failure rate.
- Receipt write failure count.

These metrics are not KPI theater. They show whether the workbench is becoming
more capable without becoming brittle.

## Retrospective

After each phase or high-friction PR, write a short retrospective:

```text
What changed?
What became easier?
What became riskier?
What did we overbuild?
What did we under-test?
What should be the next slice?
What should not be touched yet?
```

Recurring lessons should become a rule, test, template, or accepted debt item.

## Current Sequence

```text
#103: merge roadmap / operating-model anchor
#104-107: Data Foundation
#108-109: Research Workspace
#110-111: Scenario Engine
#112-114: Paper Performance Loop
#115-119: Agent Task Runtime
#120+: Frontend Workbench upgrade
```

The next implementation slice should be PR 104: `DataSourceRegistry` and
`DataCatalog`. It should not include agent workflow, scenario, paper review, or
frontend redesign work.
