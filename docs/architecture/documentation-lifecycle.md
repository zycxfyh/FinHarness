# Documentation Lifecycle Contract

> **Documentation lifecycle:** `current`

This document is the canonical lifecycle contract for authored FinHarness
Markdown. It complements Diátaxis: Diátaxis answers what kind of help a page
provides; lifecycle answers whether the page is current authority, a supported
transition, a proposal, historical evidence, or archived lookup material.

The lifecycle is deliberately closed:

```text
current
preview
deprecated
superseded
historical
archived
```

A recent edit does not promote old content. A move alone does not establish
historical meaning. Runtime code, Taskfile commands, tests, receipts, and the
canonical current documents remain the authority for shipped behavior.

## Ownership Model

`docs/architecture/system-catalog.yml` owns the repository-level current graph
and its non-current roots/paths:

- `documentation.navigation.entrypoints` start current traversal;
- `historical_roots` and `historical_paths` are excluded from current-fact
  traversal;
- `docs/archive/**` is interpreted as `archived`;
- the remaining configured historical roots/paths are interpreted as
  `historical`.

A document outside those configured roots is `current` unless it carries the
visible lifecycle banner defined below. There is no separate lifecycle JSON,
spreadsheet, or generated registry.

## State Semantics

| State | Current navigation | Maintained for shipped behavior | Required boundary | Command examples | Review expectation |
| --- | --- | --- | --- | --- | --- |
| `current` | Yes | Yes | Optional explicit banner | Must match live Taskfile/runtime truth | Updated with the owning change |
| `preview` | No | No | Banner, reason, and current-authority pointer | Must be labelled proposed/non-shipped | Reassess before implementation or promotion |
| `deprecated` | Yes, while supported | Yes, only for the transition window | Banner, replacement, reason, and removal trigger | Must remain executable until removal | Remove or extend only through the named trigger owner |
| `superseded` | No | No | Banner, exact current-authority link, and reason | Historical examples only | Retain only when distinct context remains |
| `historical` | No | No | Root/path classification or banner plus current-authority framing | Preserved as authored evidence; never runnable authority | Do not rewrite original claims to look current |
| `archived` | No | No | Archive root or banner plus reason | Lookup only; broken historical references may remain visible | Change only for safety, discoverability, or integrity |

## Visible Banner

Documents outside a catalog-owned non-current root use a visible blockquote
immediately after the title:

```markdown
> **Documentation lifecycle:** `superseded`
> **Current authority:** [Capital OS Layering](capital-os-layering.md)
> **Reason:** The implementation plan is complete; this copy remains for design history.
```

`deprecated` additionally requires:

```markdown
> **Removal trigger:** Remove after the compatibility consumer audit reaches zero callers.
```

`preview`, `historical`, and `archived` must state why the page is not current.
They should point to current authority when one exists; `None` is permitted only
when there is genuinely no maintained replacement.

## Redirect Stubs

When an important path moves, the old path may become a short redirect stub:

```markdown
# Previous title

> **Documentation lifecycle:** `superseded`
> **Current authority:** [Current authority](../current.md)
> **Reason:** The authored evidence moved into the archive without being duplicated.
> **Redirect stub:** [Archived evidence](../archive/family/original.md)
```

A redirect stub is not a second editable copy. It contains no duplicated body,
no independent commands, and no new design claims. The archived destination is
the preserved authored evidence.

## Movement And Deletion

- Prefer in-place classification when a page still has a useful stable path.
- Move completed plans, snapshots, and retired specifications by bounded family,
  preserving Git history and leaving a stub only where discoverability matters.
- Do not maintain both the old and new paths as complete copies.
- Delete only when no unique evidence or supported consumer remains and the PR
  records why Git history alone is sufficient.
- Do not recreate removed source files merely to make historical links green.

## Current-To-Noncurrent Links

A current page may link to non-current evidence only as visible context, not as a
runnable or canonical instruction. The source sentence must identify the target
as preview, superseded, historical, or archived context. The target's own banner
or catalog root remains the lifecycle source of truth.

## Promotion And Demotion

Promotion to `current` requires all of the following:

1. a named current owner;
2. verified correspondence with current code/Taskfile/product behavior;
3. inclusion through an intentional current route or canonical owner relation;
4. removal of unsupported future-tense or legacy claims;
5. `task docs:current-check` passing.

Demotion requires an exact lifecycle state, a reason, and—when another page now
owns the facts—a current-authority link. A timestamp or completed checklist is
not enough by itself.

## Machine Enforcement

`task docs:current-check` enforces that:

- only `current` and supported `deprecated` documents enter the current graph;
- catalog-owned historical/archive roots cannot be promoted by inbound links;
- explicit lifecycle states belong to the closed vocabulary;
- `superseded` documents identify current authority;
- `deprecated` documents identify current authority and a removal trigger;
- redirect stubs remain bounded and point to preserved evidence;
- generated current views and existing current-fact checks remain unchanged.

The checker validates lifecycle structure and graph authority. It does not infer
whether historical prose is philosophically correct, whether a proposal should
ship, or whether an old external URL remains reachable.
