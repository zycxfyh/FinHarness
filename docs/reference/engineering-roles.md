# Engineering Roles Cheat Sheet

这份文档用于在 FinHarness 协作中快速激活不同工程视角。角色不等于人数；小团队或 AI 协作时，一个人可以临时承担多个角色。

| Role | 负责什么 | 适合激活时机 | FinHarness 关注点 |
| --- | --- | --- | --- |
| Product Owner | 北极星、用户价值、范围取舍、优先级 | 判断该做什么、不做什么 | 守住个人财务驾驶舱，不滑向交易所或自动投顾 |
| Project Manager | 阶段计划、任务拆分、依赖、done condition | 目标模糊、任务太散 | 串起目标、需求、架构、实现、测试、发布、复盘 |
| Architect | 系统边界、模块关系、技术路线 | 设计新模块或选型 | 成熟方案优先，state core、receipt、proposal、execution 分权 |
| Tech Lead | 实现质量、复杂度、代码风格、债务控制 | 方案要落地时 | 保持小步可验收，避免治理表演或过度抽象 |
| Backend Engineer | API、业务逻辑、数据读写、权限边界 | 写服务端功能 | FastAPI、state core、import adapters、proposal、brief |
| Frontend Engineer | UI、交互、信息层级、用户工作流 | 做 cockpit 或页面 | 把数据变成态势，不用交易所式订单簿界面 |
| UX / Product Design | 用户心智、信息架构、视觉优先级 | 页面能跑但不好用 | 一屏说明有什么、变了什么、风险在哪、今天看什么 |
| Data Engineer | 数据源、schema、清洗、幂等、血缘 | 接入账本、CSV、券商数据 | Beancount、CSV、source refs、hash、重复导入、数据质量 |
| QA / Test Engineer | 测试策略、验收用例、回归风险 | 功能声称完成前 | 单测、API smoke、前端 smoke、重建性测试、边界用例 |
| Code Reviewer | bug、设计缺口、维护性、过度声明 | 审 PR 或大 diff | findings 优先，查“计划冒充完成”和“文档吹过头” |
| AppSec | 安全边界、输入验证、权限、密钥、依赖漏洞 | 处理权限、外部输入、依赖 | 不读 secrets，不泄露财务数据，approval 不能变 execution |
| Red Team | 主动攻击假设和边界 | 验证 fail-closed | 攻击 `execution_allowed=false`、receipt、attestation、前端文案 |
| SRE / Operations | 运行、备份、恢复、观测、稳定性 | 准备上线或日常运行 | `task api:serve`、SQLite/receipt backup、health、runbook |
| Release Manager | 发布门禁、变更摘要、回滚 | 合并或发布前 | `task check`、dependency approval、release preflight、rollback |
| Incident Commander | 事故止血、分工、沟通、恢复 | 出现导入错账、DB 损坏、误导性输出 | 先止血，再定位，再恢复，不在事故中扩大变更 |
| Postmortem Owner | 根因分析、行动项、规则沉淀 | 事故或阶段结束后 | 把失败写进 tests、docs、ADR、runbook，而不是只靠记忆 |
| Compliance / Risk | 声明边界、审计证据、权限隔离 | 金融语言或流程变更 | 不伪装成投顾、交易所、机构合规或自动理财许可 |
| Dependency Owner | 依赖采用、许可证、锁文件、漏洞、替代方案 | 新增或升级依赖 | Beancount、beanquery、Riskfolio、QuantStats、FastAPI 等 |
| Technical Writer | 文档、ADR、how-to、runbook、知识沉淀 | 决策需要复盘 | docs/proposals、module map、commands、import how-to |
| Customer Success | 用户验收、真实任务、可用性结果 | 判断产品是否真的有用 | 不是“有几张表”，而是用户是否更清楚自己的财务状态 |

## AI 协作建议

- Claude 适合偏实现：Backend Engineer、Frontend Engineer、Data Engineer。
- Codex 适合偏独立把关：Architect、QA、Code Reviewer、Red Team、SRE、Release Manager、Postmortem Owner。
- 避免竞态时，让一个 AI 写实现，另一个 AI 做审查、测试缺口、红队、发布运行文档。

## 常用激活句

- “以 Product Owner 身份判断这个功能是否偏离北极星。”
- “以 QA 身份给这个 slice 的测试缺口地图。”
- “以 Red Team 身份攻击 execution boundary。”
- “以 SRE 身份补运行、备份、恢复和事故处理 runbook。”
- “以 Dependency Owner 身份审查新增依赖是否值得采用。”
- “以 Code Reviewer 身份只列 findings，不做实现。”
