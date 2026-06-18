"""Eighth-layer independent risk gate governance package.

The package preserves the original ``finharness.risk_gate`` interface while
keeping implementation concerns in smaller modules.
"""

from __future__ import annotations

from finharness.risk_gate._constants import (
    BLOCKED_RISK_GATE_LANGUAGE,
    RISK_GATE_NORMALIZED_ROOT,
    RISK_GATE_RECEIPT_ROOT,
    RiskGateCheckStatus,
    RiskGateDecisionValue,
)
from finharness.risk_gate._util import (
    check,
    decision_text_for_guard,
    find_blocked_language,
    now_utc,
    write_json,
)
from finharness.risk_gate.bundle import (
    build_risk_gate_bundle_from_proposal_snapshot,
    build_risk_gate_quality,
    execution_handoff,
    persist_risk_gate_bundle,
    snapshot_review_questions,
)
from finharness.risk_gate.context import (
    normalize_allocation_summary,
    representative_risk_context,
    risk_context_for_candidate,
    riskfolio_concentration_evidence_refs,
)
from finharness.risk_gate.controls import (
    authorization_for_risk_context,
    candidate_checks,
    restricted_symbol_for_candidate,
    tradability_for_candidate,
)
from finharness.risk_gate.decisions import (
    build_risk_gate_decision,
    build_risk_gate_decisions,
    classify_decision,
)
from finharness.risk_gate.models import (
    RiskGateBundle,
    RiskGateCheck,
    RiskGateContext,
    RiskGateDecision,
    RiskGateLineage,
    RiskGateQuality,
    RiskGateReceipt,
    RiskGateSnapshot,
    RiskGateSourceSpec,
)

__all__ = [
    "BLOCKED_RISK_GATE_LANGUAGE",
    "RISK_GATE_NORMALIZED_ROOT",
    "RISK_GATE_RECEIPT_ROOT",
    "RiskGateBundle",
    "RiskGateCheck",
    "RiskGateCheckStatus",
    "RiskGateContext",
    "RiskGateDecision",
    "RiskGateDecisionValue",
    "RiskGateLineage",
    "RiskGateQuality",
    "RiskGateReceipt",
    "RiskGateSnapshot",
    "RiskGateSourceSpec",
    "authorization_for_risk_context",
    "build_risk_gate_bundle_from_proposal_snapshot",
    "build_risk_gate_decision",
    "build_risk_gate_decisions",
    "build_risk_gate_quality",
    "candidate_checks",
    "check",
    "classify_decision",
    "decision_text_for_guard",
    "execution_handoff",
    "find_blocked_language",
    "normalize_allocation_summary",
    "now_utc",
    "persist_risk_gate_bundle",
    "representative_risk_context",
    "restricted_symbol_for_candidate",
    "risk_context_for_candidate",
    "riskfolio_concentration_evidence_refs",
    "snapshot_review_questions",
    "tradability_for_candidate",
    "write_json",
]
