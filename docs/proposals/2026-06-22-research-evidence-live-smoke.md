# `--with-research` opt-in live smoke — mini-RFC (C3)

Architect 设计稿,2026-06-22。**设计 gate 用,不开码。** 按
[mini-rfc 模板](../templates/mini-rfc.md)(8 节)。目标:用一次**隔离、opt-in、可丢弃**的真实联网
运行验证 RE3 的 `--with-research` 接线端到端可用,而**不让网络进入默认路径或 CI**。

### 1. Change Class
**C3** —— 命中 [change-control](../engineering/change-control.md) 触发器:**联网**(真实市场数据)+ **投资证据
语义**。故走 mini-RFC + threat/surface inventory + independent gate;**不**纳入 `task check` 的 CI 硬化。

### 2. Current behavior
- 默认 `decisions:scan` 用 `NoopResearchEnricher`,离线确定([record_decisions.py](../../scripts/record_decisions.py))。
- `--with-research` flag 已存在,opt-in 注入 `ProviderResearchEnricher(HistoricalRiskProfileProvider(MarketDataHistorySource()))`
  (RE3b,commit `a46bcd8`)。
- 真实联网路径**只被 fixture 覆盖**(`MarketDataHistorySource` 标注 best-effort、不单测网络)。
  端到端真实拉数 → enrich → proposal evidence/receipt 这条链**从未被真实跑过**,只在设计上成立。

### 3. Target behavior
路线 **(b)**:一个**专用 smoke harness**(`task decisions:research-smoke` + 背后脚本),**显式排除于** `task check`。
**不复用** `record_decisions.py` 的常规 stdout(它不足以证明 evidence/gap、lineage、receipt 都正确)。harness 对一个
**合成隔离样本**(临时 DB + 一个高集中度持仓,symbol 用公开宽基如 `SPY`)跑一次 `--with-research`,断言:
- 真实 provider 被调用(经 `MarketDataHistorySource`),且
- 要么产出一条 `historical_risk_profile` evidence(四键 value + 过去时 claim + non_claims +
  `lineage.provider/source/as_of/reconciliation`),
- 要么产出一条**脱敏 data_gap**(网络不可达/symbol 缺/历史不足),
- 两种结果都**不崩**、**不打印敏感数据/原始 provider payload/堆栈**、**不声称投资建议**,
- proposal receipt 落 tempdir 可复盘;`source_refs` **若 provider 提供则保留,不强制非空**
  (现 live `MarketDataHistorySource` 返回空 source_refs,靠 `lineage` 复盘——强制非空会越界到"市场数据 receipt 写入"另一个 slice)。
默认 `decisions:scan`(无 flag)行为**逐字节不变**。

### 4. Surface Inventory
- **输入**:隔离临时 DB(`--db-path` 指向 tempdir)+ 一个合成 concentration 持仓(public symbol);`--with-research` flag;`--receipt-root` 指向 tempdir。
- **输出**:harness 读回 proposal evidence 后打印**有限 JSON summary**(命中 detector、有无 research item、
  value 键集、有无 gap、lineage 字段是否齐、receipt 路径)——**不**回显原始 provider payload/真实账本/堆栈;
  proposal/receipt 落 tempdir。
- **外部调用/网络面**:`MarketDataHistorySource._fetch_openbb_history`(OpenBB/yfinance)——**仅此一处**,属 RE2/market_data,本 slice 不新增。
- **失败面**:网络不可达、symbol 不存在、历史不足、reconciliation 单源 → 各自一条 `data_gap`(RE1/RE2 已守)。
- **用户可见面**:**无新增**——冒烟是开发者/运维动作,不进 cockpit、不改前端。
- **排除面(明确不碰)**:默认路径、`task check`/CI、cockpit、新端点、Proposal schema、真实个人账本(用合成样本)。

### 5. Default Path Invariant
默认 `decisions:scan`(无 `--with-research`)**完全不变**:
- **现状事实**:默认走 `NoopResearchEnricher` → proposal evidence `research_evidence: []`、无 `research_evidence_gaps`、无网络。
- **锁它的测试**:`tests/test_allocation.py::...test_default_path_keeps_pre_re3_research_shape`(快照逐字段相等)。
- 本 slice **不新增任何默认路径代码**;冒烟是独立 opt-in 调用。**网络绝不进 `task check`**——冒烟 task(若加)
  显式排除在 `check` 序列外,且文档标注"手动/按需"。

### 6. Traceability Matrix
| 设计承诺 | 计划代码点 | 测试/验证 | gate 探针 |
| --- | --- | --- | --- |
| 默认路径不变、网络不进 CI | 不动默认路径;冒烟 task 不入 `check`/`governance:check`/`test:*` | 默认快照测试仍绿 | grep:`check`/`governance:check`/`test:*` 依赖链均无冒烟 task |
| 真实 provider 被调用 | `ProviderResearchEnricher` + `MarketDataHistorySource` | 冒烟运行产出 evidence 或 data_gap | 人工/脚本观察 source 命中 |
| 失败→脱敏 data_gap 不崩 | RE2/RE3 既有 try→`sanitize_gap` | 断网/坏 symbol 复跑 → data_gap、exit 0 | 反例:坏 symbol 跑一次 |
| 不打印敏感数据 | 合成样本 + 不 dump 原始账本/堆栈 | 冒烟输出审查无 PII/路径/堆栈 | 输出 grep 无敏感 token |
| 不声称投资建议 | RE1/RE2 红线 + 过去时 claim | evidence 过 RE1 校验 | 现有红线探针 |
| receipt + lineage 可复盘 | 既有 `create_governed_proposal`;evidence 带 `lineage` | tempdir receipt 可读;research item `lineage` 字段齐(provider/source/as_of/reconciliation) | 检查 receipt 文件 + lineage 键 |
| 失败语义清晰(exit code) | harness 区分管线 data_gap vs setup 失败 | 坏 symbol/断网 → exit 0 + data_gap;schema/import/setup 坏 → 非零 | 反例跑一次 |

### 7. Test / Gate Plan
通过条件(写死,供 implementation gate 核):
- `task decisions:research-smoke` 是 **manual / on-demand / network** 目标;**明确不在** `task check`、
  `task governance:check`、`task test:*` 的依赖链内。
- **exit code 语义**:管线本身正常时,离线 / 坏 symbol / provider 失败应 **`exit 0` + 输出 sanitized `data_gap`**;
  **只有** harness/setup/schema/import 失败才 **非零**。
- **fixture 单测已覆盖**接线逻辑(`test_research_enrichment` / `test_allocation` opt-in 集成);真实 smoke 只补
  "真网络跑一次"的证据,**不作为 CI 断言**。
- **implementation gate 必须**用 grep/探针证明 smoke task **未进入** `check`/`governance:check`/`test:*` 默认链。
- **Gate**:C3 → design gate(本稿)+ Risk/Compliance 视角(联网不入默认、不打印敏感)+ implementation gate。

### 8. Not claimed / Debt
- **不**主张:这是持续/定时联网;这是投资建议;这覆盖真实个人账本(用合成样本)。
- **债务**:真实个人账本端到端(Track B-2)是**单独 C3 slice**,需隐私/脱敏专门设计,不在本 smoke 内;
  浏览器 Playwright E2E(D8)仍后续。
- **已裁定(design gate)**:落成 **(b) 专用 `task decisions:research-smoke` 目标**,显式排除于 `check`——
  可复跑/可记录/可审计;implementation gate 用探针保证不被默认链误纳入。
