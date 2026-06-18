"""Seventh-layer structured proposal governance package.

The package preserves the original ``finharness.proposal`` interface while
keeping implementation concerns in smaller modules.
"""

from __future__ import annotations

from finharness.proposal._constants import (
    BLOCKED_PROPOSAL_LANGUAGE,
    PROPOSAL_NORMALIZED_ROOT,
    PROPOSAL_RECEIPT_ROOT,
    STRUCTURAL_READY_RESULTS,
    ActionType,
    ProposalStatus,
)
from finharness.proposal._util import (
    candidate_text_for_guard,
    find_blocked_language,
    now_utc,
    write_json,
)
from finharness.proposal.bundle import (
    build_proposal_bundle_from_validation_snapshot,
    persist_proposal_bundle,
    proposal_storage_roots,
)
from finharness.proposal.formulation import (
    build_proposal_candidates,
    build_risk_gate_request,
    classify_action_type,
    constraints_for_candidate,
    formulate_proposal_candidate,
    group_results_by_hypothesis,
    invalidation_from_results,
    result_ids,
    status_for_action,
    summary_counts,
    symbol_for_results,
)
from finharness.proposal.models import (
    ProposalBundle,
    ProposalCandidate,
    ProposalLineage,
    ProposalQuality,
    ProposalReceipt,
    ProposalSnapshot,
    ProposalSourceSpec,
    RiskGateRequest,
)
from finharness.proposal.providers import (
    HermesProposalDraftProvider,
    NullProposalDraftProvider,
    ProposalDraftProvider,
)
from finharness.proposal.quality import (
    build_proposal_quality,
    missing_proposal_fields,
    risk_gate_handoff,
    snapshot_review_questions,
)

__all__ = [
    "BLOCKED_PROPOSAL_LANGUAGE",
    "PROPOSAL_NORMALIZED_ROOT",
    "PROPOSAL_RECEIPT_ROOT",
    "STRUCTURAL_READY_RESULTS",
    "ActionType",
    "HermesProposalDraftProvider",
    "NullProposalDraftProvider",
    "ProposalBundle",
    "ProposalCandidate",
    "ProposalDraftProvider",
    "ProposalLineage",
    "ProposalQuality",
    "ProposalReceipt",
    "ProposalSnapshot",
    "ProposalSourceSpec",
    "ProposalStatus",
    "RiskGateRequest",
    "build_proposal_bundle_from_validation_snapshot",
    "build_proposal_candidates",
    "build_proposal_quality",
    "build_risk_gate_request",
    "candidate_text_for_guard",
    "classify_action_type",
    "constraints_for_candidate",
    "find_blocked_language",
    "formulate_proposal_candidate",
    "group_results_by_hypothesis",
    "invalidation_from_results",
    "missing_proposal_fields",
    "now_utc",
    "persist_proposal_bundle",
    "proposal_storage_roots",
    "result_ids",
    "risk_gate_handoff",
    "snapshot_review_questions",
    "status_for_action",
    "summary_counts",
    "symbol_for_results",
    "write_json",
]
