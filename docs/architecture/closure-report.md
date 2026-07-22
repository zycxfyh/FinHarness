# Architecture Closure Report — FinHarness Execution Spine Migration

状态: 2026-07-08
版本: v1

---

## Executive Summary

FinHarness 已完成从 ActionIntent / PaperValidation shadow-execution 架构
到 canonical Execution Spine 架构的迁移。

Execution 现在由 OrderDraft → PreTradeCheck → ApprovalRecord
→ ExecutionOrder → SimulatedBrokerAdapter.submit_order()
→ ExecutionReport → PositionDelta → ReconciliationReport 承载。

旧 ActionIntent / TradePlan / PaperValidation 链已被标记为 legacy，
通过 legacy_bridge.py 分离 execution facts 与 agentic artifacts。

Local task check 报告 845 tests pass。
GitHub Actions 实际状态：fuzz workflow green；security workflow 中
CodeQL/Trivy/Gitleaks green，但 Local verification (Run standard project checks)
仍 failure；browser golden paths 失败（CI-optional，不在 task check 覆盖范围）。

后续工作：bounded engineering debt + CI 信号修复。核心架构迁移已完成，
但 debt paydown 仍在进行中。

---

## Original Problem

旧系统没有真正 execution spine。旧系统用 ActionIntent / AuthorityBinding /
SimulationReport / TradePlanCandidate / CapitalObjectiveFit / ReviewGate /
PaperOrderTicketCandidate 承载 execution 周边语义。

系统大量依赖 not-live / not-order / not-broker / execution_allowed=false
保护性语言。这导致 agentic execution complexity 被错误翻译成
classical object complexity。

核心句:
> 问题不是没有治理；问题是治理对象太多，而真正的 execution entity 太弱。

---

## Architecture Thesis

本轮工作的理论核心: 把 FinHarness 分成三个清晰平面。

**Classical Software Plane**: StateCore models, services, receipts, API routes,
UI surfaces, deterministic lifecycle — 承载事实和状态转移。

**Agentic Software Plane**: context, tool output, skill output, workflow output,
evaluator finding, permission trace, review memo, trace — 承载智能体如何工作。

**Control / Safety Plane**: capabilities, adapter boundary, credential boundary,
no real broker SDK, no external network/venue, simulated-only substrate —
承载权限、安全、隔离、边界。

关键判断规则:
- 长期业务事实进入 classical layer
- agent 工作产物留在 agentic layer
- 真实外部副作用边界进入 control/safety layer

---

## Final Canonical Mainline

```
financial state import
→ proposal / review
→ OrderDraft
→ PreTradeCheck
→ ApprovalRecord
→ ExecutionOrder
→ SimulatedBrokerAdapter.submit_order()
→ ExecutionReport
→ PositionDelta
→ ReconciliationReport
→ retrospective / learning
```

ExecutionEnvironment.LIVE 是合法建模概念。submit_order 是合法命令。
但当前只有 simulated substrate。没有真实 broker SDK。没有真实 credential
loader。没有 funded account path。没有 external venue/network adapter。

---

## Before / After Architecture

**Before**:
```
Proposal → ActionIntent → AuthorityBinding → SimulationReport
→ TradePlanCandidate → CapitalObjectiveFit → TradePlanReviewGate
→ PaperOrderTicketCandidate → PaperValidation
```
问题: execution 没有正面实体；agentic artifacts 被 object 化；
大量 negative protection language 维持边界。

**After**:
```
Proposal / Review → OrderDraft → PreTradeCheck → ApprovalRecord
→ ExecutionOrder → SimulatedBrokerAdapter → ExecutionReport
→ PositionDelta → ReconciliationReport
```
旧链: ActionIntent chain = legacy, PaperValidation = legacy,
PreTradePacket = legacy projection, legacy_bridge.py = migration path.

---

## PR Timeline

| PR | Layer | Purpose |
|---|---|---|
| #114 | taxonomy | abstraction classification |
| #115 | bridge | PreTradePacket legacy projection |
| #116 | schema | 9 execution kernel tables |
| #117 | services | 8 lifecycle services + 9 receipt kinds |
| #118 | adapter | simulated broker + submit command |
| #119 | API | 8 /execution endpoints |
| #120 | cockpit | execution tab |
| #121 | bridge | legacy separation bridge |
| #122 | docs | promote execution mainline |
| #123 | downgrade | legacy route marking |
| #124 | cleanup | stale protection language deletion |
| #125 | ledger | debt paydown plan |
| #126 | CI | flaky freshness test fix |
| #127–#130 | governance | registry alignment + policy update |
| #129 | docs | PreTradePacket downgrade |
| #130 | code | agentic artifact kind taxonomy (comment only; enum not implemented) |
| #131 | debt | final classification + debt ledger |
| #132 | docs | closure truth patch |
| #133 | CI | deterministic freshness test + registry alignment |
| #134 | docs/nav | remove legacy from main docs |
| #135 | ledger | PreTradePacket debt status reconciliation |
| #136 | runtime | legacy response deprecation headers |
| #137 | agentic | AgenticArtifactKind StrEnum |
| #138 | bridge | multi-projection cardinality test |
| #139 | execution | lifecycle state transition hardening |
| #140 | execution | receipt contract — report/order link |
| #141 | boundary | adapter boundary tests |
| #142 | control | ExecutionCapabilities model |
| #143 | control | simulated-only adapter registration policy |
| #144 | registry | substrate semantics (execution_substrate field) |
| #145 | docs | legacy receipt field deprecation |
| #146 | CI | browser golden path tab count fix |
| #147 | CI | deterministic freshness (already fixed #133, ledger closure) |
| #148 | legacy | OpenAPI deprecated + legacy tags |
| #149 | ledger | final debt ledger sweep |
| #150 | execution | no-adapter submit lifecycle completeness |
| #151 | execution | blocked pretrade cannot stage |

