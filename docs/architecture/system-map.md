# FinHarness System Map

状态:current(2026-07-02)。目的:把 FinHarness 从"很多安全小块"看成几个
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

### 3. IPS / Policy / Authority Credentials

- **职责**:用户自己的 Investment Policy Statement,把 L2 状态映射到 L4 detector
  的个性化阈值与 policy compliance check;CapitalMandate 则在 IPS 之上记录
  human-attested policy domain,供未来 delegated authority 对象引用;
  AgentAuthorityGrant 在 active CapitalMandate 下授予 Agent 受限 authority
  credential,并提供 dynamic validator。
- **domain**:`ips.py`、`InvestmentPolicyStatement`、`statecore/capital_mandates.py`、
  `CapitalMandate`、`statecore/agent_authority_grants.py`、`AgentAuthorityGrant`。
- **read**:`GET /ips/current`、`GET /ips/check`、`GET /capital-mandates/current`、
  `GET /capital-mandates/{capital_mandate_id}`、`GET /agent-authority-grants`、
  `GET /agent-authority-grants/{grant_id}`。
- **write(command)**:`POST /ips/draft` / `record_ips` 写 receipt-backed policy;
  `POST /capital-mandates` / `record_capital_mandate` 写 receipt-backed
  human-attested mandate;`POST /agent-authority-grants` /
  `record_agent_authority_grant` 写 receipt-backed mandate-bound credential;
  `POST /agent-authority-grants/{grant_id}/validate` 动态重查 grant 与 mandate
  当前状态并返回 structured deny reasons。
- **invariants**:IPS 是用户政策,不是投资建议;`execution_allowed=false`;
  compliance check 是描述性检查,不是交易建议。CapitalMandate 不是授权对象,
  不授予 Agent identity,不创建 order ticket 或 broker instruction;它要求
  `human_attester`、`human_reason`、`explicit_confirmation=true`,且
  `execution_allowed=false`、`authority_transition=false`。AgentAuthorityGrant
  是 mandate-bound authority credential,不是 authentication、trade-plan
  approval、preflight bypass、broker submission 或 execution authorization;
  没有 active CapitalMandate 时 default-deny,grant validation 必须 use-time
  重查当前 grant/mandate/scope。

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
- **read model**:`read_proposal_timeline`、`read_compare_marks`、
  `read_review_queue`、`read_review_risk_register`、review/risk routes。
- **write(command)**:`create_governed_attestation`、`revise_governed_proposal_scaffold`、
  `create_governed_review_event`、`task review:annual`、`task lessons:*`。
- **invariants**:append-only;attestation 是 decision of record,不是 execution
  authorization;scaffold revision 只补 review evidence 和 `counter_evidence`,
  不授权执行;review queue triage 是派生 read model,用于排序 human review
  work,不是 approval/rejection/attestation;risk register v0 只把 review queue
  signals 派生成 risk objects,不是 persistent risk DB、risk acceptance、scoring
  或 scenario generation;receipt 写失败必须清理 queryable mirror。

### 6. Capital Action Intent

- **职责**:把当前 proposal/revision state 翻译成 candidate-only capital
  action intent,并把 system preflight 绑定到 qualitative simulation report,
  再把 simulation evidence 转成 pre-trade plan candidate,作为未来
  AuthorityContract 的输入。
- **domain**:`statecore/action_intents.py`、`ActionIntent`、
  `statecore/action_intent_simulations.py`、`statecore/trade_plan_candidates.py`、
  `action_intent_preflight.py`、`api/routes_action_intents.py`。
- **write(command)**:`POST /proposals/{proposal_id}/action-intents` /
  `create_governed_action_intent`;
  `POST /action-intents/{action_intent_id}/simulation-reports` /
  `create_governed_action_intent_simulation_report`;
  `POST
  /action-intent-simulation-reports/{simulation_report_id}/trade-plan-candidates` /
  `create_governed_trade_plan_candidate`。
