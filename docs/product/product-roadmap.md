# FinHarness Product Roadmap

> Status: current planning draft (2026-07-05). This is a product sequencing
> document, not a promise of dates. It follows the [Product North Star](../product-north-star.md),
> the [Product Thesis](product-thesis.md), and the deeper
> [Capital Workbench Roadmap](capital-workbench-roadmap.md).

## Direction

FinHarness is moving from a governance skeleton into an AI-native Personal
Capital Workbench:

```text
data in -> capital state -> research packs -> scenario comparison
-> paper validation -> agent task runtime -> cockpit -> review and learning
```

The next work should be named after user-visible capabilities: data catalog,
research memo workspace, scenario comparison, paper performance review, agent
task timeline. Receipts, gates, permission checks, and API allowlists remain
acceptance criteria, not the product headline.

## Eight-Layer Roadmap

| Layer | Product capability | Current status | Next outcome |
| --- | --- | --- | --- |
| L0 Data Ingestion & Connectors | Bring in personal, market, research, macro, receipt, and agent-run data. | Thin imports and mature-wheel adapters exist. | DataSourceRegistry and connector inventory. |
| L1 Data Lake / Catalog / Quality | Know source, freshness, coverage, lineage, and whether data is usable. | DataCatalog, DataQualityReport, FreshnessPolicy, Data Quality API, Cockpit Data Trust Console shipped (#104–#108). | Data Contracts, per-dataset policy registry, lineage evidence. |
| L2 State Core / Capital Graph | Query personal capital state as accounts, assets, positions, liabilities, goals, documents, receipts, and exposures. | State Core and Capital Map are current. | PersonalCapitalGraph language and richer capital-state read models. |
| L3 Research Workspace | Organize instrument/macro questions into evidence packs, memos, filings, events, valuation snapshots, factors, and gaps. | Research evidence exists as backend contract. | EvidencePack, ResearchMemo, InstrumentProfile, research API/page. |
| L4 Scenario / What-if Engine | Compare candidate actions against a do-nothing baseline. | Action simulation is qualitative. | Scenario, WhatIfRun, PortfolioDelta, RiskImpactReport, ScenarioComparison. |
| L5 Paper Validation Runtime | Validate reviewed plans in isolated paper state. | Runtime v0 shipped in #102. | PaperPerformanceReview, PaperPnLSeries, ScenarioVsPaperComparison. |
| L6 Agent Task Runtime | Make agents traceable, resumable, checkpointed task executors. | Agent explanation/runtime v0 exists. | AgentTask, AgentStep, AgentToolRun, HumanHandoff, task artifacts. |
| L7 Cockpit / Frontend Workbench | Let users operate without reading receipt files. | Cockpit v0 is read/review focused. | Home, Portfolio, Research, Scenarios, Decisions, Paper, Agent Tasks, Data Catalog. |
| L8 Review / Learning / Governance | Preserve receipts, attestation, lessons, rule candidates, policy updates, risk register, audit trail, and permission boundaries. | Strong current layer. | Keep as cross-cutting system property rather than the roadmap headline. |

## Execution Phases

| Phase | Goal | PR shape |
| --- | --- | --- |
| Phase 0 | Reframe current docs around the Capital Workbench roadmap. | Pure docs/architecture PR. |
| Phase 1 | Data foundation. ✅ Shipped (#104–#108). | DataSourceRegistry, DataCatalog, DataQualityReport, FreshnessPolicy, Data Quality API, Cockpit Data Trust Console. |
| Phase 2 | Research Workspace v1. | InstrumentProfile, EvidencePack, ResearchMemo, research API/page, agent memo draft. |
| Phase 3 | Scenario Engine v1. | Scenario/WhatIfRun, PortfolioDelta, RiskImpactReport, DoNothingBaseline, ScenarioComparison. |
| Phase 4 | Paper Performance Loop. | PaperPerformanceReview, PnL series, scenario-vs-paper comparison, lesson candidates. |
| Phase 5 | Agent Task Runtime. | AgentTask/Step/Artifact, tool-run tracing, human handoff, first task workflows. |
| Phase 6 | Frontend Workbench upgrade. | Iterative cockpit pages, then typed client / richer UI when the API surface stabilizes. |

## Recommended PR Order

| PR | Title shape | Capability |
| --- | --- | --- |
| 103 | `docs: reframe FinHarness as capital workbench roadmap` | Positive product roadmap and 8-layer map. |
| 104 | `data: add DataSourceRegistry and DataCatalog` | Register data sources and catalog artifacts. |
| 105 | `data: add DataQualityReport and freshness policy` | Track quality, missing fields, age, and data usability. |
| 106 | `api: expose data catalog and data gaps` | Product API for data source and quality inspection. |
| 107 | `cockpit: add Data Catalog and Data Gaps page` | First user-visible data-quality surface. |
| 108 | `research: add EvidencePack and ResearchMemo` | Research artifacts users and agents can review. |
| 109 | `cockpit: add Research workspace v1` | Instrument/question page with evidence and gaps. |
| 110 | `scenario: add Scenario and WhatIfRun` | Scenario inputs and persisted runs. |
| 111 | `scenario: add PortfolioDelta and ScenarioComparison` | Compare candidate consequences. |
| 112 | `paper: add PaperPerformanceReview and scenario comparison` | Close paper validation into review. |
| 113 | `agent: add AgentTask, AgentStep, and AgentArtifact` | Stateful task runtime primitives. |
| 114 | `agent: add ResearchBriefTask workflow` | First traceable multi-step financial task. |
| 115 | `cockpit: add Agent Task timeline` | User sees agent state, artifacts, and handoffs. |

## PR Principles

1. One PR advances one product capability.
2. Governance is an acceptance condition, not the product headline.
3. Build in this order where possible: state model -> API -> tests -> cockpit -> agent tool -> agent workflow.
4. Every agent workflow must produce a durable artifact such as `ResearchMemo`, `EvidencePack`, `ScenarioComparison`, `PaperPerformanceReview`, or `LessonCandidate`.
5. Data quality beats model complexity: wrong timestamps, stale fields, missing cashflows, bad currency, survivorship bias, or future leakage must surface before agents treat data as fact.

## Near-Term Exclusions

Complex strategy automation, automated allocation, and high-consequence execution
are not B0/B1 work. They require mature state, review, paper validation,
authority objects, limits, kill switches, receipts, and post-action review before
they can be evaluated as controlled capital-action surfaces.
