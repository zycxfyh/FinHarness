# FinHarness 受控词表(Controlled Vocabulary)

> 由 [ADR: 受控词表与两层语言政策](../adr/2026-06-18-controlled-vocabulary-and-two-tier-language.md) 管辖。
>
> **两层规矩**:思想层(docs/think、docs/musings、docs/archive、内部笔记)随便用内部词;
> **正式层**(会发布的 docstring、API 字段与描述、UI 文案、风控/合规措辞、对外评审)
> 必须用行业词,或为内部词挂一个能从用词处够得到的锚点(链到本表或兄弟仓库)。
>
> `user_visible` = 是否允许出现在用户可见处;`api_allowed` = 是否允许做 API 字段/键名。

## A. 行业词 —— 直接用,保持用法一致

| 词 | 一行定义 | 注意 |
|---|---|---|
| `lineage` / provenance | 一个数据/结论的来源与变换链,可追溯回证据 | 已是行业词(W3C PROV / OpenLineage)。用法要一致:指"可追溯到 receipt 的来源链",别和别的意思混 |
| `receipt` | 不可变的文件证据记录(发生了什么、何时、依据什么) | 源自 Ordivon;行业近义:audit record / evidence record。保留,首次出现锚定一次即可 |
| `audit trail` | 决策/动作的可追溯留痕 | 正式层优先用它描述"留痕",而非内部隐喻 |
| `pre-trade risk control` | 下单前的风控闸门(本项目的 risk gate / ledger) | 对外措辞优先用此行业词 |

## B. 项目词 —— 锚定,不退役(这些是 operator 的真实兄弟项目/方法论)

| 词 | 行业/通俗对应 | 锚点(兄弟仓库) | 正式层 |
|---|---|---|---|
| `Ordivon` | 语义防火带 / 确定性治理闸门(evidence→authorization→observation) | 兄弟项目 `../Ordivon`,见其 `docs/semantic-firebreak.md` | 需锚点;`api_allowed: no` |
| `semantic firebreak` / `firebreak` | "语言↔现实"的强制过渡点 | 同上 | 需锚点 |
| `ABC` | 目标导向的状态变换模型(A 现状 / B 目标 / C 变换结构 / R 回执);近邻:state-space search、classical planning、控制论 | 兄弟项目 `../abc-thinking-system`,见其 `docs/abc-discovery-history.md` | 需锚点 |
| `B4` / `target-state-b` | 目标状态判据(源自 ABC 的 B);本项目指"规则改动可追溯到 lesson 再到 receipt" | 同上 + `docs/adr/2026-06-13-target-state-b-is-the-governing-roadmap.md` | 需锚点;`api_allowed: no` |
| `Hermes` | 兄弟 agent 运行时(注意:**也是 FinHarness 的真实代码依赖**,src 内多处引用,不只是词) | 兄弟项目 `../hermes-agent` | 需锚点;代码引用处注明用途 |
| `wheels` | "成熟的第三方库"(adopt-not-invent) | 项目内部用语 | 正式层改写为"mature third-party libraries" |
| `razor` | 范围/决策取舍规则 | 项目内部用语 | 正式层改写为"scope rule / decision rule" |

## C. 越权 overclaim 短语 —— 正式层禁用(除非带证据等级或 non-claim)

| 短语 | 为什么禁 | 正式层该怎么说 |
|---|---|---|
| `edge proven` / "已证明 alpha" | 把"通过验证档位"说成"证明了 edge" | "supported at rung X" + 证据等级 + non-claim |
| `safe to trade` / "可以交易" | 暗示执行授权 | "passed pre-trade checks; not execution authorization" |
| `工业级` / `机构级` | 自我拔高,无外部认证 | 删,或说明具体对标的标准条目 |
| `证明` / `proven`(无证据等级) | 绝对化 | "evidence at level …" / "supported / inconclusive / weakened" |
| `合规` / `compliant`(无认证) | 暗示监管合规 | "primitive-correct analogue of …;not a compliance certification" |

## D. `supported` 的语境消歧(安全相关)

`supported` 在已归档的旧 validation layer 中曾是判定枚举值,但被不同性质的检查共用,
易被误读为"有经验 edge"。规矩:

```text
经验性检查(backtest 档位):保留强义 supported —— 表示"在该研究档位上有经验证据支持"。
存在性检查(mechanism_present / benchmark_context / source-linkage):
  不得读作 supported, 改用 present / linked / well_formed —— 表示"要素齐备", 不表示"有 edge"。
```

详见 [术语治理执行手册](../proposals/2026-06-18-terminology-governance-execution-brief.md) 的 T2。

---

新增/修改条目时:先定义概念 → 选行业已有词 → 再决定是否保留内部别名并锚定。
小改动按影响分级,不必每次惊动本表。
