# FinHarness System Map

状态:current(2026-06-29)。目的:把 FinHarness 从"很多安全小块"看成几个
deep modules。每个 system 有固定形状:

```text
domain model / read model / write(command) model / adapters / invariants
```

新功能先选归属 system,再实现。FinHarness 是 modular monolith,不是微服务:
边界靠清晰接口和依赖方向,不靠进程拆分。

## Current Systems

### 1. State Core

- **职责**:可查询的本地状态 + receipt-backed 证据根。
- **domain**:`statecore/models.py`、`statecore/store.py`、`statecore/receipt_io.py`。
- **read**:`statecore/diff.py`、`statecore/snapshots.py`、`statecore/receipt_index.py`。
- **write(command)**:`write_records` / `upsert_records` / receipt atomic write。
- **adapters**:`api/routes_state.py`、personal-finance / beancount import scripts。
- **invariants**:receipt 文件是 source of truth; SQLite row 是 queryable mirror;
  金额字段以 DecimalText/TEXT 方式持久化;路径必须留在 allowed root 内。

### 2. Capital Map

- **职责**:把 State Core 转成个人资本状态视图:净资产、现金、集中度、现金流、
  利率/负债、税务/保险 review gaps。
- **domain**:`exposure.py`、`daily_brief.py`、`daily_change_brief.py`。
- **read**:`/exposure`、`/brief/daily`、`/dashboard/summary`。
- **write(command)**:`task brief:daily`、`task cockpit:daily` 写 receipt/Markdown。
- **invariants**:描述状态,不授权动作;数据缺口必须显式披露,不能编出完整性。

### 3. IPS / Policy

- **职责**:用户自己的 Investment Policy Statement,把 L2 状态映射到 L4 detector
  的个性化阈值与 policy compliance check。
- **domain**:`ips.py`、`InvestmentPolicyStatement`。
- **read**:`GET /ips/current`、`GET /ips/check`。
- **write(command)**:`POST /ips/draft` / `record_ips` 写 receipt-backed policy。
- **invariants**:IPS 是用户政策,不是投资建议;`execution_allowed=false`;
  compliance check 是描述性检查,不是交易建议。

### 4. Decision Workflow

- **职责**:把 exposure + IPS thresholds 变成受治理、可拒绝、不执行的资本分配
  candidates,再进入 governed proposal。
- **domain**:`allocation.py`、`statecore/decision_scaffold.py`、
  `statecore/risk_classification.py`。
- **write(command)**:`task decisions:scan`、`create_governed_proposal`。
- **read**:候选经 `/proposals` 和 cockpit proposal view 暴露。
- **invariants**:candidate 无执行权;do-nothing option 永远存在;高风险 approval
  缺 `counter_evidence` 时 fail-closed,但 proposal creation 和 rejection 不被阻断。

### 5. Review System

- **职责**:人类对 governed proposal 的复核:attestation、decision-scaffold
  revision、annotation、archive、reopen、compare mark、annual review、lesson-to-rule。
- **domain**:`statecore/proposals.py`、`statecore/proposal_revisions.py`、
  `review_read.py`、`annual_review.py`、`lesson_loop.py`、`rule_change_ledger.py`。
- **read model**:`read_proposal_timeline`、`read_compare_marks`、review routes。
- **write(command)**:`create_governed_attestation`、`revise_governed_proposal_scaffold`、
  `create_governed_review_event`、`task review:annual`、`task lessons:*`。
- **invariants**:append-only;attestation 是 decision of record,不是 execution
  authorization;scaffold revision 只补 review evidence 和 `counter_evidence`,
  不授权执行;receipt 写失败必须清理 queryable mirror。

### 6. Research Evidence

- **职责**:为某个 candidate 拉取只读、历史描述性证据;不预测、不优化、不写状态。
- **domain**:`research_evidence.py`、`research_history_provider.py`、
  `research_enrichment.py`、`research_rigor.py`、`redlines.py`。
- **adapters**:`data_entry.py`、`market_data.py`、`providers/ccxt_provider.py`。
- **invariants**:默认不联网;provider 失败变成 data gap;证据只能挂在 candidate
  下,不能反向驱动 cockpit 或产生行动指令。

