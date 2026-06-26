# FinHarness System Map

状态:v0(2026-06-22)。目的:把 FinHarness 从"很多安全小块"看成"几个深模块"。每个 system 有固定形状
(domain model / read model / write(command) model / adapters / invariants),新功能**先选归属 system**,再实现。
这是 [architecture-principles.md](../engineering/architecture-principles.md) 的"Module Placement"依据。

> modular monolith,不是微服务:边界靠**清晰接口**,不靠进程拆分。

## Systems

### 1. State Core
- **职责**:可查询的本地状态 + 持久 receipt(证据根)。
- **domain**:`statecore/models.py`(Account/Position/.../Proposal/Attestation/ReviewEvent/ReceiptIndex)、不变量
  (execution_allowed CheckConstraint、closed kind 约束)。
- **read**:`statecore/store.py`(read_all)、`statecore/diff.py`、`snapshots.py`。
- **write(command)**:`store.write_records/upsert_records`(单事务);`receipt_io`(`atomic_write_json` + `resolve_under` 路径护栏)。
- **adapters**:`api/routes_state.py`。
- **invariants**:写入失败清理 receipt;路径不越 allowed root;table 模型校验靠 DB 约束 + create-fn(SQLModel 跳构造校验)。

### 2. Decision Workflow
- **职责**:把 exposure 变成**受治理、可拒绝、不执行**的资本分配候选 → governed proposal。
- **domain**:`allocation.py`(AllocationCandidate + detectors)、`exposure.py`。
- **read**:`api/routes_cockpit.py` 的 `/exposure`、候选经 proposal 暴露。
- **write**:`allocation.record_allocation_candidates`(经 Review System 的 `create_governed_proposal`)。
- **adapters**:`scripts/record_decisions.py` + `task decisions:scan`。
- **invariants**:候选无执行权;默认离线;research enrichment 默认 Noop(见 Research Evidence)。

### 3. Review System  ← **首个"深模块"试点(R2/R3/R4 都属于它)**
- **职责**:人类对 governed proposal 的**复核**:决策(attestation)、交互(ReviewEvent:annotation/archive/reopen/
  compare_mark)、复盘(annual review / lesson→rule 闭环),全部 receipt-backed、append-only、不执行。
- **domain**:`statecore/proposals.py`(Proposal/Attestation/ReviewEvent + `create_governed_*` commands)、
  `statecore/proposal_revisions.py`、`annual_review.py`、`rule_change_ledger.py`、`lesson_loop.py`。
- **read model(应统一)**:timeline(attestations+events)、retrospective(最新 annual_review)、compare-marks(配对)。
  **当前散在 `routes_review.py`/`routes_proposals.py` 内联**——**G5 目标:抽 `review_read.py`(或 `review/`)
  统一 read model**,路由仅 HTTP adapter。
- **write(command)**:`create_governed_proposal` / `create_governed_attestation` / `create_governed_review_event`
  (唯一 id → receipt → DB,失败清理)。
- **adapters**:`api/routes_proposals.py`、`api/routes_review.py`;frontend review renderers(`renderReviewTimeline`/
  `renderReviewEventForm`/`renderRetrospectivePanel` + 待加 compare)。
- **invariants**:attestation=决策 of record;ReviewEvent 附加、视图合并/存储分离;archive=事件非状态;
  content_hash 非幂等;只读面无写/执行(只读 selection 除外)。

### 4. Research Evidence
- **职责**:候选**拉取**历史描述性证据(RE1 契约 / RE2 provider / RE3 enrichment),**绝不**预测/优化/执行。
- **domain**:`research_evidence.py`(RE1 redline 契约)、`redlines.py`。
- **read/provider**:`research_history_provider.py`(RE2,注入式、网络隔离)。
- **command/seam**:`research_enrichment.py`(RE3,Noop 默认 / Provider opt-in / capability routing / typed attachment)。
- **invariants**:无优化器/预测;默认不联网;载体构造点自守红线;前端披露 fail-closed。

### 5. Cockpit
- **职责**:**只读**产品面(read-only adapter),把上述 read model 呈现给人。
- **adapters**:`api/app.py` + `routes_*`;`frontend/app.js` + `index.html`。
- **invariants**:`execution_allowed=false` 常显;view 只读(只读 selection 除外);披露/grade 强制常显;
  **不无限加顶级 tab**(加 view 先问信息架构,见 G5)。

### 6. EOS Governance(平台能力)
- **职责**:"怎么安全变更" + "可枚举风险机器化"。
- **assets**:`docs/engineering/{change-control,gate-checklists,postmortem-triggers,architecture-principles}.md`、
  `docs/templates/mini-rfc.md`、`task governance:check`、`tests/test_governance_invariants.py`。
- **invariants**:C0–C3 分级 + mini-RFC + gate;重复风险进机器护栏;**新增:mini-RFC 须声明 Module Placement**(G5)。

### 7. Headless Trading / Research Engine
- **职责**:OKX/Alpaca/风险门/执行图/市场数据/指标/回测——**headless**,经 task 消费,**不**搬进个人 cockpit 主界面。
- **modules**:`okx_*`、`trading_*`、`execution_graph`、`market_data*`、`indicator_*`、`portfolio_risk`、`*_runner`、`risk_gate*`。
- **invariants**:保持 headless;联网/执行边界为 C3;不污染 cockpit。

## 关系(谁依赖谁)
- Decision Workflow → State Core(写 proposal)、→ Research Evidence(经 RE3 enrichment 注入,默认 Noop)。
- Review System → State Core(proposal/attestation/ReviewEvent + receipts);Cockpit → Review/Decision/Research 的 **read model**。
- Research Evidence 被 Decision Workflow 拉取,**不**反向驱动 cockpit。
- EOS 横切所有 system(平台),不属任何业务流。
- Headless Engine 自成一支,不进 cockpit 产品面。

## Executable Boundary Probes

部分系统边界已进入 `task governance:check` 的 policy registry,不是只停在本文:

- `GOV-ARCH-003`:Cockpit/API adapters 不导入 headless trading/execution 模块。
- `GOV-ARCH-004`:State Core 不反向依赖 `review_read`、API adapters 或 Research adapters。
- `GOV-RESEARCH-001`:Research Evidence 契约/enrichment/provider 不引用 optimizer/route/write surfaces。

## 用法
- 新功能/slice 在 mini-RFC 的 **Module Placement** 节声明归属本图中的某个 system;若跨多个,说明边界与依赖方向。
- 第 3 次在同一 system 散点加 route/renderer/read-model → 先抽该 system 的共享模块(见 G5)。
