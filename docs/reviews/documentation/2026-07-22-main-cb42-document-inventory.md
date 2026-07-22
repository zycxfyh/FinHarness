# Documentation Inventory Review — `main@cb42d460`

> Status: historical exact-SHA audit evidence  
> Issue: #450 (`DOCS-BOOT-00`)  
> Baseline: `cb42d460ac5d6267f59d8497b0565456537c9b9d`  
> Audit tool: `finharness-doc-inventory/1.0.0`  
> Scope: tracked repository Markdown only  
> Source mutation: none

## Decision

The documentation reconstruction may proceed beyond inventory, but the current
repository does not yet have a closed documentation lifecycle or a task-oriented
current graph.

The reviewed inventory contains **347** tracked Markdown files exactly once.
The governed current graph reaches **79** pages; **268** tracked pages are outside
that graph. The current graph is structurally valid but is not audience-balanced:
**57 of 79 pages (72.2%)** are primarily maintainer material, while user,
operator, developer, and auditor routes together account for 22 pages.

The inventory found four distinct problems that must not be collapsed into one
rewrite:

1. maintained entry and first-run pages contain concrete current-truth defects;
2. historical and superseded evidence can still appear in the current graph or
   be linked without a closed lifecycle boundary;
3. many valid current ADRs, contracts, runbooks, and generated views are
   intentionally or accidentally orphaned from current navigation;
4. commands and other machine-owned facts are repeated manually across many
   documents.

Issue #450 does not correct any of those documents. It establishes the reviewed
baseline and transfers each finding to the already-defined bounded owner.
Issue #451 remains dormant until #450 is merged and closed.

## Evidence

### Exact machine pass

The successful machine pass was produced by workflow run `29883336721` from
implementation head `b7193cfb4394e802b1ec2f72ea1d4f9dfaa428f6` against the
immutable pull-request base SHA above.

Artifact:

```text
name: documentation-inventory
artifact_id: 8515585849
digest: sha256:8ffcb442eb7ce259116a4301ca8fd6f40e9d7f22720bc644bf00824019a2dcea
```

The artifact contains:

```text
documentation-inventory.json
documentation-inventory.schema.json
documentation-link-graph.json
documentation-conflict-clusters.json
documentation-machine-report.md
documentation-source-bundle.tar.gz
```

The source bundle contains the same 347 Markdown blobs from the baseline tree.
The inventory records a SHA-256 content digest for every document.

### Method

The audit deliberately uses mature mechanics rather than a project-specific
Markdown platform:

```text
git ls-tree / git show
→ exact tracked tree and immutable blob content
→ markdown-it-py CommonMark AST
→ internal-link and heading extraction
→ closed JSON Schema validation
→ ignored .artifacts evidence
→ manual content review
```

Git timestamps were not used to classify lifecycle. A copied old document with a
recent timestamp therefore receives no automatic promotion, and an old current
contract receives no automatic demotion.

### Manual review coverage

The manual pass reviewed:

- all 79 current-navigation pages against their actual content;
- all 84 machine-identified current-looking orphan candidates;
- every current hard-coded-path finding;
- all 43 broken-link findings;
- the one duplicate-title cluster and six content-similarity clusters;
- every repeated live-Taskfile command cluster;
- every historical document family and each exceptional page whose status,
  location, or prose contradicted the family default.

Every one of the 347 inventory rows received one reviewed disposition through a
page-level review or a reviewed family contract. Machine fields remain marked
`machine_only` in the artifact because the artifact is discovery evidence, not a
second permanent documentation registry. This report records the reviewed
interpretation.

## Inventory Summary

| Measure | Result |
| --- | ---: |
| Tracked Markdown files | 347 |
| Current-navigation reachable | 79 |
| Outside current navigation | 268 |
| Current pages with machine error findings | 5 |
| Broken internal links | 43 |
| Documents containing hard-coded local paths | 55 |
| Hard-coded path occurrences | 98 |
| Conflict / repeated-fact candidate clusters | 62 |
| Duplicate-title clusters | 1 |
| Content-similarity pairs | 6 |
| Repeated live-task clusters | 55 |

### Current graph by primary audience

| Audience | Pages | Share |
| --- | ---: | ---: |
| Maintainer | 57 | 72.2% |
| User | 8 | 10.1% |
| Operator | 8 | 10.1% |
| Developer | 4 | 5.1% |
| Auditor | 2 | 2.5% |

This confirms the failure described by #453: the entry graph says “start with
the job” but routes most strongly into architecture, ADR, product direction, and
engineering governance.

## Reviewed Dispositions

