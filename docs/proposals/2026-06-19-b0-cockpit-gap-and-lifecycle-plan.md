# B0 Cockpit Gap And Lifecycle Plan

Status: draft
Date: 2026-06-19
Scope: compare the pasted "FinHarness 从零实现指南" with the current local repo,
then define the next execution path from goal discovery to operation.

This is a planning artifact. It does not authorize new dependencies, live
trading, broker writes, ceiling increases, or compliance claims.

## A / B / C / R

A:
- Current repo already has a locked product north star for B0 personal financial
  situational awareness.
- Current repo has Python state core, FastAPI state/proposal routes, ten-layer
  LangGraph workflows, risk/execution guards, receipts, governance dashboards,
  and 420 passing unit tests.
- Current repo now has a static same-origin cockpit MVP; it still lacks browser
  E2E and visual regression coverage.

B:
- FinHarness should become a local-first personal financial cockpit: assets,
  exposures, changes, external events, proposals, brakes, and decision history
  visible in 5-10 minutes.
- Heavy domain work should be adopted from mature projects. Local code should
  stay thin: adapters, guards, receipts, workflows, lineage, and tests.

C:
- Use this document as the execution spine for the next slice.
- Close stale documentation first, then expose a read-only product BFF, then add
  frontend cockpit views, then deepen personal finance state with mature ledger
  or budgeting tools.

R:
- Evidence collected: `task --list`, `task wheels:check` (historical project
  task name; see `docs/reference/glossary.md`), `task status`,
  `task test`, source reads under `src/finharness/api`,
  `src/finharness/statecore`, `docs/product-north-star.md`,
  `docs/architecture/module-map.md`, and the pasted guide.
- Verification result: `task test` ran 420 tests and passed.

## Current Local State

Already present:
- Product doctrine: `docs/product-north-star.md`, README, AGENTS, ADRs.
- State core: `Account`, `Position`, `Snapshot`, `ReceiptIndex`, `Proposal`,
  `Attestation` in SQLite/SQLModel.
- API: existing read/proposal surface exposes state, positions, snapshots, diff,
  individual receipt lookup, proposal creation, and human attestation.
- Workflows: daily evidence, daily change brief, market cockpit, ten-layer chain,
  proposal, risk gate, execution, post-trade, lesson and rule-change loops.
- Controls: authorization, restricted symbols, effective ceilings, market access
  ledger, OKX live gate, control-owner certification, terminology lint.
- Mature third-party libraries: vectorbt, Backtrader, NautilusTrader,
  Riskfolio-Lib, QuantStats, pandas-ta, TA-Lib, yfinance, LangGraph,
  OpenAI Agents SDK, promptfoo, DeepEval.

Important drift:
- `docs/architecture/industry-benchmark/03-gap-register-codex.md` still says
  there is no backend API. That was true for the 2026-06-15 analysis, but is no
  longer current.
- `docs/notes/adopt-not-invent-trading-stack.md` still contains Rust-first
  language even though the 2026-06-13 ADR superseded it with pragmatism-first.

## Missing Parts Against The Guide

| Guide area | Local state | Gap | Debt |
| --- | --- | --- | --- |
| L0 Product Doctrine | Mostly present | Stale Rust-first note can mislead implementation | A1 |
| L1 Frontend Cockpit | Static MVP built | Overview / Proposals / Timeline exist under `/cockpit/`; no browser E2E or visual regression yet | A3 |
| L2 API / BFF | P0 endpoints built | Product-shaped read endpoints exist; BFF remains thin and local-only | A2 |
| L3 Daily Brief Workflow | Partial | Daily change brief and market cockpit exist, but no unified user-facing brief API combining portfolio, market, events, risks, proposals | A3 |
| L4 Domain Core | Strong for trading/research controls | No first-class `Decision`, `Evidence`, `RiskState`, `ControlLimit`, `Exposure` state tables yet | A3 |
| L5 State Core | Partial | Accounts/positions/snapshots/proposals exist; personal-finance export CSV can mirror typed rows for holdings, liabilities, goals, cashflows, tax events, insurance, and documents | A3 |
| L6 Evidence Store | Strong receipts | Receipt list/timeline product view exists in P0 API/UI; receipt drill-down remains shallow | A2 |
| L7 AI Runtime | Partial | LLM is mostly generator seat; no scheduled product brief/proposal/lesson runtime surfaced through cockpit | A3 |
| L8 Quant & Analytics | Strongest around investment research | Personal-finance exposure map is thin: sector, currency, rate sensitivity, cash buffer, tax windows | A3/A4 |
| L9 Integrations | Market/broker-adjacent partial | Portfolio/account aggregation is shallow; OpenBB is optional-missing locally | A4 |
| L10 Governance/Security | Strong | Product-level controls status view exists; incident linkage remains shallow | A2 |
| L11 Testing/Ops/Docs | Strong backend tests | Static frontend service and JS syntax checked; API `/health` and trace header exist; no browser E2E or OTel/OpenLineage export | A3/A4 |

