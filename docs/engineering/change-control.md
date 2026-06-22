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

详见 [architecture-principles.md](./architecture-principles.md)(G5,后续)。一句话先行:
**最小不可逆风险 > 最小 diff**。跨边界 slice 宁可抽一个小而完整的子系统(Noop 默认 + opt-in +
capability routing + typed attachment),也不要在多个现有函数里补 if。

## 与现有实践的关系

- author ≠ gate 已是惯例;本制度细化职责:author 负责**机械自查**,independent gate 负责
  **创造性对抗**(见 gate checklists)。
- receipt / source_refs / redline / jsdom / `task check` 不变;可枚举检查逐步进
  `task governance:check`(G4,后续),减少人肉抓机械漏项。

## 当前在用的分类(活页)

| Slice | Class | 状态 |
| --- | --- | --- |
| RE1 research-evidence redline contract | C2 | DONE `80b1793` |
| RE2 historical risk-profile provider | C3(联网 + 投资证据语义) | DONE `7e7595e` |
| RE3 Research Enrichment Subsystem | **C3**(默认行为 + 联网 opt-in + 投资证据用户可见解释) | design gate PASS;后端(RE3a/b)impl gate PASS;RE3c/G4 待 impl gate + release |