| Reviewed disposition | Count | Meaning |
| --- | ---: | --- |
| `historical_keep` | 182 | Preserve authored evidence outside current authority. |
| `current_keep` | 64 | Current, reachable, and no inventory-level correction required. |
| `maintained_orphan_link_453` | 52 | Current maintained asset; add an intentional audience route or catalog relation. |
| `preview_or_historical_452` | 14 | Idea/musing family requires lifecycle decision, not current promotion. |
| `reclassify_historical_or_superseded_452` | 12 | Current-looking plan, snapshot, report, or old spec should leave current status. |
| `current_historical_link_boundary_452_453` | 6 | Keep current page but govern its historical links. |
| `current_truth_containment_451` | 5 | Current entry/first-run truth defect; narrow containment owner is #451. |
| `owner_decision_required` | 4 | Current contract versus completed plan cannot be inferred safely. |
| `remove_from_current_graph_452` | 3 | Explicitly historical page is reachable as current. |
| `superseded_keep` | 1 | Preserve with replacement boundary. |
| `archived_keep` | 1 | Preserve outside maintained guidance. |
| `current_path_cleanup` | 1 | Current ADR contains machine-specific sibling-repository paths. |
| `preview_refresh_or_supersede` | 1 | Roadmap contains a stale inspected-run snapshot. |
| `preview_explanation` | 1 | Educational policy draft must not appear as shipped product behavior. |

Counts sum to 347.

## Current-Truth Containment Transfer — #451

The following five maintained surfaces form one first-run truth cluster. They
should be corrected together under #451, not piecemeal in this inventory PR.

### 1. `docs/tutorials/golden-path.md`

Observed:

- contains the machine-specific command `cd /root/projects/finharness`;
- calls an isolated direct-seed receipt demo the supported first-run path;
- `task decisions:golden-path` creates temporary synthetic state;
- the next step starts `task api:serve`, which opens the default persistent
  workspace rather than the temporary demo workspace;
- describes the cockpit as potentially allowing human attestation/rejection even
  though `api:serve` is read-only;
- does not use canonical capital import, explicit shared workspace arguments, or
  restart/replay of the same persistent review state.

### 2. `docs/reference/commands.md`

Observed:

- describes `task api:serve` as a local “read/review” surface;
- omits `task cockpit:review` from the current product loop;
- therefore does not expose the actual governed human-review entrypoint or its
  write boundary.

### 3. `README.md`

Observed:

- correctly states later that `api:serve` is read-only and names
  `cockpit:review`, but earlier product-surface wording combines API reads and
  governed attestation without making the mode distinction explicit;
- promotes the synthetic Golden Path as the safe first step before the tutorial
  itself discloses the workspace discontinuity.

### 4. `docs/README.md`

Observed:

- routes a new user to the same Golden Path as the first end-to-end flow;
- leads with product direction, operating model, framework, and engineering
  leverage before the user task route is stable;
- does not distinguish the synthetic receipt demo from a canonical imported
  capital-review journey.

### 5. `docs/how-to/README.md`

Observed:

- labels the same Golden Path the first safe end-to-end run;
- inherits the tutorial’s workspace, mode, and product-completeness ambiguity.

Transfer rule: #451 may contain these false current claims but must not implement
the canonical first-capital-review journey owned later by #455.

## Lifecycle And Archive Transfer — #452

### Non-current pages inside the current graph

Three pages explicitly declare themselves historical/superseded while remaining
reachable through current navigation:

```text
docs/architecture/documentation-and-onboarding-plan.md
docs/architecture/evidence-inventory.md
docs/architecture/policy-contract.md
```

These are the clearest lifecycle counterexamples. They should retain historical
meaning but cease acting as current authority.

### Current-to-historical edges

Eight current pages contain eleven links into roots that the current catalog
classifies as historical. Some links are legitimate historical context, but the
repository has no uniform banner or link semantics that distinguishes context
from runnable authority.

Affected current pages include:

```text
README.md
docs/README.md
docs/architecture/capital-os-layering.md
docs/architecture/framework-index.md
docs/explanation/README.md
docs/product/product-roadmap.md
docs/reference/glossary.md
docs/reference/interfaces.md
```

### Reclassify as historical or superseded

The reviewed queue includes completed migration reports, superseded plans, old
execution-era specifications, and stale generated snapshots, including:

