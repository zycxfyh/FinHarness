# System Directory Standard — EOS

状态:v0(2026-06-23)。把 [G5 architecture-principles](./architecture-principles.md) 里"每个 system 固定形状"
**落成具体、可照抄的标准**,以 **Review System 为参考实现**(reference)。配合 [system-map](../architecture/system-map.md)。

目的:**新代码按固定形状长,不再每个 slice 临时长一套**。这是从 slice-first 到 system-first 的肌肉。

## 固定形状(6 角色)

| 角色 | 职责 | 不放什么 |
| --- | --- | --- |
| **domain** | 核心对象 + 不变量(模型、closed enums、DB 约束、构造校验) | 不放 HTTP/CLI/渲染 |
| **commands** | 受治理的写(唯一 id → receipt → DB,失败清理);execution_allowed=false | 不放只读、不放 adapter |
| **read_model** | 只读 DTO(纯函数:输入 engine/roots → DTO);供 adapter 消费 | **不写、不重算**已有口径 |
| **adapters** | API / CLI / frontend——只做协议转换,调 commands/read_model | **不放业务不变量** |
| **fixtures** | system 级**共用**测试 setup(隔离库 + seed helpers) | 不每个测试自造 temp DB |
| **governance** | 该 system 的可枚举红线探针(进 `governance:check`) | 不靠 reviewer 记忆 |

## 参考实现:Review System

| 角色 | 文件 |
| --- | --- |
| domain | [`statecore/models.py`](../../src/finharness/statecore/models.py)(Proposal/Attestation/ReviewEvent + DB CheckConstraint)、[`statecore/proposals.py`](../../src/finharness/statecore/proposals.py)(`_safe_id`/校验) |
| commands | `statecore/proposals.py`:`create_governed_proposal` / `create_governed_attestation` / `create_governed_review_event`(唯一 id → `resolve_under` receipt → DB,`StateCoreStoreError` 清理) |
| read_model | [`review_read.py`](../../src/finharness/review_read.py):`read_proposal_timeline` / `read_retrospective` / `read_compare_marks`(纯只读 DTO) |
| adapters | [`api/routes_proposals.py`](../../src/finharness/api/routes_proposals.py)、[`api/routes_review.py`](../../src/finharness/api/routes_review.py)(薄 HTTP)、`frontend/app.js` 的 review renderers |
| fixtures | [`tests/_review_fixtures.py`](../../tests/_review_fixtures.py)(`ReviewFixture`:隔离库 + proposal/attest/event helpers) |
| governance | [`tests/_policy_registry.py`](../../tests/_policy_registry.py)(`PolicyRule` 注册表:`GOV-REVIEW-001` 等带 id/owner/scope/source/check)+ 薄 driver `tests/test_governance_invariants.py` |

> 这套形状已被 R2/R3/R4 + Golden Path 反复验证;新 read model(timeline→retrospective→compare)是**在 read_model 层扩展**,
> 不是在 route 散点——这就是标准要复制的行为。

## Fixture 标准化样板

| System | Fixture | 职责 |
| --- | --- | --- |
| Review System | [`tests/_review_fixtures.py`](../../tests/_review_fixtures.py):`ReviewFixture` | 隔离 State Core + proposal/attestation/review_event seed helpers |
| State Core | [`tests/_statecore_fixtures.py`](../../tests/_statecore_fixtures.py):`StateCoreFixture` | 隔离 sqlite + receipt root + JSON receipt writer |

这些 fixture 是渐进迁移目标,不是一次性大搬家。新 State Core / Review System 测试优先复用它们;
旧测试只在触碰相关区域时迁移。

## 扩展一个已有 system(checklist)
- [ ] 新写 → 进 **commands**(governed,receipt,失败清理),不在 adapter 里直接写。
- [ ] 新只读 → 进 **read_model**(纯 DTO),adapter 只映射;**第 3 次同类 → 必抽共享**(G5 原则 3)。
- [ ] 新测试 → 复用 system **fixtures**,不自造 temp DB。
- [ ] 新红线/边界 → 进 **governance** 探针。
- [ ] mini-RFC 的 Module Placement 节声明归属 + 是否第 3 次散点。

## 新建一个 system(checklist)
- [ ] 在 [system-map](../architecture/system-map.md) 登记:职责 + domain/read/command/adapters/invariants。
- [ ] 至少先有 domain + 一个 read_model + fixtures;commands/adapters 随首个用例。
- [ ] 依赖方向单向(被消费,不反向驱动 cockpit);跨 system 在 mini-RFC 说明边界。

## 机器约束(标准不只是文档)
`tests/_policy_registry.py::GOV-ARCH-001` 断言 **Review System 参考实现的 6 角色文件都存在**——
参考实现若被删/改名,`governance:check` fail,标准不会悄悄烂掉。(承我复盘:架构文档要是"会 fail 的契约"。)
`GOV-ARCH-002` 断言 State Core / Review System 的 shared fixture 样板存在。

## 不是什么
- 不是一次性大重构:**旧代码渐进对齐,新代码按此长**。
- 不是框架化:前端先按 render 分区(view contract),不引 React。
- 不是 microservices:modular monolith,边界靠接口。
