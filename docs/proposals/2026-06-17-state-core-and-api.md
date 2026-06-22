# 提案:状态核心(数据库)+ 后端 API —— 第一层地基

> 类型:开工前方案(pre-action plan)。状态:待 operator 拍板。
> 对应北极星:[docs/product-north-star.md](../product-north-star.md) 的"核心三件事 #1 状态核心是地基"。

## 1. 现状(为什么这是新东西)

- **没有数据库,也没有后端 API。** 所有状态是 `data/` 下的 JSON/Markdown 文件;
  `pyproject.toml` 里没有 SQLite/Postgres/SQLAlchemy/FastAPI。
- 已有强约定,**新代码必须沿用**:
  - 状态记录都是 **Pydantic** 模型,带 `schema_version`。
  - 写入**原子化**(tmp→replace),读到损坏文件**fail-closed**(不静默给干净状态)。
  - **Receipts 是不可变文件证据**,内容寻址(`receipt_id`),靠文件路径互相引用。
  - 代码已明确区分两层:**state ≠ evidence**——"store is state, not evidence;
    receipts remain the evidence layer"(`trading_state_store.py`)。

## 2. 设计原则(三层各自的边界)

1. **证据层不动:Receipts 仍是 append-only 的不可变文件。**
   它们是审计资产、git 友好、已被全仓按路径引用。**不迁进数据库。** 数据库里
   只存一个**只读索引**(receipt_id → 路径 / kind / 时间 / 交叉引用),用于快查;
   文件永远是 source of truth。

2. **数据库 = 状态核心(可查询的当前状态 + 带时间戳的快照历史)。**
   它存"现在的财务状态"和"状态随时间的快照",好让运行时算"**变了什么**"。
   这是北极星里"运行时盯 diff"的物理基础。

3. **API = 读 + 提案,永不执行。**
   读端点查状态;提案端点写 governed-advice 提案 + receipt,但**不碰钱**。
   执行权仍留在已有的 fail-closed 门(risk_gate / okx_live_gate / 人工 attestation),
   **API 里不存在任何下单/转账端点**。

## 3. 技术选型(单人本地工具的务实默认)

| 选择 | 决定 | 理由 |
|------|------|------|
| 数据库 | **SQLite** | 单用户本地、零运维、文件即库、git/备份友好、与 pragmatism-first 一致。多用户再谈 Postgres,届时换驱动不换 schema。 |
| ORM/驱动 | **SQLModel 或 sqlite3 + Pydantic** | 复用已有 Pydantic 契约;模型即表。倾向 SQLModel(Pydantic 原生)。 |
| API 框架 | **FastAPI + Pydantic** | 与 Python 控制面一致,自带类型校验与 OpenAPI。 |
| 迁移 | 轻量(Alembic 可选,初期手写 `schema_version` 守) | 初期表少,先不上重型迁移。 |

## 4. 范围纪律(这一版只建什么)

按北极星"状态核心要通用、但只填第一条竖线需要的东西":
- **建**:`accounts`、`positions`、`snapshots`、`receipt_index`、`proposals`、`attestations`。
- **只填**:portfolio/持仓 + 市场上下文(对接已有 daily-evidence / broker read)。
- **留作扩展点、本版不建表**:现金流、税务事件、负债、保险。它们是后续驾驶舱的
  视图来源,等第一条竖线跑通、且真的改变过一次决策后再加。

## 5. 数据模型(最小集,英文标识符给实现用)

每张状态表都带三个公共列(沿用现有约定):
`schema_version`、`as_of_utc`、`source_refs`(→ 指向 receipt 文件路径的列表)。
另加治理列 `authority_level`(把"治理是状态的属性"落成一列)。