- **read**:`GET /action-intents/{action_intent_id}`、
  `GET /action-intents/{action_intent_id}/preflight`、
  `GET /action-intent-simulation-reports/{simulation_report_id}`、
  `GET /trade-plan-candidates/{trade_plan_candidate_id}`。
- **invariants**:ActionIntentCandidate 不是 order ticket、broker action、
  simulation、approval、investment advice 或 execution authorization;创建时必须
  绑定当前 proposal receipt,拒绝 stale receipt,拒绝 order/broker/execution/
  authority markers,并写 `state_core_action_intent_candidate` receipt;system
  preflight 只读重算 freshness、scope、IPS policy、evidence、precondition、
  v0 impact summary、risk posture 和 deterministic report hash;simulation report
  创建时必须重新计算并匹配 current preflight hash,block 则拒绝,warn 必须显式
  acknowledge all warning codes,并写
  `state_core_action_intent_simulation_report` receipt;v0 simulation report
  仍不生成 order、broker action、approval 或 execution authorization;
  TradePlanCandidate 只允许 plan direction/scope/cap/constraint fields,拒绝
  exact quantity、broker/order-ready/execution/authority markers 和 stale
  simulation/preflight evidence,写 `state_core_trade_plan_candidate` receipt,但
  `submitted_to_broker=false`,必须等待未来 AuthorityContract 才能进入任何执行路径
  或生成 order ticket。

### 7. Research Evidence

- **职责**:为某个 candidate 拉取只读、历史描述性证据;不预测、不优化、不写状态。
- **domain**:`research_evidence.py`、`research_history_provider.py`、
  `research_enrichment.py`、`research_rigor.py`、`redlines.py`。
- **adapters**:`data_entry.py`、`market_data.py`、`providers/ccxt_provider.py`。
- **invariants**:默认不联网;provider 失败变成 data gap;证据只能挂在 candidate
  下,不能反向驱动 cockpit 或产生行动指令。

### 8. Agent Explanation

- **职责**:把 Agent 团队放进个人资本办公室的治理运行时:解释状态、IPS policy、
  proposal/review timeline、风险笔记和工具结果,并通过显式 profile/tool/evidence/
  context projection contract 逐步开放更强能力。
- **read model**:`agent_context.py` 中的 bounded context packs:
  capital summary、current IPS、IPS check、open proposals、proposal timeline。
- **domain/adapters**:`agent_context.py`、`agent_context_projection.py`、
  `agent_capabilities.py`、`agent_evidence.py`、`agent_tools.py`、
  `proposal_queue_checks.py`、`hermes_bridge.py`。
