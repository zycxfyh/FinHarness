# FinHarness Evolution Roadmap — mini-RFC

Status: implemented; release gate passed
Logical slice: `ROADMAP-01`
Date: 2026-07-10

## 1. Change Class

**C2.** This slice creates a repository-grounded architecture and delivery
roadmap plus current-fact tests. It does not change runtime behavior.

## 1b. Product Claim / Layer / Thin Slice

FinHarness will have one maintained evolution plan that connects current
system status, canonical debt, classical/agentic ownership, the actual PR
genealogy, and future PR-sized slices with explicit entry and exit gates.

## 2. Current Problem

Roadmaps, closure reports, ledgers, and fast PR chains have described different
versions of the product. They do not give future contributors one answer to:

1. which debts must be paid before feature expansion;
2. which responsibilities are deterministic software versus Agent judgment;
3. which previous PR phases created, corrected, or merely relabeled a system;
4. what evidence permits the next phase to begin.

## 3. Target Behavior

- The roadmap derives active debt from the canonical register.
- It defines a three-plane responsibility model: classical, agentic, and
  human authority.
- It records causal PR phases from #78 through #227 and the local truth-recovery
  chain after `origin/main`.
- Every future slice has prerequisites, owned plane, artifacts, tests, exit
  criteria, and explicit deferrals.
- Current-fact tests fail when active debt or Agent closure status drifts.

## 4. Surface Inventory

- **Inputs:** git history, system catalog/maps, canonical debt register,
  executable Agent acceptance gate, implemented code/tests.
- **Outputs:** one architecture roadmap and fact-governance tests.
- **Network/runtime/database/receipts:** none.
- **Excluded:** paying down remaining debt, implementing Agent closure, opening
  product authority, creating GitHub PRs.

## 5. Default Path Invariant

No production code, API, frontend, database, receipt, Agent dispatch, or
execution behavior changes.

## 6. Release Decision

Merge now. The roadmap fact tests prove exact agreement with seven active and
three resolved canonical debts, eleven open and four passing Agent acceptance
contracts, the audited PR phases, responsibility laws, and ordered future
slices. Documentation-current checks and the complete project gate pass with
lint, mypy, 891 unit tests, eight integration tests, frontend/governance checks,
the research experiment, and evaluation smoke at real zero exit status.
