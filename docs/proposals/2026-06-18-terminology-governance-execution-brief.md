# 执行手册:术语治理(lint / supported 消歧 / 锚定清扫)

> 类型:执行手册(给 Codex)。角色分工:Claude 设计/审查,Codex 执行。
> 设计依据:[ADR 受控词表与两层语言政策](../adr/2026-06-18-controlled-vocabulary-and-two-tier-language.md)
> 与 [glossary.md](../reference/glossary.md)。每个任务独立验收。

## 0. 锁定的事实(由扫描决定,不要再讨论)

```text
- 内部词没有进 schema / Pydantic 字段名 / API 键 —— 不做"字段改名"工程。
- 债在 docstring 与文档, 量小。这是"薄闸门 + 小清理", 不是语义治理工程。
- 不引入 SKOS / FIBO / ontology / term-card(ADR 已明确缓办)。
```

## 1. 不可逾越的护栏

```text
- 思想层永不动:docs/think、docs/musings、docs/archive、内部笔记 —— lint 必须豁免它们。
- 不退役 Ordivon/ABC/B4/Hermes —— 它们是真实兄弟项目, 只"锚定"。
- supported 消歧只动会被误读为"有 edge / 可交易"的地方, 不做全量重命名。
- 不改任何执行授权语义;execution_allowed 仍恒 false。
- lint 用 grep 级实现, 不引入语义/NLP 依赖。
```

## 2. 任务序列(独立验收)

### T1 — `task vocab:lint`(grep 级 advisory 词表 lint)
交付:
```text
scripts/vocab_lint.py + Taskfile 入口 task vocab:lint。
规则(只扫"正式层": src/**/*.py 的 docstring 与字符串、docs/** 但排除豁免目录、
     API 描述、UI 文案):
  R1 出现 C 类 overclaim 短语(edge proven / safe to trade / 工业级 / 机构级 /
     无证据等级的"证明"|proven / 无认证的"合规"|compliant) → 报告 finding,
     除非同段落含证据等级或 non-claim 标记。
  R2 出现 B 类项目词(Ordivon/ABC/B4/target-state-b/firebreak/Hermes/wheels/razor)
     而附近无 glossary 锚点链接 → WARN。
豁免:docs/think/**、docs/musings/**、docs/archive/**、本词表与本手册自身、tests/**、
     blocked-language 常量/测试语料等"为了拦截而列出禁词"的位置。
v1 只做 advisory, 不接入 task check 硬门;等误报率稳定后再讨论是否升级。
```
验收:
```text
- 种入一个 overclaim 短语到一个正式层文件 → lint 报 finding;移除 → 不再报告。
- 种入一个未锚定 B 类词到正式层 → lint WARN;加锚点 → 不再 WARN。
- 对 docs/think 下同样的词不报。
- task lint + task test 通过。
```
审查门:豁免范围严格按第 1 节;不误伤思想层;不把 blocklist 常量当违规;无新依赖。

### T2 — `supported` 语境消歧(安全项,带测试)
交付:
```text
在 src/finharness/validation.py:
  - 经验性 backtest 档位:保留 "supported"。
  - 存在性检查(mechanism_present / benchmark_context / source-linkage 等
    "要素在不在"的判定):把结果值从 "supported" 改为 present / linked / well_formed
    (择最贴切者), 使其不再读作"有经验 edge"。
  - 同步 proposal.py 里对 "supported" 的计数/聚合逻辑, 确保只统计经验性 supported。
受影响的 receipt/schema 字段同步更新; 旧值若已落盘, 在读取侧做向后兼容映射或标注。
```
验收:
```text
- 新增/更新测试断言:存在性检查的结果不等于 "supported";
  backtest 经验档位仍可为 "supported";聚合计数只计经验性 supported。
- 一次 validation 运行的 receipt 中, 存在性检查不再出现 "supported"。
- task lint + task test 通过(注意回归:原本依赖 result=="supported" 的存在性分支)。
```
审查门:强义 supported 在经验档位完好;存在性检查不再可被误读为 edge;
        计数逻辑正确;无执行语义改动。

### T3 — 锚定清扫(正式层 docstring/文档)
交付:
```text
先给本次触碰的正式层里出现的 B 类项目词加一行可达锚点
(链到 glossary.md 或兄弟仓库);历史债由 task vocab:lint advisory 清单保留:
  - src/finharness/rule_change_ledger.py 的 "Shape (Ordivon)"。
  - src 内 docstring 中的 B4 / target-state-b 出现处。
  - 会发布的 reference/how-to 文档中首次出现的项目词。
不碰 docs/think、docs/musings、docs/archive。
```
验收:
```text
- T1 的 lint 对本次触碰的位置不再 WARN。
- 锚点链接可达(指向 glossary.md 锚或兄弟仓库真实路径)。
- task lint + task test 通过。
```
审查门:思想层未被改动;锚点真的可达;无语义改写,只加指针。

## 3. 完成定义(对齐 ADR Confirmation)
```text
- task vocab:lint 存在并能 advisory 报告 overclaim 短语与未锚定项目词, 豁免思想层。
- supported 在非经验检查中不再读作"有 edge"(测试断言)。
- 本次新增/触碰的正式层项目词带可达锚点;既有历史债保留为 advisory finding。
- task check 与 task security:scan 全绿, execution_allowed=false。
- 没有引入 SKOS/FIBO/ontology/语义依赖。
```

## Links
```text
docs/adr/2026-06-18-controlled-vocabulary-and-two-tier-language.md
docs/reference/glossary.md
src/finharness/validation.py / proposal.py(T2)
src/finharness/rule_change_ledger.py(T3)
```
