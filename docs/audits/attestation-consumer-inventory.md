# Attestation Consumer Inventory

## Baseline

`a24198a6fabcbf70a91063c22bbda837395326b4` (main, post PR #245 merge)

## Executive conclusion

The Attestation model currently serves **three distinct semantic roles** across the codebase:

1. **Historical review evidence** (preserve): Timeline display, receipt replay, audit trails.
2. **Review-completion proxy** (migrate): `open_for_review`, `_queue_status`, `status=attested`, `ReviewTaskLifecycle.completed`, `build_open_proposals_context`.
3. **Canonical decision claim** (remove): Docstrings, non_claims, system-map that call attestation "the decision of record."

Attestation has **no version binding** — it binds only to `proposal_id`, not to `proposal_version_id`, `proposal_content_hash`, `decision_case_version_id`, or `scenario_version_id`. The daily brief, annual review, and agent context also consume Attestation for review-state gating and period aggregation.

**Key conclusion**: Attestation remains historical review evidence, but current-state consumers that treat any Attestation as canonical review completion must be migrated to a version-bound DecisionRecord / DecisionValidity pair.

```
Attestation historical evidence ≠ version-bound canonical DecisionRecord.
Preserving Attestation history ≠ using Attestation existence as current DecisionValidity.
```

## Semantic distinction

### Preserve as historical evidence

| Consumer | Why |
|---|---|
| ATT-CONS-001 — Attestation model | Historical data and receipt replay |
| ATT-CONS-002 — ReviewEvent.attestation_ref | Compatibility link |
| ATT-CONS-004 — Decision enum | Historical decision values |
| ATT-CONS-018 — read_proposal_timeline | Historical evidence display |
| ATT-CONS-030 — renderAttestations (frontend) | Frontend historical display |
| ATT-CONS-032 — renderTimeline attestation entries | Frontend timeline |
| ATT-CONS-035 — attestation serialization tests | Data integrity |

### Migrate away from review-completion proxy

| Consumer | Current semantic | Target |
|---|---|---|
| ATT-CONS-010 — _proposal_review_response | `open_for_review = not attestations` | DecisionValidity |
| ATT-CONS-011 — ProposalReviewResponse | API contract | Dual-read → DecisionValidity |
| ATT-CONS-012 — ReviewTaskLifecycle | Task state from attestation | DecisionValidity |
| ATT-CONS-016 — read_review_queue | `attested_ids` → `reviewed` | DecisionValidity |
| ATT-CONS-017 — _queue_status | Status = reviewed if attested | DecisionValidity |
| ATT-CONS-019 — _build_review_queue_item | open_for_review from attestation | DecisionValidity |
| ATT-CONS-020 — _duplicate_open_proposal_ids | attested_ids filter | DecisionValidity |
| ATT-CONS-026 — _open_reviews (daily brief) | Attested proposal IDs → open count | DecisionValidity |

### Remove canonical-decision claims

| Consumer | Current wording |
|---|---|
| ATT-CONS-003 — ReviewEvent docstring | "attestation stays the decision of record" |
| ATT-CONS-022 — AgentReviewSurface non_claims | "decision of record" |
| ATT-CONS-023 — get_proposal_timeline docstring | "Attestation stays the decision of record" |
| ATT-CONS-025 — system-map.md | "attestation is decision of record" |

### Deprecate after replacement exists

| Consumer | Replacement |
|---|---|
| ATT-CONS-006 — create_governed_attestation | DecisionRecord write command |
| ATT-CONS-009 — attest_proposal endpoint | DecisionRecord endpoint |
| ATT-CONS-031 — renderAttestationForm (frontend) | DecisionRecord form |

### Investigate

| Consumer | Reason |
|---|---|
| ATT-CONS-024 — AGENT_PROPOSAL_DRAFT_NON_CLAIMS | "decision of record" claim needs AUT3 alignment |
| ATT-CONS-033 — test_statecore_api.py | Complex test file; needs dual-read coverage review |
| ATT-CONS-034 — test_agent_proposal_drafts.py | Agent draft/attestation lifecycle tests |
| ATT-CONS-036 — test_risk_classification.py | Risk classification may need DecisionRecord |

## Consumer matrix

| ID | Path / symbol | Role | Semantic | Risk | Disposition |
| -- | ------------- | ---- | -------- | ---- | ----------- |
| ATT-CONS-001 | models.py / Attestation | schema_model | legacy_unbound_decision | high | preserve |
| ATT-CONS-002 | models.py / ReviewEvent.attestation_ref | compatibility_link | compatibility_reference | low | preserve |
| ATT-CONS-003 | models.py / ReviewEvent docstring | documentation_claim | canonical_decision_claim | medium | remove_canonical_claim |
| ATT-CONS-004 | models.py / Decision enum | schema_model | legacy_unbound_decision | low | preserve |
| ATT-CONS-005 | models.py / StateCoreRecord union | schema_model | legacy_unbound_decision | low | preserve |
| ATT-CONS-006 | proposals.py / create_governed_attestation | write_surface | legacy_unbound_decision | medium | deprecate_after_replacement |
| ATT-CONS-007 | proposals.py / GovernedAttestationWrite | receipt_writer | legacy_unbound_decision | low | preserve |
| ATT-CONS-008 | proposals.py / create_governed_review_event | receipt_writer | compatibility_reference | low | preserve |
| ATT-CONS-009 | api/routes_proposals.py / attest_proposal | api_contract | legacy_unbound_decision | high | deprecate_after_replacement |
| ATT-CONS-010 | api/routes_proposals.py / _proposal_review_response | state_gate | review_completion_proxy | high | migrate_to_decision_validity |
| ATT-CONS-011 | api/routes_proposals.py / ProposalReviewResponse | api_contract | review_completion_proxy | high | dual_read_transition |
| ATT-CONS-012 | api/routes_proposals.py / ReviewTaskLifecycle | api_contract | review_completion_proxy | high | migrate_to_decision_validity |
| ATT-CONS-013 | api/routes_proposals.py / status filter | api_contract | review_completion_proxy | medium | dual_read_transition |
| ATT-CONS-014 | api/routes_proposals.py / _agent_review_surface | state_gate | review_completion_proxy | medium | migrate_to_decision_validity |
| ATT-CONS-015 | api/routes_cockpit.py / count_open | read_projection | review_completion_proxy | low | dual_read_transition |
| ATT-CONS-016 | review_read.py / read_review_queue | state_gate | review_completion_proxy | high | migrate_to_decision_validity |
| ATT-CONS-017 | review_read.py / _queue_status | state_gate | review_completion_proxy | high | migrate_to_decision_validity |
| ATT-CONS-018 | review_read.py / read_proposal_timeline | read_projection | historical_evidence | low | preserve |
| ATT-CONS-019 | review_read.py / _build_review_queue_item | state_gate | review_completion_proxy | high | migrate_to_decision_validity |
| ATT-CONS-020 | proposal_queue_checks.py / _duplicate_open | state_gate | review_completion_proxy | medium | migrate_to_decision_validity |
| ATT-CONS-021 | proposal_queue_checks.py / _blocked_transition | state_gate | review_completion_proxy | low | preserve |
| ATT-CONS-022 | api/routes_proposals.py / AgentReviewSurface | documentation_claim | canonical_decision_claim | low | remove_canonical_claim |
| ATT-CONS-023 | api/routes_proposals.py / timeline docstring | documentation_claim | canonical_decision_claim | low | remove_canonical_claim |
| ATT-CONS-024 | agent_tools.py / NON_CLAIMS tuples | documentation_claim | unknown | low | investigate |
| ATT-CONS-025 | docs/architecture/system-map.md | documentation_claim | canonical_decision_claim | medium | remove_canonical_claim |
| ATT-CONS-026 | daily_brief.py / _open_reviews | state_gate | review_completion_proxy | medium | migrate_to_decision_validity |
| ATT-CONS-027 | annual_review.py / compute_annual_review | read_projection | review_completion_proxy | high | dual_read_transition |
| ATT-CONS-028 | docs/reference/interfaces.md | documentation_claim | legacy_unbound_decision | medium | preserve |
| ATT-CONS-029 | docs/…/04-review-lifecycle.md | documentation_claim | review_completion_proxy | medium | preserve |
| ATT-CONS-030 | frontend/app.js / renderAttestations | frontend_surface | historical_evidence | low | preserve |
| ATT-CONS-031 | frontend/app.js / renderAttestationForm | frontend_surface | legacy_unbound_decision | medium | deprecate_after_replacement |
| ATT-CONS-032 | frontend/app.js / renderTimeline | frontend_surface | historical_evidence | low | preserve |
| ATT-CONS-033 | tests/test_statecore_api.py | test_contract | legacy_unbound_decision | low | investigate |
| ATT-CONS-034 | tests/test_agent_proposal_drafts.py | test_contract | legacy_unbound_decision | low | investigate |
| ATT-CONS-035 | tests/test_statecore_vertical_reconstruction.py | test_contract | legacy_unbound_decision | low | preserve |
| ATT-CONS-036 | tests/test_risk_classification.py | test_contract | legacy_unbound_decision | low | investigate |
| ATT-CONS-037 | docs/governance/receipt-backed-write-registry.json | write_surface | legacy_unbound_decision | low | preserve |

## High-risk migration order

1. ATT-CONS-016 — `read_review_queue` — drives the review queue UX
2. ATT-CONS-017 — `_queue_status` — core queue classification
3. ATT-CONS-010 — `_proposal_review_response` — API review gate
4. ATT-CONS-019 — `_build_review_queue_item` — per-item classification
5. ATT-CONS-011 — `ProposalReviewResponse` — API shape contract
6. ATT-CONS-012 — `ReviewTaskLifecycle` — task lifecycle
7. ATT-CONS-027 — `compute_annual_review` — period aggregation
8. ATT-CONS-001 — Attestation model — schema preservation
9. ATT-CONS-009 — `attest_proposal` — endpoint deprecation

## Test impact map

| Test file | Inventory ID | Impact |
|---|---|---|
| `tests/test_statecore_api.py` | ATT-CONS-033 | Dual-read transition tests needed |
| `tests/test_agent_proposal_drafts.py` | ATT-CONS-034 | Agent lifecycle transition tests |
| `tests/test_risk_classification.py` | ATT-CONS-036 | Risk evaluation may need DecisionRecord |
| `tests/test_statecore_vertical_reconstruction.py` | ATT-CONS-035 | Preserved; add DecisionRecord tests |

## Compatibility constraints

| Constraint | Scope |
|---|---|
| Attestation table must remain | Forever — historical data and receipt replay |
| `open_for_review` API field must remain during transition | Backward-compatible dual read |
| `status=open|attested` filter must remain | API backward compatibility |
| Frontend attestation form must remain | Until DecisionRecord form exists |
| Timeline attestation entries must remain | Forever — historical evidence display |

## Explicit non-goals

- No migration implementation
- No deprecation activation
- No write-surface replacement
- No frontend changes
- No runtime activation
- No DecisionRecord model creation
