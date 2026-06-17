# 执行手册:状态核心 + API(第一条竖线)

> 类型:执行手册(给 Codex)。设计依据见下方 Links 的 ADR/提案/北极星。
> 角色分工:Claude 设计/审查,Codex 执行。每个任务做完即可独立验收。

## 0. 锁定的技术栈(由 ADR 决定,不要再讨论)

```text
DB        SQLite + SQLModel, 开 WAL
API       FastAPI(+ uvicorn)
配置/密钥  pydantic-settings + keyring(broker key)
日志      structlog
调度      cron / systemd timer(本手册不涉及, 沿用 hermes)
备份      task backup = sqlite VACUUM INTO + tar receipts
```

## 1. 依赖(加进 pyproject.toml,用 uv)

```text
runtime: sqlmodel, fastapi, "uvicorn[standard]", pydantic-settings, structlog, keyring
dev:     pytest(若未配置), httpx(FastAPI TestClient 用)
```

加完跑 `uv sync` 并更新 lockfile。

## 2. 代码布局(新层用子包,现有扁平模块不动)

```text
src/finharness/statecore/
  __init__.py
  models.py          SQLModel 表: Account, Position, Snapshot, ReceiptIndex,
                     Proposal, Attestation。公共列 schema_version/as_of_utc/
                     source_refs, 治理列 authority_level。
  store.py           open/init(WAL)、原子写、读到损坏 fail-closed(对齐
                     trading_state_store.py 的纪律)。
  diff.py            两个 snapshot 间的持仓/敞口差异 → "变了什么"。
  receipt_index.py   扫 data/receipts/** 建只读索引(文件仍是 source of truth)。
src/finharness/api/
  __init__.py
  app.py             FastAPI app + structlog 中间件。
  routes_state.py    只读端点。
  routes_proposals.py 提案 + 人工确认。
src/finharness/config.py      pydantic-settings(BaseSettings) + keyring 取密钥。
src/finharness/runtime_log.py structlog 配置。
scripts/backup.py             task backup 的实现。
tests/                        每个模块配单测。
```

## 3. 不可逾越的护栏(审查会逐条查)

```text
- API 中不存在任何下单/转账/改风险上限端点;无 execution_allowed=true 写路径。
- Proposal.execution_allowed 恒为 0/False。
- Receipts 不进库, 只建索引;文件永远是 source of truth。
- 不可计算的字段(如 cost_basis)留空, 绝不臆造。
- 读到损坏/缺失状态 fail-closed, 不静默给"干净"结果。
- 不自建引擎: diff 只是 snapshot 上的查询, 不是新策略/会计/路由引擎。
- 复用现有 Pydantic 约定与 schema_version, 不另起一套。
```

## 4. 任务序列(每个独立验收;按序做)

### T1 — 存储层
交付:`statecore/models.py` + `store.py`,6 张表 + 公共列,WAL,原子写。
验收:单测覆盖"建库/写读往返/损坏文件→fail-closed";`task lint` + `task test` 通过。
审查门:表结构对齐提案第 5 节;fail-closed 行为与 trading_state_store 一致。

### T2 — 快照接入 + receipt 索引
交付:从已有 daily-evidence / broker read 落一个 `portfolio` snapshot;`receipt_index.py` 扫描建索引。
验收:能从一次真实/样例输入生成一个 snapshot 行,并在 receipt_index 查到对应 receipt。
审查门:source_refs 正确指回 receipt 文件路径。
跟进(审查发现,非阻断):批量索引的 fail-closed 不一致——非对象 JSON(如 `[]`)被
优雅标记为 `raw_json_*` 并继续,但**不可读/非法 JSON 会让整个 14k 文件的索引整体中止**。
应让批量路径(`build_receipt_index_records`/`index_receipts`)对单文件错误记一条
错误标记行(如 `kind="unreadable_json"` + 错误信息)并继续,保留 fail-closed 的
"可见性"而不让一个坏文件让整个审计目录静默变黑。单文件入口保持严格。

### T3 — diff 查询
交付:`diff.py`,给两个 snapshot_id 返回持仓/敞口变化。
验收:单测:构造两份 snapshot,断言新增/减少/变动被正确识别。
审查门:是纯查询,无任何决策/建议逻辑混入。

### T4 — 只读 API
交付:`api/app.py` + `routes_state.py`:`/state/accounts`、`/state/positions`、`/snapshots`、`/diff`、`/receipts/{id}`;`task api:serve`。
验收:TestClient 跑通各端点;OpenAPI 自动生成;端点复用 Pydantic 模型。
审查门:确认无任何写/执行端点存在。
硬化(并发前必做):用 `event.listens_for(engine, "connect")` 在每个新连接上设
`PRAGMA foreign_keys=ON`。现状靠连接池复用碰巧生效,多线程服务下新连接默认 OFF,
外键会静默失效。加回归测试:写入孤儿外键(指向不存在的 snapshot/account)应被拒。

### T5 — 提案 + 人工确认
交付:`routes_proposals.py`:`POST /proposals`(写提案+receipt)、`POST /proposals/{id}/attest`(approve/reject + 书面理由)。
验收:提案落库且写出 receipt 文件;attest 无理由时 fail-closed 拒绝;execution_allowed 始终 False。
审查门:逐条对照第 3 节护栏。

### T6 — 配置/日志/备份(支撑层)
交付:`config.py`(pydantic-settings + keyring)、`runtime_log.py`(structlog)、`scripts/backup.py` + `task backup`。
验收:broker key 经 keyring 读取(不落明文);每次运行留一条结构化日志;`task backup` 产出一致 DB 快照 + receipts 打包。
审查门:仓库内无明文 broker 密钥;data/ 备份不依赖 git。
并入 T6 的 receipt 文件健壮性(来自 T2/T5 审查,需一起收口):
  (a) `_write_json` 改原子写(tmp+rename),对齐仓库 trading_state_store 的纪律;
  (b) 提案/确认写入:DB 写失败后 best-effort 清理孤儿 receipt 文件;保留"先文件后 DB"
      的安全顺序(永不产生 DB→缺失文件的悬空指针),并在文档记录此残留窗口;
  (c) 批量 receipt 索引对单个不可读/非法 JSON 记错误标记行并继续,不整体中止
      (T2 跟进项)。(a) 与 (c) 联动:截断 receipt 不应让整个审计目录变黑。
残留窗口说明:提案/确认仍采用"先写完整 receipt 文件,再写 DB 指针"。若进程在
receipt 原子替换成功后、DB 事务提交前崩溃,可能留下孤儿 receipt 文件;普通 DB 写失败
会 best-effort 删除该文件。这个方向优先保证不会出现"DB 指向不存在 receipt"的悬空证据。
后续可通过 `receipt_index` 扫描发现孤儿或坏 receipt,但该扫描本身不是执行授权。

## 5. 完成的定义(对齐北极星的治理成功指标)

```text
- 能仅凭 DB 记录 + receipt 文件, 重建一次提案: 看到什么状态、变化是什么、
  AI 提了什么、人为什么 approve/reject、execution 是否被挡。
- 全程不存在任何"动钱"代码路径。
- 新增一种状态类型(如 cashflow)时是加表/加视图, 不是重写核心。
```

## Links

```text
docs/product-north-star.md
docs/proposals/2026-06-17-state-core-and-api.md
docs/adr/2026-06-17-sqlite-for-the-state-core.md
docs/adr/2026-06-17-fastapi-for-the-local-api.md
docs/adr/2026-06-17-supporting-runtime-infrastructure.md
```
