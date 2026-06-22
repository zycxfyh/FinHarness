# 执行手册:G09 配置上限 vs 单次请求的硬隔离

> 类型:执行手册(给 Codex)。角色分工:Claude 设计/审查,Codex 执行。
> 这是 Next 段最后一块;焊完 Next 段清零,之后只剩 Later(前端/可观测性)。
> 设计依据:gap register G09、北极星硬原则、B4 血缘(lesson→rule→receipt)。
> 不需要新 ADR:扩展现有刹车与已成熟的血缘机制,非新技术选型。

## 0. 要堵的精确漏洞(先看清楚)

```text
现状: okx_live_gate.LiveOrderRequest.max_notional 是【请求上的字段】(默认 50,
      调用方可传任意值), 门用 `notional > request.max_notional` 判断。
后果: 请求自己决定自己的上限 —— CLI 传 max_notional=10000 就把刹车从 50 抬到 10000,
      注释 okx_live_gate.py:53 "Override only upward" 正是这条自由覆盖路径。
G09:  上限(ceiling)必须与单次请求(request)硬隔离。请求只能【收紧】, 永远不能抬升
      生效上限; 抬升 ceiling 本身必须经【可追溯的 rule-change 或 owner 收据】, 任何
      CLI 标志/env/改配置都不得悄悄抬升。
```

## 1. 核心设计(复用现成血缘范式,不另造)

```text
两个概念硬分开:
  configured_ceiling  人类拥有的最大值。不在请求上, 由受治理的来源解析。
  request_limit       单次调用请求的值(原 request.max_notional)。只能收紧。
生效上限 enforced_cap = min(request_limit, effective_ceiling)
  - request_limit > effective_ceiling → 取 effective_ceiling(请求无法抬升), 并在
    receipt 记 "request_limit_clamped_to_ceiling"; 绝不让请求成为生效上限。
  - 未配置 ceiling → fail-closed 拒绝(账本已是此行为, 保持)。

effective_ceiling 的解析(镜像 effective_rules.resolve_guard_thresholds):
  effective_ceiling = default_ceiling 叠加【仅】满足以下之一的提升:
    (a) rule_change_ledger 里 active 且 is_traceable(lesson→receipts)、带 attester、
        rule_target 命中 ceiling 命名空间(如 `ceiling.max_live_notional`)的变更; 或
    (b) control_owner 的认证收据显式授权该 ceiling 的更高值。
  返回 (effective_ceiling, provenance, ignored), provenance 指回 rule_change_id /
  owner certification_id。没有任一来源 → effective_ceiling == default_ceiling。
  ceiling 解析与 guard 阈值解析互不串味(ceiling.* 命名空间独立)。
```

## 2. 不可逾越的护栏(审查逐条查)

```text
- 这仍是【刹车】: 只约束上限或要求血缘才能放松; 不新增任何执行权;
  execution_allowed 不受影响。
- 请求永远不能抬升生效上限: 代码层面 enforced_cap <= configured/effective_ceiling 恒成立。
- 抬升 ceiling 的唯一路径 = 可追溯 rule-change 或 owner 收据; 无 CLI/env/配置后门。
- 复用 rule_change_ledger / control_owner / effective_rules 范式, 不另造血缘。
- fail-closed: 无 ceiling 配置 → 拒绝; ceiling 来源不可读 → 拒绝, 不回退到"无限"。
- 不可追溯/无 attester 的变更被拒(rule_change_ledger 已强制, 保持并测试)。
- 同时作用于两处上限: okx_live_gate 的 notional cap 与 market_access_ledger 的
  MarketAccessLimit 来源, 二者都从受治理解析取 ceiling, 不从请求取。
```

## 3. 任务序列

