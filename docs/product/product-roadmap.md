# FinHarness Product Roadmap

> Status: current planning draft (2026-07-11). This is a product sequencing
> document, not a promise of dates. It follows the [Product North Star](../product-north-star.md),
> the [Product Thesis](product-thesis.md), and the deeper
> [Capital Workbench Roadmap](capital-workbench-roadmap.md).

## Direction

FinHarness is moving from a receipt-backed review workbench toward an
**Agent-Native Personal Capital Operating System**. The current product is not
yet the north star. Its first validated job is Material Decision Review with Scheduled
Retrospective:

```text
trusted capital state -> material trigger -> decision review
-> deterministic scenario comparison -> human decision
-> scheduled outcome review -> learning
```

Home/Today is the intake surface, not the engagement goal. Near-term
Human-in-the-loop review and simulated execution are autonomy stages, not the
permanent role of the Agent. Receipts, gates, permission checks, recovery, and
API allowlists exist to let the Agent safely gain objective-level control.

The detailed, repository-grounded slice order and gates live in
[`2026-07-11-finharness-evolution-execution-plan.md`](../proposals/2026-07-11-finharness-evolution-execution-plan.md).

## Product Layer Roadmap

| Layer | Product capability | Current status | Next outcome |
| --- | --- | --- | --- |
| L0 Data Ingestion & Connectors | Bring in personal, market, research, macro, receipt, and agent-run data. | Thin imports and mature-wheel adapters exist. | DataSourceRegistry and connector inventory. |
| L1 Data Lake / Catalog / Quality | Know source, freshness, coverage, lineage, and whether data is usable. | DataCatalog, DataQualityReport, FreshnessPolicy, Data Quality API, Cockpit Data Trust Console shipped (#104–#108). | Data Contracts, per-dataset policy registry, lineage evidence. |
| L2 State Core / Capital State | Query personal capital state as accounts, assets, positions, liabilities, goals, documents, receipts, and exposures. | State Core is a useful local mirror, but valuation currency/time/readiness are incomplete. | Position valuation contract, ImportBatch, reconciliation, CapitalStateView, cross-domain DataReadiness. |
| L3 Research Workspace | Organize instrument/macro questions into evidence packs, memos, filings, events, valuation snapshots, factors, and gaps. | Research evidence exists as backend contract. | EvidencePack, ResearchMemo, InstrumentProfile, research API/page. |
| L4 Scenario / What-if Engine | Compare candidate actions against a do-nothing baseline. | Action simulation is qualitative. | Scenario, WhatIfRun, PortfolioDelta, RiskImpactReport, ScenarioComparison. |
| L5 Paper Outcome Runtime | Compare a reviewed decision with do-nothing and benchmark outcomes. | Canonical simulated Execution Kernel exists; legacy PaperValidation is not a performance loop. | PaperPerformanceReview, PaperPnLSeries, ScenarioVsPaperComparison. |
| L6 Agent Task Runtime | Make one bounded review task traceable, durable, and reviewable. | Agent Operating Cycle v0.1 passes the 15/15 AUT2 foundation gate with typed observations and a terminal searchable chain. | Bind a useful counter-evidence review packet to W1/W2 world prerequisites, then design AUT3 delegated Decision Review. |
| L7 Cockpit / Frontend Workbench | Let users complete review without reading receipt files. | Proposal Review is strongest; Execution UI is currently misleading. | Home/Today, Decision Inbox/Workspace, trust metadata, stable read models, required browser paths. |
| L8 Review / Learning / Governance | Preserve receipts, attestation, lessons, rule candidates, policy updates, risk register, audit trail, and permission boundaries. | Strong current layer. | Keep as cross-cutting system property rather than the roadmap headline. |

## Current Workstreams

| Workstream | Goal | PR shape |
| --- | --- | --- |
| E0 | Repair evidence and architecture gates. | Run unittest + pytest, add SCC/layer gate, register material debt, consolidate current truth. |
| E1 | Contain misleading execution/legacy surfaces. | Hide or repair Execution UI, seal simulated adapter boundary, freeze legacy writes. |
| D0 | Build trustworthy capital state. | Valuation currency/time, Decimal ingestion, ImportBatch, receipt/mirror reconciliation, CapitalStateView/DataReadiness. |
| D1 | Bind decisions to immutable proposal versions. | ProposalVersion, DecisionRecord, command-consumed readiness, effective policy consumer, Decision Inbox projection. |
| P0 | Deliver Material Decision Review v1. | Home/Today intake, Decision Workspace, point-in-time EvidencePack, concentration Scenario v0, scheduled outcome. |
| A0 | AUT2 bounded Agent cycle foundation (complete locally). | Typed request/observation/reducer, Harness admission, durable terminal chain, search/workspace hydration, 15/15. |
| A1 | Prove one useful delegated review outcome. | Counter-evidence review packet over versioned decisions and Scenario, explicit mandate, out-of-mandate escalation, no effect authority. |
| O0 | Close outcome and learning. | Monotonic simulated execution, decision binding, PaperPerformanceReview, later policy-consumption evidence. |

## Immediate Concurrency Plan

1. Foundation convergence: `E0-01`, `E0-03`, and `E1-01` repair the evidence
   floor and stop current surfaces from reporting false capability.
2. World lane: `D0-01` through `D0-05`, then `D1-01` through `D1-04`, build W0
   capital truth and W1 versioned decisions.
3. Agent lane in parallel: `A0-01` through `A0-05` build AUT2 against typed
   fixtures, then integrate the same loop with W0/W1 contracts as they land.
4. Product/world integration: `P0-01` through `P0-05` build W2 Material Decision
   Review; W2 + AUT2 becomes the entry gate for AUT3 delegated review.
5. Outcome/autonomy integration: `O0-01` through `O0-04` build W3/W4; W3 + AUT3
   becomes the entry gate for AUT4 autonomous paper management.
6. AUT5 real action remains a separate authorization program after W4/AUT4
   evidence; it is neither current work nor a permanent exclusion.

No PR number is preallocated. Each slice advances only when its executable exit
gate passes on the same commit.

## Autonomy Ladder

Product and Agent development move on two intersecting axes:

```text
World: W0 facts -> W1 decisions -> W2 Scenario -> W3 Outcome -> W4 Learning
Agent: AUT0 context -> AUT1 tools -> AUT2 loop -> AUT3 delegated review
       -> AUT4 paper manager -> AUT5 bounded real operator -> AUT6 continuous agent
```

Material Decision Review proves W1/W2. The current 15-contract loop gate is the
minimum AUT2 Harness foundation. It is not the Agent product endpoint.
Autonomous Paper Capital Manager requires W3 + AUT4. Mandate-bound real action
is a later, separately authorized AUT5 program—not a current implementation
promise and not a permanent architectural exclusion.

## PR Principles

1. One PR advances one product capability.
2. Governance is an acceptance condition, not the product headline.
3. Build in this order where possible: failing behavior -> typed state/service -> migration -> API contract -> product projection -> browser path -> optional Agent consumer.
4. Every agent workflow must produce a durable artifact such as `ResearchMemo`, `EvidencePack`, `ScenarioComparison`, `PaperPerformanceReview`, or `LessonCandidate`.
5. Data quality beats model complexity: wrong timestamps, stale fields, missing cashflows, bad currency, survivorship bias, or future leakage must block unsupported uses before agents treat data as fact.

## Near-Term Exclusions

Complex strategy automation, generalized Research Workspace, automated
allocation, sessions/schedulers/subagents, and high-consequence execution are
not current work. They require trustworthy state, versioned decisions, a proven
user loop, paper outcomes, authority contracts, and explicit new authorization.