```text
accounts
  account_id        TEXT PK
  kind              TEXT   -- broker | bank | crypto | manual | ...
  venue             TEXT   -- alpaca-paper | okx | manual | ...
  authority_level   TEXT   -- read_only | needs_human_confirm | never_auto
  display_name      TEXT
  schema_version    TEXT
  created_at_utc    TEXT

positions               -- 每行是某次快照里的一个持仓(append, 不就地改)
  position_id       TEXT PK
  snapshot_id       TEXT FK -> snapshots
  account_id        TEXT FK -> accounts
  symbol            TEXT
  quantity          REAL
  market_value      REAL
  cost_basis        REAL    -- nullable; 不可算时留空, 不臆造
  as_of_utc         TEXT
  source_refs       JSON

snapshots               -- diff 的基底: 一次"当时的状态"
  snapshot_id       TEXT PK
  kind              TEXT   -- portfolio | market_context | ...
  as_of_utc         TEXT
  payload           JSON   -- 规范化后的完整快照(也可只存指针)
  source_refs       JSON
  schema_version    TEXT

receipt_index           -- 只读索引; 文件才是 source of truth
  receipt_id        TEXT PK
  kind              TEXT
  path              TEXT   -- data/receipts/<...>.json
  created_at_utc    TEXT
  refs              JSON   -- 交叉引用的其它 receipt_id / payload 路径

proposals               -- governed advice; 永不等于执行
  proposal_id       TEXT PK
  kind              TEXT   -- rebalance | risk_alert | cash_reserve | ...
  claim             TEXT
  evidence          JSON
  assumptions       JSON
  limitations       JSON
  non_claims        JSON   -- 明确"它不主张什么"
  authority_level   TEXT   -- 默认 needs_human_confirm
  execution_allowed BOOLEAN DEFAULT 0   -- 永远 0, 除非走完 attestation+门
  receipt_ref       TEXT
  created_at_utc    TEXT

attestations            -- 人工确认 (fail-closed)
  attestation_id    TEXT PK
  proposal_id       TEXT FK -> proposals
  attester          TEXT
  reason            TEXT    -- 必填, 书面理由
  decision          TEXT    -- approved | rejected
  created_at_utc    TEXT
```

> fail-closed 守则沿用现有代码:读到损坏/缺失状态不得静默给"干净"结果;
> `cost_basis` 等不可计算的字段留空,**绝不臆造**(对应 trading_state_store
> 的"fake fills carry no P&L"诚实原则)。

## 6. 后端 API 表面(只读 + 提案 + 确认)

```text
读 (read-only)
  GET  /state/accounts
  GET  /state/positions?as_of=latest
  GET  /snapshots?kind=portfolio&limit=...
  GET  /diff?kind=portfolio&since=<snapshot_id|utc>   -- "变了什么"
  GET  /proposals?status=open
  GET  /receipts/{receipt_id}                          -- 经索引取文件

提案 + 确认 (写, 但永不动钱)
  POST /proposals                  -- 写 governed-advice 提案 + receipt
  POST /proposals/{id}/attest      -- 人工 approve/reject + 书面理由

明确不存在
  ✗ 任何下单 / 转账 / 改风险上限 / 报税提交端点
  ✗ 任何 execution_allowed=true 的写路径
```

执行永远走仓库已有的 CLI + 门(`okx:live-write` 等),不经 API。这是"默认只读、
AI 无授权"的物理保证。

## 7. 与现有代码的关系(增量,不是替换)

- `trading_state_store.py` 等文件式状态**保留**;状态核心是**新增的、加性的**一层。
  可先让 DB 旁路镜像现有 JSON,验证一致后再决定谁是 source of truth。
- Receipts / `data/normalized/` / LangGraph 图**全部不动**。新层从它们**读**,
  把规范化结果写进 snapshots,并在 receipt_index 建索引。
- "diff 引擎"是 `snapshots` 上的一个查询,不是新引擎——守住"不自建引擎"的边界。

## 8. 实施切分(给 Codex 的执行顺序)

1. **存储层**:SQLModel 模型 + SQLite store(原子写、fail-closed),含上面 6 张表
   + 公共列。单测覆盖损坏/缺失 fail-closed。
2. **快照接入**:从已有 daily-evidence / broker read 落一个 `portfolio` snapshot,
   并在 receipt_index 建索引。
3. **diff 查询**:`/diff` 的核心——两个 snapshot 之间的持仓/敞口变化。
4. **只读 API**:FastAPI app + 读端点 + OpenAPI;`task api:serve` 起本地服务。
5. **提案 + 确认**:`/proposals`、`/attest`,写 receipt,`execution_allowed` 恒 0,
   attestation fail-closed。
6. (验收)用 `/diff` 产出一条"相对昨天变了什么"的态势变化,落 receipt——第一条
   竖线的最小可见成果。

## 9. 验收口径(对齐北极星的"治理形态成功指标")

- 能否**仅凭 receipt + DB 记录**重建一次提案:看到了什么状态、变化是什么、
  AI 提了什么、人为什么 approve/reject、execution 是否被挡。
- 全程没有任何"动钱"的代码路径存在。
- 加一个新状态类型(如 cashflow)时,是新增 view/表行,**不是重写核心**。

## 10. 待 operator 拍板的点

1. 选型默认(SQLite + SQLModel + FastAPI)是否同意?
2. 第一条竖线的可见成果定为"每天的持仓/敞口 diff 简报",是否同意?
3. 实现是否照惯例**交给 Codex 执行**(本提案即 spec),还是要我先 scaffold 骨架?