### C1 — 受治理的 ceiling 解析器(复用范式)
交付:
```text
src/finharness/effective_ceilings.py(新; 或并入 effective_rules.py)
  resolve_effective_ceiling(*, field, default_ceiling, rule_changes, owner_certs)
    -> (effective_ceiling, provenance, ignored)
  - 只接受 active + is_traceable + 有 attester + rule_target 命中 ceiling.<field> 的变更;
  - 或 control_owner 认证显式授权更高值;
  - 无来源 → 返回 default_ceiling, provenance 空。
```
验收:
```text
- 单测: 无变更 → effective==default; 一条可追溯 rule-change → effective 提升 + provenance
        指回 rule_change_id; 无 attester / 不可追溯的变更 → 被忽略(effective 不变);
        owner 认证授权更高值 → 提升 + provenance 指回 certification_id。
- 与 guard 阈值解析互不影响(各自命名空间)。
- task lint + task test 通过。
```
审查门:无血缘 → 默认值;ceiling.* 与 guard.* 不串味。

### C2 — 两处上限的硬隔离
交付:
```text
okx_live_gate:
  - 将 LiveOrderRequest.max_notional 语义改为 request_limit(只能收紧)。
  - configured/effective ceiling 改由 resolve_effective_ceiling 取得, 不取自请求。
  - enforced_cap = min(request_limit, effective_ceiling); 门改用 enforced_cap 判断。
  - 删除/改写 okx_live_gate.py:53 "Override only upward" 注释与其语义。
market_access_ledger:
  - 调用点的 MarketAccessLimit 由受治理解析取得(ceiling 不来自请求/CLI)。
  - evaluate_market_access 行为不变(仍 fail-closed when limit is None)。
```
验收:
```text
- 单测: request_limit 高于 ceiling → enforced_cap==ceiling(被收紧), 且 receipt 记
        request_limit_clamped_to_ceiling; notional 超 enforced_cap → 拦截。
- 单测: 不存在任何使 enforced_cap > configured/effective ceiling 的输入路径
        (含 CLI/env)。
- task lint + task test 通过。
```
审查门:enforced_cap <= ceiling 恒成立;请求无法抬升;无 CLI/env 后门。

### C3 — receipt 证据 + "抬升不可绕过"回归测试
交付:
```text
- live-gate / market-access receipt 暴露: configured_ceiling、effective_ceiling、
  provenance、request_limit、enforced_cap, 并标注 enforced_cap <= ceiling。
- 一条核心回归测试: 仅凭 CLI/env/改请求【无法】抬升生效上限; 唯有写入一条可追溯
  rule-change(带 attester)或 owner 认证后, 生效上限才上升, 且 receipt 带 provenance。
```
验收:
```text
- 该回归测试同时断言: 无血缘时抬升尝试被收紧/拦截 + 有血缘时上升并留 provenance。
- task check + task security:scan 全绿, release_blocked=false, execution_allowed=false。
```
非声明(写进 receipt):`不批准更高风险`(有血缘地抬升上限不等于该风险变安全, 只是可追溯)。
审查门:把 gap 的 evidence "cap-raising path is impossible without lineage and human
attestation" 编码成可执行断言。

## 4. 完成定义(对齐 gap register 的 evidence 列)

```text
- 抬升生效上限的路径在无【可追溯 rule-change 或 owner 收据】时【不可能】(被测试证明)。
- 请求/CLI 只能收紧, 永不抬升; enforced_cap <= ceiling 恒成立。
- 两处上限(live notional、market-access)都从受治理解析取 ceiling。
- 加这块没有重写刹车(纯增量: 新 ceiling 解析器 + 两处取值改造 + receipt 字段 + 测试)。
- Next 段自此清零。
```

## 5. 待 operator 拍板

```text
1. ceiling 提升的授权来源 = 可追溯 rule-change(lesson→receipt)【或】control-owner 认证,
   二者任一即可 —— 是否同意?(我的建议: 两者都收, owner 收据覆盖"无 lesson 但人类明确
   决定"的情形)
2. ceiling 变更用独立命名空间 ceiling.*(不与 guard.* 阈值混) —— 是否同意?
```

## Links

```text
docs/product-north-star.md
docs/architecture/industry-benchmark/03-gap-register-codex.md(G09 权威定义)
docs/how-to/promote-lesson-to-rule.md
src/finharness/rule_change_ledger.py / effective_rules.py / control_owner.py(复用来源)
src/finharness/okx_live_gate.py(改造点 1)
src/finharness/market_access_ledger.py(改造点 2)
```