---

## What Was Deleted / Downgraded

**Deleted**: stale not-live / not-broker / not-execution documentation,
dead receipt reference rows, duplicate legacy mainline explanations,
execution_allowed=false theology.

**Downgraded**: ActionIntent routes, PaperValidation routes, PreTradePacket,
CapitalObjectiveFit as canonical object candidate, AuthorityBinding as
execution authority object, PaperOrderTicketCandidate as execution substitute.

**Preserved**: historical StateCore readability, legacy receipts,
migration bridge, read compatibility.

---

## Safety / External Side-effect Boundary

The system models execution. The system does not perform real external execution.

Invariants:
- Only SimulatedBrokerAdapter registered
- No real broker SDK
- No credential loader
- No funded account
- No external venue adapter
- No external network execution path
- submit_order targets simulated substrate only

---

## Final Layer Map

```
Classical Software Plane:
  Execution Kernel (OrderDraft → ReconciliationReport)
  StateCore execution models, services, receipts, routes, cockpit

Agentic Plane:
  ActionIntent legacy context, ObjectiveFit as skill/review memo,
  AuthorityBinding as evaluator/permission trace,
  SimulationReport as workflow output

Control/Safety Plane:
  WriteCapability, simulated adapter boundary,
  service-enforced ExecutionCapabilities, registry alignment,
  no external side effect invariants
```

---

## Decision Log

1. Execution is classical software, not agentic artifact.
2. Paper/live share lifecycle but differ by substrate.
3. LIVE is legal as environment modeling; real broker connectivity is absent.
4. Agentic artifacts are preserved as context/trace/evaluator outputs.
5. Legacy surfaces are downgraded before deletion.
6. Governance is restored after execution spine, not before.
7. CI signal is part of debt paydown.

---

## Anti-regression Rules

- Do not expand ActionIntent chain.
- Do not create new shadow execution objects.
- Do not use not-live docs as substitute for execution modeling.
- Do not put review memos into ExecutionOrder.
- Do not put evaluator findings into ApprovalRecord.
- Do not introduce real broker SDK without capability/credential design.
- Do not add governance framework unless it removes more surface than it adds.

---

## Verification

**Local task check**: 108+ tests pass across all execution, legacy bridge,
adapter boundary, capabilities, life-cycle hardening, receipt contract,
and registry alignment suites.

**GitHub Actions (as of #151 merge)**:
- fuzz: green
- security: CodeQL/Trivy/Gitleaks green; Local verification (standard
  project checks) — pre-existing CI debt tracked separately
- browser-golden-paths: updated for Execution tab (CI-optional, not in task check)

---

## Remaining Debt (Post-#151, historical snapshot)

This table records the state at the end of the #125–#151 paydown chain. The
current canonical source is `docs/governance/debt-register.json`; the two
items below continue as ENG-DEBT-0009 and ENG-DEBT-0010.

After #150–#151, only 2 items remain partially addressed:

| Debt ID | Layer | 状态 | 说明 |
|---|---|---|---|
| DEBT-REG-001 | historical registry | retired | The classification inventory was removed; source and behavior tests own current execution facts. |
| DEBT-CTL-001 | control | partially_addressed | ExecutionCapabilities 已定义，未接入 enforcement |

All other 15 debt items resolved across #134–#151.

## Final Status

FinHarness has completed its execution architecture migration (phase 1–4)
and debt paydown (phase 4–5). 38 PRs from #114 to #151.

The Execution Kernel is the canonical execution surface.
Legacy ActionIntent/PaperValidation chains are downgraded, deprecated,
and bridged. The simulated-only adapter boundary is hardened. Only
abstraction inventory update and capability enforcement remain.

The project no longer relies on ActionIntent/PaperValidation as the
execution substitute. Execution is now a canonical classical software
layer with models, services, receipts, routes, adapter, command, and
cockpit surface.

The legacy chain has been separated, downgraded, and partially cleaned.

The core architecture is no longer in question.
