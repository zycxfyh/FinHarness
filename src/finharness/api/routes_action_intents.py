"""Action intent candidate routes.

These endpoints bridge proposal review state to future capital-action workflows.
They do not create orders, broker instructions, approvals, or execution
authorization.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel import Session

from finharness.action_intent_preflight import (
    ACTION_INTENT_PREFLIGHT_NON_CLAIMS,
    ActionIntentImpactSummary,
    ActionIntentPreflightFinding,
    preflight_action_intent,
)
from finharness.api.dependencies import EngineDependency, ReceiptRootDependency
from finharness.statecore.action_intents import (
    ACTION_INTENT_NON_CLAIMS,
    ActionIntentCreator,
    ActionIntentNextStep,
    ActionIntentStaleProposalError,
    ActionIntentType,
    ActionIntentValidationError,
    create_governed_action_intent,
)
from finharness.statecore.models import ActionIntent

router = APIRouter(tags=["action-intents"])


class ActionIntentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: ActionIntentType
    intent_summary: str
    rationale: str
    target_scope: dict[str, Any]
    constraints: dict[str, Any] = Field(default_factory=dict)
    trigger_context: dict[str, Any] = Field(default_factory=dict)
    required_preconditions: list[str] = Field(default_factory=list)
    expected_next_step: ActionIntentNextStep = "action_preflight"
    expected_proposal_receipt_ref: str
    source_refs: list[str]
    source_revision_receipt_ref: str | None = None
    created_by: ActionIntentCreator = "human"
    active_profile: str | None = None

    @field_validator("intent_summary", "rationale", "expected_proposal_receipt_ref")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("action intent requires summary, rationale, and receipt freshness")
        return value

    @field_validator("source_refs")
    @classmethod
    def require_source_refs(cls, value: list[str]) -> list[str]:
        clean = sorted({str(item).strip() for item in value if str(item).strip()})
        if not clean:
            raise ValueError("action intent requires at least one source_ref")
        return clean


class ActionIntentCreateResponse(BaseModel):
    action_intent: ActionIntent
    receipt_ref: str
    non_claims: tuple[str, ...] = ACTION_INTENT_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


class ActionIntentResponse(BaseModel):
    action_intent: ActionIntent
    non_claims: tuple[str, ...] = ACTION_INTENT_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


class ActionIntentPreflightFindingView(BaseModel):
    code: str
    severity: str
    message: str
    recovery_hint: str
    source_refs: list[str]
    receipt_refs: list[str]
    blocks_progression: bool


class ActionIntentImpactSummaryView(BaseModel):
    affected_scope: dict[str, Any]
    risk_direction: str
    risk_posture: str
    requires_simulation: bool
    requires_human_review: bool
    known_state_refs: list[str]
    missing_data: list[str]
    order_intent: None = None
    notional_estimate: None = None


class ActionIntentPreflightResponse(BaseModel):
    action_intent_id: str
    proposal_id: str
    action_type: str
    status: str
    system_preflight_recomputed: bool
    action_intent_receipt_ref: str | None
    source_proposal_receipt_ref: str | None
    current_proposal_receipt_ref: str | None
    freshness_status: str
    target_scope_status: str
    policy_status: str
    evidence_status: str
    precondition_status: str
    risk_posture: str
    findings: list[ActionIntentPreflightFindingView]
    impact_summary: ActionIntentImpactSummaryView
    next_actions: list[str]
    report_hash: str
    non_claims: tuple[str, ...] = ACTION_INTENT_PREFLIGHT_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


def _preflight_finding_view(
    finding: ActionIntentPreflightFinding,
) -> ActionIntentPreflightFindingView:
    return ActionIntentPreflightFindingView(
        code=finding.code,
        severity=finding.severity,
        message=finding.message,
        recovery_hint=finding.recovery_hint,
        source_refs=finding.source_refs,
        receipt_refs=finding.receipt_refs,
        blocks_progression=finding.blocks_progression,
    )


def _impact_summary_view(summary: ActionIntentImpactSummary) -> ActionIntentImpactSummaryView:
    return ActionIntentImpactSummaryView(
        affected_scope=summary.affected_scope,
        risk_direction=summary.risk_direction,
        risk_posture=summary.risk_posture,
        requires_simulation=summary.requires_simulation,
        requires_human_review=summary.requires_human_review,
        known_state_refs=summary.known_state_refs,
        missing_data=summary.missing_data,
        order_intent=None,
        notional_estimate=None,
    )


@router.post(
    "/proposals/{proposal_id}/action-intents",
    response_model=ActionIntentCreateResponse,
)
async def create_action_intent(
    proposal_id: str,
    request: ActionIntentCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ActionIntentCreateResponse:
    try:
        write = create_governed_action_intent(
            proposal_id=proposal_id,
            expected_proposal_receipt_ref=request.expected_proposal_receipt_ref,
            action_type=request.action_type,
            intent_summary=request.intent_summary,
            rationale=request.rationale,
            target_scope=request.target_scope,
            constraints=request.constraints,
            trigger_context=request.trigger_context,
            required_preconditions=request.required_preconditions,
            expected_next_step=request.expected_next_step,
            created_by=request.created_by,
            active_profile=request.active_profile,
            source_refs=request.source_refs,
            source_revision_receipt_ref=request.source_revision_receipt_ref,
            engine=engine,
            receipt_root=receipt_root,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"proposal not found: {proposal_id}") from exc
    except ActionIntentStaleProposalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ActionIntentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ActionIntentCreateResponse(
        action_intent=write.action_intent,
        receipt_ref=write.receipt_ref,
        execution_allowed=False,
        authority_transition=False,
    )


@router.get("/action-intents/{action_intent_id}", response_model=ActionIntentResponse)
async def get_action_intent(
    action_intent_id: str,
    engine: EngineDependency,
) -> ActionIntentResponse:
    with Session(engine) as session:
        action_intent = session.get(ActionIntent, action_intent_id)
    if action_intent is None:
        raise HTTPException(
            status_code=404,
            detail=f"action intent not found: {action_intent_id}",
        )
    return ActionIntentResponse(
        action_intent=action_intent,
        execution_allowed=False,
        authority_transition=False,
    )


@router.get(
    "/action-intents/{action_intent_id}/preflight",
    response_model=ActionIntentPreflightResponse,
)
async def get_action_intent_preflight(
    action_intent_id: str,
    engine: EngineDependency,
) -> ActionIntentPreflightResponse:
    report = preflight_action_intent(action_intent_id, engine=engine)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"action intent not found: {action_intent_id}",
        )
    return ActionIntentPreflightResponse(
        action_intent_id=report.action_intent_id,
        proposal_id=report.proposal_id,
        action_type=report.action_type,
        status=report.status,
        system_preflight_recomputed=report.system_preflight_recomputed,
        action_intent_receipt_ref=report.action_intent_receipt_ref,
        source_proposal_receipt_ref=report.source_proposal_receipt_ref,
        current_proposal_receipt_ref=report.current_proposal_receipt_ref,
        freshness_status=report.freshness_status,
        target_scope_status=report.target_scope_status,
        policy_status=report.policy_status,
        evidence_status=report.evidence_status,
        precondition_status=report.precondition_status,
        risk_posture=report.risk_posture,
        findings=[_preflight_finding_view(finding) for finding in report.findings],
        impact_summary=_impact_summary_view(report.impact_summary),
        next_actions=report.next_actions,
        report_hash=report.report_hash,
        execution_allowed=False,
        authority_transition=False,
    )