## Adopt, Do Not Invent Map

| Domain | Adopt first | Local FinHarness role | Build only if |
| --- | --- | --- | --- |
| Market/reference data | yfinance now; OpenBB when package adoption is approved | Normalize, quality label, source refs, receipts | Provider output cannot express needed lineage |
| Indicators/features | TA-Lib, pandas-ta, vectorbt indicators | Feature naming, non-advice boundary, receipts | A feature is genuinely FinHarness-specific governance metadata |
| Research/backtests | vectorbt, Backtrader, NautilusTrader | Parameter evidence, validation ladder, no execution authority | A mature engine cannot expose needed evidence shape |
| Portfolio construction | Riskfolio-Lib; QuantStats for reporting | Requested weight/risk evidence only | The local piece is a guard or receipt, not optimization |
| Personal ledger/accounting | Beancount/Fava-style normalized CSV export first; Actual Budget or Firefly III remain later candidates | Read-only export adapter into state core; do not parse ledgers locally | A mature export cannot cover a required state shape |
| Broker/venue | Official broker SDKs/CLIs; CCXT only for read/public multi-exchange where appropriate | Thin adapters, allowlists, gates, receipts | Official tooling lacks a read-only surface needed for evidence |
| Workflow orchestration | LangGraph | Durable workflow state and gates | A workflow is trivial deterministic code |
| Agent runtime | OpenAI Agents SDK behind local tool boundaries | Tool exposure, traces, non-authority output | Provider-specific feature is needed and isolated |
| Data quality | Pandera | Contract, verdict, limitation disclosure | Schema semantics are project-specific |
| Observability | OpenTelemetry later | Trace IDs that index receipts | Receipts alone are enough for current single-user CLI phase |
| Lineage | OpenLineage later | Export receipt lineage, not replace receipts | External consumers need standardized lineage |
| Security scans | gitleaks, Trivy, pip-audit | Aggregate results, redaction, fail-closed gates | A checker cannot express FinHarness-specific safety invariant |

## Lifecycle Execution Path

### 1. 目标发现

Goal: B0 personal financial situational awareness, not alpha discovery and not
automatic trading.

Done when a user can answer: what I hold, what changed, what risks rose, what
needs review, what is blocked, and what past decisions taught me.

### 2. 需求定义

P0 requirements:
- Read-only dashboard summary.
- Proposal review queue and detail.
- Timeline of receipts, proposals, attestations, blocked reasons, lessons.
- No order, transfer, raise-ceiling, auto-trade, or execution endpoint.
- Every product view shows non-claims and `execution_allowed=false`.

P1 requirements:
- Portfolio/account read model with exposures.
- Personal finance state extensions: cash, liabilities, goals, cashflow,
  taxes, insurance, documents.
- Mature personal-finance adapter decision: Beancount/Fava vs Actual vs Firefly.

### 3. 架构设计

Selected architecture:
- State core remains SQLite + receipts as source evidence.
- API becomes a product BFF over existing state, receipts, and workflows.
- Frontend is a read/review cockpit over the BFF.
- Heavy finance/accounting engines are adopted behind adapters.

Rejected:
- Direct frontend execution triggers.
- Homemade accounting, optimizer, broker, OMS, or backtest engines.
- Governance-only expansion that does not improve B0 user awareness.

