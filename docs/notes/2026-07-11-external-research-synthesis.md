# FinHarness 外部调研综合与代码校准

Date: 2026-07-11
Status: current research note
Source: nine external audit and ecosystem reports supplied for the 2026-07-11 review
Repository baseline: `main` at `8a313e8`, plus the audited Wave 3 corrections in the current worktree

## 1. Purpose and evidence rule

This note preserves the durable content of nine external reports and separates
three different things:

1. claims that current FinHarness code proves;
2. useful recommendations that still require implementation;
3. claims made stale by later repository changes or contradicted by direct
   execution.

The reports are research inputs, not repository truth. Most were static audits
against commits between `8161a1b` and `a3be01b`, and explicitly did not run the
full test suite. Current code, executable probes, migrations, API contracts, and
behavioral tests take precedence.

The nine reports covered:

| Report | Primary subject |
| --- | --- |
| 01 | Product positioning, target users, and current user journeys |
| 02 | Data architecture, StateCore, Capital Map, identity, time, currency, and receipts |
| 03 | IPS, Proposal, Review, Authority, Decision, and Learning lifecycle |
| 04 | Agent runtime, tools, cognition, authority, and 15-contract closure gate |
| 05 | Architecture, dependencies, tests, CI, debt, and repository governance |
| 06 | Research, financial risk, Scenario, and paper-performance validity |
| 07 | Execution Kernel, simulated-only boundary, capabilities, and legacy migration |
| 08 | API, Cockpit, frontend contracts, trust display, and user experience |
| 09 | Competitors, open-source ecosystem, build/buy/integrate, regulation, and product evidence |

## 2. Combined strategic conclusion

The most defensible current product category is:

> **Currently, a local-owned Personal Capital Review and Decision Ledger;
> ultimately, an Agent-Native Personal Capital Operating System.**

The north star is not a classical product with an Agent explanation layer. The
Human Principal owns constitutional goals and delegation; the Capital Agent
eventually owns the objective loop; FinHarness is the admissibility/recovery
Harness; deterministic engines guarantee effect correctness. The repository
already has a real chain from
imported capital state through deterministic risk candidates, do-nothing
options, human review, receipts, and retrospective records. It does not yet
provide trustworthy multi-currency capital truth, numerical scenario
comparison, decision-version integrity, outcome attribution, or a closed Agent
work cycle.

The first product job should be **Material Decision Review with Scheduled
Retrospective**. Home/Today is the intake and prioritization surface for that
job, not a daily-engagement goal by itself:

```text
trusted capital state
-> material change or review trigger
-> evidence + counter-evidence + do-nothing
-> deterministic scenario comparison
-> human decision of record
-> scheduled outcome review
-> lesson proposal
-> human-confirmed policy update
```

This resolves a difference between the reports. Daily Brief is the strongest
existing awareness entry, but external product evidence does not support daily
use as the core value proposition. Material decisions and 30/90/180-day reviews
are the more credible retention loop.

## 3. What FinHarness genuinely has today

### 3.1 Proven strengths

- StateCore is a real local query mirror with SQLite transactions, WAL,
  migrations, Decimal-backed money columns, and receipt provenance.
- Capital Map exposes positions, liabilities, cashflow, concentration, cash
  runway, interest burden, obligations, and explicit data gaps.
- Proposal review is the strongest complete user path: trigger evidence,
  alternatives, do-nothing, risks, decision scaffold, counter-evidence,
  revision, attestation, review events, and timeline.
- IPS numeric thresholds change deterministic detector behavior.
- High-risk approval requires counter-evidence.
- Execution Kernel has a real classical lifecycle through simulated submit and
  ExecutionReport, with service/API capability gates.
- Agent tools, context projections, evidence envelopes, evaluators, receipts,
  search, playbooks, memory drafts, and review-workspace components exist.
- Current Agent closure truth is **4/15 passing, 11 open**.
- Dependency ownership is now explicit and clean-install probes exist for
  base, data, research, agent, and eval profiles.
- Paper legacy import and broker-registry isolation now have corrected
  executable boundaries.

### 3.2 Accurate current product boundary

FinHarness can reliably help an operator answer:

1. What state has been imported?
2. What obvious capital risks or data gaps need review?
3. What alternatives, including no action, should be considered?
4. What decision was recorded and why?

It cannot yet reliably answer:

1. What is my current net worth across currencies and valuation times?
2. Which option has the best quantified consequences under explicit
   assumptions?
3. What exactly did an Agent observe, decide, persist, and hand off?
4. Did the selected decision outperform doing nothing, and why?
5. Did a promoted lesson actually change a later decision?

## 4. Findings that remain true after code verification

### 4.1 Repository evidence has a false-green gap

`Taskfile.yml` runs `python -m unittest discover -s tests`. Two known pytest-only
files demonstrate the gap:

