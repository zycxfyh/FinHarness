# Capital Workbench Roadmap

> Status: current planning draft (2026-07-05). Scope: product / architecture
> roadmap. Non-runtime: this document does not add code paths, APIs, authority,
> broker connectivity, or execution behavior.

## North-Star Definition

FinHarness should become an AI-native Personal Capital Workbench:

```text
connect data, organize research, compare scenarios, run paper validation,
capture agent tasks, and turn outcomes into review, rules, and better judgment.
```

Safety boundaries stay in code, tests, permissions, gates, receipts, API
allowlists, security docs, and architecture invariants. Current product docs
should describe what capability we are building rather than defining the product
as a list of category denials.

## Reference Posture

FinHarness should borrow from mature financial and agent systems without copying
their business model or consequence level.

| Reference | Learn | Do not copy |
| --- | --- | --- |
| Bloomberg Terminal / professional workstations | Multi-source data, multi-view research flow, evidence organization, fast question answering. | Becoming a professional trading terminal or broker execution platform. |
| QuantConnect / LEAN-style platforms | Separation among data, portfolio state, holdings, cashbook, orders, reality modeling, fees, slippage, risk, and performance. | Jumping directly into automated strategy execution or live brokerage. |
| OpenAI Agents SDK / LangGraph / LlamaIndex Workflows / AutoGen | Agents as stateful, traceable, tool-using, human-in-the-loop task runtimes with sessions, guardrails, handoffs, checkpoints, and observability. | Treating an agent as a one-shot chat answer or prompt-only glue. |

## Layer Map

```text
L0 Data Ingestion & Connectors
L1 Data Lake / Catalog / Quality
L2 State Core / Capital Graph
L3 Research Workspace
L4 Scenario / What-if Engine
L5 Paper Validation Runtime
L6 Agent Task Runtime
L7 Cockpit / Frontend Workbench
L8 Review / Learning / Governance
```

Governance remains cross-cutting. It should not disappear, but it should stop
consuming the product headline.

## L0 — Data Ingestion & Connectors

Goal: bring data in.

Data categories:

- personal finance: accounts, positions, transactions, cashflows, liabilities, goals;
- market and research: prices, fundamentals, filings, news, macro, rates, earnings, ETFs;
- system runtime: receipts, agent traces, tool runs, paper executions, reviews.

First-stage shape:

- CSV / manual import;
- yfinance / OpenBB-style market adapter;
- SEC filings / FRED / basic macro;
- paper account event stream.

Target artifacts:

- `DataConnector`
- `RawDataArtifact`
- `NormalizedDataFrame`
- `DataReceipt`
- `DataSourceRegistry`

## L1 — Data Lake / Catalog / Quality

Goal: know whether data can be used.

