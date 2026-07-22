# Review: PR #459 Fifth-Round Truth-Boundary Redesign

Date: 2026-07-22

Status: open

Related Issue: #375

Related PR: #459

Author-side reviewed head: `eaf8f8360bd1fc60cc11226efc15710794d22b44`

Base at author-side validation: `cb42d460ac5d6267f59d8497b0565456537c9b9d`

Classification: process issue | model issue | recovery authority issue | provenance issue

## Evidence Legend

- **Observed** — directly established by repository state, tests, artifacts, or the execution trace.
- **Inferred** — a reasoned conclusion from multiple observed facts.
- **Proposed** — a decision or action recommended for the next stage.
- **Unknown** — evidence is not yet available or is insufficient.

## Binding Status

This review records the author-side fifth-round design, implementation, and delivery
closure. It deliberately does not claim that PR #459 is independently approved or
production mature.

Pending bindings:

- **Unknown:** fifth independent C3 review conclusion and reviewer identity.
- **Unknown:** real legacy database migration rehearsal artifact.
- **Unknown:** concurrent import/recovery and crash-point evidence.
- **Unknown:** production-scale materialized-commitment benchmark.
- **Unknown:** final-main commit identity after merge.

These items must be appended or linked later rather than silently inferred.

### Independent Review Binding Template

Complete this block when the independent C3 result is available. Do not replace the
author-side evidence above.

```text
review_date:
reviewer:
reviewed_pr_head:
reviewed_merge_ref:
decision: approve | request_changes | blocked
finding_ids:
finding_summary:
resolution_commits:
revalidation_runs:
remaining_p0_p1:
linked_review_artifact:
```

---

## 1. Task Overview and Goal Review

### 1.1 Core objective

The fifth round was not another zero-row feature increment. It addressed the final
truth-boundary findings from the fourth independent C3 review:

1. current authority could still be derived from an incomplete or corrupted
   `ImportDomainHead`;
2. historical replay still temporarily overwrote user-owned CSV or Beancount files;
3. canonical `InstrumentIdentity` rows contained source-specific mutable provenance;
4. legacy migration could still infer current state from weak clock ordering;
5. receipt commitment normalization used a basename heuristic broad enough to hide
   path drift.

### 1.2 Scope

The implementation scope was limited to:

- exact current-projection authority proof;
- transaction-time authority revalidation;
- isolated immutable replay workspaces;
- critical source-integrity error propagation;
- canonical instrument/source-claim separation;
- fail-closed legacy domain-head migration;
- field-aware materialized-record commitment normalization;
- manifest v6 and StateCore v17 compatibility boundaries;
- destructive contracts and exact-head delivery evidence.

Explicit non-goals were live execution, new importer features, Agent/DecisionCase
work, a general provenance framework, a full StateCore rewrite, and the documentation
system restart.

### 1.3 Success criteria

The round required all of the following:

- each independent-review finding had a destructive test that failed on the prior head;
- current authority could only be produced from exact head/batch/manifest bindings;
- replay did not write user-owned source paths;
- source-integrity failures could not be swallowed by broad recovery handling;
- multiple sources could coexist around one canonical instrument;
- migration with multiple candidates remained unresolved;
- same-basename path drift changed the commitment;
- focused, full local, browser, profile, fuzz, red-team, and security checks passed;
- GitHub proved both PR-head and synthetic merge-ref identities;
- the PR remained Draft.

### 1.4 Overall result

**Observed:** the author-side implementation and delivery closure completed at
`eaf8f8360bd1fc60cc11226efc15710794d22b44`, with 13 successful GitHub checks,
one expected skip, no failures, and no pending checks.

**Inferred:** author-side goal attainment was approximately 96%. The missing portion
is independent approval and production-oriented evidence, not a known unimplemented
fifth-round code requirement.

---

## 2. Execution Process Review

### 2.1 Material phases

