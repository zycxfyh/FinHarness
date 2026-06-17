# 执行手册:Next 段后端刹车(G07 授权 / G08 受限标的 / G04 TCA)

> 类型:执行手册(给 Codex)。角色分工:Claude 设计/审查,Codex 执行。
> 每个任务独立验收。建在已提交的状态核心 + G06 限额账本之上。
> 设计依据:gap register G04/G07/G08(Next 段)、北极星硬原则、后端/前端指南。
>
> 不需要新 ADR:这三项是 gap register 已授权的领域功能(扩展现有模块),
> 不是新技术选型;按"docs should scale with impact"与"不扩张治理面"两条原则,
> 本执行手册即为设计记录。

## 0. 这三项的本质(一句话定性)

```text
G07 授权模型   = 把"谁在动手"从散字符串变成类型化、可校验、fail-closed 的注册表。
G08 受限标的   = 在白名单之外加一条带版本的 deny-list + provider 可交易性证据。
G04 后交易 TCA = 给已成交的纸面订单补"到达价 vs 成交价"的 implementation shortfall
                 与完整生命周期数量对账。
```

**三项的共同性质:它们只会 *拦截* 或 *记录*,从不 *授权*。** 没有任何一项产生
执行权;`execution_allowed` 全程 False。这是"焊刹车",不是"加油门"。

## 1. 不可逾越的护栏(审查逐条查)

```text
- 全程无下单/转账/改上限/放开 live 的代码路径;execution_allowed 处处 False。
- 复用而非另造:
    G07 复用 market_access_ledger 的 (environment,venue,operator,account,symbol) 维度,
        与 okx_live_gate 的 attester 概念对齐, 不另起第二套身份概念。
    G08 在 risk_gate 现有 check() 链里加一个 deny 检查, 不绕过现有 allowed_symbols。
    G04 扩展现有 PostTradeReconciliation / PostTradeCostEstimate, 不新建并行 TCA 引擎。
- fail-closed:
    G07 未注册的 operator/account/scope/environment → 拦截, 不放行。
    G08 命中受限清单 → 拦截; provider 可交易性未知 → 标注并拦截(不静默放行)。
    G04 缺到达价/成交价 → 记 "undisclosed", 绝不臆造数字(承袭 cost_basis 纪律)。
- G07 模型/配置/receipt 中不得出现任何密钥/token/账户私钥/口令字段(gap 硬要求)。
- deny 优先于 allow:受限清单命中即拦, 即便它同时在 allowed_symbols 里。
- 每项都落 receipt, 带各自的 non-claims(见各任务)。
```

## 2. 任务序列(按依赖排序;N1 先做)

### N1 — G07 授权的 operator/account 模型(基础,先做)

交付:
```text
src/finharness/authorization.py(新)
  AuthorizedOperator: operator_id, display_name, scopes[], environments[]   (无密钥)
  AuthorizedActor    解析: 从 config 文件/注册表加载(data/security/ 或 config 指定),
                     不读任何凭证。
  AuthorizedAccount : account_id, venue, environment, operator_id, scope     (无密钥)
  authorize(*, operator, account, environment, scope) -> AuthorizationDecision
    - 校验 operator 已注册、account 已注册且归该 operator、environment/scope 在授权范围内。
    - 任一不满足 → allowed=False + 明确 reason(fail-closed)。
  把 operator/account/environment/scope/reason 织入现有 risk_gate 与 execution 的
  attestation 字段, 以及 market_access_ledger 记录(复用其 operator/account 维度)。
```
验收:
```text
- 单测: 已注册 operator+account+scope+environment → allowed;
        未注册 operator / 错配 account / 越权 scope / 错 environment 各一条 → fail-closed。
- 一条"模型与 receipt 无凭证字段"的扫描测试(禁词: key/secret/token/password/private_key)。
- risk_gate / execution 的 attestation 现在带 typed operator+account+environment+scope+reason。
- task lint + task test 通过。
```
非声明(写进 receipt):`不存储凭证`、`不证明法律授权`。
审查门:无凭证落地;未注册一律 fail-closed;复用账本维度而非另造身份。

### N2 — G08 受限标的控制(挂进 risk_gate)

