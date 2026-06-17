# ADR: SQLite 作为状态核心数据库

Date: 2026-06-17
Status: accepted
Deciders: FinHarness project operator and Claude

## Context

北极星([docs/product-north-star.md](../product-north-star.md))把"可查询的状态
核心"定为地基。现状是:全部状态存在 `data/` 下的 JSON/Markdown 文件,没有数据库
(`pyproject.toml` 无 SQLite/Postgres/SQLAlchemy)。JSON 文件的痛点正是我们要解决的:
查不了、做不到多记录原子更新、diff 低效。

约束(决定选型的四个前提):① 单用户 ② 本地跑 ③ Python 控制面 ④ 全仓已用 Pydantic。
另有一条现有纪律必须继承:原子写(tmp→replace)、读到损坏 fail-closed
(`trading_state_store.py`)。

## Decision

用 **SQLite** 作为状态核心数据库。

```text
- 访问层用 SQLModel(Pydantic 原生)或 sqlite3 + Pydantic,复用已有模型契约。
- 开启 WAL 模式,缓解多进程并发写。
- Receipts 不进库:它们是不可变文件证据,库里只存只读索引(receipt_id→路径)。
- 每张状态表带公共列 schema_version / as_of_utc / source_refs,外加治理列
  authority_level——把"治理是状态的属性"落成一列。
```

将来若真要多用户/联网,SQLite→Postgres 由 SQLModel/SQLAlchemy 承接,基本只换驱动、
不换 schema。届时另写 ADR 取代本条。

## Considered Options

### Option 1: 继续用 JSON 文件

Pros:

```text
零新依赖
极简, 与现状一致
```

Cons:

```text
无法查询
做不到多记录原子更新
diff 低效 —— 正是我们要解决的痛
```

### Option 2: SQLite(选定)

Pros:

```text
零运维, 整库就是一个文件
ACID 事务 = 原子写, 正好接上现有 fail-closed 纪律
Python 标准库自带 sqlite3, 连驱动都不用额外装
世界上部署最多的数据库, 稳定到会比项目活得久
单文件 → 备份就是复制一个文件, 可版本化
```

Cons:

```text
怕多进程同时写 → 用 WAL 模式缓解(单用户单进程下基本无感)
```

### Option 3: PostgreSQL / MySQL

Pros:

```text
多用户、高并发、网络访问
```

Cons:

```text
要跑服务器、管用户权限、运维
单用户本地下是纯 overhead, 推迟到真多用户再说
```

### Option 4: DuckDB

Pros:

```text
分析型查询极快(列存)
```

Cons:

```text
擅长只读分析、不擅长实时状态的行更新
更适合将来分析 receipt 历史, 不当状态核心
```

## Consequences

Positive:

```text
状态从此可查询、可原子更新、可高效 diff —— 运行时"盯变化"有了物理基础。
备份/恢复变得几乎免费(复制单个文件)。
与 Pydantic/控制面同栈, 无翻译层。
```

Negative:

```text
新增一层持久化, 初期需与现有 JSON 状态并存/对账后再定 source of truth。
多进程写需记得开 WAL。
```

Neutral:

```text
Receipts 与 data/normalized/ 不动, 仍是文件。
向 Postgres 的迁移路径保持开放, 但当前无此需要。
```

## Confirmation

本决策生效的标志:

```text
状态可被 SQL 查询、支持多记录原子更新、读到损坏时 fail-closed。
备份 = 复制一个文件即可。
Receipts 仍是不可变文件, 库内仅有只读索引。
将来若上 Postgres, 是换驱动而非重写 schema。
```

## Links

```text
docs/product-north-star.md
docs/proposals/2026-06-17-state-core-and-api.md
src/finharness/trading_state_store.py(现有文件式状态, 继承其 fail-closed 纪律)
```
