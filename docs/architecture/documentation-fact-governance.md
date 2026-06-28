# Documentation Fact Governance

状态:current(2026-06-28)。这是 FinHarness 的轻量文档事实治理模块。

目标不是多写文档,而是让每次架构快进后用很小成本保持入口事实正确。

## Model

FinHarness documents have two lanes:

| Lane | Examples | Rule |
| --- | --- | --- |
| Current facts | `README.md`, `docs/README.md`, `docs/tutorials/golden-path.md`, `docs/reference/commands.md`, `docs/reference/config-env.md`, `docs/architecture/capital-os-layering.md`, `engineering-leverage-map.md`, `framework-index.md`, `system-catalog.yml`, `system-map.md`, `module-map.md` | Must match current code, Taskfile, and product boundary. |
| History | `docs/notes/`, `docs/reviews/`, `docs/proposals/`, `docs/archive/` | May preserve old commands/modules as historical evidence; do not rewrite history just to make it current. |

The high-leverage habit: when a PR changes current facts, update the current
docs in the same PR and run:

```bash
task docs:current-check
```

## Single Source By Fact Type

| Fact type | Source of truth | Current docs that mirror it |
| --- | --- | --- |
| Product direction | `docs/product-north-star.md` | README, product thesis/roadmap |
| Architecture layering | `docs/architecture/capital-os-layering.md` | system-map, module-map |
| Framework summary | `docs/architecture/framework-index.md` | README, docs task map |
| Engineering leverage layers | `docs/architecture/engineering-leverage-map.md` | framework-index, docs task map |
| Machine-readable system catalog | `docs/architecture/system-catalog.yml` | framework-index, repo intelligence follow-up |
| System placement | `docs/architecture/system-map.md` | proposals, mini-RFCs, module-map |
| Live task names | `Taskfile.yml` | command reference, README, golden path |
| Runtime config | `src/finharness/config.py`, direct env reads | config/env reference, `.env.example` |
| Mainline/archive boundary | source tree + Taskfile | README, Capital OS, module-map |
| Review/proposal behavior | `statecore/proposals.py`, `decision_scaffold.py`, `risk_classification.py` | golden path, command reference, product roadmap |

## Drift Classes

| Drift | Example | Fix |
| --- | --- | --- |
| Command drift | Current docs mention a removed task. | Update docs or restore task intentionally. |
| Layer drift | A shipped module is still described as a gap. | Update Capital OS and module-map. |
| Boundary drift | Archived live-trading code appears as mainline. | Move the mention to history/archive lane. |
| Config drift | Env reference lists secrets for archived runtime. | Remove from current reference; link archive if needed. |
| Product drift | Text implies trading bot / stock picker / execution authority. | Rewrite against North Star non-claims. |

## Tiny Operating Loop

For every non-trivial PR:

1. If Taskfile changed, update `docs/reference/commands.md`.
2. If mainline modules changed, update `docs/architecture/module-map.md`.
3. If system ownership changed, update `docs/architecture/system-map.md`.
4. If a system's one-line role or mature-solution posture changed, update
   `docs/architecture/framework-index.md` and `docs/architecture/system-catalog.yml`.
5. If a future-tooling / mature-solution trigger changed, update
   `docs/architecture/engineering-leverage-map.md`.
6. If layer status changed, update `docs/architecture/capital-os-layering.md`.
7. If first-run behavior changed, update `README.md` and `docs/tutorials/golden-path.md`.
8. Run `task docs:current-check`.

This is intentionally smaller than a release process. It is a fact sync habit.

## External Patterns We Borrow

FinHarness adapts, but does not copy, mature practices from:

- Kubernetes KEPs: durable enhancement proposals with status, motivation,
  alternatives, and implementation history.
- Rust RFCs: significant language/project changes go through a public proposal
  process before implementation becomes the shared rule.
- Diataxis: separate tutorials, how-to guides, reference, and explanation so a
  quick command lookup does not become an architecture essay.
- GitLab documentation: docs-as-code discipline where documentation is reviewed
  alongside the change that makes it necessary.

References:

- https://github.com/kubernetes/enhancements/tree/master/keps
- https://rust-lang.github.io/rfcs/
- https://diataxis.fr/
- https://docs.gitlab.com/development/documentation/

## Current Machine Guard

The source of truth for machine checks is the existing governance policy
registry: `tests/_policy_registry.py`.

Docs rules use `GOV-DOCS-*` ids and scan only the current-facts lane. The
focused runner `tests/test_docs_current_facts.py` exists so a docs-only PR can
run `task docs:current-check` quickly, while `task governance:check` still sees
the same rules through the main registry. History lanes are not scanned, so
old task names can remain as evidence instead of being erased.

Current checks:

- task commands mentioned in current docs exist in `Taskfile.yml`;
- current docs do not expose archived live-trading task prefixes;
- Capital OS says IPS is implemented, not still the next gap;
- module-map does not list retired ten-layer/live-trading modules as current.

Security docs have an adjacent focused guard:
`tests/test_security_maturity_docs.py`. It checks the current threat model,
SSDF map, response runbook, and CODEOWNERS against the current Capital OS /
archived-live-trading boundary.

Older architecture specs may remain in place when they are useful historical
design evidence, but they must carry a clear historical/superseded banner if
they mention retired execution, risk-gate, OKX, Alpaca, or ten-layer paths.

Add checks only when a drift has recurred. The point is high signal, not a giant
lint wall.