| Phase | Material event | Result |
| --- | --- | --- |
| Design freeze | Five architecture decisions were written before implementation | Prevented another local patch-only round |
| Red contracts | Invalid head, real-file replay, critical failure, multi-source identity, migration ambiguity, and path collision were reproduced | Five failures and one missing error type on the old implementation |
| Authority redesign | Added `CurrentProjectionAuthority` and a single strict validator | Invalid or stale heads stopped authorizing current projection |
| Replay redesign | Added temporary `ReplayWorkspace` staging | Historical bytes stopped being written to user files |
| Provenance redesign | Added `InstrumentIdentitySourceClaim` | Canonical identity and source-specific claims could coexist |
| Migration redesign | StateCore advanced to v17 and multi-candidate resolution became fail-closed | Weak clock ordering was removed from current-head selection |
| Commitment redesign | Manifest advanced to v6 with context-aware receipt references | Same basename no longer implied equivalent lineage |
| Verification | Focused, full local, independent local, and GitHub exact-head gates ran | All author-side gates passed |
| Documentation binding | This review was added after the implementation closure | Independent-review and production gaps remain explicit |

Routine Git status checks, workflow polling, artifact downloads, and repeated log tails
are intentionally aggregated here.

### 2.2 Key decisions

#### Authority as a capability object

**Observed:** the previous convenience API returned a `set[str]` of domains and could
not carry exact head, batch, manifest, clock, or revision evidence.

The replacement introduced:

```text
CurrentProjectionAuthority
validated_current_projection_authority()
```

The proof binds source kind, source ID, domain, batch, manifest, canonical head ID,
materialization clock, and head revision.

**Inferred:** this converted current state from a query convention into a capability
that can be validated, invalidated, and revalidated inside a transaction.

#### Eliminate external compensation where possible

**Observed:** the previous round improved rollback after writing historical bytes to
real files, but the normal replay path still created a source-integrity window.

The fifth round instead staged immutable bytes in a temporary source tree and passed
the staged physical path while preserving the logical source identity.

**Inferred:** removing the side effect is stronger than attempting to make its
compensation perfect.

#### Separate entity from provenance

**Observed:** two valid sources for the same SPY canonical ID produced different
`source_refs`, causing one receipt's content proof to invalidate the other.

`InstrumentIdentitySourceClaim` now stores receipt-specific provenance, while the
canonical row stores cross-source identity attributes.

**Inferred:** the defect was ontological, not merely a last-writer bug.

#### Refuse to guess during migration

**Observed:** the old migration selected a candidate from multiple historical batches
using clock ordering.

The new rule is:

```text
0 candidates -> no head
1 candidate  -> backfill
>1 candidates -> unresolved
```

**Inferred:** an explicit absence of current truth is safer than a fabricated current
truth in a capital-state system.

#### Version the proof ontology

**Observed:** the fifth round changed canonical identity commitments, source claims,
and receipt-reference normalization.

Manifest v6 and StateCore v17 were used rather than silently changing v5/v16 meaning.

### 2.3 Failures and corrections

#### Invalid task name

**Observed:** `task dependency:base` did not exist. The repository task list was read,
and `task deps:probe-all` was then used successfully.

**Root cause:** a remembered or inferred command was used before consulting repository
truth.

**Impact:** low; no code or evidence was corrupted.

#### PR contract mismatch

**Observed:** the first PR-body update lacked the exact governance fields `Negative
evidence` and `Persistence/restart`. The repository checker rejected it. The fields
were added and the contract then passed.

**Root cause:** semantically present prose did not match the machine-owned contract.

#### GitHub observation-channel failure

**Observed:** `gh run watch` exited with `unexpected EOF` while the workflow continued.
The existing run was queried directly; no workflow was retriggered.

**Inferred:** observation failure and execution failure were correctly kept separate.

### 2.4 Tool and method efficiency

**Observed strengths:** real worktree execution, test-first contracts, exact SHA
tracking, repository-owned tasks, PR contract validation, and merge-ref identity
artifacts.

**Observed inefficiencies:** one invalid task invocation, one malformed local JSON
parser, one incomplete PR contract draft, and substantial repeated full-suite
execution.

**Inferred:** repeated full-suite execution is justified for a C3 truth-boundary
change. The avoidable waste lies in command discovery and contract generation, not in
removing independent evidence layers.

---

## 3. Results and Metrics

### 3.1 Repository result

| Metric | Result |
| --- | --- |
| Author-side head | `eaf8f8360bd1fc60cc11226efc15710794d22b44` |
| Base | `cb42d460ac5d6267f59d8497b0565456537c9b9d` |
| Commits | 31 |
| Changed files | 21 |
| Diff | `+6367 / -416` |
| Local/remote | identical |
| Ahead/behind main | `31 / 0` |
| Worktree | clean |
| PR state | Open, Draft |
| Mergeability | `MERGEABLE` |
| Merge state | `CLEAN` |