```text
PYTHONPATH=src uv run python -m unittest \
  tests.test_agent_work_loop_models tests.test_agent_cognition_flow
-> Ran 0 tests

PYTHONPATH=src uv run pytest --collect-only -q \
  tests/test_agent_work_loop_models.py tests/test_agent_cognition_flow.py
-> 38 tests collected
```

The 2026-07-11 full `check:ci` passed 954 unittest-discovered tests and 8 graph
integration tests, but that result does not cover these 38 tests. Test-runner
alignment is therefore the first repository debt, even though it is not in the
current ten-entry debt register.

### 4.2 StateCore is not yet a trustworthy capital-fact layer

Current `Position` stores quantity, market value, cost basis, symbol, and refs,
but not instrument identity, valuation currency, unit price, valuation time,
price source, or FX evidence. `compute_exposure()` still sums all position
market values and liabilities before resolving a guessed base currency. A
mixed-currency data gap does not stop the unified net-worth headline.

Time semantics also remain collapsed across effective, valued, observed,
ingested, and receipt-created times. Personal-capital freshness/readiness is
not a mandatory gate for Daily Brief, Scenario, or Agent context.

### 4.3 Human decisions are not bound to proposal versions

`Attestation` references only `proposal_id`. It does not bind the current
proposal receipt, content hash, or version identity. A later scaffold revision
does not supersede the earlier decision, while queue projections treat any
attestation as reviewed. This is the most important integrity defect in the
decision ledger.

Queue and risk findings are also mostly read-model metadata. The attestation
command enforces the high-risk counter-evidence rule, but it does not consume a
single canonical readiness report covering data, policy, source, and evidence
blocks.

### 4.4 The Agent runtime is still split into two unconnected paths

The real model path can select tools, while the deterministic work orchestrator
has receipts and evaluation components. They are not one lifecycle. Current
`run_agent_work_loop()` still:

- iterates caller-preselected tool names;
- dispatches every tool with `arguments={}`;
- creates no typed observation consumed by the next decision;
- builds generic option/plan text unrelated to tool result content;
- stores tool names as `tool_result_refs`;
- leaves `agent_run_receipt_ref` and `review_workspace_ref` empty;
- returns an in-memory WorkResult.

The 4/15 result is the correct baseline; the later DeepSeek 7/15 claim used
standalone fakes that were never injected into production execution.

### 4.5 Execution is classical but not yet a safe monotonic state machine

The current official adapter is simulated and there is no current live broker
implementation. However:

- broker registration trusts a duck-typed `adapter_kind="simulated"` string;
- the global registry is mutable without a dedicated capability;
- staging selects an unordered `.first()` PreTradeCheck and ApprovalRecord;
- approval is not bound to an immutable draft version or check hash;
- no-adapter submit records a submitted lifecycle and synthetic acknowledgement;
- adapter failure can occur after submitted state has been written;
- report, position-delta, and reconciliation writes are not one command chain;
- legacy ActionIntent and PaperValidation write routes remain registered.

“Official implementation is simulated” is true. “The process is mechanically
incapable of a network broker side effect” is not proven.

### 4.6 Cockpit presents engineering state more clearly than user decisions

Proposal Review is useful, but Overview and Exposure hide valuation time,
currency, freshness, and source boundaries next to exact-looking numbers.
Review Queue and Risk Register exist as APIs but are not the main UI entry.

Execution UI is currently misleading: it calls a missing OrderDraft GET route,
uses an order receipt ref as an execution-report ID, bypasses the shared API
helper, catches failures as empty data, and shows no unavoidable simulated-only
state. Controls still default to reporting that execution endpoints are absent
even though the router is mounted.

### 4.7 Repository architecture and truth governance remain incomplete

`repo_intelligence.py` produces import nodes and edges but no SCC/cycle result,
layer matrix, or CI violation. The canonical debt register says 10/10 resolved,
but its schema does not yet include the verified test-runner, data-truth,
decision-version, API-contract, or execution-state debts. “All registered debts
are resolved” must not be interpreted as “the repository has no material debt.”

Several current planning documents also retain superseded product and PR
sequences. A machine catalog can be canonical for lifecycle labels without
being a complete product or architecture truth source.

## 5. Findings corrected by the current worktree

The following report findings were valid against their audit commits but are
not current gaps after the Wave 3 review corrections:

| Earlier finding | Current correction |
| --- | --- |
| All Python dependencies are in base and optional groups are empty | Dependencies are separated into base/data/research/agent/eval, with intentional empty paper/security groups. |
| Base API implicitly imports yfinance/Nautilus through `market_data.ROOT` | Lightweight `project_paths.py` removes path-only imports from market-data consumers; base API is probed without optional wheels. |
| Group probes only import package names | Probes now import maintained FinHarness consumers and real API surfaces. |
| Clean dependency profiles are not in CI | `.github/workflows/dependency-profiles.yml` rebuilds all five profiles. |
| Paper AST boundary proves network isolation | The original graph was vacuous; it is now canonicalized, preserves external leaf imports, resolves relative imports, and fails missing roots. |
| Agent Work Loop behavioral acceptance is 7/15 | The added fakes did not exercise production; the truthful baseline is restored to 4/15. |
| pandas-ta, Plotly, and TA-Lib remain unused direct dependencies | They were removed in DEPS-02D. |