### 4. 任务拆分

P0.1: Correct stale adopt-not-invent docs. Completed in this slice.

P0.2: Add product read endpoints:
- `GET /dashboard/summary`
- `GET /brief/latest`
- `GET /proposals`
- `GET /proposals/{id}`
- `GET /receipts`
- `GET /timeline`
- `GET /controls/status`
- `GET /controls/limits`

Completed in this slice through `src/finharness/api/routes_cockpit.py` and
`src/finharness/api/routes_proposals.py`.

P0.3: Add API tests proving:
- no forbidden execution paths exist;
- proposal approval is not execution authorization;
- timeline is read-only;
- dashboard summary carries non-claims.

Completed in this slice in `tests/test_statecore_api.py`.

P0.4: Build frontend MVP only after P0.2/P0.3:
- Overview
- Proposals
- Timeline

Completed in this slice as a static same-origin cockpit under `frontend/`,
served by FastAPI at `/cockpit/`.

P1.1: Choose mature personal-finance source of truth:
- Beancount/Fava if plain-text accounting and reviewable git diffs are primary;
- Actual Budget if budgeting UX and local-first transaction workflow are primary;
- Firefly III if self-hosted transaction management API is primary.

Completed in this slice for the first adapter path: use Beancount/Fava-style
normalized CSV exports as the read-only boundary. FinHarness does not parse
`.bean` files and did not add a Beancount/Fava dependency without approval.

P1.2: Add read-only adapter into state core, not a replacement for receipts.

Completed in this slice through `src/finharness/personal_finance.py`,
`scripts/import_personal_finance_export.py`, and `task personal-finance:import`.

P1.3: Extend state core for personal-finance cockpit context:
- `Liability`
- `FinancialGoal`
- `CashflowEvent`
- `TaxEvent`
- `InsurancePolicy`
- `DocumentRef`

Completed in the follow-up slice with typed `record_type` CSV ingestion and
read-only API routes for each table.

### 5. 实现

Implemented in this slice:
- Wrote this lifecycle plan.
- Corrected stale Rust-first language.
- Added P0 product BFF endpoints and proposal read queue/detail.
- Added static B0 cockpit frontend served at `/cockpit/`.
- Added API/static frontend tests and JS syntax verification.

Next implementation slice:
- Add first-class personal-finance state extensions only where the upstream
  export cannot express needed B0 state: liabilities, goals, cashflow, tax
  events, insurance, and document refs. Completed in the follow-up slice.
- Add browser/E2E checks for the static cockpit before treating the UI as more
  than a local MVP.

### 6. 评审

Review gates:
- Does any new endpoint imply execution authority?
- Does any new model confuse evidence with truth?
- Does any new dependency duplicate a mature adopted tool?
- Does the surface serve B0, or only add governance ceremony?

### 7. 测试

Smallest checks:
- `task test` after API/model changes.
- `task lint` after docs/code edits.

Broader checks before release:
- `task check`
- `task hardening:gate` when security-sensitive paths change.

### 8. 集成

Integration order:
1. State-core read model.
2. API BFF.
3. Markdown/JSON cockpit compatibility.
4. Frontend read + attest cockpit (reads plus governed human attestation only).
5. Mature personal-finance adapters.

### 9. 发布

Release criteria:
- All P0 endpoints documented in OpenAPI.
- Tests prove no order/transfer/execution/ceiling endpoint exists.
- README/docs point users to the cockpit path.
- Release preflight stays green.

### 10. 运行

Runtime posture:
- Local-first.
- Read-mostly.
- `execution_allowed=false` by default.
- AI drafts only: analysis, proposals, lesson candidates.

### 11. 观测

Near-term:
- Structured request logs already exist.
- API `/health` and `X-FinHarness-Trace-Id` request/response headers exist.

Later:
- Adopt OpenTelemetry for traces/metrics.
- Adopt OpenLineage-compatible export for dataset/job lineage.

### 12. 事故处理

Incident triggers:
- Any unintended live mutation path.
- Any credential or account-data exposure.
- Any API/UI phrase that implies AI authorization.
- Receipt write/index failure hiding evidence.
- Data corruption in state core.

