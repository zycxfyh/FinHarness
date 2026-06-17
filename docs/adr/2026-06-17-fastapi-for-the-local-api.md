# ADR: FastAPI 作为本地后端 API 层

Date: 2026-06-17
Status: accepted
Deciders: FinHarness project operator and Claude

## Context

状态核心(见 SQLite ADR)需要一个对外表面,让运行时和未来的 cockpit 能**读状态、
提交提案**。现状没有任何后端 API(`pyproject.toml` 无 FastAPI/Flask/Django)。

约束:① Python 控制面 ② 全仓已用 Pydantic ③ 北极星硬原则"默认只读、AI 无授权"——
API 里**不允许存在任何动钱端点**。

## Decision

用 **FastAPI** 作为本地 API 层。

```text
- 直接复用全仓已有的 Pydantic 模型当请求/响应 schema, 零翻译层。
- 仅暴露三类端点: 读(state/snapshots/diff/proposals/receipts)、
  提案(POST /proposals)、人工确认(POST /proposals/{id}/attest)。
- 不存在下单/转账/改风险上限端点; 不存在 execution_allowed=true 的写路径。
- 执行永远走仓库已有的 CLI + 门(okx_live_gate 等), 不经 API。
```

## Considered Options

### Option 1: 不做框架, 只用脚本/CLI

Pros:

```text
最简单, 与现状一致
```

Cons:

```text
没有类型化的 HTTP 表面, 未来 cockpit 前端难以构建
读/提案/确认 缺少统一、自带校验的入口
```

### Option 2: Flask

Pros:

```text
成熟、简单、生态大
```

Cons:

```text
不内置校验/类型/文档, Pydantic 要自己拼
FastAPI 约等于 Flask + 类型 + 校验 + 文档(内置)
```

### Option 3: FastAPI(选定)

Pros:

```text
Pydantic 原生 → 与全仓数据契约零翻译
自动生成 OpenAPI 文档 + 入参校验, 免费拿到类型化自文档接口
async 友好(broker / LLM 这类 I/O)
行业标准、维护活跃
```

Cons:

```text
只是 API 层, 不是"全能框架" —— 对我们正合适
```

### Option 4: Django(+DRF)

Pros:

```text
电池齐全(ORM/admin/auth)
```

Cons:

```text
太重, 其重量是给大型网站的
单用户本地 API 用它是纯负担
```

## Consequences

Positive:

```text
未来 cockpit(阅读/比较/复核/确认/归档)可直接构建在这套类型化端点上。
"默认只读、AI 无授权"从架构上被保证: API 里根本不存在动钱路径。
与 SQLite/Pydantic 同栈, 无翻译层。
```

Negative:

```text
新增一个需要启动的本地服务(task api:serve)。
```

Neutral:

```text
执行权仍在已有 CLI + 门, 与 API 解耦 —— 这是有意为之, 不是缺陷。
```

## Confirmation

本决策生效的标志:

```text
端点直接复用 Pydantic 模型, 自动产出 OpenAPI 文档。
API 中不存在任何下单/转账端点, 也没有 execution_allowed=true 的写路径。
未来 cockpit 能基于这套端点构建, 无需绕过后端边界。
```

## Links

```text
docs/product-north-star.md
docs/proposals/2026-06-17-state-core-and-api.md
docs/adr/2026-06-17-sqlite-for-the-state-core.md
```