### 3.2 Verification result

Focused fifth-round contracts:

```text
14 / 14 passed
```

Full local gate:

```text
1571 / 1571 unittest
95 / 95 pytest
8 / 8 integration
```

Also passed:

- Ruff;
- Mypy over 157 source files;
- Python compile;
- frontend, governance, architecture, and rules;
- five browser paths;
- base/data/research/agent/eval dependency profiles;
- deterministic fuzz 68/68;
- Promptfoo boundary 6/6 with `quality_ok=true`;
- Gitleaks with zero findings;
- Trivy with zero vulnerabilities and zero misconfigurations.

Local timing artifact:

```text
status=passed
failed_stage=null
stage_count=12
total_duration_seconds=397.184
```

Remote timing artifact:

```text
status=passed
failed_stage=null
stage_count=12
total_duration_seconds=359.805
```

GitHub identity evidence:

```text
PR head: eaf8f8360bd1fc60cc11226efc15710794d22b44 -> passed
merge ref: 05106226c0f3c3cc96c7fd3d29839ad76f3b0570 -> passed
```

### 3.3 Quality assessment

**Observed:** known fourth-review counterexamples are directly covered and pass on the
new head.

**Inferred:** correctness and auditability are high for the defined contracts.

**Unknown:** concurrency safety, real-database migration behavior, crash recovery, and
large-data performance remain unproven.

### 3.4 Goal comparison

| Goal | Status | Evidence type |
| --- | --- | --- |
| Exact authority proof | achieved | Observed |
| User source files remain unwritten during replay | achieved | Observed |
| Multi-source canonical instrument coexistence | achieved | Observed |
| Migration no longer guesses current | achieved | Observed |
| Field-aware path commitment | achieved | Observed |
| Full local and remote exact-head closure | achieved | Observed |
| Independent C3 approval | pending | Unknown |
| Real legacy DB rehearsal | pending | Unknown |
| Production-scale performance | pending | Unknown |

---

## 4. Comparative Analysis

### 4.1 Planned versus actual path

The intended path was:

```text
authority proof
-> replay isolation
-> provenance split
-> fail-closed migration
-> field-aware commitment
-> full validation
```

**Observed:** the implementation broadly followed this sequence.

Material deviations:

- StateCore advanced to v17 rather than only adjusting v16 because exact head revision
  and source claims required new persisted structure.
- The destructive suite grew from six initial cases to fourteen to cover ordinary
  retry, transaction-time revalidation, Broker multi-source behavior, and v5/v6
  compatibility.
- PR size grew to 21 files and 6367 added lines.

**Inferred:** most scope growth was necessary to make the original invariants true,
but the total size increases review fatigue and signals that #375 initially
underestimated the ontology impact of full-import deletion authority.

### 4.2 Alternative approaches

| Alternative | Advantage | Failure mode | Decision |
| --- | --- | --- | --- |
| Continue returning domain strings | simple | cannot prove exact authority or freshness | rejected |
| Overwrite real files then compensate | reuses path-only adapters | creates a source-integrity window | replaced |
| Last-writer-wins canonical identity | simple persistence | valid sources invalidate each other | rejected |
| Select maximum timestamp | no new unresolved state | clock is not transaction order | rejected |
| Normalize all receipt basenames | stable retry | hides path drift | replaced |
| Full event-sourcing rewrite | conceptually broad | disproportionate scope and migration cost | non-goal |

### 4.3 Mature-practice comparison

The implementation aligns with mature practice in:

- capability-style authority;
- transaction-time revalidation;
- external-side-effect isolation;
- entity/provenance separation;
- fail-closed migration;
- semantic schema versioning;
- exact-head CI evidence.

It remains below production maturity because it lacks:

- independent review on the new head;
- real database migration rehearsal;
- concurrency and crash-point tests;
- formal capacity benchmarks;
- an operator runbook and unresolved-head workflow.

### 4.4 Relative strengths and weaknesses

**Inferred strengths:** stronger authority boundary, smaller external failure domain,
correct provenance model, and clearer uncertainty handling.

