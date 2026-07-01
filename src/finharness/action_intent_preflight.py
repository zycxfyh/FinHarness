"""System-recomputed preflight for ActionIntentCandidate.

Action intents describe what capital action may be considered next. This module
recomputes whether a stored candidate is fresh, structurally complete, policy
compatible, and ready for its expected next workflow stage without mutating
state or creating an order/simulation artifact.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import Engine, desc
from sqlmodel import Session, select

from finharness.ips import current_ips
from finharness.statecore.action_intents import forbidden_action_intent_marker
from finharness.statecore.models import (
    ACTION_INTENT_NEXT_STEPS,
    ACTION_INTENT_TYPES,
    ActionIntent,
    Position,
    Proposal,
    Snapshot,
)

ActionIntentPreflightStatus = Literal["pass", "warn", "block"]
ActionIntentPreflightSeverity = Literal["info", "warning", "blocking"]
RiskDirection = Literal["reduce", "increase", "neutral", "evidence_only", "unknown"]
RiskPosture = Literal[
    "defensive",
    "offensive",
    "neutral",
    "protective",
    "observational",
    "evidence_only",
    "unknown",
]

ACTION_INTENT_PREFLIGHT_NON_CLAIMS: tuple[str, ...] = (
    "Action intent preflight is a deterministic readiness report, not approval.",
    "Action intent preflight does not create an order, broker instruction, or simulation.",
    "Action intent preflight is not investment advice or execution authorization.",
)

_EXPOSURE_ACTIONS = frozenset(
    {
        "reduce_exposure",
        "increase_exposure",
        "rebalance",
        "raise_cash",
        "hedge_review",
    }
)


@dataclass(frozen=True)
class ActionIntentPreflightFinding:
    code: str
    severity: ActionIntentPreflightSeverity
    message: str
    recovery_hint: str
    source_refs: list[str]
    receipt_refs: list[str]
    blocks_progression: bool


@dataclass(frozen=True)
class ActionIntentImpactSummary:
    affected_scope: dict[str, Any]
    risk_direction: RiskDirection
    risk_posture: RiskPosture
    requires_simulation: bool
    requires_human_review: bool
    known_state_refs: list[str]
    missing_data: list[str]
    order_intent: None = None
    notional_estimate: None = None


@dataclass(frozen=True)
class ActionIntentPreflightReport:
    action_intent_id: str
    proposal_id: str
    action_type: str
    status: ActionIntentPreflightStatus
    system_preflight_recomputed: bool
    action_intent_receipt_ref: str | None
    source_proposal_receipt_ref: str | None
    current_proposal_receipt_ref: str | None
    freshness_status: str
    target_scope_status: str
    policy_status: str
    evidence_status: str
    precondition_status: str
    risk_posture: RiskPosture
    findings: list[ActionIntentPreflightFinding]
    impact_summary: ActionIntentImpactSummary
    next_actions: list[str]
    report_hash: str
    non_claims: tuple[str, ...] = ACTION_INTENT_PREFLIGHT_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


def preflight_action_intent(
    action_intent_id: str,
    *,
    engine: Engine,
) -> ActionIntentPreflightReport | None:
    """Recompute readiness checks for an ActionIntentCandidate."""

    with Session(engine) as session:
        action_intent = session.get(ActionIntent, action_intent_id)
        if action_intent is None:
            return None
        proposal = session.get(Proposal, action_intent.proposal_id)
        portfolio_snapshot = _latest_portfolio_snapshot(session)
        portfolio_refs = _portfolio_refs(session, portfolio_snapshot)
    ips = current_ips(engine)

    source_refs = _dedupe([*action_intent.source_refs])
    receipt_refs = _dedupe(
        [
            *action_intent.receipt_refs,
            *([action_intent.receipt_ref] if action_intent.receipt_ref else []),
            *([proposal.receipt_ref] if proposal and proposal.receipt_ref else []),
            *(portfolio_refs if portfolio_snapshot else []),
            *([ips.receipt_ref] if ips and ips.receipt_ref else []),
        ]
    )
    freshness_status, freshness_findings = _freshness_findings(
        action_intent=action_intent,
        proposal=proposal,
        source_refs=source_refs,
        receipt_refs=receipt_refs,
    )
    target_scope_status, target_findings = _target_scope_findings(
        action_intent=action_intent,
        source_refs=source_refs,
        receipt_refs=receipt_refs,
    )
    policy_status, policy_findings = _policy_findings(
        action_intent=action_intent,
        ips_restricted_actions=list(ips.restricted_actions) if ips else None,
        source_refs=source_refs,
        receipt_refs=receipt_refs,
    )
    evidence_status, evidence_findings = _evidence_findings(
        action_intent=action_intent,
        portfolio_snapshot=portfolio_snapshot,
        source_refs=source_refs,
        receipt_refs=receipt_refs,
    )
    precondition_status, precondition_findings = _precondition_findings(
        action_intent=action_intent,
        source_refs=source_refs,
        receipt_refs=receipt_refs,
    )
    findings = [
        *freshness_findings,
        *_closed_set_findings(
            action_intent=action_intent,
            source_refs=source_refs,
            receipt_refs=receipt_refs,
        ),
        *target_findings,
        *policy_findings,
        *evidence_findings,
        *precondition_findings,
        *_simulation_findings(
            action_intent=action_intent,
            source_refs=source_refs,
            receipt_refs=receipt_refs,
        ),
    ]

    risk_posture = _risk_posture(action_intent.action_type)
    impact = _impact_summary(
        action_intent=action_intent,
        risk_posture=risk_posture,
        known_state_refs=portfolio_refs,
        missing_data=[
            finding.code
            for finding in findings
            if finding.severity == "warning" and finding.code.startswith("missing_")
        ],
    )
    next_actions = _next_actions(
        findings=findings,
        expected_next_step=action_intent.expected_next_step,
    )

    return _report(
        action_intent=action_intent,
        proposal=proposal,
        freshness_status=freshness_status,
        target_scope_status=target_scope_status,
        policy_status=policy_status,
        evidence_status=evidence_status,
        precondition_status=precondition_status,
        risk_posture=risk_posture,
        findings=findings,
        impact_summary=impact,
        next_actions=next_actions,
    )


def _latest_portfolio_snapshot(session: Session) -> Snapshot | None:
    return session.exec(
        select(Snapshot)
        .where(Snapshot.kind == "portfolio")
        .order_by(desc(Snapshot.as_of_utc), desc(Snapshot.snapshot_id))
        .limit(1)
    ).first()


def _portfolio_refs(session: Session, snapshot: Snapshot | None) -> list[str]:
    if snapshot is None:
        return []
    refs = list(snapshot.source_refs)
    positions = session.exec(
        select(Position).where(Position.snapshot_id == snapshot.snapshot_id)
    ).all()
    for position in positions:
        refs.extend(position.source_refs)
    return _dedupe(refs)


def _freshness_findings(
    *,
    action_intent: ActionIntent,
    proposal: Proposal | None,
    source_refs: list[str],
    receipt_refs: list[str],
) -> tuple[str, list[ActionIntentPreflightFinding]]:
    findings: list[ActionIntentPreflightFinding] = []
    status = "fresh"
    if not action_intent.receipt_ref:
        findings.append(
            _finding(
                code="missing_action_intent_receipt",
                severity="blocking",
                message="ActionIntentCandidate does not expose its receipt reference.",
                recovery_hint="Recreate the action intent so its receipt is indexed.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
    if proposal is None:
        findings.append(
            _finding(
                code="missing_source_proposal",
                severity="blocking",
                message="ActionIntentCandidate references a proposal that is not in state core.",
                recovery_hint="Restore the proposal state or discard this action intent.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
        status = "missing_source_proposal"
    elif proposal.receipt_ref != action_intent.source_proposal_receipt_ref:
        findings.append(
            _finding(
                code="stale_source_proposal_receipt",
                severity="blocking",
                message="ActionIntentCandidate was created against an older proposal receipt.",
                recovery_hint="Regenerate the action intent from the current proposal state.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
        status = "stale"
    return status, findings


def _closed_set_findings(
    *,
    action_intent: ActionIntent,
    source_refs: list[str],
    receipt_refs: list[str],
) -> list[ActionIntentPreflightFinding]:
    findings: list[ActionIntentPreflightFinding] = []
    if action_intent.action_type not in ACTION_INTENT_TYPES:
        findings.append(
            _finding(
                code="unknown_action_type",
                severity="blocking",
                message="ActionIntentCandidate carries an unknown action_type.",
                recovery_hint="Recreate the intent using the governed action_type closed set.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
    if action_intent.expected_next_step not in ACTION_INTENT_NEXT_STEPS:
        findings.append(
            _finding(
                code="unknown_expected_next_step",
                severity="blocking",
                message="ActionIntentCandidate carries an unknown expected_next_step.",
                recovery_hint="Recreate the intent using the governed next-step closed set.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
    return findings


def _target_scope_findings(
    *,
    action_intent: ActionIntent,
    source_refs: list[str],
    receipt_refs: list[str],
) -> tuple[str, list[ActionIntentPreflightFinding]]:
    findings: list[ActionIntentPreflightFinding] = []
    target_scope = action_intent.target_scope
    status = "valid"
    if not isinstance(target_scope, dict):
        findings.append(
            _finding(
                code="target_scope_not_object",
                severity="blocking",
                message="ActionIntentCandidate target_scope is not an object.",
                recovery_hint="Recreate the intent with an object target_scope.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
        status = "invalid"
    elif not str(target_scope.get("scope_type", "")).strip():
        findings.append(
            _finding(
                code="target_scope_missing_scope_type",
                severity="blocking",
                message="ActionIntentCandidate target_scope does not declare scope_type.",
                recovery_hint="Recreate the intent with a target_scope.scope_type.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
        status = "invalid"
    elif _target_scope_unresolved(target_scope):
        findings.append(
            _finding(
                code="target_scope_unresolved",
                severity="warning",
                message="ActionIntentCandidate target_scope is not resolved to a known object.",
                recovery_hint="Attach a symbol, account_scope, or evidence ref before progressing.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
                blocks_progression=False,
            )
        )
        status = "unresolved"

    marker = _forbidden_marker(action_intent)
    if marker is not None:
        findings.append(
            _finding(
                code="forbidden_action_authority_marker",
                severity="blocking",
                message=(
                    "ActionIntentCandidate carries forbidden order, broker, "
                    f"or authority marker {marker!r}."
                ),
                recovery_hint="Recreate the intent without order, broker, or authority fields.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        )
        status = "invalid"
    return status, findings


def _policy_findings(
    *,
    action_intent: ActionIntent,
    ips_restricted_actions: list[str] | None,
    source_refs: list[str],
    receipt_refs: list[str],
) -> tuple[str, list[ActionIntentPreflightFinding]]:
    if ips_restricted_actions is None:
        return "unknown", [
            _finding(
                code="missing_current_ips",
                severity="warning",
                message="No active IPS is available for action policy checks.",
                recovery_hint=(
                    "Record an active IPS before treating this preflight "
                    "as policy complete."
                ),
                source_refs=source_refs,
                receipt_refs=receipt_refs,
                blocks_progression=False,
            )
        ]
    if action_intent.action_type in set(ips_restricted_actions):
        return "restricted", [
            _finding(
                code="ips_restricted_action_type",
                severity="blocking",
                message="The active IPS explicitly restricts this action_type.",
                recovery_hint="Choose a different action intent or revise the user-owned IPS.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
            )
        ]
    return "not_restricted", []


def _evidence_findings(
    *,
    action_intent: ActionIntent,
    portfolio_snapshot: Snapshot | None,
    source_refs: list[str],
    receipt_refs: list[str],
) -> tuple[str, list[ActionIntentPreflightFinding]]:
    findings: list[ActionIntentPreflightFinding] = []
    status = "complete"
    if not source_refs or not receipt_refs:
        findings.append(
            _finding(
                code="missing_action_intent_evidence",
                severity="warning",
                message="ActionIntentCandidate lacks complete source or receipt refs.",
                recovery_hint=(
                    "Attach source_refs and receipt_refs before using this report downstream."
                ),
                source_refs=source_refs,
                receipt_refs=receipt_refs,
                blocks_progression=False,
            )
        )
        status = "incomplete"
    if action_intent.action_type in _EXPOSURE_ACTIONS and portfolio_snapshot is None:
        findings.append(
            _finding(
                code="missing_exposure_snapshot",
                severity="warning",
                message=(
                    "No current portfolio snapshot is available for "
                    "exposure-aware action preflight."
                ),
                recovery_hint=(
                    "Import or mirror current portfolio state before "
                    "simulation or order-ticket work."
                ),
                source_refs=source_refs,
                receipt_refs=receipt_refs,
                blocks_progression=False,
            )
        )
        status = "incomplete"
    return status, findings


def _precondition_findings(
    *,
    action_intent: ActionIntent,
    source_refs: list[str],
    receipt_refs: list[str],
) -> tuple[str, list[ActionIntentPreflightFinding]]:
    required_preconditions = _dedupe(action_intent.required_preconditions)
    if not required_preconditions:
        return "incomplete", [
            _finding(
                code="required_preconditions_incomplete",
                severity="warning",
                message="ActionIntentCandidate does not declare required preconditions.",
                recovery_hint="Attach required workflow preconditions before downstream use.",
                source_refs=source_refs,
                receipt_refs=receipt_refs,
                blocks_progression=False,
            )
        ]
    if "action_preflight" not in required_preconditions:
        return "incomplete", [
            _finding(
                code="required_preconditions_incomplete",
                severity="warning",
                message=(
                    "ActionIntentCandidate does not include action_preflight "
                    "as a precondition."
                ),
                recovery_hint=(
                    "Include action_preflight in required_preconditions "
                    "for workflow gating."
                ),
                source_refs=source_refs,
                receipt_refs=receipt_refs,
                blocks_progression=False,
            )
        ]
    return "complete", []


def _simulation_findings(
    *,
    action_intent: ActionIntent,
    source_refs: list[str],
    receipt_refs: list[str],
) -> list[ActionIntentPreflightFinding]:
    if action_intent.action_type != "increase_exposure":
        return []
    if action_intent.expected_next_step == "simulation":
        return []
    return [
        _finding(
            code="simulation_recommended",
            severity="warning",
            message="Increase-exposure intents should normally progress through simulation.",
            recovery_hint="Route the intent to simulation before any future order-ticket work.",
            source_refs=source_refs,
            receipt_refs=receipt_refs,
            blocks_progression=False,
        )
    ]


def _forbidden_marker(action_intent: ActionIntent) -> str | None:
    for payload in (
        action_intent.target_scope,
        action_intent.constraints,
        action_intent.trigger_context,
    ):
        marker = forbidden_action_intent_marker(payload)
        if marker is not None:
            return marker
    return None


def _target_scope_unresolved(target_scope: dict[str, Any]) -> bool:
    if target_scope.get("scope_type") in {"single_instrument", "single_position"}:
        return not any(
            str(target_scope.get(key, "")).strip()
            for key in ("symbol", "instrument_id", "position_id")
        )
    return False


def _risk_posture(action_type: str) -> RiskPosture:
    if action_type in {"reduce_exposure", "raise_cash"}:
        return "defensive"
    if action_type == "hedge_review":
        return "protective"
    if action_type in {"rebalance", "defer_action"}:
        return "neutral"
    if action_type == "increase_exposure":
        return "offensive"
    if action_type == "watchlist":
        return "observational"
    if action_type == "request_more_evidence":
        return "evidence_only"
    return "unknown"


def _risk_direction(action_type: str) -> RiskDirection:
    if action_type in {"reduce_exposure", "raise_cash"}:
        return "reduce"
    if action_type == "increase_exposure":
        return "increase"
    if action_type == "request_more_evidence":
        return "evidence_only"
    if action_type in {"rebalance", "defer_action", "watchlist"}:
        return "neutral"
    return "unknown"


def _impact_summary(
    *,
    action_intent: ActionIntent,
    risk_posture: RiskPosture,
    known_state_refs: list[str],
    missing_data: list[str],
) -> ActionIntentImpactSummary:
    return ActionIntentImpactSummary(
        affected_scope=dict(action_intent.target_scope),
        risk_direction=_risk_direction(action_intent.action_type),
        risk_posture=risk_posture,
        requires_simulation=action_intent.expected_next_step == "simulation"
        or action_intent.action_type in {"increase_exposure", "rebalance", "hedge_review"},
        requires_human_review=action_intent.expected_next_step == "human_review",
        known_state_refs=list(known_state_refs),
        missing_data=sorted(set(missing_data)),
        order_intent=None,
        notional_estimate=None,
    )


def _next_actions(
    *,
    findings: list[ActionIntentPreflightFinding],
    expected_next_step: str,
) -> list[str]:
    if any(finding.blocks_progression for finding in findings):
        return ["Resolve blocking preflight findings before progressing."]
    warning_codes = [finding.code for finding in findings if finding.severity == "warning"]
    if warning_codes:
        return [
            "Review and acknowledge warning findings before downstream use.",
            f"Progress to {expected_next_step} only with warning context attached.",
        ]
    return [f"Progress to {expected_next_step} with this report hash attached."]


def _finding(
    *,
    code: str,
    severity: ActionIntentPreflightSeverity,
    message: str,
    recovery_hint: str,
    source_refs: list[str],
    receipt_refs: list[str],
    blocks_progression: bool = True,
) -> ActionIntentPreflightFinding:
    return ActionIntentPreflightFinding(
        code=code,
        severity=severity,
        message=message,
        recovery_hint=recovery_hint,
        source_refs=list(source_refs),
        receipt_refs=list(receipt_refs),
        blocks_progression=blocks_progression,
    )


def _report(
    *,
    action_intent: ActionIntent,
    proposal: Proposal | None,
    freshness_status: str,
    target_scope_status: str,
    policy_status: str,
    evidence_status: str,
    precondition_status: str,
    risk_posture: RiskPosture,
    findings: list[ActionIntentPreflightFinding],
    impact_summary: ActionIntentImpactSummary,
    next_actions: list[str],
) -> ActionIntentPreflightReport:
    if any(finding.blocks_progression for finding in findings):
        status: ActionIntentPreflightStatus = "block"
    elif findings:
        status = "warn"
    else:
        status = "pass"
    report = ActionIntentPreflightReport(
        action_intent_id=action_intent.action_intent_id,
        proposal_id=action_intent.proposal_id,
        action_type=action_intent.action_type,
        status=status,
        system_preflight_recomputed=True,
        action_intent_receipt_ref=action_intent.receipt_ref,
        source_proposal_receipt_ref=action_intent.source_proposal_receipt_ref,
        current_proposal_receipt_ref=proposal.receipt_ref if proposal else None,
        freshness_status=freshness_status,
        target_scope_status=target_scope_status,
        policy_status=policy_status,
        evidence_status=evidence_status,
        precondition_status=precondition_status,
        risk_posture=risk_posture,
        findings=findings,
        impact_summary=impact_summary,
        next_actions=next_actions,
        report_hash="",
        execution_allowed=False,
        authority_transition=False,
    )
    return ActionIntentPreflightReport(
        **{
            **report.__dict__,
            "report_hash": _report_hash(report),
        }
    )


def _report_hash(report: ActionIntentPreflightReport) -> str:
    payload = {
        "action_intent_id": report.action_intent_id,
        "proposal_id": report.proposal_id,
        "action_type": report.action_type,
        "status": report.status,
        "system_preflight_recomputed": True,
        "action_intent_receipt_ref": report.action_intent_receipt_ref,
        "source_proposal_receipt_ref": report.source_proposal_receipt_ref,
        "current_proposal_receipt_ref": report.current_proposal_receipt_ref,
        "freshness_status": report.freshness_status,
        "target_scope_status": report.target_scope_status,
        "policy_status": report.policy_status,
        "evidence_status": report.evidence_status,
        "precondition_status": report.precondition_status,
        "risk_posture": report.risk_posture,
        "findings": [finding.__dict__ for finding in report.findings],
        "impact_summary": report.impact_summary.__dict__,
        "next_actions": report.next_actions,
        "execution_allowed": False,
        "authority_transition": False,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _dedupe(values: list[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})
