# Documentation Fact Governance

> **Documentation lifecycle:** `current`

FinHarness documentation exists to enable supported tasks, explain durable
boundaries, and preserve unique evidence. It must not become a second runtime,
work-state, schema, command, or roadmap database.

Lifecycle semantics are owned by the
[Documentation Lifecycle Contract](documentation-lifecycle.md). Current product
orientation and fact ownership are summarized in
[FinHarness Current System](../current-system.md).

## Authority lanes

| Lane / state | Rule |
| --- | --- |
| `current` | Maintained guidance. Must agree with its canonical code, model, task, catalog, or GitHub owner. |
| `deprecated` | Still-supported compatibility guidance with a replacement and removal trigger. |
| `preview` | Proposed material. Never current capability or work authorization. |
| `superseded` | Replaced material retained only for distinct context and linked to current authority. |
| `historical` | Authored evidence preserved as it was; not runnable current guidance. |
| `archived` | Lookup-only legacy material outside the maintained graph. |

An inbound link, timestamp, recent edit, or directory move cannot promote a
non-current document.

## Canonical owners

| Fact | Canonical owner | Prose responsibility |
| --- | --- | --- |
| Current capability and boundaries | `docs/current-system.md` grounded in code/tests | Explain the smallest accurate current system. |
| Product objective | GitHub Program #277 | Explain the stable outcome and investment principles, not child status. |
| Work authorization and sequence | GitHub Issue/PR state, labels, and native relationships | Link to live views; never copy Waves or mutable status. |
| Commands | `Taskfile.yml` | Explain how and when to use supported commands. |
| API operations | Effective FastAPI route graph and models | Explain user/operator semantics and boundaries. |
| Configuration and schemas | Canonical config/model sources and direct environment reads | Document supported external fields only. |
| System ownership and lifecycle | `system-catalog.yml` | Generate inventory views; do not add a parallel catalog. |
| Documentation lifecycle | `documentation-lifecycle.md` plus catalog roots/paths and visible banners | Keep current and non-current material separate. |
| Verified engineering debt | `debt-register.json` | Link to the register; do not copy counts or active lists. |
| Consumer classification | `attestation-consumers.json` | Generate its audit view. |
| Support-surface lifecycle | `support-surface-registry.yml` | Project the registered support boundary. |
| Historical decisions and evidence | ADRs, proposals, reviews, notes, and Git history | Preserve context without rewriting it as current truth. |

A prose page may summarize and link to a canonical owner. It must not redefine
that owner's mutable fact set.

## Minimal update rule

When a change alters a user-visible task or durable boundary:

1. change the canonical source;
2. update only the maintained guidance that a user or maintainer actually needs;
3. regenerate catalog-owned views when their source changes;
4. run `task docs:current-check`.

Do not update every architecture, module, roadmap, review, or historical page
that contains related words. Do not create a proposal, review, lesson, or module
log for an ordinary reversible change unless it preserves unique decision or
failure evidence.

## Current machine guard

`task docs:current-check`:

- renders catalog-owned generated sections and rejects drift;
- traverses the maintained Markdown graph from catalog entrypoints;
- validates internal links and live Taskfile references in that graph;
- enforces the closed lifecycle and current/deprecated entry eligibility;
- prevents non-current roots or banners from being promoted by inbound links;
- validates superseded replacement links and deprecated removal triggers;
- runs focused catalog, lifecycle, support-surface, and removal contracts.

Historical and archived material is intentionally excluded from current command
truth. Old claims may remain as evidence.

Generated views are refreshed with:

```bash
task docs:generate-current-views
```

Add a new machine check only after the same material drift has recurred or the
failure protects a concrete irreversible boundary. The goal is high-signal
current truth, not a larger lint wall.
