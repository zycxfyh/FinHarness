# Change Control — FinHarness Engineering Operating System v0

状态:v0(2026-06-22 起)。目标**不是变官僚**,而是把"什么时候轻、什么时候重"制度化:
**按风险面选择工程形态,而不是按 diff 大小**。

核心原则:**不再问"改动大不大",先问"风险面是什么"。** 验收标准也从"最小 diff"改成
**最小可审计边界(smallest auditable boundary)**——有时是 5 行,有时是一个小子系统;判断依据是
默认行为、边界、回滚、测试是否清晰,而不是行数。

## Change Class

每个 slice 动手前先归类。归类决定流程强度。归类由 **PM / Tech Lead** 拍板(见
[engineering-roles.md](../reference/engineering-roles.md))。

| Class | 适用 | 流程强度 |
| --- | --- | --- |
| **C0** | 文档、小修、测试补充、重命名、依赖升级 | 直接做 + 跑相关检查。无需 RFC。 |
| **C1** | 单模块功能改动,默认行为可能变但不跨边界 | 简短设计说明 + targeted tests + implementation gate。 |
| **C2** | 跨模块 / 用户可见 / 默认行为变化 | **mini-RFC** + design gate + implementation gate。 |
| **C3** | 财务 / 投资 / 税务 / 联网 / 自动化 / 安全边界 | mini-RFC + threat/surface inventory + **independent** gate + CI hardening。 |

> C2/C3 必须走 [mini-RFC 模板](../templates/mini-rfc.md),并交 [gate checklist](./gate-checklists.md)。
> C0/C1 不必。

## 触发器:出现任一即至少 C2

把"这是不是跨边界"变成可勾选清单,而不是临场判断:

- [ ] 改变**默认行为**(默认 scan / 默认开关 / 默认输出)。
- [ ] 引入或改变**外部网络 / 外部依赖**调用面。
- [ ] 改变**证据语义**(claim / evidence / grade / source_refs / 红线)。
- [ ] 改变**用户可见的解释**(cockpit 展示、披露、措辞)。
- [ ] 触及**财务 / 税务 / 投资边界**(可能被误读为建议/执行)。
- [ ] 新增**自动化**(定时、cron、自动触发)。

命中财务/投资/税务/联网/自动化/安全中的任一 → 升到 **C3**。

## 边界模块优先(把"最小改动"重定义)

详见 [architecture-principles.md](./architecture-principles.md)(G5)+ [system-map.md](../architecture/system-map.md)。
一句话先行:**最小不可逆风险 > 最小 diff**;且 C2/C3 须声明 **Module Placement**(归属哪个 system),同一 system
第 3 次散点先抽共享模块。跨边界 slice 宁可抽一个小而完整的子系统,也不要在多个现有函数里补 if。

## 与现有实践的关系

- author ≠ gate 已是惯例;本制度细化职责:author 负责**机械自查**,independent gate 负责
  **创造性对抗**(见 gate checklists)。
- receipt / source_refs / redline / jsdom / `task check` 不变;可枚举检查逐步进
  `task governance:check`(G4,已建并纳入 `task check`),减少人肉抓机械漏项。
- 重复痛点经 [postmortem-triggers.md](./postmortem-triggers.md)(G6)固化成规则/测试/脚手架;
  同类问题第 2 次出现默认走机器化。

## 当前在用的分类(活页)

| Slice | Class | 状态 |
| --- | --- | --- |
| RE1 research-evidence redline contract | C2 | DONE `80b1793` |
| RE2 historical risk-profile provider | C3(联网 + 投资证据语义) | DONE `7e7595e` |
| RE3 Research Enrichment Subsystem | **C3**(默认行为 + 联网 opt-in + 投资证据用户可见解释) | DONE `a46bcd8`(RE3a/b/c + EOS G4;design+impl gate PASS) |
| 移除 vestigial candidate research 字段 | **C1**(单模块、未读字段) | DONE `9edc44b` |
| `--with-research` opt-in live smoke | **C3**(联网 + 投资证据) | DONE(merged PR #18,87e0fea) |
| CI triage S1/S2/S3(okx flake / deps+gitleaks / path-traversal harden) | CI/security baseline | DONE(merged PR #18) |
| S4-R2 Review Workspace(ReviewEvent/Annotation/Archive) | **C3**(人工写入治理面 + 审计) | DONE(merged PR #21,abf8953;R2a/b/c + gates) |
| S4-R3 Retrospective Cockpit(annual review + lesson/rule 闭环只读露出) | **C2**(只读视图;加 promote 即升 C3) | DONE(merged PR #22,295b0ad;R3a/b + gates) |
| S4-R4 Candidate Compare(复用 compare_mark 并排只读比较) | **C2**(只读;无裁决/无写) | DONE(merged PR #23,24436d5;R4a-0/a/b + 架构 checkpoint) |
| Golden Path 受 receipt-consumption demo(端到端回放) | **C2**(隔离 tmp 写 + 回放;离线;无执行/PII) | DONE(merged PR #24,e863cd9;端到端 receipt-consumption CI 锚) |
| System Directory Standard(#2) | **C1**(架构/测试治理标准,无产品行为变化) | DONE(merged PR #25,36da01b;6 角色形状 + Review System 参考实现探针) |
| Repo intelligence 性能 + 测试分层 | **C1**(性能/测试结构,输出等价) | DONE(merged PR #26,0142714;walk 剪枝 + integration 分层) |
| Policy Registry(#3) | **C1**(governance 探针结构化,行为保持) | DONE(merged PR #27,77c92bc;id/owner/scope/source/check) |
| Graph Rationalization Audit | **C0**(纯架构判断文档,无代码变化) | DONE(merged PR #28,fa91ced;R0/R1/R2/R5 路线,不删图) |
| Fixture Standardization(#4) | **C1**(测试脚手架标准化,无产品行为变化) | DONE(merged PR #29,5830a56;StateCoreFixture + GOV-ARCH-002) |
| D7 OpenTelemetry trace/receipt indexing | **C2**(跨 API/task/receipt 的 observability 边界;外部 exporter 仍需 C3 批准) | D7a/D7b implemented(trace contract + trace-index receipt + local-only OTel SDK provider, no exporter);trace consumer implemented(`task observability:trace`, bounded summary, no raw payload); D7c external exporter still gated |
| D8 Browser Golden Paths(真实浏览器 smoke) | **C2**(测试基础设施;仅 dev/test 依赖,不进产品 runtime;不进默认 check) | DONE(merged PR #32,714a3d1;test:browser + Playwright devDep + cockpit_smoke spec + GOV-EOS-002 + seeded server + CI optional job; first CI red caught async render race, fix green) |
| Architecture Boundary Probes(Task 3) | **C1**(governance 探针;无产品行为变化) | DONE(merged PR #34,8b808be;`GOV-ARCH-003` API 不导入 headless engine,`GOV-ARCH-004` State Core 不反向依赖上层,`GOV-RESEARCH-001` 扩面;独立复核合前修掉 from-import 盲区 + 回归测试) |
| Graph Registry R1(Task 4) | **C1**(架构治理元数据登记;无产品行为/依赖/runtime 变化) | in progress;`tests/_graph_registry.py` 把 graph-rationalization-audit 从 prose 升级成可校验 registry(20 资产,`task governance:graphs` 可发现);**判断资产,非删除授权**;纠正 audit 失实的 docs/archive 路径声明 |
