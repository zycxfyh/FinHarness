"""Governed TradePlanReviewGate writes.

TradePlanReviewGate records whether a human reviewer allows a
TradePlanCandidate to enter future order-ticket-candidate staging. It does not
create an order ticket, submit to a broker, certify suitability, create an
AuthorityContract, or authorize execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Engine
from sqlmodel import Session

from finharness.action_intent_preflight import preflight_action_intent
from finharness.statecore.action_intents import _dedupe_text, forbidden_action_intent_marker
from finharness.statecore.models import (
    TRADE_PLAN_REVIEW_GATE_DECISIONS,
    TRADE_PLAN_REVIEW_GATE_REVIEWER_TYPES,
    ActionIntent,
    ActionIntentSimulationReport,
    ReceiptIndex,
    TradePlanCandidate,
    TradePlanReviewGate,
)
from finharness.statecore.proposals import (
    _display_path,
    _now_utc,
    _receipt_index,
    _revision_stamp,
    _safe_id,
)
from finharness.statecore.receipt_io import (
    atomic_write_json,
    remove_file_best_effort,
    resolve_under,
)
from finharness.statecore.store import StateCoreStoreError, write_records

TradePlanReviewGateDecision = Literal[
    "allow_order_ticket_candidate_staging",
    "deny_order_ticket_candidate_staging",
]
TradePlanReviewGateReviewerType = Literal["human"]

TRADE_PLAN_REVIEW_GATE_NON_CLAIMS: tuple[str, ...] = (
    "TradePlanReviewGate is not an order ticket.",
    "TradePlanReviewGate does not create an order ticket.",
    "TradePlanReviewGate is not a broker instruction or broker submission.",
    "TradePlanReviewGate is not an AuthorityContract.",
    "TradePlanReviewGate is not suitability certification.",
    "TradePlanReviewGate does not authorize paper or live execution.",
)

ORDER_READY_REVIEW_KEYS: frozenset[str] = frozenset(
    {
        "broker_order_id",
        "execution_allowed",
        "execution_status",
        "fix_tags",
        "limit_price",
        "market_order",
        "order_submit_payload",
        "order_type",
        "quantity",
        "route",
        "side",
        "stop_price",
        "submitted_to_broker",
        "time_in_force",
        "venue",
    }
)


class TradePlanReviewGateValidationError(ValueError):
    """Raised when review-gate input crosses its staging-only boundary."""


class TradePlanReviewGateStaleError(ValueError):
    """Raised when caller freshness evidence no longer matches current state."""


@dataclass(frozen=True)
class GovernedTradePlanReviewGateWrite:
    review_gate: TradePlanReviewGate
    receipt_ref: str
    execution_allowed: bool = False
    authority_transition: bool = False
    submitted_to_broker: bool = False
    creates_order_ticket: bool = False


def create_governed_trade_plan_review_gate(
    *,
    trade_plan_candidate_id: str,
    expected_trade_plan_candidate_receipt_ref: str,
    expected_action_intent_receipt_ref: str,
    expected_action_preflight_report_hash: str,
    expected_simulation_report_receipt_ref: str,
    review_decision: TradePlanReviewGateDecision,
    reviewer_id: str,
    review_reason: str,
    reviewer_type: TradePlanReviewGateReviewerType = "human",
    review_context: dict[str, Any] | None = None,
    review_findings: list[dict[str, Any]] | None = None,
    deny_reasons: list[str] | None = None,
    source_refs: list[str] | None = None,
    engine: Engine,
    receipt_root: str | Path,
) -> GovernedTradePlanReviewGateWrite:
    """Persist a review gate bound to current trade-plan evidence."""

    clean_decision = str(review_decision).strip()
    clean_reviewer_type = str(reviewer_type).strip()
    clean_reviewer_id = reviewer_id.strip()
    clean_reason = review_reason.strip()
    context = dict(review_context or {})
    findings = [dict(finding) for finding in review_findings or []]
    clean_deny_reasons = _dedupe_text(list(deny_reasons or []))
    clean_source_refs = _dedupe_text(list(source_refs or []))

    _require_review_gate_fields(
        review_decision=clean_decision,
        reviewer_type=clean_reviewer_type,
        reviewer_id=clean_reviewer_id,
        review_reason=clean_reason,
        deny_reasons=clean_deny_reasons,
        review_context=context,
        review_findings=findings,
    )

    with Session(engine) as session:
        trade_plan_candidate = session.get(TradePlanCandidate, trade_plan_candidate_id)
        if trade_plan_candidate is None:
            raise KeyError(trade_plan_candidate_id)
        action_intent = session.get(ActionIntent, trade_plan_candidate.action_intent_id)
        simulation_report = session.get(
            ActionIntentSimulationReport,
            trade_plan_candidate.simulation_report_id,
        )
    if action_intent is None:
        raise KeyError(trade_plan_candidate.action_intent_id)
    if simulation_report is None:
        raise KeyError(trade_plan_candidate.simulation_report_id)

    _require_current_evidence(
        trade_plan_candidate=trade_plan_candidate,
        action_intent=action_intent,
        simulation_report=simulation_report,
        expected_trade_plan_candidate_receipt_ref=(
            expected_trade_plan_candidate_receipt_ref
        ),
        expected_action_intent_receipt_ref=expected_action_intent_receipt_ref,
        expected_action_preflight_report_hash=expected_action_preflight_report_hash,
        expected_simulation_report_receipt_ref=expected_simulation_report_receipt_ref,
        engine=engine,
    )

    allowed = clean_decision == "allow_order_ticket_candidate_staging"
    created_at = _now_utc()
    review_gate_id = _safe_id(f"trade_plan_review_gate_{_revision_stamp()}_{uuid4().hex[:8]}")
    receipt_id = f"receipt_{review_gate_id}"
    receipt_path = resolve_under(
        receipt_root,
        "trade-plan-review-gates",
        f"{receipt_id}.json",
    )
    receipt_ref = _display_path(receipt_path)
    candidate_warning_codes = _candidate_validation_finding_codes(trade_plan_candidate)
    receipt_refs = _dedupe_text(
        [
            *_receipt_refs_without_hashes(trade_plan_candidate.receipt_refs),
            trade_plan_candidate.receipt_ref or "",
            trade_plan_candidate.source_simulation_report_receipt_ref,
            trade_plan_candidate.source_action_intent_receipt_ref,
            receipt_ref,
        ]
    )
    review_gate = TradePlanReviewGate(
        review_gate_id=review_gate_id,
        trade_plan_candidate_id=trade_plan_candidate.trade_plan_candidate_id,
        action_intent_id=trade_plan_candidate.action_intent_id,
        simulation_report_id=trade_plan_candidate.simulation_report_id,
        proposal_id=trade_plan_candidate.proposal_id,
        source_trade_plan_candidate_receipt_ref=trade_plan_candidate.receipt_ref or "",
        source_action_intent_receipt_ref=trade_plan_candidate.source_action_intent_receipt_ref,
        source_action_preflight_report_hash=(
            trade_plan_candidate.source_action_preflight_report_hash
        ),
        source_simulation_report_receipt_ref=(
            trade_plan_candidate.source_simulation_report_receipt_ref
        ),
        review_decision=clean_decision,
        reviewer_type=clean_reviewer_type,
        reviewer_id=clean_reviewer_id,
        review_reason=clean_reason,
        review_context=context,
        review_findings=findings,
        deny_reasons=clean_deny_reasons,
        candidate_validation_finding_codes=candidate_warning_codes,
        may_enter_order_ticket_candidate_staging=allowed,
        source_refs=_dedupe_text([*trade_plan_candidate.source_refs, *clean_source_refs]),
        receipt_refs=receipt_refs,
        preflight_refs=[trade_plan_candidate.source_action_preflight_report_hash],
        non_claims=list(TRADE_PLAN_REVIEW_GATE_NON_CLAIMS),
        receipt_ref=receipt_ref,
        execution_allowed=False,
        authority_transition=False,
        submitted_to_broker=False,
        creates_order_ticket=False,
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    atomic_write_json(
        receipt_path,
        _receipt_payload(
            review_gate=review_gate,
            trade_plan_candidate=trade_plan_candidate,
            action_intent=action_intent,
            simulation_report=simulation_report,
        ),
    )
    receipt_index: ReceiptIndex = _receipt_index(
        receipt_id=receipt_id,
        kind="state_core_trade_plan_review_gate",
        path=receipt_path,
        created_at_utc=created_at,
        refs=_dedupe_text(
            [
                review_gate.review_gate_id,
                trade_plan_candidate.trade_plan_candidate_id,
                trade_plan_candidate.action_intent_id,
                trade_plan_candidate.simulation_report_id,
                trade_plan_candidate.proposal_id,
                trade_plan_candidate.receipt_ref or "",
                trade_plan_candidate.source_action_preflight_report_hash,
                *review_gate.source_refs,
            ]
        ),
    )
    try:
        write_records([review_gate, receipt_index], engine=engine)
    except StateCoreStoreError:
        remove_file_best_effort(receipt_path)
        raise
    return GovernedTradePlanReviewGateWrite(
        review_gate=review_gate,
        receipt_ref=receipt_ref,
        execution_allowed=False,
        authority_transition=False,
        submitted_to_broker=False,
        creates_order_ticket=False,
    )


def _require_review_gate_fields(
    *,
    review_decision: str,
    reviewer_type: str,
    reviewer_id: str,
    review_reason: str,
    deny_reasons: list[str],
    review_context: dict[str, Any],
    review_findings: list[dict[str, Any]],
) -> None:
    if review_decision not in TRADE_PLAN_REVIEW_GATE_DECISIONS:
        raise TradePlanReviewGateValidationError(
            f"unknown trade plan review decision: {review_decision}"
        )
    if reviewer_type not in TRADE_PLAN_REVIEW_GATE_REVIEWER_TYPES:
        raise TradePlanReviewGateValidationError(
            f"reviewer_type must be one of {TRADE_PLAN_REVIEW_GATE_REVIEWER_TYPES}"
        )
    if not reviewer_id or not review_reason:
        raise TradePlanReviewGateValidationError(
            "trade plan review gate requires reviewer_id and review_reason"
        )
    if review_decision == "deny_order_ticket_candidate_staging" and not deny_reasons:
        raise TradePlanReviewGateValidationError(
            "denied trade plan review gates require at least one deny_reason"
        )
    if review_decision == "allow_order_ticket_candidate_staging" and deny_reasons:
        raise TradePlanReviewGateValidationError(
            "allowed trade plan review gates cannot carry deny_reasons"
        )
    for finding in review_findings:
        if str(finding.get("severity", "")).strip() == "blocking":
            raise TradePlanReviewGateValidationError(
                "review_findings cannot carry blocking severity in an allowed/denied gate"
            )
    marker = _order_ready_marker(review_context)
    if marker is not None:
        raise TradePlanReviewGateValidationError(
            f"review_context cannot carry order-ready field {marker!r}"
        )
    marker = _order_ready_marker(review_findings)
    if marker is not None:
        raise TradePlanReviewGateValidationError(
            f"review_findings cannot carry order-ready field {marker!r}"
        )


def _require_current_evidence(
    *,
    trade_plan_candidate: TradePlanCandidate,
    action_intent: ActionIntent,
    simulation_report: ActionIntentSimulationReport,
    expected_trade_plan_candidate_receipt_ref: str,
    expected_action_intent_receipt_ref: str,
    expected_action_preflight_report_hash: str,
    expected_simulation_report_receipt_ref: str,
    engine: Engine,
) -> None:
    if trade_plan_candidate.receipt_ref != expected_trade_plan_candidate_receipt_ref.strip():
        raise TradePlanReviewGateStaleError(
            "trade plan candidate receipt ref does not match expected receipt"
        )
    if action_intent.receipt_ref != expected_action_intent_receipt_ref.strip():
        raise TradePlanReviewGateStaleError(
            "action intent receipt ref does not match expected receipt"
        )
    if simulation_report.receipt_ref != expected_simulation_report_receipt_ref.strip():
        raise TradePlanReviewGateStaleError(
            "simulation report receipt ref does not match expected receipt"
        )
    preflight = preflight_action_intent(action_intent.action_intent_id, engine=engine)
    if preflight is None:
        raise KeyError(action_intent.action_intent_id)
    if preflight.report_hash != expected_action_preflight_report_hash.strip():
        raise TradePlanReviewGateStaleError(
            "action preflight report hash does not match current preflight"
        )
    if trade_plan_candidate.source_action_preflight_report_hash != preflight.report_hash:
        raise TradePlanReviewGateStaleError(
            "trade plan candidate is not bound to the current action preflight hash"
        )
    if trade_plan_candidate.source_action_intent_receipt_ref != (action_intent.receipt_ref or ""):
        raise TradePlanReviewGateStaleError(
            "trade plan candidate is not bound to the current action intent receipt"
        )
    if trade_plan_candidate.source_simulation_report_receipt_ref != (
        simulation_report.receipt_ref or ""
    ):
        raise TradePlanReviewGateStaleError(
            "trade plan candidate is not bound to the current simulation report receipt"
        )
    if simulation_report.source_action_preflight_report_hash != preflight.report_hash:
        raise TradePlanReviewGateStaleError(
            "simulation report is not bound to the current action preflight hash"
        )


def _candidate_validation_finding_codes(candidate: TradePlanCandidate) -> list[str]:
    codes: list[str] = []
    for finding in candidate.validation_findings:
        code = str(finding.get("code", "")).strip()
        if code:
            codes.append(code)
    return _dedupe_text(codes)


def _receipt_refs_without_hashes(values: list[str]) -> list[str]:
    return [value for value in values if not str(value).startswith("sha256:")]


def _order_ready_marker(value: Any) -> str | None:
    marker = forbidden_action_intent_marker(value)
    if marker is not None:
        return marker
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).strip()
            normalized = key_text.lower().replace("-", "_").replace(" ", "_")
            if normalized in ORDER_READY_REVIEW_KEYS:
                return key_text
            found = _order_ready_marker(child)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = _order_ready_marker(child)
            if found is not None:
                return found
    return None


def _receipt_payload(
    *,
    review_gate: TradePlanReviewGate,
    trade_plan_candidate: TradePlanCandidate,
    action_intent: ActionIntent,
    simulation_report: ActionIntentSimulationReport,
) -> dict[str, Any]:
    return {
        "receipt_id": f"receipt_{review_gate.review_gate_id}",
        "kind": "state_core_trade_plan_review_gate",
        "created_at_utc": review_gate.created_at_utc,
        "review_gate_id": review_gate.review_gate_id,
        "trade_plan_candidate_id": review_gate.trade_plan_candidate_id,
        "action_intent_id": review_gate.action_intent_id,
        "simulation_report_id": review_gate.simulation_report_id,
        "proposal_id": review_gate.proposal_id,
        "source_trade_plan_candidate_receipt_ref": (
            review_gate.source_trade_plan_candidate_receipt_ref
        ),
        "source_action_intent_receipt_ref": review_gate.source_action_intent_receipt_ref,
        "source_action_preflight_report_hash": (
            review_gate.source_action_preflight_report_hash
        ),
        "source_simulation_report_receipt_ref": (
            review_gate.source_simulation_report_receipt_ref
        ),
        "review_decision": review_gate.review_decision,
        "reviewer": {
            "reviewer_type": review_gate.reviewer_type,
            "reviewer_id": review_gate.reviewer_id,
        },
        "review_context": review_gate.review_context,
        "review_findings": review_gate.review_findings,
        "deny_reasons": review_gate.deny_reasons,
        "candidate_validation_finding_codes": (
            review_gate.candidate_validation_finding_codes
        ),
        "may_enter_order_ticket_candidate_staging": (
            review_gate.may_enter_order_ticket_candidate_staging
        ),
        "trade_plan_review_gate": review_gate.model_dump(mode="json"),
        "evidence_snapshot": {
            "trade_plan_candidate_status": trade_plan_candidate.candidate_status,
            "action_intent_receipt_ref": action_intent.receipt_ref,
            "simulation_report_receipt_ref": simulation_report.receipt_ref,
            "preflight_hash": review_gate.source_action_preflight_report_hash,
        },
        "governance": {
            "execution_allowed": False,
            "authority_transition": False,
            "submitted_to_broker": False,
            "creates_order_ticket": False,
            "may_enter_order_ticket_candidate_staging": (
                review_gate.may_enter_order_ticket_candidate_staging
            ),
            "review_gate_only": True,
            "not_order_ticket": True,
            "not_broker_instruction": True,
            "not_broker_submission": True,
            "not_execution_authorization": True,
            "not_suitability_certification": True,
            "not_authority_contract": True,
            "non_claims": list(TRADE_PLAN_REVIEW_GATE_NON_CLAIMS),
        },
    }
