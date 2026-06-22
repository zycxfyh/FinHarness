# 执行手册:抬高工程地板(类型检查 / lint 规则集 / 大文件拆分)

> 类型:执行手册(给 Codex)。角色分工:Claude 设计/审查,Codex 执行。
> 每个任务独立验收。建在当前 403 测试全绿、ruff 默认规则全过、`task check`
> 已含 `rules:audit` 之上。
> 依据:2026-06-18 代码质量评估;module-map.md;pragmatism-first;G15。
> 不需要新 ADR:这是工程地板加固(扩展现有 ruff + 加 mypy + 行为保持的重构),
> 非新技术方向;但**任务 3(拆分)落地后补一条简短 ADR 记录"包化 + 再导出"模式**。

## 0. 本质定性(一句话)

```text
任务 1 lint    = 把"干净但门槛低"抬到"广而严", 用 noqa-带理由 处理有意的安全告警。
任务 2 类型    = 给满仓类型注解配一个 *会验证它们* 的 mypy, 安全核心从严, 其余渐进。
任务 3 拆分    = 把 6 个 >700 行文件按职责包化, 公开 API 经 __init__ 再导出,
                 行为零改动, 每步全测试 + rules:audit 绿。
```

**三项共同性质:只抬地板,不改行为、不改授权。** `execution_allowed` 全程 False;
公开 import 路径不变;无逻辑重写。这是"加护栏 + 整理",不是"换方向"。

## 1. 不可逾越的护栏(审查逐条查)

```text
- 行为保持:任务 3 只搬代码,不改逻辑;每个文件拆完,403 测试 + task rules:audit
  必须全绿,且 git diff 里无语义改动(只有移动 + import 调整)。
- 公开契约不破:from finharness.validation import X 等现有导入必须继续可用
  (靠新包的 __init__.py 再导出)。先 grep 全仓 + tests + scripts 的现有 import 清单,
  拆后逐条验证仍可解析。
- 安全告警不静默:src 里的 S603/S607/S310 等 bandit 命中, 用 *带理由的*
  `# noqa: S603 -- 本地可信 CLI, 无 shell, 参数为常量` 处理, 不开全局 ignore、
  不无脑 --fix。能真修的(C4/RUF 自动修)才 --fix。
- 类型不放水:mypy 渐进 = 安全核心模块从严, 其余 lenient; 不靠满地 `# type: ignore`
  凑零错误。新增的 ignore 必须带具体 error code。
- 不扩张治理面(G15):这三项是正确性保险, 不新增治理图、不新增 receipt 种类。
- 拆分不是按行数硬切:按 *职责内聚* 找缝(见任务 3 的 validation 范例), 不为凑行数
  制造无意义文件。
```

## 2. 任务序列(护栏先行,重构在后)

> 顺序是设计的一部分:**先 1、2 再 3**。类型检查 + 广 lint + 现有测试,正是拆分
> 大文件时防止改坏的安全网;反过来先拆再补网,风险大得多。

### N1 — 扩展 ruff 规则集(最便宜,先做)

现状基线(已实测):扩展集下全仓仅 **27 处**,4 处可自动修,大头是 `S`(subprocess/urlopen)。

交付(`pyproject.toml`):
```toml
[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "C4", "S", "RUF", "PTH", "TID", "C901"]

[tool.ruff.lint.mccabe]
max-complexity = 12          # 守住大函数, 为任务 3 提供客观触发器

[tool.ruff.lint.per-file-ignores]
"tests/*"       = ["S101", "S105", "S106", "S108"]   # assert + 测试夹具
"scripts/*"     = ["S603", "S607"]                   # 有意的本地子进程
"experiments/*" = ["S101"]
```
处理 27 处:先 `ruff check --fix`(C4/RUF 自动);src 里剩余 `S603/S607/S310/S105/S108`
逐条判断——真风险则修,有意调用则加*带理由*的 `# noqa`。

验收:
```text
- ruff check . 全过(扩展集)。
- 每条 src 内的 # noqa 都带 error code + 一句理由。
- task lint 仍是 check 链一环;CI security workflow 自动覆盖。
```
非声明:`lint 不证明逻辑正确, 只抬静态地板`。
审查门:无全局 ignore;noqa 带理由;max-complexity 已设。

### N2 — 引入 mypy 类型检查(渐进,安全核心从严)

现状基线(已实测):`mypy src/finharness --ignore-missing-imports` = **24 错误 / 14 文件 / 共 89 文件**。先清零这 24 处,再设分级严格度。