Dependency grouping is closed as an ownership problem, not as a final strategic
dependency decision. Backtrader, vectorbt, Riskfolio, LangGraph, DeepEval, and
NautilusTrader still require evidence-based keep/remove reviews when their
actual product slices are selected.

## 6. External market and ecosystem lessons

### 6.1 The category is relatively sparse, not empty

ProjectionLab, TraderSync, Origin, planning tools, trackers, and robo-advisors
already cover parts of scenario comparison, plan-versus-actual review, AI
explanation, and automated allocation. FinHarness cannot claim that decision
loops do not exist. Its narrower hypothesis is:

> Cross-domain personal-capital state plus evidence, counter-evidence,
> human-controlled decisions, outcome review, and rule history may form a useful
> long-term decision archive for self-directed users.

That hypothesis still needs user evidence: completion rate, review return rate,
decision-change rate, rule adoption, data-maintenance burden, retention, and
willingness to pay.

### 6.2 Build / adopt / integrate boundary

Build locally:

- canonical capital semantics and readiness;
- versioned DecisionCase/DecisionRecord;
- evidence relationships, authority boundaries, review, and learning;
- scenario contracts and comparison semantics;
- receipt integrity and human-readable lineage.

Adopt behind thin ports:

- Pandas/Pandera for tabular mechanics and validation;
- QuantStats or one characterized analytics implementation for mature metrics;
- OpenTelemetry for technical traces;
- CodeQL, secret scanning, Trivy, SBOM, and release checksums for supply-chain
  controls.

Integrate, do not own:

- account and broker aggregation;
- licensed market/reference data;
- model providers;
- external ledgers such as Beancount.

Defer until explicit triggers exist:

- Polars, Temporal, OPA, Cedar, OpenLineage, MLflow, MCP server;
- LangGraph as a second canonical workflow state;
- NautilusTrader as a product execution engine;
- live broker credentials, funded accounts, and automated allocation;
- sessions, resume, scheduling, subagents, and multi-agent delegation.

### 6.3 Data, regulation, and privacy dominate formula novelty

Financial formulas are widely available. Harder constraints are data licenses,
point-in-time correctness, user authorization, privacy, model responsibility,
and the regulatory boundary around personalized or continuously managed
advice. Receipts prove integrity and provenance; they do not prove correctness,
authority, or user understanding.

## 7. Responsibility split

| Work | Classical software | Agentic software | Human authority |
| --- | --- | --- | --- |
| Capital facts, identity, time, currency, migrations | Owns | Reads bounded projection | Corrects/attests sources |
| Deterministic risk and scenario calculations | Owns | Selects questions and explains results | Chooses assumptions |
| Tool schema, capability, budget, idempotency, stop/retry | Owns | Proposes typed action | Grants/revokes scope |
| Evidence search and interpretation | Validates refs and policy | Owns candidate search/synthesis/critique | Accepts relevance |
| Proposal and DecisionRecord persistence | Owns invariant and versioning | Drafts options/counterarguments | Accepts/rejects/defers |
| Execution strategy | Enforces mandate and transaction boundary | Increasingly owns whether/when/why to act | Sets mandate and handles escalations |
| Execution effects | Deterministic Kernel owns correctness | Observes reports and replans; never bypasses Kernel | Approves until delegated autonomy gate permits on-loop supervision |
| Outcome attribution | Computes measurements | Drafts explanations and alternatives | Confirms lesson meaning |
| Lesson promotion and effective policy | Resolves/version-controls | Proposes candidate rule | Promotes/reverts |

## 8. Durable decisions from this research

1. Product truth is **Personal Capital Review and Decision Ledger now;
   Agent-Native Personal Capital Operating System as north star**.
2. Primary wedge is **Material Decision Review + Scheduled Retrospective**;
   Today is its intake surface.
3. Repository evidence repair precedes new runtime claims.
4. Trusted capital state and proposal-version binding precede Scenario, Agent
   task productization, or decision-to-execution binding.
5. Deterministic product work does not wait for Agent closure.
6. Agent closure starts with one bounded counter-evidence/review-packet task,
   then advances through an explicit autonomy ladder; the first task is not the
   permanent Agent role.
7. Execution is quarantined and hardened before it is expanded or shown as a
   product capability.
8. No live broker, session, scheduler, subagent, MCP server, or generalized
   authority program is authorized in the current phase. Some may become later
   Harness mechanisms after explicit entry gates; they are not implied by the
   north star alone.

The implementation sequence and per-slice gates are defined in
[`2026-07-11-finharness-evolution-execution-plan.md`](../proposals/2026-07-11-finharness-evolution-execution-plan.md).