```text
docs/architecture/agent-native-target-space.md
docs/architecture/closure-report.md
docs/architecture/data-quality-interface-plan.md
docs/architecture/market-access-ledger-spec.md
docs/architecture/policy-evidence-interface-plan.md
docs/architecture/post-mvp-maturity-roadmap.md
docs/architecture/research-interface-vectorbt-spec.md
docs/engineering/execution-spine-debt-paydown.md
docs/operations/governance-dashboard-latest.md
docs/operations/repository-governance.md
docs/reports/trading-validation-report-v1.md
docs/security/sbom-and-provenance.md
```

### Preview / historical decision families

The eleven `ideas/` documents and three `docs/musings/` documents are useful
idea evidence, but none should become current product guidance merely because it
contains current-looking prose. They require one explicit preview/historical
family policy.

### Owner decisions that cannot be inferred

Four pages combine a plan/spec title with evidence that some or all of the work
has shipped:

```text
docs/architecture/agent-work-loop-plan.md
docs/architecture/data-quality-interface-pandera-spec.md
docs/architecture/data-validity-spec.md
docs/architecture/graph-rationalization-audit.md
```

Their canonical implementation owners must decide whether to split current
contract from historical delivery plan, supersede the document, or maintain it
as current Reference. The inventory does not guess.

## Navigation Transfer — #453

Fifty-two reviewed documents are maintained/current but outside the current
entry graph. This is not one homogeneous “orphan cleanup” list.

### Current accepted ADRs

Twenty accepted ADRs are not reachable from current navigation. They should be
available through one maintained decision index or the future “Understand
FinHarness” route, not individually injected into user navigation.

### Current contracts and architecture owners

Examples include:

```text
docs/architecture/artifact-store-contract.md
docs/architecture/canonical-capital-identities.md
docs/architecture/governance-proof-contract.md
docs/architecture/import-provenance-contract.md
docs/architecture/position-valuation-contract.md
docs/architecture/replay-safe-agent-authority-grants.md
docs/architecture/state-api-query-contract.md
docs/architecture/versioned-capital-mandate.md
docs/modules/agent-autonomy-control.md
docs/modules/capital-imports.md
```

These should be reachable from developer/auditor architecture routes while
remaining below user task entrypoints.

### Operator and auditor material

Current but unreachable material includes the security response runbook, MVP
hardening boundary, quality-governance operating model, generated attestation
inventory, and repository license decision. The future operator/auditor routes
must expose these deliberately.

### Intentionally non-navigation repository assets

`.github/SECURITY.md`, `.github/pull_request_template.md`, and selected source
folder READMEs are maintained assets but do not belong in primary product
navigation. “Not reachable from README” is therefore a discovery signal, not an
automatic defect.

## Generated Reference Transfer — #454

The inventory identified **55** live Taskfile commands repeated in three or more
documents. This is not 55 duplicate-document defects; it is evidence that command
facts lack one generated or schema-compared projection.

Largest repetition clusters:

| Task | Documents mentioning it |
| --- | ---: |
| `task check` | 72 |
| `task test` | 25 |
| `task governance:check` | 21 |
| `task docs:current-check` | 19 |
| `task lint` | 15 |
| `task security:scan` | 13 |
| `task hardening:gate` | 11 |
| `task beancount:import` | 9 |
| `task api:serve` | 8 |
| `task release:preflight` | 8 |
| `task wheels:check` | 8 |

The command Reference should derive command existence and machine-owned
descriptions from `Taskfile.yml`. Authored guidance may retain boundaries and
examples. The same pattern should later be applied to effective API operations,
config/environment reads, and selected supported schemas.

## Executable Journey Transfer — #455

No maintained current tutorial presently proves all of the following in one
workspace:

```text
canonical synthetic import
→ capital-truth readiness
→ positions and valuation gaps
→ Daily Brief
→ decision candidate scan
→ governed Cockpit review
→ receipt/timeline inspection
→ restart of the same workspace
→ no duplicate domain effect
```

The existing Golden Path proves a narrower direct-seed receipt-consumption demo.
That narrower proof remains useful after #451 labels it truthfully. It must not be
expanded into #455 inside the documentation containment PR.

## Link Findings

The machine pass found 43 broken internal links. Manual review confirmed that
none originate from a current-navigation page.

| Family | Broken links | Interpretation |
| --- | ---: | --- |
| Old industry-benchmark architecture pack | 24 | Links point to removed/moved ten-layer documents and modules. |
| `discipline-layer-baseline.md` | 13 | Line links point to removed execution/risk/trading source files. |
| Archived ten-layer docs | 2 | Archived tutorial targets no longer exist. |
| `ideas/README.md` and `ideas/backlog.md` | 2 | Both point to missing `ideas/BES.md`. |
| Other historical specs | 2 | Links point to removed execution/risk source files. |

