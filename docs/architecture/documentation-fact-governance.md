# Documentation Fact Governance

状态:current(2026-07-22)。这是 FinHarness 的轻量文档事实治理模块。

目标不是多写文档,而是让每次架构快进后用很小成本保持入口事实正确。
文档类型使用 Diátaxis；文档是否仍是当前权威由
[Documentation Lifecycle Contract](documentation-lifecycle.md) 管理。

## Model

FinHarness documents have two maintained-authority lanes and four non-current
lifecycle states:

| Lane / state | Examples | Rule |
| --- | --- | --- |
| `current` facts | `README.md`, `docs/README.md`, current tutorials/reference/architecture, `system-catalog.yml` | Must match current code, Taskfile, and product boundary. |
| `deprecated` transition | A still-supported compatibility page with a named replacement and removal trigger. | Remains current-check eligible only while the compatibility behavior is supported. |
| `preview` | Proposed idea or design not yet admitted as shipped behavior. | Never becomes current merely because a current page links to it. |
| `superseded` | A former plan or reference replaced by a named current authority. | Retained only for distinct context; not runnable guidance. |
| `historical` | `docs/notes/`, `docs/reviews/`, `docs/proposals/`, `docs/lessons/`, `docs/think/`, and configured historical paths. | Preserve authored evidence; do not rewrite it merely to look current. |
| `archived` | `docs/archive/`. | Lookup-only legacy material outside maintained guidance. |

The closed lifecycle and visible banner syntax are defined only in
[Documentation Lifecycle Contract](documentation-lifecycle.md). A timestamp,
folder move, or recent edit is not lifecycle authority by itself.

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
| System ownership and lifecycle | `docs/architecture/system-catalog.yml` | generated sections in framework-index and module-map |
| Documentation lifecycle semantics | `docs/architecture/documentation-lifecycle.md` plus catalog navigation roots/paths | lifecycle banners and current graph traversal |
| Verified engineering debt | `docs/governance/debt-register.json` | evolution-roadmap active-debt block |
| Implementation sequencing | `docs/architecture/finharness-evolution-roadmap.md` | framework navigation and execution planning |
| Consumer classification | `docs/governance/attestation-consumers.json` | generated inventory Markdown |
| Support surface lifecycle | `docs/architecture/support-surface-registry.yml` | docs-current check, support sweep planning |
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
| Lifecycle drift | A completed plan remains reachable as current authority or a superseded page has no replacement. | Apply the closed lifecycle and preserve evidence through a bounded move or banner. |
| Config drift | Env reference lists secrets for archived runtime. | Remove from current reference; link archive if needed. |
| Product drift | Text defines the product mainly by defensive category denial instead of the staged judgment/review/paper-validation/execution roadmap. | Rewrite against the North Star capability path. |

## Tiny Operating Loop

For every non-trivial PR:

1. If Taskfile changed, update `docs/reference/commands.md`.
2. If mainline modules changed, update `docs/architecture/module-map.md`.
3. If system ownership changed, update `docs/architecture/system-map.md`.
4. If a system's one-line role or mature-solution posture changed, update
   `docs/architecture/framework-index.md` and `docs/architecture/system-catalog.yml`.
5. If a long-lived support surface was added, retired, downgraded, or changed
   ownership/review cadence, update `docs/architecture/support-surface-registry.yml`.
6. If a future-tooling / mature-solution trigger changed, update
   `docs/architecture/engineering-leverage-map.md`.
7. If layer status changed, update `docs/architecture/capital-os-layering.md`.
8. If first-run behavior changed, update `README.md` and `docs/tutorials/golden-path.md`.
9. If a document stops being current, apply the lifecycle contract in the same
   PR; do not leave current-looking copies or duplicate redirects.
10. Run `task docs:current-check`.

This is intentionally smaller than a release process. It is a fact-sync and
lifecycle-boundary habit.

## External Patterns We Borrow

FinHarness adapts, but does not copy, mature practices from:

- Kubernetes KEPs: durable enhancement proposals with status, motivation,
  alternatives, and implementation history.
- Rust RFCs: significant language/project changes go through a public proposal
  process before implementation becomes the shared rule.
- Diátaxis: separate tutorials, how-to guides, reference, and explanation so a
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
registry: `tests/_policy_registry.py`. The current-doc set is no longer a
hand-maintained Python tuple: it is the internal Markdown graph reachable from
the entrypoints declared in `system-catalog.yml`.

`system-catalog.yml` also owns repository-level non-current roots/paths.
`docs/archive/**` is interpreted as `archived`; the remaining configured
historical roots/paths are `historical`. Documents outside those locations may
use the visible lifecycle banner from the lifecycle contract. No inbound link
can promote a `preview`, `superseded`, `historical`, or `archived` document into
the current graph.

Catalog-owned sections and the attestation audit view carry generated markers.
Refresh them with:

```bash
task docs:generate-current-views
```

`task docs:current-check` runs the same renderer in check mode, validates every
navigation-reachable maintained document's internal links and task references,
and fails if a generated view differs from its source.

Lifecycle checks additionally enforce:

- the closed six-state vocabulary;
- current/deprecated entrypoint eligibility;
- `superseded` current-authority links;
- `deprecated` replacement and removal triggers;
- non-current root non-promotion;
- bounded redirect stubs that point to preserved historical/archive evidence.

Docs rules use `GOV-DOCS-*` ids and scan only the current-facts lane. The
focused runner `tests/test_docs_current_facts.py` exists so a docs-only PR can
run `task docs:current-check` quickly, while `task governance:check` still sees
the same rules through the main registry. Historical/archive lanes are not
scanned for current command truth, so old task names can remain as evidence
instead of being erased.

Current checks:

- task commands mentioned in current docs exist in `Taskfile.yml`;
- current docs do not expose archived live-trading task prefixes;
- Capital OS says IPS is implemented, not still the next gap;
- module-map does not list retired ten-layer/live-trading modules as current;
- support surface registry entries have closed statuses, owners, review due
  dates, and existing source/dependency paths;
- catalog-derived Framework Index and Module Map sections match the catalog;
- attestation inventory Markdown matches the machine JSON exactly;
- every internal link from a navigation-reachable maintained document resolves;
- non-current lifecycle pages cannot become current through an inbound link.

Security docs have an adjacent focused guard:
`tests/test_security_maturity_docs.py`. It checks the current threat model,
SSDF map, response runbook, and CODEOWNERS against the current Capital OS /
archived-live-trading boundary.

Older architecture specs may remain when they are useful design evidence, but
they must use the lifecycle contract if they sit outside a catalog-owned
historical/archive root. Add checks only when a drift has recurred. The point is
high signal, not a giant lint wall.