Runbook:
- Use existing `docs/security/security-response-runbook.md`.
- Write an incident/review receipt.
- Fail closed before adding new automation.

### 13. 复盘迭代

After each slice:
- Record what changed, what evidence exists, what surprised us, and what should
  change next.
- Promote lessons to rules only through human-reviewed lineage.
- Keep the product question visible: did this make the user's financial state
  clearer, or only make the harness look more governed?

## Non-Claims

- This plan does not close the listed gaps.
- This plan does not prove investment alpha, broker correctness, tax correctness,
  security compliance, or production readiness.
- External project maturity is a selection input, not a claim that FinHarness has
  integrated or validated those projects.

## External References

Primary project sources checked for the adopt-first map:
- OpenBB: https://github.com/OpenBB-finance/OpenBB
- vectorbt: https://github.com/polakowo/vectorbt
- NautilusTrader: https://github.com/nautechsystems/nautilus_trader
- Riskfolio-Lib: https://github.com/dcajasn/Riskfolio-Lib
- Beancount: https://github.com/beancount/beancount
- Fava: https://github.com/beancount/fava
- Actual Budget: https://github.com/actualbudget/actual
- Firefly III: https://github.com/firefly-iii/firefly-iii
- OpenTelemetry Python: https://github.com/open-telemetry/opentelemetry-python
- OpenLineage: https://github.com/OpenLineage/OpenLineage

## Follow-Up Slice 2026-06-19 (Review Fixes)

A review of the first slice found two verified defects and three quality gaps.
This follow-up closed them:

- P1 (verified fix): the serving engine path (`open_state_core`) did not create
  tables added after a database was first created, so the cockpit dashboard and
  new `/state/*` reads returned 500 (`no such table`) on an existing database.
  Added `ensure_state_core_schema` (idempotent `create_all` of missing tables)
	  and call it on both the lazy-open and injected-engine paths. Repro now returns
	  200. A follow-up SQLite-native `PRAGMA user_version` migration now also rebuilds
	  legacy `positions` money columns as TEXT and adds source columns to
	  personal-finance tables.
- P2 (verified fix): the CSV adapter stamped every import as a `portfolio`
  snapshot, so a liabilities-only later import shadowed the latest holdings and
  zeroed the dashboard's positions. Snapshots are now `kind=portfolio` only when
  positions are present, else `kind=personal_finance`. Repro now keeps holdings.
- Real adapter: added `finharness/beancount_adapter.py` — a direct, read-only
  connection to a real Beancount ledger via `bean-query` (`beanquery`), with
  `task beancount:import`. The earlier "Beancount/Fava-style" CSV label was
  corrected: that path is a FinHarness-defined import contract, not a real tool
  export.
- Decimal: monetary fields use exact `Decimal`, stored as TEXT (`DecimalText`)
  so SQLite NUMERIC affinity does not round-trip through float. This covers the
  personal-finance models (`Liability`, `FinancialGoal`, `CashflowEvent`,
  `TaxEvent`, `InsurancePolicy`) and `Position` (quantity/market value/cost
  basis). `Position` was the larger migration: it is read from the DB as
  `Decimal`, `diff.py`/`observations.py` aggregate exposures and totals in
  `Decimal`, and only the diff result / observation `numbers` / receipts / API
  responses present `float` (the JSON-evidence layer stays numeric and
  backward-compatible). A regression test stores `0.1 + 0.2` positions and
  asserts the read-back sum is exactly `Decimal("0.3")`.
- Refactors: CSV row ingestion uses a per-type builder dispatch table instead of
  a long if/elif chain; the duplicated `/state/*` list endpoints share one
  `_list_all` helper.

Evidence from Claude's slice claimed `task check` green (ruff, mypy 134 files,
unit tests, properties, rules audit, experiments, eval smoke), P1/P2 repros
re-run, and `task beancount:import` mirrored a fixture ledger end-to-end with
`execution_allowed=false`. Current Codex verification must be re-run before
closing the active goal.

New dependencies introduced by Claude's slice: `beancount`, `beanquery`. They
match the adopt-mature-tools direction, but still need explicit project-owner
acceptance before this branch is treated as dependency-approved.