- **tool posture**:`agent_capabilities.py` 定义显式 capability profiles;default
  profile 是 read/explain baseline,不是最终 ceiling;planned capabilities 只表达路线图,
  不能被 runtime 当成权限,但可以通过 profile、ToolEntry、evidence provider、
  receipt-backed command path、review/approval surface 和测试毕业为 active capability;
  `agent_tools.py` 的 `AgentToolEntry` registry/factory 把 profile tool names 映射成
  actual SDK tools,并暴露 capability、toolset、side-effect、availability 和
  non-authority metadata;`agent_context_projection.py` 提供 profile-aware
  context budget 和 `get_capital_context_projection` office brief 工具,让 Agent
  团队按角色拿到适量、可追踪、可诊断的 Capital OS 上下文;`agent_evidence.py` 提供 evidence provider registry 和
  dispatch evidence envelope,把 source_refs、receipt_refs、context_pack_refs、
  data_gaps 和 non-claims 从裸 payload 投影成可审查 provenance;`agent_runtime.py`
  负责 visible/hidden/unavailable tool resolution、structured result/error/evidence、
  profile-aware context projection、result-budget truncation 和 dispatch wrapper;
  review-draft profile 允许 Agent 创建 append-only governed proposal draft;
  review-note profile 允许 Agent 在已有 proposal timeline 上创建 append-only
  `AgentReviewNoteDraft` typed artifact,用于 findings、risks、open questions、
  evidence refs、data gaps 和 human review 准备,不修改 proposal/scaffold/attestation;
  scaffold-candidate profile 允许 Agent 基于 `/risk/register` 的 active risk item
  创建 append-only `AgentScaffoldRevisionApplyCandidate`,包含 `scaffold_patch`、
  `proposed_scaffold`、changed fields、risk coverage、preflight、rollback 和 human
  confirmation requirements,但不直接修改 proposal scaffold;
  `/scaffold-revision-candidates/{candidate_id}/preflight` 是 system-recomputed
  read-only preflight,会重新检查 candidate payload、当前 proposal receipt、
  scaffold forcing/changed fields、active risk register basis 和 forbidden authority
  markers,返回 pass/warn/block findings 与 deterministic report hash,但不应用
  patch、不授权 apply;
  `/scaffold-revision-candidates/{candidate_id}/apply` 是 human-confirmed apply
  path,要求 human attester/reason、expected candidate/proposal receipts、
  expected preflight report hash 和 explicit confirmation;server 会在 apply 时
  重新计算 preflight,hash 不匹配或 status=block 时拒绝,warn 只有在人类显式
  ack 所有 warning codes 后才可继续;通过后调用 existing scaffold revision
  command 并把 proposal revision receipt 链回 candidate receipt/review event 和
  preflight evidence;
  proposal review surface 会暴露 created_by=agent、active profile、context/source
  refs、receipt ref、requires_human_review、execution_allowed=false;proposal queue
  checks 暴露 pass/warn/block、block code、blocked transition scope、recovery hint、
  source/receipt refs,并区分 review_entry、human_attestation、authority_transition
  和 execution;review-task lifecycle 把 proposal/timeline/queue checks 投影成
  read-only ReviewTask/EvidenceRequest;`/review/queue` 把 proposals、
  attestations、archived state、review events、AgentReviewNoteDraft payloads、
  receipt index 和 queue checks 投影成 deterministic ReviewQueueItem,让人类
  reviewer 看到 priority、triage reasons、open questions、data gaps、duplicate/
  stale flags 和 next actions;`/risk/register` 再把这些 queue signals 派生成
  read-only RiskRegisterItem,用于比较 evidence gaps、stale context、duplicates、
  policy mismatch、counter-evidence needs、Agent-reported risks 和 open questions,
  不接受/关闭风险、不评分、不生成 scenario;未来 scaffold revision、simulation、
  approval prep 或其他更强权限,应通过新增工具、registry 映射、
  evidence envelope、测试和 receipt-backed command path 变成 active capabilities,
  而不是靠 prompt 承诺。
- **invariants**:Agent 只通过 profile-selected tools 和最小上下文读数据;不裸读全库;
  capability profiles 不是 permission bypass;Agent draft proposal 是 review object,
  不是 approval、recommendation 或 execution authorization;default profile 不写核心状态;
  没有 live order、transfer、broker write API、receipt 删除/覆盖或 Agent approval。

### 9. Cockpit / Product API

- **职责**:产品表面,让人阅读、比较、复核、拒绝、确认、归档。
- **adapters**:`api/app.py`、`api/routes_cockpit.py`、`api/routes_proposals.py`、
  `api/routes_review.py`、`api/routes_ips.py`、`frontend/`。
- **invariants**:`execution_allowed=false` 常显;前端只能展示和复核边界,不能放松
  后端边界;不无限加顶级 tab。

### 10. EOS Governance / Quality

- **职责**:怎么安全变更、怎么证明边界、怎么阻止 docs/facts drift。
- **assets**:`tests/_policy_registry.py`、`tests/test_governance_invariants.py`、
  `tests/test_docs_current_facts.py`、`hardening.py`、`quality_governance_graph.py`、
  `release_preflight_graph.py`、`repo_intelligence_graph.py`、
  `receipt_usage_audit.py`。
- **invariants**:机器检查只管当前事实和当前入口;历史 notes/reviews 不被改写。

### 11. Archived Live-Trading Legacy

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
