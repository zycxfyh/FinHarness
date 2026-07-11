# Attestation Consumer Inventory

## Baseline

`a24198a6fabcbf70a91063c22bbda837395326b4` (main, post PR #245 merge)

## Executive conclusion

The Attestation model currently serves **three distinct semantic roles** across the codebase:

1. **Historical review evidence** (preserve): Timeline display, receipt replay, audit trails.
2. **Review-completion proxy** (migrate): `open_for_review`, `_queue_status`, `status=attested`, `ReviewTaskLifecycle.completed`.
3. **Canonical decision claim** (remove): Docstrings, non_claims, system-map that call attestation "the decision of record."

Attestation has **no version binding** — it binds only to `proposal_id`, not to `proposal_version_id`, `proposal_content_hash`, `decision_case_version_id`, or `scenario_version_id`. This makes it unsuitable as a canonical decision artifact.

**Key conclusion**: Attestation remains historical review evidence, but current-state consumers that treat any Attestation as canonical review completion must be migrated to a version-bound DecisionRecord / DecisionValidity pair.

## Semantic distinction

### Preserve as historical evidence

| Consumer | Why |
|---|---|
| Attestation model (ATT-CONS-001) | Historical data and receipt replay |
| ReviewEvent.attestation_ref (ATT-CONS-002) | Compatibility link |
| Decision enum (ATT-CONS-004) | Historical decision values |
| read_proposal_timeline (ATT-CONS-018) | Historical evidence display |
| renderAttestations (ATT-CONS-026) | Frontend historical display |
| renderTimeline attestation entries (ATT-CONS-028) | Frontend timeline |
| attestation serialization tests (ATT-CONS-031) | Data integrity |

### Migrate away from review-completion proxy

| Consumer | Current semantic | Target |
|---|---|---|
| _proposal_review_response (ATT-CONS-010) | `open_for_review = not attestations` | DecisionValidity.status |
| ProposalReviewResponse.open_for_review (ATT-CONS-011) | API contract | Dual-read → DecisionValidity |
| ReviewTaskLifecycle.completed (ATT-CONS-012) | Task state from attestation | DecisionValidity |
| read_review_queue (ATT-CONS-016) | `attested_ids` → `reviewed` | DecisionValidity |
| _queue_status (ATT-CONS-017) | Status = reviewed if attested | DecisionValidity |
| _build_review_queue_item (ATT-CONS-019) | open_for_review from attestation | DecisionValidity |
| _duplicate_open_proposal_ids (ATT-CONS-020) | attested_ids filter | DecisionValidity |

### Remove canonical-decision claims

| Consumer | Current wording |
|---|---|
| ReviewEvent docstring (ATT-CONS-003) | "attestation stays the decision of record" |
| AgentReviewSurface non_claims (ATT-CONS-022) | "decision of record" |
| get_proposal_timeline docstring (ATT-CONS-023) | "Attestation stays the decision of record" |
| AgentToolEntry non_claims (ATT-CONS-024) | "decision of record" |
| system-map.md (ATT-CONS-025) | "attestation is decision of record" |

### Deprecate after replacement exists

| Consumer | Replacement |
|---|---|
| create_governed_attestation (ATT-CONS-006) | DecisionRecord write command |
| attest_proposal endpoint (ATT-CONS-009) | DecisionRecord endpoint |
| renderAttestationForm (ATT-CONS-027) | DecisionRecord form |

### Investigate

| Consumer | Reason |
|---|---|
| test_statecore_api.py (ATT-CONS-029) | Complex test file; needs review for dual-read coverage |
| test_agent_proposal_drafts.py (ATT-CONS-030) | Agent draft/attestation lifecycle tests |
| test_risk_classification.py (ATT-CONS-032) | Risk classification may need DecisionRecord |

## Consumer matrix

| ID | Path / symbol | Role | Semantic | Risk | Disposition |
| -- | ------------- | ---- | -------- | ---- | ----------- |
| ATT-CONS-001 | statecore/models.py / Attestation | schema_model | legacy_unbound_decision | high | preserve |
| ATT-CONS-002 | statecore/models.py / ReviewEvent.attestation_ref | compatibility_link | compatibility_reference | low | preserve |
| ATT-CONS-003 | statecore/models.py / ReviewEvent docstring | documentation_claim | canonical_decision_claim | medium | remove_canonical_claim |
| ATT-CONS-004 | statecore/models.py / Decision enum | schema_model | legacy_unbound_decision | low | preserve |
| ATT-CONS-005 | statecore/models.py / StateCoreRecord union | schema_model | legacy_unbound_decision | low | preserve |
| ATT-CONS-006 | statecore/proposals.py / create_governed_attestation | write_surface | legacy_unbound_decision | medium | deprecate_after_replacement |
| ATT-CONS-007 | statecore/proposals.py / GovernedAttestationWrite | receipt_writer | legacy_unbound_decision | low | preserve |
| ATT-CONS-008 | statecore/proposals.py / RecordReviewEvent | receipt_writer | compatibility_reference | low | preserve |
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
| ATT-CONS-024 | agent_tools.py / AgentToolEntry non_claims | documentation_claim | canonical_decision_claim | low | remove_canonical_claim |
| ATT-CONS-025 | docs/architecture/system-map.md | documentation_claim | canonical_decision_claim | medium | remove_canonical_claim |
| ATT-CONS-026 | frontend/app.js / renderAttestations | frontend_surface | historical_evidence | low | preserve |
| ATT-CONS-027 | frontend/app.js / renderAttestationForm | frontend_surface | legacy_unbound_decision | medium | deprecate_after_replacement |
| ATT-CONS-028 | frontend/app.js / renderTimeline | frontend_surface | historical_evidence | low | preserve |
| ATT-CONS-029 | tests/test_statecore_api.py | test_contract | legacy_unbound_decision | low | investigate |
| ATT-CONS-030 | tests/test_agent_proposal_drafts.py | test_contract | legacy_unbound_decision | low | investigate |
| ATT-CONS-031 | tests/test_statecore_vertical_reconstruction.py | test_contract | legacy_unbound_decision | low | preserve |
| ATT-CONS-032 | tests/test_risk_classification.py | test_contract | legacy_unbound_decision | low | investigate |
| ATT-CONS-033 | docs/governance/receipt-backed-write-registry.json | write_surface | legacy_unbound_decision | low | preserve |

## High-risk migration order

1. **ATT-CONS-016** / `read_review_queue` — drives the review queue UX
2. **ATT-CONS-017** / `_queue_status` — core queue classification
3. **ATT-CONS-010** / `_proposal_review_response` — API review gate
4. **ATT-CONS-019** / `_build_review_queue_item` — per-item classification
5. **ATT-CONS-011** / `ProposalReviewResponse` — API shape contract
6. **ATT-CONS-012** / `ReviewTaskLifecycle` — task lifecycle
7. **ATT-CONS-001** / Attestation model — schema preservation (no migration needed, just no new version-bound writes)
8. **ATT-CONS-009** / `attest_proposal` — endpoint deprecation

## Test impact map

| Test file | Inventory ID | Impact |
|---|---|---|
| `tests/test_statecore_api.py` | ATT-CONS-029 | Dual-read transition tests needed |
| `tests/test_agent_proposal_drafts.py` | ATT-CONS-030 | Agent lifecycle transition tests |
| `tests/test_risk_classification.py` | ATT-CONS-032 | Risk evaluation may need DecisionRecord |
| `tests/test_statecore_vertical_reconstruction.py` | ATT-CONS-031 | Preserved; add DecisionRecord tests |

## Compatibility constraints

| Constraint | Scope |
|---|---|
| Attestation table must remain | Forever — historical data and receipt replay |
| `open_for_review` API field must remain during transition | Backward-compatible dual read |
| `status=open|attested` filter must remain | API backward compatibility |
| Frontend attestation form must remain | Until DecisionRecord form exists |
| Timeline attestation entries must remain | Forever — historical evidence display |

Attestation historical evidence ≠ version-bound canonical DecisionRecord.
Preserve Attestation history ≠ continue using any Attestation as current review-completion truth.

## Explicit non-goals

- No migration implementation
- No deprecation activation
- No write-surface replacement
- No frontend changes
- No runtime activation
- No DecisionRecord model creation
