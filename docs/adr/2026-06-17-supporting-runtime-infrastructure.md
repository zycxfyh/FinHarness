# ADR: 支撑型运行时基础设施(密钥 / 日志 / 调度 / 备份)

Date: 2026-06-17
Status: accepted
Deciders: FinHarness project operator and Claude

## Context

运行时还需要四样支撑型基础设施:配置/密钥、运行日志、定时触发、备份。每一样都有
从轻到重的成熟工具。约束:① 单用户本地 ② 现有"adopt not invent、保持本地薄"法律
③ broker key 是这里风险最高的秘密(它能动钱)。

本 ADR 记录的是一个**统一姿态**:每样都"采用最无聊的轻量默认、推迟重型系统",直到
某样真有需要时再为它单独写 ADR 取代本条相应部分。这符合本仓"docs should scale with
impact"的原则——这四样目前都不是深度承诺。

## Decision

```text
配置/密钥: pydantic-settings(类型化配置) + keyring(broker key 进操作系统钥匙串,
           不落明文); direnv 留作开发便利。推迟 Vault/云密钥管理器。
日志/可观测: structlog 写结构化运行日志(成功否/耗时/报错)。LLM 侧因用 LangGraph,
           待运行多了再上 Langfuse(开源可自托管)或 LangSmith 看 prompt/成本。
           推迟 Prometheus/Grafana/OTel。Receipts 仍是领域审计日志。
调度/后台: 操作系统 cron / systemd timer(hermes 已在用)。推迟 APScheduler/Celery/
           Airflow/Temporal。注意区分: "一次运行内编排步骤"已由 LangGraph 承担,
           cron 只负责"按时触发这次运行"。
备份/恢复: task backup = SQLite VACUUM INTO(一致快照) + 打包 receipts 到带日期文件
           (可选 rclone 推云)。想零操心持续备份再上 litestream。注意 data/ 多半被
           gitignore, 别指望 git 兜底。
```

## Considered Options

### Option 1: 现在就上生产/团队级(Vault + Langfuse + Airflow + restic)

Pros:

```text
可扩展、功能完整、面向多人/生产
```

Cons:

```text
对单用户本地过早; 是会重塑项目的重型承诺
徒增运维与认知负担, 当前零收益
```

### Option 2: 轻量默认now / 重型defer(选定)

Pros:

```text
每样都用操作系统自带/标准库/Pydantic 原生的最无聊选项, 便宜好删
broker key 这一最高风险项得到实质加固(进钥匙串)
与"adopt not invent、保持本地薄"一致
重型系统留作"真有需要再单独 ADR 引入"
```

Cons:

```text
将来某样若需升级, 要再写一份取代本条的相应部分(这正是 ADR 的正常生命周期)
```

### Option 3: 什么都不做 / 临时拼凑

Pros:

```text
零前期投入
```

Cons:

```text
密钥留在明文文件(碰钱碰 key, 不可接受)
运行无可见性, 出问题两眼一抹黑
无备份 → 财务状态与决策档案一旦丢失无法再生
```

## Per-Item: now vs later

```text
密钥/配置    now: pydantic-settings + keyring + direnv     later: Vault/云密钥管理
日志/可观测  now: structlog 运行日志                        later: Langfuse/LangSmith, 监控系统
调度/后台    now: cron / systemd timer(已有)               later: APScheduler/Celery/Airflow
备份/恢复    now: task backup(VACUUM INTO + tar)           later: litestream/restic + 云
```

## Consequences

Positive:

```text
最高风险的 broker key 离开明文文件。
运行时有结构化日志, 出错可定位。
财务状态有最便宜的"后悔药"。
没有任何重型系统被过早引入。
```

Negative:

```text
新增几个轻量依赖(pydantic-settings/structlog/keyring)与一条 task backup。
```

Neutral:

```text
LangGraph 仍负责单次运行内的编排; cron 只负责触发, 两者不重叠。
Receipts 仍是领域审计日志, 运行日志是其补充而非替代。
```

## Confirmation

本决策生效的标志:

```text
仓库内不存在明文 broker 密钥。
每次运行时执行都留下一条结构化运行日志。
存在一条可一键产出一致备份的 task backup。
没有 Vault/Airflow/Celery/Prometheus 这类重型系统被引入。
```

## Links

```text
docs/product-north-star.md
docs/proposals/2026-06-17-state-core-and-api.md
docs/adr/2026-06-17-sqlite-for-the-state-core.md
docs/adr/2026-06-17-fastapi-for-the-local-api.md
```
