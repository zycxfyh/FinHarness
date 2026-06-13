# Proposal: B4 — Lesson-to-Rule-Change Lineage (Minimal Closed Loop)

Date: 2026-06-13
Status: implemented & verified 2026-06-13
Author: FinHarness project operator and Claude
Governing roadmap: docs/adr/2026-06-13-target-state-b-is-the-governing-roadmap.md

> DONE: src/finharness/rule_change_ledger.py (promote / trace / is_traceable /
> audit_untraceable) + tests/test_rule_change_ledger.py (9 tests). Entry points:
> scripts/promote_lesson.py, scripts/audit_rule_lineage.py; tasks
> lessons:promote, rules:audit. End-to-end on 191 real receipts: lesson draft
> (100 refs) -> human-promoted rule change -> trace returns rule_change ->
> lesson -> 100 receipts -> audit clean. Full suite 214 passed, ruff clean.
>
> NEXT DONE 2026-06-13:
> - H2.next enforcement: `src/finharness/effective_rules.py` resolves effective
>   guard thresholds from traceable active rule changes; `okx_live_gate.py`
>   consumes those thresholds when no explicit test threshold is supplied.
> - H3 validation depth: `src/finharness/validation_metrics.py` computes a real
>   realized-move disconfirming check when cached price history exists. Current
>   repo state has no `data/cache/*_history.csv`, so this is verified by tests
>   and degrades to input availability in the live checkout.
> - H4 attribution seed: `lesson_loop.py` now fills `proposed_rule_changes` from
>   quality failures, post-trade final-status patterns, repeated live-boundary
>   blocks, and repeated attestation blocks. These are draft seeds only; human
>   promotion is still required.
> Verification: `task check` passed: ruff clean, 228 unittest tests OK,
> 4 property tests OK, backtrader smoke ran, and promptfoo smoke passed 1/1.

## Charter

Close the one predicate that is the project's reason to exist. B4: every
rule/threshold/checklist change carries lineage to a lesson, which carries
lineage to receipts. Today `lesson_loop.py` drafts lessons but stops at "a human
promotes it" — `proposed_rule_changes` is always empty, and no rule change can
be traced back to the evidence that justified it. This builds the missing half.

## Boundary

In scope:

```text
- a RuleChange object with lineage: rule target, old->new, rationale, the
  promoted lesson, and the transitive receipt refs the lesson came from
- promote_lesson_to_rule_change: the HUMAN action (requires an attester) that
  turns a lesson draft into a recorded rule change with lineage
- an append-only rule-change ledger + a receipt per change
- trace_rule_change: returns the full chain (rule_change -> lesson -> receipts)
- is_traceable: deterministic B4 check — a rule change without a lesson and
  receipt refs is NOT traceable and must be flagged
```

Non-goals (this increment):

```text
- no autonomous application: only human-promoted, traceable rule changes can
  affect the behavioral guard. Risk-gate thresholds and checklists are not yet
  read from the ledger.
- no LLM evaluator: the comparator is the human (B-doc section 3). AI only
  drafts (existing lesson_loop); promotion is a human authorization.
- no autonomous rule changes; promotion always carries an attester.
```

## Design (Ordivon-shaped)

```text
GroundingClaim   lesson draft scanned from real receipts (lesson_loop, exists)
AuthorizationGrant  promote_lesson_to_rule_change(attester=...) — human grant
ObservationReceipt  RuleChange written to data/state/rule-changes/ + receipt
ClosureDecision  is_traceable(rule_change) — lineage complete or not
```

`RuleChange` fields: rule_change_id, created_at_utc, rule_target (e.g.
"guard.hard_stop_drawdown_pct"), change_kind (threshold|checklist|allowlist|
prompt_template), old_value, new_value, rationale, attester, lesson_draft_id,
lesson_doc_ref, receipt_refs (from the lesson), status (active|reverted).

## Verification

```text
Tests (tests/test_rule_change_ledger.py):
- promote without an attester is refused (authorization-before-action)
- a promoted change carries lesson_draft_id + non-empty receipt_refs
- trace_rule_change returns rule_change -> lesson -> receipts
- a hand-built change with no lineage is is_traceable() == False
- ledger round-trips (persist/load)
End-to-end: promote a draft built from the 191 real receipts; trace it.
```

## Next increments (not now)

```text
- guard/risk thresholds read their current value + provenance from the ledger
  (implemented for behavioral guard thresholds; risk-gate thresholds remain
  future work)
- post-trade attribution feeds the lesson draft (implemented as deterministic
  draft seeds; human promotion remains mandatory)
- a periodic "untraceable rule change" audit fails closed
```
