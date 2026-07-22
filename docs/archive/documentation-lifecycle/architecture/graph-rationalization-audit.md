# Graph Rationalization Audit

Status: draft v0 (2026-06-23)

Purpose: ask the reverse architecture question: which graphs, workflows, and
support tools still earn their complexity, and which should be kept headless,
downgraded to ordinary commands, archived, or deleted after usage evidence.

This audit is intentionally conservative: it does not delete code. It classifies
the current graph-shaped modules by consumer, product value, and whether the
graph abstraction is earning its keep.

## Thesis

FinHarness needs the evidence system, not graphs everywhere.

Keep graph/workflow machinery where it provides real leverage:

- conditional flow or interrupt semantics
- orchestration across independently useful layers
- explicit evidence lineage across layers
- manual review / fail-closed control points
- reusable headless research workflows

Downgrade graph-shaped modules when they are mostly linear report builders,
thin wrappers, or project-process ceremony. A normal command function plus a
receipt is often a better interface than a LangGraph wrapper.

## Evaluation Rules

Use these rules before adding or keeping a graph:

1. **Consumer rule**: a graph must have at least one real consumer: task, API,
   frontend, CI, golden-path, or documented human operation.
2. **Complexity rule**: if the flow is linear and has no branching, retry,
   interrupt, multi-provider fan-out, or resumable state, prefer a plain
   command/report module.
3. **Product rule**: cockpit-facing work should depend on read models and
   receipts, not on research/workflow graphs directly.
4. **Headless rule**: trading/research graphs may remain, but they should stay
   headless and opt-in.
5. **Deletion rule**: deletion requires a usage audit first. No consumer plus no
   receipt consumption plus no active task equals delete candidate.
6. **Replacement rule**: do not introduce Temporal, Backstage, OPA, or another
   platform until the repo has repeated pain that the simpler Taskfile/Python
   shape cannot handle.

## Current Inventory

### Product-Critical Core (keep)

These are not just scaffolding; deleting them would push complexity back into
multiple callers.

| Asset | Current consumers | Judgment | Reason |
| --- | --- | --- | --- |
| State Core receipts / proposals / attestation / ReviewEvent | API, cockpit, Golden Path, review system | keep | Evidence root and human review ledger. |
| `review_read.py` | proposal timeline, retrospective, compare view | keep | Deep read-model module; good system-first seam. |
| `allocation.py` / `exposure.py` | decisions scan, proposals, cockpit | keep | Turns personal finance state into governed candidates. |
| `research_evidence.py` / `research_enrichment.py` | proposal evidence enrichment, frontend render | keep | Redline contract and optional evidence seam. |
| Golden Path harness | manual demo + CI test | keep | Proves receipt-consumption loop, not just writes. |

### Headless Domain Graphs (keep headless, rationalize later)

These graphs are not current cockpit material, but they represent the trading /
research engine. Keep them opt-in and headless unless a later phase proves
otherwise.

| Graph | Current consumers | Judgment | Notes |
| --- | --- | --- | --- |
| `market_data_graph.py` | task `market-data:graph`, indicator graph, market cockpit | keep headless | Real adapter/provider boundary. |
| `indicator_graph.py` | task, daily evidence, market cockpit | keep headless | Derived evidence layer; may later become plain feature command if too linear. |
| `events_graph.py` | task `events:snapshot`, interpretation, daily evidence | keep headless | Event evidence layer. |
| `interpretation_graph.py` | task, hypotheses, daily evidence | keep headless | Source-backed interpretation layer. |
| `hypotheses_graph.py` | task, validation | keep headless | Candidate hypothesis layer. |
| `validation_graph.py` | task, proposal | keep headless | Research validation boundary; important non-claim discipline. |
| `proposal_graph.py` | task, risk gate | keep headless | Trading/research proposal path, separate from personal finance proposals. |
| `risk_gate_graph.py` | task, execution, interactive tests | keep | This earns graph shape because it has gates and interrupt semantics. |
| `execution_graph.py` | task, post-trade | keep headless | Safety-critical; keep isolated from cockpit. |
| `post_trade_graph.py` | task | keep headless | Review/reconciliation layer; candidate for later simplification if linear. |
| `ten_layer_graph.py` | task `ten-layer:graph` | keep as orchestrator | Its job is orchestration/freshness across layers, not product UI. |

### Support / Governance Graphs (review for downgrade)

These are most likely to be over-structured. They are useful, but may not need
to be graphs.

| Graph / tool | Current consumers | Judgment | Better shape if downgraded |
| --- | --- | --- | --- |
| `repo_intelligence_graph.py` | task `repo:intelligence`, quality governance, dashboard | downgrade candidate | Plain `repo_intelligence_report(root, changed_files)` command returning DTO + receipt. |
| `quality_governance_graph.py` | task `quality:governance`, release preflight, integration tests | downgrade candidate | Plain `quality_governance_report(checks, repo_intelligence)` with explicit input evidence. |
| `release_preflight_graph.py` | task `release:preflight`, governance dashboard | downgrade candidate | Plain `release_preflight_report(quality, supply_chain)`; graph shape not obviously earning keep. |
| `governance_dashboard_graph.py` | task `governance:dashboard` | downgrade candidate | Plain dashboard report writer; likely linear. |
| `engineering_delivery_graph.py` | task `workflow:engineering-delivery`, docs | archive/downgrade candidate | EOS docs + gate receipts now carry most of this value. Keep only if humans actively use it. |
| `cognitive_graph.py` | task `workflow:cognitive`, docs | archive/downgrade candidate | Useful as idea-capture history, but likely not needed in core engineering path. |
| `daily_evidence_graph.py` | task `workflow:daily-evidence`, tests | keep or downgrade after review | Bundles multiple evidence layers; may earn orchestration shape if used operationally. |