**Observed weaknesses:** large PR, concentrated complexity in `store.py` and recovery,
multiple schema generations inside one issue, and increased operational burden.

---

## 5. Success Factors and Lessons

### 5.1 Successful practices

#### Design before the fifth implementation round

**Observed:** implementation began only after the user approved an ADR-level five-part
design.

**Why it worked:** it stopped another sequence of local patches and established shared
invariants.

**Reusable rule:** after repeated architecture-level review failures, pause coding and
freeze ontology, authority, provenance, and failure boundaries first.

#### Counterexamples mapped directly to findings

**Observed:** the first new run produced five failures and one missing exception type,
each corresponding to an independent finding.

**Why it worked:** passing tests could later be interpreted as closure of explicit
counterexamples rather than generic confidence.

#### Side-effect elimination

**Observed:** replay moved from real-file overwrite/restore to isolated staging.

**Why it worked:** correctness no longer depends on compensating a normal-path external
mutation.

#### A single authority validator

**Observed:** recovery, retry, predecessor selection, and audit were routed through the
strict authority proof.

**Why it worked:** it reduced local interpretations of current truth.

#### Honest completion status

**Observed:** when asked whether the task was done, the response distinguished local
implementation completion from remote delivery closure.

### 5.2 Start / Stop / Continue

#### Start

- Generate PR bodies from repository-validated templates.
- Discover Taskfile commands before invocation.
- Add a scope-escalation checkpoint when one issue crosses schema, recovery, and
  identity boundaries.
- Run migration rehearsals on realistic database copies.
- Build state-machine tests for concurrency and crash points.

#### Stop

- Inferring transaction order from timestamps.
- Treating physical paths as immutable source identity.
- Storing mutable source provenance in canonical entities.
- Replaying history by modifying user-owned files.
- Calling author-side green checks production maturity.
- Guessing repository task names.

#### Continue

- Destructive tests before implementation.
- Separate test, implementation, and governance commits.
- Exact PR-head and merge-ref proof.
- Fail-closed ambiguity handling.
- Draft status until independent review completes.

### 5.3 Root-cause analysis

#### Why did repeated reviews reveal deeper issues?

1. #375 appeared to be a zero-row importer edge case.
2. Full zero-row import carries deletion and current-state replacement semantics.
3. Replacement authority depends on ownership, lineage, current-head truth, immutable
   evidence, recovery rights, and migration semantics.
4. Those concepts were initially implemented across separate mechanisms rather than one
   explicit truth model.
5. Each review closed one layer and exposed the next hidden assumption.

**Inferred root cause:** the issue was initially scoped below its true authority and
ontology impact.

#### Why did canonical identities conflict across sources?

1. The same canonical instrument ID was correctly derived by several sources.
2. The canonical row also stored source-specific references.
3. Later sources overwrote those references.
4. Earlier receipts then observed content drift.
5. Legal multi-source coexistence was treated as corruption.

**Inferred root cause:** canonical entity and provenance relation were mixed.

#### Why did replay write real files?

1. Adapters accepted physical paths.
2. Recovery possessed immutable bytes but lacked logical/physical source separation.
3. Reusing adapters therefore required writing the bytes to their original path.
4. Compensation was added to undo the write.
5. Compensation failure became a user-source integrity risk.

**Inferred root cause:** adapter input contracts coupled logical identity to physical
read location.

---

## 6. Limitations, Risks, and Improvements

### 6.1 Current limitations

- **Observed:** no fifth independent C3 decision is bound to this review.
- **Observed:** no real legacy database migration rehearsal is recorded.
- **Unknown:** concurrent import/recovery behavior under head revisions.
- **Unknown:** crash behavior around staging, artifact writes, and DB commit boundaries.
- **Unknown:** commitment and audit cost at production-scale row counts.
- **Observed:** PR review surface is large: 21 files and 6367 additions.
- **Observed:** `store.py` and recovery responsibilities continue to grow.
- **Observed:** v5 current receipts require explicit v6 re-import rather than transparent
  promotion.
- **Inferred:** fail-closed unresolved heads need an operator-facing resolution path.
- **Observed:** default-branch dependency alerts exist independently of this PR; this
  PR's dependency review, Gitleaks, and Trivy checks passed.

### 6.2 Actionable improvements

#### Process