**Current shipped capability (#104–#108):**

- `DataSourceRegistry` — known data sources with bias controls and limitations
- `DataCatalog` / `DataCatalogEntry` — catalog built from local market-data receipts
- `DataQualityReport` / `FreshnessPolicy` — structured freshness, quality, bias, reconciliation, readiness assessment
- `DataQualityFinding` — severity-coded findings with blocks
- `/data/catalog`, `/data/quality`, `/data/gaps` GET-only API surface
- `Cockpit Data Trust Console` — Summary, Catalog, Quality Reports, Data Gaps panels
- Market-data receipt loading is single-pass via `load_market_data_receipts()`
- All surfaces: read-only, no network, no provider refresh, execution_allowed=false

**Next outcome:** Data Contracts, per-dataset policy registry, lineage evidence.

## L2 — State Core / Capital Graph

Goal: make personal capital state queryable as a graph-like model.

Core objects:

- `Account`
- `Asset`
- `Position`
- `Transaction`
- `Cashflow`
- `Liability`
- `Goal`
- `Policy`
- `RiskExposure`
- `TaxLot`
- `Document`
- `Receipt`

Questions answered:

- What do I own?
- Where is risk concentrated?
- What changed since last time?
- Which data is not trustworthy?
- Which events affect me?

## L3 — Research Workspace

Goal: move from evidence contracts to a real research workspace.

Target surfaces:

- Watchlist
- Instrument Page
- Research Memo
- Evidence Pack
- Filing Reader
- News/Event Timeline
- Valuation Snapshot
- Factor Exposure
- Comparable Assets

Opening an asset should show price history, fundamentals, valuation range,
filing changes, news/events, risk exposure, related ETFs/sectors/factors,
volatility/drawdown, data gaps, and agent research notes.

Primary outputs:

- `ResearchBrief`
- `EvidencePack`
- `QuestionList`
- `RiskSummary`
- `UncertaintyMap`

## L4 — Scenario / What-if Engine

Goal: compare consequences before action.

Example questions:

- What if I reduce this holding by 10 percent?
- What if I add 5 percent?
- What if I do nothing?
- What if the market falls 20 percent?
- What if FX moves 10 percent?
- What if cashflow stops for six months?
- What if a single stock halves?

Target artifacts:

- `Scenario`
- `WhatIfRun`
- `PortfolioDelta`
- `RiskImpactReport`
- `CashflowImpact`
- `TaxAssumptionSet`
- `DoNothingBaseline`
- `ScenarioComparison`

Output should be state change, risk change, cash change, concentration change,
loss assumptions, and data gaps across A/B/C options.

## L5 — Paper Validation Runtime

Goal: validate reviewed plans in isolated paper state.

Runtime v0 exists through:

- `PaperOrderTicketCandidate`
- `PaperExecutionReceipt`
- `PaperAccount`
- `PaperPosition`

Missing loop artifacts:

- `PaperPerformanceReview`
- `PaperValidationSession`
- `ScenarioVsPaperComparison`
- `PaperPnLSeries`
- `PaperRiskDrift`
- `PaperLessonCandidate`

Target loop:

```text
TradePlanCandidate
-> PaperOrderTicketCandidate
-> PaperExecutionReceipt
-> PaperAccount / PaperPosition
-> PaperPerformanceReview
-> Lesson / RuleCandidate
```

The point is to validate judgment, assumptions, risk estimates, and behavior,
not to create simulated-trading theater.

## L6 — Agent Task Runtime

Goal: make agents controlled financial task runners rather than chat boxes.

Target artifacts:

- `AgentTask`
- `AgentPlan`
- `AgentStep`
- `AgentToolRun`
- `AgentArtifact`
- `AgentTrace`
- `AgentCheckpoint`
- `HumanHandoff`
- `AgentEvaluation`

Example workflow:

```text
Task: analyze whether to reduce single-stock concentration

1. Read current holdings.
2. Read risk exposure.
3. Pull historical volatility and drawdown.
4. Generate three what-if scenarios.
5. Generate an evidence pack.
6. Write a ResearchMemo.
7. Generate a TradePlanCandidate.
8. Wait for human review.
9. If allowed, enter paper validation.
10. Feed paper results into review.
```

Agent workflows should have state, tools, handoff, guardrails, sessions, tracing,
human-in-the-loop, and durable execution. A workflow without an artifact cannot
be reviewed or learned from.

## L7 — Cockpit / Frontend Workbench

Goal: make FinHarness usable without reading receipt files.

Current tabs: Overview, Exposure, Policy, Proposals, Timeline, Retrospective, Compare, Data Trust.

Data Trust tab (shipped #107) shows: Summary, Data Catalog, Quality Reports, Data Gaps.

Target pages beyond current cockpit:

1. Research Workspace
2. Scenarios
3. Paper Validation Review
4. Agent Tasks
5. Settings / Configuration

The short-term UI can stay vanilla while the information architecture is
validated. A typed frontend stack should wait until the API shape stabilizes.

## L8 — Review / Learning / Governance

Goal: keep the system auditable and improving.

Owns:

- receipt
- attestation
- review
- lesson
- rule candidate
- policy update
- risk register
- audit trail
- permission boundary

This layer is still essential, but it is a system property. It should support
the workbench rather than replace the workbench.

## Immediate Roadmap

Execution discipline is defined in the [Operating Model](../engineering/operating-model.md):
each capability slice should have shaping, an RFC/pitch, architecture review,
capability-specific verification, product surface review, release decision, and
retrospective when needed.

The next PR sequence should be:

```text
PR 103: docs: reframe FinHarness as capital workbench roadmap
PR 104: data: add DataSourceRegistry and DataCatalog
PR 105: data: add DataQualityReport and freshness policy
PR 106: api: expose data catalog and data gaps
PR 107: cockpit: add Data Catalog / Data Gaps page
PR 108: research: add EvidencePack and ResearchMemo
PR 109: cockpit: add Research workspace v1
PR 110: scenario: add Scenario and WhatIfRun
PR 111: scenario: add PortfolioDelta and ScenarioComparison
PR 112: paper: add PaperPerformanceReview and scenario-vs-paper comparison
PR 113: agent: add AgentTask / AgentStep / AgentArtifact
PR 114: agent: add ResearchBriefTask workflow
PR 115: cockpit: add Agent Task timeline
```

Each PR should be judged by what the user can see, compare, validate, understand,
or learn afterward.
