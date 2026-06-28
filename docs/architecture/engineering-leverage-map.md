# Engineering Leverage Map

状态:current(2026-06-28)。这是 FinHarness 的工程推进风险地图:
哪些事平时看起来“不急”,但不留结构会让未来每个 PR 都变慢、变脆、变难审。

本页不是新流程大礼包。它把成熟项目常见的平台能力压成 FinHarness 当前阶段能承受的
轻量结构,并说明什么时候再升级成熟工具。

## Operating Thesis

Engineering speed is not just writing code quickly. It is keeping enough
project memory, ownership, checks, fixtures, receipts, and rollback shape that
the next slice does not restart from archaeology.

FinHarness 的原则:

```text
keep the domain core small
standardize repeated engineering work
adopt mature wheels for heavy generic capability
defer heavy platforms until repeated pain proves the need
```

## Leverage Layers

| Layer | If ignored, future cost | Lightweight structure now | Mature reference | Upgrade trigger |
| --- | --- | --- | --- | --- |
| Product/category memory | 每次都重新争论“我们是什么”,文案和能力越权。 | README, Product North Star, Framework Index, controlled vocabulary. | Product principles, Diataxis, handbook pages. | 多人协作或对外发布需要正式 product handbook. |
| System catalog / ownership | 新功能找不到归属,代码散在 routes/scripts/helpers。 | `framework-index.md`, `system-map.md`, `module-map.md`, `system-catalog.yml`. | Backstage catalog metadata. | 多 repo、多 owner、自动 ownership/reporting 需求出现。 |
| Change classification | 小改动夹带大风险,大改动没有设计入口。 | `change-control.md`, mini-RFC, gate checklists. | Kubernetes KEPs, Rust RFCs, ADR/MADR. | C2/C3 变多后,把 RFC/gate 状态登记成机器可查 registry. |
| Current-doc facts | README/commands/security docs 保护旧事实,新人走错路。 | `GOV-DOCS-*`, `task docs:current-check`, history/current lane split. | docs-as-code, GitLab docs discipline. | 漂移频繁时,从 grep probes 升级到 generated reference docs. |
| Policy and invariant checks | reviewer 靠记忆抓机械漏项,漏一次就进主线。 | Python `PolicyRule` registry in `tests/_policy_registry.py`. | OPA, Conftest, Cedar. | 规则多到 Python 难读、需要跨语言/CI artifact policy. |
| Fixtures and test locality | 每个测试自造世界,慢、脆、难迁移。 | system fixtures: `_statecore_fixtures.py`, `_review_fixtures.py`. | pytest fixtures, test data builders. | 第三个 system 重复临时 DB/receipt setup. |
| Read models and adapters | route/frontend/scripts 直接拼业务语义,改一个视图牵动全局。 | system directory standard: domain / commands / read_model / adapters / fixtures / governance. | modular monolith, hexagonal/adapters style. | 同一 read shape 第三次散点,先抽 read_model. |
| Repository intelligence | 改动影响面靠猜,检查要么过宽要么漏测。 | `repo_intelligence.py`, `task repo:intelligence`, blast-radius hints. | CodeCharta, Emerge, GitDiagram-style repo maps. | 多人并行或 PR 量上来后,把建议检查接进 CI comment/report. |
| Workflow durability | 线性脚本越积越多,失败后不知道从哪继续。 | Taskfile + receipt + LangGraph only where branching/interrupt earns it. | Temporal, Airflow, Dagster. | 出现长审批、重试补偿、跨日状态恢复。 |
| Observability | 出错只剩终端滚屏,receipt 和请求对不上。 | trace id -> receipt/task/request index, local-only OpenTelemetry adapter. | OpenTelemetry. | 有远程服务、多用户、生产监控或 exporter 需求。 |
| Evidence lineage | 数据/结论来源靠文字描述,外部工具无法消费。 | receipts with source refs, receipt usage audit. | OpenLineage, MLflow, DVC, Sigstore. | 数据集/模型/实验版本成为主要协作对象。 |
| Security and supply chain | 密钥、依赖、CI、release posture 每次临场查。 | threat model, SSDF map, CODEOWNERS, fuzz baseline, SBOM/provenance baseline. | OpenSSF Scorecard, CodeQL, Gitleaks, Trivy, SLSA, CycloneDX/SPDX. | 发布 artifact 或多人环境需要 signed provenance / formal SBOM. |
| Backup and recovery | SQLite/receipt 丢失后无法重建决策历史。 | `task backup`, ignored data awareness, receipt roots. | restic, litestream, managed backup. | 状态价值超过手工重建成本或需要异地恢复。 |
| Frontend confidence | cockpit 改动靠眼看,旧 affordance 悄悄回来。 | jsdom DOM tests, optional browser smoke. | Playwright E2E, visual regression. | cockpit 成为主要产品面或复杂交互增多。 |

