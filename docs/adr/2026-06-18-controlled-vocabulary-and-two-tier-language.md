# ADR: 受控词表与两层语言政策

Date: 2026-06-18
Status: accepted
Deciders: FinHarness project operator
Authors: Claude draft, Codex review/implementation notes

## Context

实地扫描(2026-06-18)显示 FinHarness 同时用三套语言:个人方法论语言(Ordivon、
ABC、B4、firebreak、wheels、razor)、工程语言(receipt、risk gate、ledger、
validation rung)、行业语言(audit trail、provenance、pre-trade risk control)。

风险**不是"词不好听"**,而是:① **够不到的锚点**——一个只加载 FinHarness、没加载
兄弟仓库的 agent 读到 `Ordivon`/`B4` 时会脑补;② **行业表面**(API 字段、UI 文案、
风控/合规措辞、对外评审)上外人不认得内部词;③ **越权措辞**("edge proven""safe
to trade""工业级""证明")让结论显得比证据更可靠。

**已澄清的事实(不要再误判)**:Ordivon、ABC、Hermes 是 operator 的**真实兄弟项目**
(`/root/projects/{Ordivon,abc-thinking-system,hermes-agent}`,各有 src/tests/README)。
本 ADR 只确认这些路径存在并可作为锚点;关于各兄弟仓库当前测试数、git 状态、
dogfood 结论,必须引用各自仓库的最新 receipt/命令输出,不能由本文自证。ABC
内核按其 discovery-history 的自述,可视为对 state-space search / 规划 / 控制论
的一种项目内压缩表达。
**所以这些词有真实、可达的源头,治理方式是"锚定",不是"退役"。**

减负事实:扫描确认这些内部词**没有进入 schema / Pydantic 字段名 / API 响应键**——
最坏的"黑话固化进对外契约"尚未发生。债主要在 docstring 与文档,量小(`Ordivon`
src 1 处、`firebreak` 0、`B4` 9)。

## Decision

采用**两层语言政策**,并配一份受控词表 + 一个 grep 级 lint。

```text
思想层(docs/think, docs/musings, docs/archive, 内部笔记):
  Ordivon / ABC / B4 / firebreak / Hermes 等内部词自由使用。

正式层(会发布的 docstring、API 字段与描述、UI 文案、风控/合规措辞、对外评审):
  必须用行业词, 或为内部词挂一个"够得到的锚点"(链到 docs/reference/glossary.md
  或兄弟仓库)。越权 overclaim 短语在正式层禁用, 除非带证据等级或 non-claim。
```

落地物:`docs/reference/glossary.md`(约 15 词,锚定而非退役)、`task vocab:lint`
(先 advisory, 豁免思想层)、`supported` 在 validation 的安全消歧(见执行手册)。

## Considered Options

### Option 1: 不治理 / 临时拼凑

Pros:
```text
零投入
```
Cons:
```text
内部词持续在 docstring/docs 扩散; AI 把它当正式框架扩写; 早晚渗进 API/UI 契约
```

### Option 2: 两层政策 + 一页词表 + grep lint(选定)

Pros:
```text
几小时级, 不违背 pragmatism-first 与 G15 HOLD
锚定保住 operator 的真实方法论, 一个字不抹
只禁真正无依据的 overclaim 短语; 用 lint 把规矩从"靠人记"变成"可执行"
高危表面(API/schema)已干净, 这个量级正好匹配
```
Cons:
```text
词表与 lint 需随项目演进维护(轻量)
```

### Option 3: 机构级语义治理(SKOS / ontology / FIBO / ISO 20022 / term-card-per-term)

Pros:
```text
受监管多团队金融机构的完整方案
```
Cons:
```text
对单用户、未服务他人的工具是过早的重型承诺(正是 G15「治理过度投资」HOLD 所挡)
高危表面已干净, 当前 ROI ≈ 0
```

## Consequences

Positive:
```text
正式层语言可被外部人理解、可验证、可锚定回真实源头。
overclaim 短语被 lint 挡在正式层之外。
operator 的方法论(Ordivon/ABC/Hermes)在思想层完整保留。
```

Negative:
```text
新增一页词表 + 一个 lint + 少量 docstring 锚点; 需轻量维护。
```

Neutral:
```text
本 ADR 不引入任何机构级语义系统; 那部分明确缓办(见下)。
```

## Explicitly deferred(外部对标,服务他人/受监管时再评估)

```text
SKOS、ontology、FIBO、ISO 20022、term-card-per-term、ontology-drift 监控。
依据: G15「治理过度投资」HOLD + pragmatism-first; 且高危表面已干净。
```

## Confirmation

本决策生效的标志:
```text
docs/reference/glossary.md 存在, 约 15 词, 项目词锚定到兄弟仓库/行业同义词。
task vocab:lint 能以 advisory 方式报告正式层里种入的 overclaim 短语和未锚定的项目词,
  且豁免 docs/think、docs/musings、docs/archive。
`supported` 在非经验检查中不再读作"有 edge"(validation 测试断言)。
新增或本次触碰的正式层项目词带可达锚点;既有历史债由 advisory lint 显式列出,
  不在 v1 中一次性作为 hard gate 清零。
没有任何机构级语义系统(SKOS/FIBO/ontology)被引入。
```

## Links

```text
docs/product-north-star.md
docs/reference/glossary.md
docs/proposals/2026-06-18-terminology-governance-execution-brief.md
docs/adr/2026-06-13-pragmatism-first-supersedes-rust-first.md
docs/architecture/industry-benchmark/03-gap-register-codex.md(G15「治理过度投资」HOLD)
sibling repos: /root/projects/Ordivon, /root/projects/abc-thinking-system, /root/projects/hermes-agent
```
