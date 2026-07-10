# FinHarness Evolution Truth Rebase — mini-RFC

Status: implemented; release gate passed  
Logical slice: `TRUTH-01`  
Date: 2026-07-10

## 1. Change Class

**C2.** This slice changes current architecture status and the meaning of a
user-visible verification script. It does not change runtime behavior, but it
does correct claims that currently affect future architecture decisions.

## 1b. Product Claim / Layer / Thin Slice

FinHarness must describe shipped capability at the level supported by runtime
evidence. The smallest slice is to downgrade Wave 2.2 from an operational Agent
Work Loop to a deterministic orchestration scaffold and make that status
machine-checked.

This is an L8 Review / Learning / Governance change. It enables later work on
the real Agent Work Loop without treating the existing scaffold as a finished
foundation.

## 1c. Module Placement / System Boundary

The change belongs to EOS Governance / Quality and Architecture Memory. It
reads the existing work-loop implementation and smoke scripts but does not
alter Agent Cognition Runtime, State Core, the Execution Kernel, API routes, or
the cockpit.

Dependency direction remains:

```text
runtime facts -> architecture status checks -> current documentation
```

Documentation must not be treated as proof of runtime behavior.

## 2. Current Behavior

`framework-index.md` says Wave 0–2.2 is delivered, describes the work loop as a
full cycle, and reports 24/21 smoke checks. The scripts actually contain 23 and
18 checks. The work-loop smoke accepts a failed quote dispatch and prints that
the loop is operational even though arguments, observation-driven decisions,
step budgeting, result persistence, receipt linkage, and workspace hydration
are not semantically closed.

Existing docs-current tests validate paths and task names but do not validate
these architecture claims.

## 3. Target Behavior

- Wave 2.2 is described as a deterministic work orchestrator scaffold.
- The Agent Work Loop remains a target whose acceptance criteria are unmet.
- Smoke output states exactly what it proves.
- Smoke check counts are derived from the scripts and enforced by tests.
- Current documentation cannot reintroduce the audited overclaims.

## 4. Surface Inventory

- **Inputs:** current work-loop code, smoke scripts, framework index, Wave 2.2
  plan.
- **Outputs:** corrected current status and executable documentation checks.
- **External calls / network:** none.
- **Failure surfaces:** brittle text claims, inaccurate check counts, future
  architecture sync that promotes status without semantic proof.
- **User-visible surface:** smoke command wording and current architecture docs.
- **Excluded:** runtime control-flow changes, new models, new receipt kinds,
  State Core changes, Execution Kernel changes, API changes.

## 5. Default Path Invariant

Production/runtime behavior is unchanged. The existing Python work-loop entry
points retain their signatures and behavior. Verification is limited to
docstrings, architecture docs, smoke wording, and docs-current tests.

## 6. Traceability Matrix

| Design commitment | Code/document point | Test | Gate probe |
| --- | --- | --- | --- |
| Work Loop is not called operational | framework index + smoke | `test_agent_work_loop_status_is_not_overclaimed` | `task docs:current-check` |
| Smoke counts reflect executable checks | both smoke scripts + framework index | `test_agent_smoke_check_counts_match_framework_index` | AST call count |
| Wave 2.2 acceptance remains visibly unmet | work-loop plan | `test_agent_work_loop_plan_records_unmet_acceptance` | required status text |
| Runtime behavior is unchanged | no functional code edits | existing agent tests | `task test` |

## 7. Test / Gate Plan

- Run `tests.test_docs_current_facts` first.
- Run work-loop model tests and both smoke scripts.
- Run `task docs:current-check` and `task governance:check`.
- Run lint, mypy, and the full unit suite before release.
- Independent review should compare each remaining Work Loop acceptance
  criterion with runtime evidence, not with this document.

## 8. Product Surface Review

No new product surface is added. The value is that future agents and humans no
longer plan Wave 3 from a false lifecycle-completion claim.

## 9. Not Claimed / Debt

This slice does not close the Agent Work Loop. It does not unify the full
system catalog, merge the two debt ledgers, remove legacy write routes, enforce
ExecutionCapabilities, or add the Claims-to-Proof manifest. Those remain
`TRUTH-02` and later slices.

## 10. Release Decision

**Merge now.** The slice changes no runtime behavior, the new AST-backed
docs-current checks reject the former status/count claims, both agent smoke
scripts pass with calibrated wording, and `task check` completed with a real
zero exit code. Remaining semantic closure work is explicitly retained as
debt rather than hidden behind the release decision.