## Current Missing / Thin Tools

These are not emergencies. They are the places where a small structure now saves
large future drag.

| Area | Current state | Next light structure |
| --- | --- | --- |
| Machine-readable system catalog | Framework Index exists as prose. | `system-catalog.yml` + schema-ish test. |
| Tool/check recommendation | `repo_intelligence.py` recommends some checks. | Keep recommendations aligned with current systems and catalog ids. |
| System fixture spread | State Core and Review System have fixtures. | Add fixture only when another system repeats setup pain twice. |
| Current docs governance | `GOV-DOCS-*` now protects entry docs. | Add checks only after drift recurs; avoid giant lint wall. |
| Architecture docs split | Some old specs are historical banners. | Move/mark more old current-looking specs only when they confuse active work. |
| Release evidence | local release preflight exists. | Formal SBOM/SLSA only when packaging artifacts exist. |

## Candidate Deepening Opportunities

These are architectural opportunities, not mandatory immediate work.

1. **System Catalog module**
   - Files: `docs/architecture/system-catalog.yml`, `tests/test_system_catalog.py`,
     `framework-index.md`.
   - Problem: prose maps help humans but are hard for repo intelligence and docs checks
     to consume.
   - Solution: keep one small YAML catalog with ids, docs, runtime roots, checks,
     mature posture, and upgrade triggers.
   - Benefit: higher locality for ownership facts; future checks can read one
     interface instead of scraping prose.

2. **Check Recommendation seam**
   - Files: `repo_intelligence.py`, `system-catalog.yml`, tests.
   - Problem: recommended checks can drift from current system ownership.
   - Solution: make repo intelligence consume catalog ids for sensitive surfaces.
   - Benefit: more leverage from one catalog; less hard-coded path lore.

3. **System Fixture expansion rule**
   - Files: `tests/_statecore_fixtures.py`, `tests/_review_fixtures.py`, future
     fixture modules.
   - Problem: fixtures are good where standardized, but not yet a general system
     habit.
   - Solution: when a third test repeats setup for a system, add a fixture module
     and a governance probe.
   - Benefit: test locality improves without a big pytest migration.

4. **Generated command/reference page**
   - Files: `Taskfile.yml`, `docs/reference/commands.md`, docs checks.
   - Problem: command reference is current but manually maintained.
   - Solution: later generate or verify the command table from Taskfile metadata.
   - Benefit: removes a recurring docs drift class.

5. **Release posture ledger**
   - Files: `release_preflight_graph.py`, security docs, SBOM/provenance outputs.
   - Problem: release readiness evidence exists, but maturity posture is spread
     across docs and generated receipts.
   - Solution: add a compact release-posture receipt/index when packaging becomes
     real.
   - Benefit: security and release decisions become easier to audit.

## How To Use This Map

- Before a non-trivial PR, identify which leverage layer it touches.
- If a layer is touched for the second time by the same kind of friction, add a
  tiny rule, fixture, catalog entry, or docs-current check.
- If a layer is touched for the third time, consider a deeper module or mature
  adapter.
- Do not introduce heavy platforms just because the category exists. Upgrade only
  when the trigger column is true.

## Maintenance

Update this map when:

- a new engineering support capability becomes part of `task check`;
- a mature external tool moves from “reference” to active dependency;
- a repeated blocker becomes a policy, fixture, catalog field, or receipt;
- a listed upgrade trigger becomes true.

Run:

```bash
task docs:current-check
task governance:check
```