### Already Removed / Do Not Resurrect

`finance_graph.py` and `trade_graph.py` were deleted in the repo prune. The graph
registry records their historical/archived status. Do not re-expose them through
Taskfile, active scripts, tests, or cockpit.

## Deletion Test Findings

### Graphs likely earning their keep

- `risk_gate_graph.py`: has explicit gates, interactive/interrupt path, and
  safety semantics. Deleting it would scatter gate logic.
- `ten_layer_graph.py`: coordinates freshness and reuse across ten evidence
  layers. Deleting it would scatter orchestration decisions.
- domain layer graphs from market data through post-trade: keep headless for
  now because they encode an institutional research chain, but do not promote
  them into personal cockpit.

### Graphs likely too shallow

- `repo_intelligence_graph.py`
- `quality_governance_graph.py`
- `release_preflight_graph.py`
- `governance_dashboard_graph.py`

These appear to be report-building and receipt-writing flows. If deleting the
LangGraph wrapper would leave one clear function with the same inputs and
outputs, the graph interface is probably not paying rent.

### Graphs with unclear active value

- `engineering_delivery_graph.py`
- `cognitive_graph.py`

They may be valuable as project-memory tools, but their value should be proven
by actual use. If humans do not run them and downstream systems do not consume
their receipts, archive or downgrade them.

## Recommended Work Plan

### R0: No Code Deletion Yet

Do not delete graphs based on this audit alone. First collect usage evidence:

- Taskfile entry exists?
- CI/default check consumes it?
- Cockpit/API consumes it?
- Other module imports it?
- Receipt usage audit consumes its outputs?
- Docs reference it as active operational entrypoint?
- Golden Path or another E2E path exercises it?

### R1: Add a Graph Registry

Create a small static registry, similar in spirit to the policy registry:

```text
id
module
task
consumer_class: product | ci | headless | docs_only | historical
graph_needed_reason: branching | interrupt | orchestration | lineage | none
status: keep | headless_keep | downgrade_candidate | archive_candidate | delete_candidate
owner
review_due
```

This turns the audit from prose into a reviewable artifact.

#### R1 Graph Registry — implemented

The registry now lives at `tests/_graph_registry.py` (one `GraphAsset` per graph:
`id / module / task / consumer_class / graph_needed_reason / status / owner / review_due /
evidence`), discoverable via `task governance:graphs`, and guarded by
`tests/test_graph_registry.py`.

**The registry is a judgment artifact, not a deletion authorization.** A
`downgrade_candidate` / `archive_candidate` / `delete_candidate` status records a decision
to make *later*, after a usage audit (R0/R5). R1 changes no graph behavior, deletes
nothing, and downgrades nothing. The guard tests enforce that the three pilot support
graphs (`repo_intelligence`, `quality_governance`, `release_preflight`) stay
`downgrade_candidate`, and that every source `*_graph.py` is registered (no graph can enter
unclassified).

**Correction to earlier path claims:** `finance_graph` / `trade_graph` are recorded
as `historical` / `archived`, but there is no `docs/archive/legacy-graphs/`
directory. Those files were deleted in the repo prune (commit `2166bba`), not
archived to disk. The registry records the true state (no module file).

### R2: Downgrade One Low-Risk Support Graph

Use `repo_intelligence_graph.py` as the pilot. It recently caused real runtime
cost, and its value is a report/receipt, not graph semantics.

Target shape:

```text
repo_intelligence_report(root, changed_files) -> DTO
record_repo_intelligence_report(report, receipt_root) -> receipt
scripts/run_repo_intelligence_graph.py remains as compatibility adapter
```

If this reduces complexity without losing tests, repeat for quality governance
and release preflight.

### R3: Keep Product Path Graph-Free

New cockpit features should depend on:

- State Core
- Review System read models
- Decision Workflow
- Research Evidence attachments
- receipts / source_refs

They should not call headless trading/research graphs directly.

### R4: Preserve Headless Engine Without Making It Product Surface

The ten-layer engine can remain as an optional research lab. Its contract should
be "produce evidence receipts", not "drive the personal finance cockpit".

### R5: Delete Only After Receipt Usage Audit

Before deleting any graph/script:

1. run receipt usage audit
2. confirm no task/CI/API/frontend consumer
3. mark archive/delete decision in this document or an ADR
4. remove task/docs references in the same PR

## Industry Alignment

This moves the project closer to mature practice:

- default path stays short and fast
- workflow engine is used only where it earns the complexity
- product code consumes stable read models, not orchestration internals
- evidence/receipt chains remain the durable core
- deletion is evidence-based, not taste-based

In short: keep the evidence system; stop treating every report as a graph.
