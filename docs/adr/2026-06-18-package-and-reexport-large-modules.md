# ADR: 大模块包化与再导出入口

Author: Codex
Parallel agent: Claude
Date: 2026-06-18
Status: accepted
Deciders: FinHarness project operator and Codex

## Context

FinHarness 的纵向十层里有多个模块已经超过 700 行。它们不是坏代码,但单文件
承载太多职责会让审查、类型检查、未来修改和 AI 协作变钝。

本轮工程地板提升已经先落了两张护网:

```text
- Ruff 广规则集 + C901 复杂度阈值
- mypy 渐进类型检查,安全核心从严
```

在这两张网之上,可以做行为保持的拆分,而不改变交易授权、receipt 语义或 public
import 契约。

## Decision

FinHarness 拆分大模块时采用 **package + `__init__.py` 再导出** 模式。

```text
- 将 `foo.py` 替换为 `foo/` package。
- `foo/__init__.py` 再导出原有公开符号,保持 `from finharness.foo import X` 可用。
- 子模块按职责拆分,例如 constants / models / providers / controls / bundle。
- 持久化 root、receipt root、外部 provider root 等测试 seam 必须由运行时读取
  package 顶层值,以保留 `patch.object(finharness.foo, "..._ROOT", ...)` 行为。
- 拆分提交不得顺手改变业务逻辑、授权边界、receipt schema 或 execution_allowed 语义。
```

已按此模式包化:

```text
validation/
execution/
risk_gate/
post_trade/
hypotheses/
proposal/
```

## Consequences

好处:

```text
- 文件边界更贴近职责,审查更容易。
- public import 兼容,下游图、测试和脚本不需要批量迁移。
- mypy / Ruff / C901 可以更早发现大函数和接口漂移。
- AI 与人类协作时可以只读相关子模块,减少误改面。
```

代价:

```text
- 总物理行数略增,因为每个 package 需要入口、docstring 和 imports。
- `__init__.py` 成为 public API 清单,以后新增公开符号需要同步维护。
- 测试 patch seam 如果直接 import 常量会失效,所以持久化代码必须用运行时 root resolver。
```

## Guardrails

```text
- 每个大模块拆分独立提交。
- 每次拆分后必须跑 targeted tests + `task check`。
- `execution_allowed` 必须保持 False 的结构性边界。
- 不为凑行数制造无意义文件;按职责内聚拆分。
- 不用包化替代产品能力建设,也不扩张治理面(G15)。
```

## Verification

本 ADR 对应的实现收据:

```text
- task check: ruff, mypy, 403 unittest, 4 property tests, rules audit,
  experiments, promptfoo smoke all passed during each package split.
- Public imports were verified through existing graph and layer tests.
- Storage-root patch seams were preserved for validation, execution, risk_gate,
  post_trade, hypotheses, and proposal packages.
```
