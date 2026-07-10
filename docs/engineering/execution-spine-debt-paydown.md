# Execution Spine Debt Paydown Plan

状态: historical / superseded (2026-07-10)
目标: 把架构迁移后的残留债务按层分类、排序、逐 PR 消除。

> 当前债务状态只以 `docs/governance/debt-register.json` 为准。本文件保留
> #125–#151 的专项治理脉络，不再作为当前 backlog。原 DEBT-REG-001 与
> DEBT-CTL-001 分别迁移为 ENG-DEBT-0009 与 ENG-DEBT-0010。

## 0. 原则

还债不是再造管理系统。还债是减少系统解释成本。

每个 PR 至少满足一个目标:
1. 删除旧东西
2. 降级旧东西
3. 把 artifact 放回正确抽象层
4. 对齐 registry / docs / tests
5. 提高 execution spine 的确定性
6. 清掉 CI / DevEx 噪音

不接受:
- 新增一套治理对象
- 新增大 registry 但不删旧 surface
- 新增 guardrail 但没有减少旧 surface
- 把 agentic artifact 又塞回 StateCore object

## 1. Phase Plan

| Phase | PRs | Focus |
|---|---|---|
| 1 — Ledger | #125 | 债务分类，建立还债清单 |
| 2 — CI First Aid | #126, #127 | 清 CI 红点，恢复 review 信号 |
| 3 — Registry Alignment | #128–#131 | inventory, route, write, receipt 对齐 |
| 4 — Legacy Downgrade | #132–#134 | 从 docs/nav/response 降级旧 surface |
| 5 — Agentic Reclassification | #135, #136 | target_layer 字段, multi-projection fix |
| 6 — Execution Hardening | #137–#139 | lifecycle transitions, receipt contract, adapter boundary |
| 7 — Control/Safety | #140, #141 | capability model, adapter registration policy |
| 8 — Final Deletion | #142+ | 删剩余死文档和旧 surface |

## 2. 债务分类

### A. Classical Execution Debt
Execution spine 自己的工程债: status consistency, receipt completeness, API DTO, cockpit polish.

### B. Legacy Shadow Surface Debt
旧 ActionIntent/PaperValidation 残留: duplicate concepts, deletion candidates not yet deleted, legacy routes still callable, old docs mixed in mainline.

### C. Agentic Artifact Debt
agent 工作产物还没完全从 classical object layer 分离: CapitalObjectiveFit, AuthorityBinding, SimulationReport 仍 object-shaped.

### D. Control/Safety Debt
权限、隔离、边界: real broker boundary not centrally expressed, capability model scattered, no runtime deprecation warnings.

### E. Documentation/Product Truth Debt
文档事实、导航、主线叙述: docs-current drift, duplicate mainline, old protection language residual.

### F. Registry/Inventory Debt
machine-readable governance: inventory stale, route/write/receipt registries misaligned.

### G. CI/DevEx Debt
security workflow red, browser golden paths red, flaky tests.

## 3. Phase 1 — Ledger (#125)

- [x] 创建本文件
- [x] 创建 `docs/governance/execution-spine-debt-ledger.yml`
- [ ] N/A (仅文档)

## 4. Phase 2 — CI First Aid (#126, #127)

- [ ] #126: 修复或隔离 flaky market-data freshness test
- [ ] #127: 稳定 browser golden paths

## 5. Phase 3 — Registry Alignment (#128–#131)

- [ ] #128: 更新 abstraction inventory 纳入 Execution Kernel
- [ ] #129: Route registry alignment (canonical vs legacy)
- [ ] #130: Write registry alignment
- [ ] #131: Receipt registry alignment

## 6. Phase 4 — Legacy Downgrade (#132–#134)

- [ ] #132: 从主导航/主文档移除 legacy routes
- [ ] #133: PreTradePacket 降级为 legacy projection
- [ ] #134: Legacy route response deprecation warnings

## 7. Phase 5 — Agentic Reclassification (#135, #136)

- [ ] #135: Agentic artifact target_layer enum fields
- [ ] #136: Multi-projection bridge fix

## 8. Phase 6 — Execution Hardening (#137–#139)

- [ ] #137: Lifecycle state transition tests
- [ ] #138: Receipt idempotency/refs contract
- [ ] #139: Simulated adapter boundary tests

## 9. Phase 7 — Control/Safety (#140, #141)

- [ ] #140: Minimal execution capability model
- [ ] #141: Adapter registration policy (simulated-only)

## 10. Phase 8 — Final Deletion (#142+)

- [ ] #142: Delete dead protection docs
- [ ] #143+: Runtime deletion candidate evaluation (future)
