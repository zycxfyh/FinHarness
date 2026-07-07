## Abstraction Classification

<!--
  FinHarness Stabilization Program:
  每个 PR 必须对新增/修改的 artifacts 做抽象层分类。
  参考: docs/engineering/agentic-abstraction-principles.md
-->

| Artifact | Current Form | Correct Layer | Migration Path |
| --- | --- | --- | --- |
| <!-- e.g. ActionIntent --> | <!-- Object / Route / Registry / Skill / ... --> | <!-- Object / Tool / Resource / Context / Skill / Workflow / Loop / Evaluator / Guardrail / Permission / Trace --> | <!-- bridge / reclassify / delete / none --> |

## Freeze Rule Compliance

<!-- 停顿期内默认禁止以下改动。如有例外，声明理由。 -->

- [ ] 不新增 StateCore model
- [ ] 不新增 receipt kind
- [ ] 不新增 API write route
- [ ] 不新增 registry
- [ ] 不新增 Agent capability profile
- [ ] 不新增 Action / Authority / TradePlan / Paper object
- [ ] 不新增 docs-current 强绑定事实
- [ ] CI checks green, or failure explained as pre-existing/unrelated

例外理由（如有）：

## Change Classification

<!-- 按 change-control.md 归类 -->

- [ ] C0 — 文档、小修、测试补充、重命名、依赖升级
- [ ] C1 — 单模块功能改动
- [ ] C2 — 跨模块 / 用户可见 / 默认行为变化
- [ ] C3 — 财务 / 投资 / 税务 / 联网 / 自动化 / 安全边界

## Self-Check

- [ ] `task check` 通过
- [ ] 无新增 lint / typecheck / test 失败
- [ ] 如果是 deletion: 在 removal-ledger.yml 中记录
- [ ] 如果是 bridge read model: 不改 StateCore schema、不删旧 endpoint、不新增 write route
- [ ] 如果是 reclassification: 旧路径保留 compatibility wrapper