#452 should decide whether historical evidence keeps visibly broken references,
receives bounded replacement links, or moves into a preserved archive bundle.
Current-doc gates should not require old source paths to reappear.

## Hard-Coded Local Paths

The inventory found 98 local-path occurrences in 55 documents.

- 93 occurrences are in non-current/historical evidence and should be handled by
  lifecycle policy rather than mass rewriting history.
- Five occurrences are in two current pages:
  - `/root/projects/finharness` in the Golden Path, owned by #451;
  - four `/root/projects/...` sibling-repository examples in
    `docs/adr/2026-06-18-controlled-vocabulary-and-two-tier-language.md`.

The ADR remains a valid current decision record, but its machine-specific sibling
paths should become neutral repository references or an explicitly historical
example under a bounded ADR-maintenance change.

## Duplicate And Similarity Review

### Duplicate title

`docs/architecture/governance-dashboard.md` and
`docs/operations/governance-dashboard-latest.md` share the title “Governance
Dashboard” but do not have equal authority. The architecture page describes the
current dashboard contract; the operations page is a generated June snapshot.
Keep the contract current and reclassify the snapshot as historical/runtime
evidence.

### Content-similarity pairs

Six pairs exceeded the conservative token-set similarity threshold.

- Two lesson drafts are near-identical generated candidates; retain their receipt
  lineage, but do not treat both as maintained guidance.
- The cognitive-engineering and goal-bound-workflow proposal pair has substantial
  overlap and should be linked, merged, or explicitly distinguished during
  lifecycle migration.
- The corresponding idea pair has the same overlap and belongs to the idea-family
  lifecycle decision.
- Three review pairs share delivery-template structure but record distinct
  historical executions; keep them as separate historical evidence.

Similarity is a review hint, not deletion authorization.

## Machine-Pass Corrections

The manual pass found and corrected several weaknesses before freezing this
report:

1. internal links must resolve against the complete tracked tree, not only the
   Markdown subset;
2. directory navigation targets are not missing files;
3. ordinary prose containing “historical” is not a lifecycle declaration;
4. `Status: accepted` on an ADR is decision status, not the documentation
   lifecycle enum;
5. repeated `task ...` candidates must be cross-checked against actual Taskfile
   task names;
6. a current-looking orphan may be an intentionally non-navigation repository
   asset;
7. automated similarity cannot decide merge, delete, or supersession.

These corrections are frozen by the adversarial self-test where mechanically
observable. Semantic disposition remains in this reviewed report.

## Ordered Migration Queue

The reviewed investment order remains:

```text
1. #451 — contain the five current first-run/entry truth defects
2. #452 — define lifecycle; remove three historical pages from current authority;
          migrate stale plans/snapshots and idea/history families in bounded slices
3. #453 — rebuild user/operator/developer/auditor/understanding routes;
          expose the 52 maintained orphan assets intentionally
4. #454 — project commands, API, config, and selected schemas from canonical source
5. #455 — prove first-run, blocked-data, and restart journeys in one workspace
6. #456 — evaluate a publisher only after the governed document graph is stable
```

At most one implementation leaf remains active at a time.

## Acceptance Review

| #450 acceptance | Evidence | Result |
| --- | --- | --- |
| Every tracked Markdown file represented exactly once | 347 Git-tree paths; uniqueness and schema checks | Pass |
| Current graph separated from historical/orphan pages | 79 current / 268 outside graph | Pass |
| Audience, type, lifecycle, source, owner, verification candidates | Closed per-document inventory fields | Pass |
| Duplicate/conflict candidates reported | 62 reviewed clusters | Pass |
| Broken links and local paths reported | 43 links; 98 path occurrences | Pass |
| Exact SHA, tool, roots, exclusions, limitations recorded | Artifact and this report | Pass |
| Manual review checks machine classifications | Page/family review and machine corrections above | Pass |
| No document moved, deleted, archived, or broadly rewritten | PR changes only audit tool, workflow, and this report | Pass |
| Findings transferred without second debt register | Ordered queue uses #451–#456 and existing owners | Pass |

## Non-Actions

This Issue did not:

- edit README, tutorial, command Reference, or product claims;
- move, delete, archive, or add lifecycle banners to source documents;
- alter product behavior;
- activate #451;
- create a permanent documentation registry, roadmap, or debt database;
- select MkDocs or another publisher;
- network-validate external URLs.

## Exit

After this report and the audit implementation pass exact-head project checks and
independent review, PR #460 may merge and #450 may close as completed. #451 must
remain dormant until a separate explicit activation decision.