### 7. Agent Explanation

- **职责**:给人解释状态、IPS policy、proposal/review timeline、风险笔记和工具结果。
- **read model**:`agent_context.py` 中的 bounded context packs:
  capital summary、current IPS、IPS check、open proposals、proposal timeline。
- **domain/adapters**:`agent_context.py`、`agent_capabilities.py`、
  `agent_tools.py`、`proposal_queue_checks.py`、`hermes_bridge.py`。
- **tool posture**:`agent_capabilities.py` 定义显式 capability profiles;default
  profile 是 read/explain;planned capabilities 只表达路线图,不能被 runtime 当成权限;
  `agent_tools.py` 的 registry/factory 把 profile tool names 映射成 actual SDK
  tools;review-draft profile 允许 Agent 创建 append-only governed proposal draft;
  proposal review surface 会暴露 created_by=agent、active profile、context/source
  refs、receipt ref、requires_human_review、execution_allowed=false;proposal queue
  checks 暴露 pass/warn/block、block code、blocked transition scope、recovery hint、
  source/receipt refs,并区分 review_entry、human_attestation、authority_transition
  和 execution,但不产生 approval、attestation 或 execution authorization;未来 review-note/simulate
  只能通过新增工具、registry 映射、测试和 receipt-backed command path 变成
  active capabilities。
- **invariants**:Agent 只通过 profile-selected tools 和最小上下文读数据;不裸读全库;
  capability profiles 不是 permission bypass;Agent draft proposal 是 review object,
  不是 approval、recommendation 或 execution authorization;default profile 不写核心状态;
  没有 live order、transfer、broker write API、receipt 删除/覆盖或 Agent approval。

### 8. Cockpit / Product API

- **职责**:产品表面,让人阅读、比较、复核、拒绝、确认、归档。
- **adapters**:`api/app.py`、`api/routes_cockpit.py`、`api/routes_proposals.py`、
  `api/routes_review.py`、`api/routes_ips.py`、`frontend/`。
- **invariants**:`execution_allowed=false` 常显;前端只能展示和复核边界,不能放松
  后端边界;不无限加顶级 tab。

### 9. EOS Governance / Quality

- **职责**:怎么安全变更、怎么证明边界、怎么阻止 docs/facts drift。
- **assets**:`tests/_policy_registry.py`、`tests/test_governance_invariants.py`、
  `tests/test_docs_current_facts.py`、`hardening.py`、`quality_governance_graph.py`、
  `release_preflight_graph.py`、`repo_intelligence_graph.py`、
  `receipt_usage_audit.py`。
- **invariants**:机器检查只管当前事实和当前入口;历史 notes/reviews 不被改写。

### 10. Archived Live-Trading Legacy

- **职责**:历史参考,非 mainline runtime。
- **location**:`experiments/archive/live_trading_legacy/`。
- **invariants**:不得被 production code、CI safety gates、Agent tools、API routes、
  Taskfile tasks 导入或调用。若未来需要只读 market-data 能力,按 ExternalData
  adapter 重新设计,不要继承归档执行代码。

## Dependency Direction

```text
State Core <- Capital Map <- IPS / Decision Workflow <- Review System <- Cockpit
                           <- Research Evidence
Agent Explanation reads through tools; it does not own source-of-truth.
EOS Governance cuts across all systems.
Archived Live-Trading Legacy has no dependency edge back into mainline.
```

## Executable Boundary Probes

这些边界不只停在本文:

- `task governance:check` runs policy registry and frontend no-action probes.
- `task docs:current-check` checks maintained docs against live Taskfile facts.
- `tests/_graph_registry.py` records graph assets by status, including retired
  and downgraded paths.

## How To Use This Map

- 新 feature/slice 在 mini-RFC 或 PR 描述里声明 Module Placement。
- 改 Taskfile/API/current architecture 时,同步 README / command reference /
  Capital OS / module map,然后跑 `task docs:current-check`。
- 历史 docs 可以保留旧命令和旧模块,但 current navigation docs 不可以。
