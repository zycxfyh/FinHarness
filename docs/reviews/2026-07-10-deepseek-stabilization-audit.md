# DeepSeek Stabilization Chain Audit

Status: corrected locally
Audited: 2026-07-10
Scope: PRs #228–#233 and commits from `1f53664` through `d0da331`

## Decision

The chain contains useful implementation work, but its final claim that all
engineering debt was cleared is false. CI was green because several debt
verifiers checked structural presence rather than the desired semantics.

After correction, the canonical register reports **8 resolved and 2 active**:

- `ENG-DEBT-0002` remains active until PaperValidation has a machine-readable
  consumer inventory plus execution/network import and broker-registry guards.
- `ENG-DEBT-0005` remains active until dependencies are mapped to real
  import/task consumers, optional groups are populated, and a base-runtime
  install is proven.

The StateCore and frontend debts remain resolved only because this audit fixes
their incomplete implementations and strengthens their verifiers.

## PR Findings

| PR | Finding | Decision / correction |
| --- | --- | --- |
| #228 SEC-BOUNDARY-01 | Database constraints, response markers, deprecation, and legacy write-gate tests are useful. The threat model still states that broker-registry and machine-checkable consumer guards are missing, while the debt was marked resolved. | Reopen `ENG-DEBT-0002`; require the missing evidence in the verifier. |
| #229 DEVEX-02 | Node majors now agree and the Rust install had no repository consumer. | Accept. |
| #230 DEVEX-01 | Named checks existed, but `check:ci` and `check:research` copied lower-layer commands instead of composing them, allowing future drift. The verifier checked names only. | Make the layers hierarchical and verify exact dependency closure. |
| #231 DEPS-01 | All six new groups were empty; no consumer audit existed; every dependency remained in base. The PR body explicitly deferred the work while closing the debt. | Reopen `ENG-DEBT-0005`; require a current consumer manifest and non-empty owned groups. |
| #232 STATECORE-01 | Models moved, but the extracted module imported `models.py` while `models.py` imported it. No semantic split test existed. | Add `model_base.py`, remove the reverse dependency, and test class identity plus metadata registration. |
| #233 FRONTEND-01 | `state.js` was a four-line placeholder, runtime state stayed in `app.js`, and all three forms bypassed `ReviewActionShell`. The verifier checked only file/symbol presence. | Extract real state and `actions.js`; route all writes through the shell; add a fail-closed jsdom contract. |

GitHub reports all six PRs merged with successful configured checks and no
recorded reviews. That is evidence about CI execution, not independent semantic
approval.

## Baseline Evidence

Before correction:

- canonical debt verifier: 10/10 reported passing;
- `task check:ci`: 916 unit tests, 8 integration tests, frontend/governance/rule
  checks passed;
- Agent Work Loop acceptance: 4/15 passing, 11 open.

The contradiction between green gates and the source facts is the core audit
finding. Empty dependency groups and placeholder state passed because the
verifiers encoded those placeholders as success.

After correction:

- debt verifier: 8 resolved checks true and 2 active checks correctly false;
- `task check:research`: Ruff, mypy, 919 unit tests, 8 integration tests,
  frontend/governance/rules, research experiment, and eval smoke passed;
- real Chromium golden paths: 3 passed with 0 page errors. The first run found
  and the correction removed a classic-script global declaration collision
  that the original jsdom loaders could not expose.

## Correction Contract

The corrected verifier now requires:

- actual Taskfile composition, not task-name presence;
- a PaperValidation consumer manifest and named semantic guards;
- a dependency consumer manifest and populated owned groups;
- an acyclic StateCore model boundary with a semantic test;
- real frontend state ownership, an extracted action shell, all three form
  consumers, script order, and a jsdom fail-closed test.

## Next Work

1. Close `ENG-DEBT-0002` with the consumer manifest, AST import boundary,
   broker-registry isolation probe, and threat-model reconciliation.
2. Close `ENG-DEBT-0005` with an import/task audit, dependency movement, grouped
   task invocations, and base-only/runtime-plus-research install probes.
3. Resume Agent Work Loop Phase 3 at LOOP-02; do not add session/resume,
   scheduling, subagents, or authority expansion before 15/15 closure.
4. Only then build Paper Execution Review and the persisted Agent Work Queue on
   canonical Execution Kernel and review artifacts.