交付(`pyproject.toml`)+ 开发依赖加 `mypy`:
```toml
[tool.mypy]
python_version = "3.12"
files = ["src/finharness"]
plugins = ["pydantic.mypy"]
ignore_missing_imports = true     # 无 stub 的三方库
warn_unused_ignores = true
warn_redundant_casts = true
check_untyped_defs = true         # 全局 lenient 基线

[[tool.mypy.overrides]]
# 安全关键核心:从严
module = [
  "finharness.risk_gate", "finharness.authorization",
  "finharness.market_access_ledger", "finharness.effective_rules",
  "finharness.effective_ceilings", "finharness.okx_live_gate",
  "finharness.rule_change_ledger", "finharness.restricted_symbols",
  "finharness.trading_guard", "finharness.statecore.*",
]
disallow_untyped_defs = true
disallow_incomplete_defs = true
warn_return_any = true
```
Taskfile 新增 `typecheck` 任务并接进 `check`:
```yaml
  typecheck:
    desc: Static type check (mypy; strict on safety-critical core)
    cmds:
      - uv run mypy
```
(`check` 的 cmds 里在 `lint` 之后加 `- task: typecheck`。)

验收:
```text
- uv run mypy 零错误(先修那 24 处真实错误, 不靠 type:ignore 堆)。
- 安全核心模块在从严 override 下也零错误。
- task check 现在包含 typecheck;本地 + CI 都跑。
- 新增的任何 # type: ignore 带具体 code + 理由。
```
非声明:`类型检查不证明业务正确, 只防注解与实现不一致`。
审查门:渐进分级而非全局 strict 一刀切;ignore 带 code;safety 核心从严。

### N3 — 大文件按职责包化(行为保持,逐个来)

目标文件(>700 行,降序):`validation.py`(1595)、`execution.py`(1119)、
`risk_gate.py`(992)、`post_trade.py`(931)、`hypotheses.py`(822)、`proposal.py`(749)。

**方法(成熟方案:包化 + 再导出,行为保持):**
```text
1. 把 foo.py 变成 foo/ 包;foo/__init__.py 再导出原有全部公开符号
   (from .models import *  等), 使 from finharness.foo import X 不破。
2. 按职责内聚把内部拆成子模块(见下方 validation 范例)。
3. 只搬代码 + 调 import, 不改逻辑。
4. 每搬完一个文件:ruff + mypy + 403 测试 + rules:audit 全绿, 再提交。
5. 一个文件一个提交/PR, 不要一次拆多个。
```

**`validation.py` 拆分范例(按实测结构,缝已找好):**
```text
validation/__init__.py    再导出公开 API(保持 import 兼容)
validation/models.py      9 个 Pydantic 模型(ValidationJob/CheckResult/Quality/
                          Lineage/Snapshot/Receipt/Bundle/SourceSpec/BacktestEvidence)
validation/providers.py   draft + backtest evidence providers
                          (Null/Hermes/Vectorbt, 约 95–604 行那段)
validation/backtest.py    backtest_metrics / oos / walk_forward / map_backtest_result /
                          respects_rung / backtest_evidence_result(764–1033)
validation/checks.py      source_validity / mechanism / event_reaction / benchmark /
                          disconfirmation / limitations / build_validation_results(1034–1304)
validation/bundle.py      build_validation_quality / proposal_handoff /
                          review_questions / persist / build_..._from_snapshot(1305–末)
validation/_util.py       now_utc / write_json / find_blocked_language / result_text_for_guard
```
其余 5 个文件:Codex 先对每个跑同样的 `grep -nE '^class |^def '` 找缝,产出各自
子模块映射给 Claude 审一遍,再动手。

验收(每个文件):
```text
- foo/ 包替代 foo.py;原有外部 import 全部仍可解析(附 grep 清单逐条核对)。
- git diff 仅"移动 + import", 无逻辑改动(审查重点)。
- 403 测试 + task rules:audit + ruff + mypy 全绿。
- 每个子模块 < ~500 行;无文件触发 C901。
```
非声明:`拆分不改任何行为、不改授权、execution_allowed 仍 False`。
审查门:行为保持;公开契约不破;按职责拆而非按行数;逐文件独立提交。

## 3. 完成定义

```text
- task check 链 = lint(广集) -> test -> test:properties -> typecheck -> rules:audit
  -> experiments -> eval:smoke, 本地与 CI 一致全绿。
- 无 src 文件 > ~700 行;无函数触发 C901(max-complexity=12)。
- mypy 零错误, 安全核心从严;ruff 广集零错误, noqa/ignore 皆带理由。
- module-map.md 的 L12 行更新为"lint 广集 + mypy 渐进 + 大文件已包化";
  受影响层的"模块/文件"列同步为新包结构。
- 一条简短 ADR 记录"包化 + __init__ 再导出"为本仓拆分大文件的标准手法。
```

## 链接

```text
docs/architecture/module-map.md                      模块表(本手册的对象)
docs/architecture/industry-benchmark/03-gap-register-codex.md   G15 治理勿过度
docs/adr/2026-06-13-pragmatism-first-supersedes-rust-first.md   渐进而非一刀切
docs/lessons/2026-06-18-stale-doc-as-current-guide.md           动手前重读现状
```
