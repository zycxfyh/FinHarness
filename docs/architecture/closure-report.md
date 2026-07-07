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

845 测试全部通过。后续工作是 bounded engineering debt，
不再是核心架构不清的问题。

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
| #130 | code | agentic artifact classification |

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
  capability model, registry alignment,
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

845 tests pass: unit, integration, governance, removal-ledger, openapi,
write-capability, execution lifecycle, simulated adapter, legacy bridge.

Known exception: browser golden paths (CI-optional, not in task check).

---

## Final Status

FinHarness has completed its execution architecture migration.

The project no longer relies on ActionIntent/PaperValidation as the
execution substitute. Execution is now a canonical classical software
layer with models, services, receipts, routes, adapter, command, and
cockpit surface.

The legacy chain has been separated, downgraded, and partially cleaned.

The core architecture is no longer in question.