交付:
```text
src/finharness/restricted_symbols.py(新)
  带版本的本地受限清单: restricted_list_version + entries[{symbol, reason, added_utc}]。
  数据文件落 data/security/restricted-symbols.json(可审计、可版本化)。
  is_restricted(symbol) 用规范化后的符号比对(复用 okx_symbols.normalize_*)。
provider 可交易性证据:
  对证券型 broker(alpaca), 从 broker-read receipt 读 asset.tradable;
  对 crypto(okx)无此概念 → 记 tradability="not_applicable" 并披露, 不伪装成已校验。
risk_gate.check(): 新增 restricted_symbol 检查 —— 命中受限清单或 tradability=false → 拦截。
  deny 优先: 即便 symbol 在 allowed_symbols, 命中受限清单仍拦。
```
验收:
```text
- 单测: 受限符号被拦; tradable=false 被拦; tradability 未知被拦+披露;
        干净符号放行; "在白名单但在受限清单" → 被拦(deny 优先)。
- RiskGate receipt 现在引用 restricted_list_version + provider tradability 结果。
- task lint + task test 通过。
```
非声明(写进 receipt):`非监管合规`。
审查门:deny 优先于 allow;未知可交易性不静默放行;receipt 带清单版本+可交易性结果。

### N3 — G04 后交易 TCA(扩展现有 post_trade,独立可并行)

交付:
```text
扩展 src/finharness/post_trade.py(不新建并行引擎):
  PostTradeReconciliation 增补完整生命周期数量对账:
    intended_quantity / submitted_quantity / filled_quantity /
    canceled_quantity / rejected_quantity, 且断言 filled+canceled+rejected 与 intended 自洽。
  PostTradeCostEstimate 增补(arrival 基准的 implementation shortfall):
    arrival_price(来源: ExecutionOrderRequest.reference_price, 已存在, 不臆造),
    side, implementation_shortfall = (avg_fill_price - arrival_price) * filled_qty,
    按 side 取号(buy 正向不利为成本, sell 反向), 并保留现有 slippage 字段。
  缺 arrival_price 或 avg_fill_price → 对应字段 None + notes 记 "tca_input_undisclosed"。
  PostTradeReceipt 暴露: arrival price、execution price、filled/canceled/rejected 状态、
    TCA limitations(paper-only)。
```
验收:
```text
- 单测: 完整成交 → implementation_shortfall 数值正确且方向(buy/sell)正确;
        部分成交/取消/拒绝 → 生命周期数量对账自洽;
        缺到达价 → shortfall=None + undisclosed note(不臆造)。
- post_trade receipt 含 arrival/execution price 与 lifecycle 状态。
- task lint + task test 通过。
```
非声明(写进 receipt):`不声称 live 执行质量`(纸面证据)。
审查门:复用现有模型扩展;shortfall 方向正确;缺输入只记不造。

## 3. 完成定义(对齐 gap register 的 evidence 列)

```text
- G07: risk/execution attestation 含 operator/account/environment/scope/reason;
       全程无凭证落地; 未注册 fail-closed。
- G08: receipt 引用受限清单版本 + provider 可交易性结果; deny 优先; 未知不放行。
- G04: post-trade receipt 含 arrival price / execution price / filled/canceled/rejected /
       TCA 局限; shortfall 缺输入时为 undisclosed 而非编造。
- 三项各自的 evidence 列都被编码成可执行断言(test), 不是文档承诺。
- 加这三项没有重写现有模块(纯扩展: 新 authorization/restricted_symbols 模块 +
  post_trade 字段增补 + risk_gate 一个 check)。
- task check 与 task security:scan 全绿, release_blocked=false, execution_allowed=false。
```

## 4. 待 operator 拍板

```text
1. G07 授权注册表落 data/security/(可版本化、无凭证) —— 是否同意?
2. G08 受限清单为本地带版本 JSON(非外部实时源, 以后需要再单独引入) —— 是否同意?
3. G04 仅做 paper-fill TCA, 不声称 live 执行质量 —— 是否同意?(gap 已如此界定)
```

## Links

```text
docs/product-north-star.md
docs/architecture/industry-benchmark/03-gap-register-codex.md(G04/G07/G08 权威定义)
docs/architecture/industry-benchmark/06-backend-frontend-guidance-codex.md
docs/architecture/market-access-ledger-spec.md(G06, G07 复用其维度)
src/finharness/market_access_ledger.py / okx_live_gate.py(G07 对齐来源)
src/finharness/risk_gate.py(G08 挂载点)
src/finharness/post_trade.py / execution.py(G04 扩展来源)
```