- Add a mandatory reference/ontology checkpoint when a fix affects three or more
  bounded contexts.
- Generate an authoritative command list, migration matrix, and consumer inventory at
  the start of each C3 execution.
- Use a PR-contract template before the first body update.

#### Verification

- Add model-based sequences across import, retry, damage, recovery, migration, and
  concurrent current transitions.
- Add fault injection at workspace staging, artifact reads, receipt writes, DB
  pre-commit/post-commit, and cleanup.
- Rehearse v14 -> v15 -> v16 -> v17 on an anonymized historical database copy.
- Benchmark 1k, 10k, and 100k materialized identities.

#### Architecture

- Separate authority, migration, materialization proof, and head transitions from
  `store.py` in a later dedicated architecture issue.
- Add a typed `RecoveryPlan` dry-run surface.
- Design an unresolved-head resolver with candidate-set digest and receipt output.

#### Agent execution rules

Before saying a C3 task is complete, verify:

```text
implementation
focused tests
full local gate
independent local gates
push
PR contract
exact-head workflows
clean worktree
```

A tool observation failure must trigger a state re-read, not duplicate execution.

---

## 7. Reproducibility, Documentation, and Engineering Maturity

### 7.1 Reproducibility

**Observed:** code-level reproducibility is high because the review binds exact local,
remote, base, PR-head, and merge-ref SHAs; repository tasks and lockfiles were used;
and the worktree was clean.

**Unknown:** environment-level reproducibility across filesystems, symlink behavior,
large Beancount include graphs, and concurrent processes is not established.

### 7.2 Documentation completeness

This review provides the execution and decision record, but the following durable
documents remain missing:

- `CurrentProjectionAuthority` ADR;
- ReplayWorkspace threat model;
- canonical instrument/source-claim ontology;
- v14-to-v17 migration runbook;
- manifest v5/v6 compatibility matrix;
- unresolved-head operator procedure;
- production capacity benchmark report.

The future independent-review result should be linked under **Binding Status** and in
section 9 without rewriting the author-side evidence.

### 7.3 Best-practice adherence

| Practice | Assessment |
| --- | --- |
| Destructive red/green contracts | high |
| Exact-head CI | high |
| Fail-closed ambiguity | high |
| Transaction-time revalidation | high |
| External side-effect isolation | high |
| Semantic schema versioning | high |
| Version-control discipline | high |
| Module separation | medium-low |
| Migration operability | medium |
| Independent review | pending |
| Performance engineering | pending |
| Production observability | insufficient |

### 7.4 Maturity boundary

**Observed:** the strongest current evidence is integration/smoke validation, exact-head
CI, deterministic fuzz, browser testing, and static/security analysis.

**Unknown:** no formal production workload benchmark, soak test, concurrent stress test,
or real historical migration rehearsal exists.

Therefore this review must not claim production maturity. The accurate status is:

> High-confidence development and integration validation completed; production
> operational maturity remains unproven.

---

## 8. Overall Assessment

### 8.1 Score

**Inferred score: 8.8 / 10.**

Positive factors:

- all five truth-boundary findings received root-cause-level changes;
- replay removed real user-file mutation from the normal path;
- authority became explicit and transactionally revalidated;
- provenance ontology was corrected;
- migration became fail-closed;
- local and remote exact-head evidence was complete;
- PR remained Draft.

Deductions:

- the PR is very large;
- foundational issues required several review rounds to expose;
- real migration, concurrency, crash, and capacity evidence is missing;
- operational documentation trails the implementation;
- independent approval is pending.

### 8.2 Project value

**Inferred:** the fifth round advances FinHarness from “manifested imports with a
current pointer” toward a system where current authority, historical evidence,
canonical identity, source provenance, and migration uncertainty have distinct,
explicit contracts.

This foundation is reusable by future capital-state admission, reconciliation, and
Agent tool-authority work, but it should not be generalized further inside #459.

---

## 9. Follow-up Actions and Knowledge Capture

### 9.1 Debt classification

#### This stage should have solved but has not yet closed

- Fifth independent C3 review binding.
- Real legacy database migration rehearsal.
- Final-main identity after merge.

#### Newly discovered and appropriate for the next stage

- Concurrent authority revision tests.
- Crash-point recovery tests.
- Manifest v5-to-v6 operational runbook.
- Unresolved-head dry-run and resolution workflow.
- ReplayWorkspace symlink/path-boundary tests.
- Production-scale proof benchmark.

#### Long-term structural debt

- `statecore/store.py` responsibility concentration.
- Recovery-module size and state complexity.
- Repeated schema evolution without a consolidated import-truth ADR.
- Governance evidence that remains partially line-number-sensitive.
- Production observability and operator tooling gaps.
- Default-branch dependency alerts outside this PR's scope.

#### Explicit non-goals

Do not add the following to the next #459 closure stage:

- live broker execution;
- Agent/DecisionCase vertical work;
- a general event store or full W3C PROV implementation;
- all identity-table refactoring;
- recovery frontend UI;
- documentation-system restart;
- broad StateCore decomposition;
- unrelated dependency remediation;
- Issue #376 or another importer feature.

### 9.2 Priority assessment

| Issue | Severity | Probability | Cost | Stage |
| --- | --- | --- | --- | --- |
| Independent C3 review pending | Critical | High | Medium | next P0 |
| Real DB migration rehearsal missing | Critical | Medium | Medium | next P0 |
| Final-main identity missing | High | Certain after merge | Low | merge P0 |
| Concurrent authority race unknown | High | Medium | Medium-High | next P1 |
| Crash-point behavior unknown | High | Medium | Medium | next P1 |
| v5/v6 operational process incomplete | High | Medium | Medium | next P1 |
| Unresolved-head operator path missing | Medium-High | Medium | Medium | next P1 |
| ReplayWorkspace symlink boundary | High | Low-Medium | Medium | next P1 |
| Large-scale proof performance unknown | Medium-High | Medium | Medium | next P1 |
| `store.py` responsibility concentration | High | High | High | separate architecture issue |
| Recovery complexity | High | High | High | separate architecture issue |
| Line-number governance fragility | Medium | High | Medium | P2 |
| Default-branch dependency alerts | High | Medium | Medium | separate security line |

### 9.3 Decision and action output

#### Overall decision

**Proposed: pause feature expansion and continue review/production-oriented
validation.**

A broad rewrite is not recommended inside #459 because it would destroy the current
causal review boundary. New product functionality is also not justified while the
remaining risk is independent approval, migration, concurrency, crash behavior, and
operations.

#### P0 actions

1. **Independent C3 review**
   - Suggested owner: reviewer independent from the implementation agent.
   - Acceptance: inspect all head consumers, ReplayWorkspace adapters, claim
     uniqueness/recovery, v17 migration, and v5/v6 compatibility; leave no unresolved
     P0/P1 finding.

2. **Real legacy DB migration dry-run**
   - Suggested owner: StateCore/data maintainer.
   - Acceptance: record before/after versions, row counts, candidate counts, ambiguous
     heads, source-claim migration counts, `foreign_key_check`, `integrity_check`, and
     unresolved findings on a copy.

3. **Pre-merge base calibration**
   - Suggested owner: PR owner.
   - Acceptance: if main advances, regenerate the merge ref, rerun required exact-head
     checks, and update all exact SHA claims.

#### P1 actions

- Model-based concurrent authority tests.
- Crash-point fault injection.
- v5/v6 re-import runbook and compatibility matrix.
- Unresolved-head resolution CLI design.
- 1k/10k/100k materialization-proof benchmark.
- ADRs for authority, replay, provenance, and migration.

#### Knowledge to make durable

1. Current state must come from an explicit, exact, transactionally revalidated
   authority proof; never infer it from clocks, paths, or record existence.
2. Recovery tests must prove both the desired repair and non-modification of every
   unauthorized current projection.
3. Canonical entities must not store source-specific mutable provenance; source claims
   are separate and coexistent.
4. When database and user resources cannot share an atomic transaction, prefer isolated
   staging over compensating mutations to user resources.
5. More than one legacy current candidate means unresolved, not “choose the most
   plausible.”
6. Completion means implementation, focused and full validation, push, PR contract,
   exact-head workflows, and clean worktree—not merely green unit tests.

---

## 10. One-Sentence Summary

The fifth round replaced a chain of recovery patches with explicit authority,
isolated replay, separated provenance, fail-closed migration, and field-aware proof
contracts; the immediate next step is independent C3 review and real migration,
concurrency, and crash validation—not additional feature scope.
