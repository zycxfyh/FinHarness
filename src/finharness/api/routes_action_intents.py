"""Action intent candidate routes.

LEGACY — superseded by Execution Kernel (/execution/* routes).
no_new_callers: true
superseded_by: /execution/order-drafts, /execution/orders, /execution/reports

These endpoints bridge proposal review state to future capital-action workflows.
They do not create orders, broker instructions, approvals, or execution
authorization.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel import Session

from finharness.action_intent_preflight import (
    ACTION_INTENT_PREFLIGHT_NON_CLAIMS,
    ActionIntentImpactSummary,
    ActionIntentPreflightFinding,
    preflight_action_intent,
)
from finharness.api.legacy_headers import (
    ACTION_INTENT_SUPERSEDED_BY,
    mark_legacy_surface,
)
from finharness.api.dependencies import (
    EngineDependency,
    ReceiptRootDependency,
    WriteCapabilityDependency,
)
from finharness.statecore.action_intent_authority_bindings import (
    ACTION_INTENT_AUTHORITY_BINDING_NON_CLAIMS,
    ActionIntentAuthorityBindingResult,
    ActionIntentAuthorityBindingValidationError,
    ActionIntentAuthorType,
    create_action_intent_authority_binding,
)
from finharness.statecore.action_intent_simulations import (
    ACTION_INTENT_SIMULATION_NON_CLAIMS,
    ActionIntentSimulationPreflightBlockedError,
    ActionIntentSimulationScenarioMode,
    ActionIntentSimulationStaleError,
    ActionIntentSimulationValidationError,
    create_governed_action_intent_simulation_report,
)
from finharness.statecore.action_intents import (
    ACTION_INTENT_NON_CLAIMS,
    ActionIntentCreator,
    ActionIntentNextStep,
    ActionIntentStaleProposalError,
    ActionIntentType,
    ActionIntentValidationError,
    create_governed_action_intent,
)
from finharness.statecore.capital_objective_fits import (
    CAPITAL_OBJECTIVE_FIT_NON_CLAIMS,
    CapitalObjectiveAlignment,
    CapitalObjectiveFitStaleError,
    CapitalObjectiveFitValidationError,
    create_governed_capital_objective_fit,
)
from finharness.statecore.models import (
    ActionIntent,
    ActionIntentAuthorityBinding,
    ActionIntentSimulationReport,
    CapitalObjectiveFit,
    TradePlanCandidate,
    TradePlanReviewGate,
)
from finharness.statecore.trade_plan_candidates import (
    TRADE_PLAN_CANDIDATE_NON_CLAIMS,
    TradePlanCandidatePreflightBlockedError,
    TradePlanCandidateStaleError,
    TradePlanCandidateValidationError,
    create_governed_trade_plan_candidate,
)
from finharness.statecore.trade_plan_review_gates import (
    TRADE_PLAN_REVIEW_GATE_NON_CLAIMS,
    TradePlanReviewGateDecision,
    TradePlanReviewGateReviewerType,
    TradePlanReviewGateStaleError,
    TradePlanReviewGateValidationError,
    create_governed_trade_plan_review_gate,
)

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
    authority_status: str
    authority_binding_id: str | None
    authority_binding_receipt_ref: str | None
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


class ActionIntentAuthorityBindingCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    author_type: ActionIntentAuthorType
    author_id: str
    agent_authority_grant_id: str | None = None
    requested_scope: dict[str, Any]
    source_rule_ref: str | None = None
    source_refs: list[str] = Field(default_factory=list)

    @field_validator("author_id")
    @classmethod
    def require_author_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("authority binding requires author_id")
        return value


class ActionIntentAuthorityBindingCreateResponse(BaseModel):
    authority_binding: ActionIntentAuthorityBinding
    binding_result: ActionIntentAuthorityBindingResult
    receipt_ref: str
    non_claims: tuple[str, ...] = ACTION_INTENT_AUTHORITY_BINDING_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


class ActionIntentAuthorityBindingResponse(BaseModel):
    authority_binding: ActionIntentAuthorityBinding
    non_claims: tuple[str, ...] = ACTION_INTENT_AUTHORITY_BINDING_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


class ActionIntentSimulationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_action_intent_receipt_ref: str
    expected_action_preflight_report_hash: str
    simulation_reason: str
    explicit_preflight_acknowledgement: bool = False
    acknowledged_preflight_warning_codes: list[str] = Field(default_factory=list)
    scenario_mode: ActionIntentSimulationScenarioMode = "descriptive_v0"
    assumptions: dict[str, Any] = Field(default_factory=dict)
    source_refs: list[str] = Field(default_factory=list)

    @field_validator(
        "expected_action_intent_receipt_ref",
        "expected_action_preflight_report_hash",
        "simulation_reason",
    )
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("simulation report requires receipt, preflight hash, and reason")
        return value


class ActionIntentSimulationCreateResponse(BaseModel):
    simulation_report: ActionIntentSimulationReport
    receipt_ref: str
    non_claims: tuple[str, ...] = ACTION_INTENT_SIMULATION_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


class ActionIntentSimulationResponse(BaseModel):
    simulation_report: ActionIntentSimulationReport
    non_claims: tuple[str, ...] = ACTION_INTENT_SIMULATION_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


class TradePlanCandidateCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_action_intent_receipt_ref: str
    expected_action_preflight_report_hash: str
    expected_simulation_report_receipt_ref: str
    plan_reason: str
    explicit_preflight_acknowledgement: bool = False
    acknowledged_preflight_warning_codes: list[str] = Field(default_factory=list)
    plan_scope: dict[str, Any]
    source_refs: list[str] = Field(default_factory=list)

    @field_validator(
        "expected_action_intent_receipt_ref",
        "expected_action_preflight_report_hash",
        "expected_simulation_report_receipt_ref",
        "plan_reason",
    )
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError(
                "trade plan candidate requires receipt refs, preflight hash, and reason"
            )
        return value


class TradePlanCandidateCreateResponse(BaseModel):
    trade_plan_candidate: TradePlanCandidate
    receipt_ref: str
    non_claims: tuple[str, ...] = TRADE_PLAN_CANDIDATE_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False
    submitted_to_broker: bool = False


class TradePlanCandidateResponse(BaseModel):
    trade_plan_candidate: TradePlanCandidate
    non_claims: tuple[str, ...] = TRADE_PLAN_CANDIDATE_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False
    submitted_to_broker: bool = False


class CapitalObjectiveFitCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_trade_plan_candidate_receipt_ref: str
    expected_action_intent_receipt_ref: str
    expected_action_preflight_report_hash: str
    expected_simulation_report_receipt_ref: str
    objective_alignment: CapitalObjectiveAlignment
    objective_basis: dict[str, Any] = Field(default_factory=dict)
    benefit_thesis: str
    risk_budget_impact: dict[str, Any] = Field(default_factory=dict)
    liquidity_impact: dict[str, Any] = Field(default_factory=dict)
    concentration_impact: dict[str, Any] = Field(default_factory=dict)
    reversibility: dict[str, Any] = Field(default_factory=dict)
    opportunity_cost: dict[str, Any] = Field(default_factory=dict)
    alternatives_considered: list[dict[str, Any]] = Field(default_factory=list)
    major_uncertainties: list[str] = Field(default_factory=list)
    user_questions: list[str] = Field(default_factory=list)
    recommended_next_safe_path: str
    source_refs: list[str] = Field(default_factory=list)

    @field_validator(
        "expected_trade_plan_candidate_receipt_ref",
        "expected_action_intent_receipt_ref",
        "expected_action_preflight_report_hash",
        "expected_simulation_report_receipt_ref",
        "benefit_thesis",
        "recommended_next_safe_path",
    )
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("capital objective fit requires current evidence and thesis")
        return value


class CapitalObjectiveFitCreateResponse(BaseModel):
    objective_fit: CapitalObjectiveFit
    receipt_ref: str
    non_claims: tuple[str, ...] = CAPITAL_OBJECTIVE_FIT_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False
    submitted_to_broker: bool = False
    creates_order_ticket: bool = False
    suitability_certified: bool = False
    approval_granted: bool = False


class CapitalObjectiveFitResponse(BaseModel):
    objective_fit: CapitalObjectiveFit
    non_claims: tuple[str, ...] = CAPITAL_OBJECTIVE_FIT_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False
    submitted_to_broker: bool = False
    creates_order_ticket: bool = False
    suitability_certified: bool = False
    approval_granted: bool = False


class TradePlanReviewGateCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_trade_plan_candidate_receipt_ref: str
    expected_action_intent_receipt_ref: str
    expected_action_preflight_report_hash: str
    expected_simulation_report_receipt_ref: str
    review_decision: TradePlanReviewGateDecision
    reviewer_type: TradePlanReviewGateReviewerType = "human"
    reviewer_id: str
    review_reason: str
    review_context: dict[str, Any] = Field(default_factory=dict)
    review_findings: list[dict[str, Any]] = Field(default_factory=list)
    deny_reasons: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)

    @field_validator(
        "expected_trade_plan_candidate_receipt_ref",
        "expected_action_intent_receipt_ref",
        "expected_action_preflight_report_hash",
        "expected_simulation_report_receipt_ref",
        "reviewer_id",
        "review_reason",
    )
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("trade plan review gate requires current evidence and reason")
        return value


class TradePlanReviewGateCreateResponse(BaseModel):
    review_gate: TradePlanReviewGate
    receipt_ref: str
    non_claims: tuple[str, ...] = TRADE_PLAN_REVIEW_GATE_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False
    submitted_to_broker: bool = False
    creates_order_ticket: bool = False


class TradePlanReviewGateResponse(BaseModel):
    review_gate: TradePlanReviewGate
    non_claims: tuple[str, ...] = TRADE_PLAN_REVIEW_GATE_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False
    submitted_to_broker: bool = False
    creates_order_ticket: bool = False


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
    _write_capability: WriteCapabilityDependency,
    response: Response,
) -> ActionIntentCreateResponse:
    mark_legacy_surface(response, ACTION_INTENT_SUPERSEDED_BY)
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
    response: Response,
) -> ActionIntentResponse:
    mark_legacy_surface(response, ACTION_INTENT_SUPERSEDED_BY)
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
    response: Response,
) -> ActionIntentPreflightResponse:
    mark_legacy_surface(response, ACTION_INTENT_SUPERSEDED_BY)
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
        authority_status=report.authority_status,
        authority_binding_id=report.authority_binding_id,
        authority_binding_receipt_ref=report.authority_binding_receipt_ref,
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


@router.post(
    "/action-intents/{action_intent_id}/authority-bindings",
    response_model=ActionIntentAuthorityBindingCreateResponse,
)
async def create_action_intent_authority_binding_endpoint(
    action_intent_id: str,
    request: ActionIntentAuthorityBindingCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    _write_capability: WriteCapabilityDependency,
    response: Response,
) -> ActionIntentAuthorityBindingCreateResponse:
    mark_legacy_surface(response, ACTION_INTENT_SUPERSEDED_BY)
    try:
        write = create_action_intent_authority_binding(
            action_intent_id=action_intent_id,
            author_type=request.author_type,
            author_id=request.author_id,
            agent_authority_grant_id=request.agent_authority_grant_id,
            requested_scope=request.requested_scope,
            source_rule_ref=request.source_rule_ref,
            source_refs=request.source_refs,
            engine=engine,
            receipt_root=receipt_root,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"action intent not found: {action_intent_id}",
        ) from exc
    except ActionIntentAuthorityBindingValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ActionIntentAuthorityBindingCreateResponse(
        authority_binding=write.binding,
        binding_result=write.result,
        receipt_ref=write.receipt_ref,
        execution_allowed=False,
        authority_transition=False,
    )


@router.get(
    "/action-intent-authority-bindings/{binding_id}",
    response_model=ActionIntentAuthorityBindingResponse,
)
async def get_action_intent_authority_binding(
    binding_id: str,
    engine: EngineDependency,
    response: Response,
) -> ActionIntentAuthorityBindingResponse:
    mark_legacy_surface(response, ACTION_INTENT_SUPERSEDED_BY)
    with Session(engine) as session:
        binding = session.get(ActionIntentAuthorityBinding, binding_id)
    if binding is None:
        raise HTTPException(
            status_code=404,
            detail=f"action intent authority binding not found: {binding_id}",
        )
    return ActionIntentAuthorityBindingResponse(
        authority_binding=binding,
        execution_allowed=False,
        authority_transition=False,
    )


@router.post(
    "/action-intents/{action_intent_id}/simulation-reports",
    response_model=ActionIntentSimulationCreateResponse,
)
async def create_action_intent_simulation_report(
    action_intent_id: str,
    request: ActionIntentSimulationCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    _write_capability: WriteCapabilityDependency,
    response: Response,
) -> ActionIntentSimulationCreateResponse:
    mark_legacy_surface(response, ACTION_INTENT_SUPERSEDED_BY)
    try:
        write = create_governed_action_intent_simulation_report(
            action_intent_id=action_intent_id,
            expected_action_intent_receipt_ref=request.expected_action_intent_receipt_ref,
            expected_action_preflight_report_hash=request.expected_action_preflight_report_hash,
            simulation_reason=request.simulation_reason,
            explicit_preflight_acknowledgement=request.explicit_preflight_acknowledgement,
            acknowledged_preflight_warning_codes=(
                request.acknowledged_preflight_warning_codes
            ),
            scenario_mode=request.scenario_mode,
            assumptions=request.assumptions,
            source_refs=request.source_refs,
            engine=engine,
            receipt_root=receipt_root,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"action intent not found: {action_intent_id}",
        ) from exc
    except ActionIntentSimulationStaleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ActionIntentSimulationPreflightBlockedError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "simulation_preflight_blocked",
                "message": str(exc),
                "finding_codes": exc.codes,
            },
        ) from exc
    except ActionIntentSimulationValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ActionIntentSimulationCreateResponse(
        simulation_report=write.simulation_report,
        receipt_ref=write.receipt_ref,
        execution_allowed=False,
        authority_transition=False,
    )


@router.get(
    "/action-intent-simulation-reports/{simulation_report_id}",
    response_model=ActionIntentSimulationResponse,
)
async def get_action_intent_simulation_report(
    simulation_report_id: str,
    engine: EngineDependency,
    response: Response,
) -> ActionIntentSimulationResponse:
    mark_legacy_surface(response, ACTION_INTENT_SUPERSEDED_BY)
    with Session(engine) as session:
        simulation_report = session.get(ActionIntentSimulationReport, simulation_report_id)
    if simulation_report is None:
        raise HTTPException(
            status_code=404,
            detail=f"action intent simulation report not found: {simulation_report_id}",
        )
    return ActionIntentSimulationResponse(
        simulation_report=simulation_report,
        execution_allowed=False,
        authority_transition=False,
    )


@router.post(
    "/action-intent-simulation-reports/{simulation_report_id}/trade-plan-candidates",
    response_model=TradePlanCandidateCreateResponse,
)
async def create_trade_plan_candidate(
    simulation_report_id: str,
    request: TradePlanCandidateCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    _write_capability: WriteCapabilityDependency,
    response: Response,
) -> TradePlanCandidateCreateResponse:
    mark_legacy_surface(response, ACTION_INTENT_SUPERSEDED_BY)
    try:
        write = create_governed_trade_plan_candidate(
            simulation_report_id=simulation_report_id,
            expected_action_intent_receipt_ref=request.expected_action_intent_receipt_ref,
            expected_action_preflight_report_hash=request.expected_action_preflight_report_hash,
            expected_simulation_report_receipt_ref=(
                request.expected_simulation_report_receipt_ref
            ),
            plan_reason=request.plan_reason,
            explicit_preflight_acknowledgement=request.explicit_preflight_acknowledgement,
            acknowledged_preflight_warning_codes=(
                request.acknowledged_preflight_warning_codes
            ),
            plan_scope=request.plan_scope,
            source_refs=request.source_refs,
            engine=engine,
            receipt_root=receipt_root,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"action intent simulation report not found: {simulation_report_id}",
        ) from exc
    except TradePlanCandidateStaleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TradePlanCandidatePreflightBlockedError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "trade_plan_candidate_preflight_blocked",
                "message": str(exc),
                "finding_codes": exc.codes,
            },
        ) from exc
    except TradePlanCandidateValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TradePlanCandidateCreateResponse(
        trade_plan_candidate=write.trade_plan_candidate,
        receipt_ref=write.receipt_ref,
        execution_allowed=False,
        authority_transition=False,
        submitted_to_broker=False,
    )


@router.get(
    "/trade-plan-candidates/{trade_plan_candidate_id}",
    response_model=TradePlanCandidateResponse,
)
async def get_trade_plan_candidate(
    trade_plan_candidate_id: str,
    engine: EngineDependency,
    response: Response,
) -> TradePlanCandidateResponse:
    mark_legacy_surface(response, ACTION_INTENT_SUPERSEDED_BY)
    with Session(engine) as session:
        trade_plan_candidate = session.get(TradePlanCandidate, trade_plan_candidate_id)
    if trade_plan_candidate is None:
        raise HTTPException(
            status_code=404,
            detail=f"trade plan candidate not found: {trade_plan_candidate_id}",
        )
    return TradePlanCandidateResponse(
        trade_plan_candidate=trade_plan_candidate,
        execution_allowed=False,
        authority_transition=False,
        submitted_to_broker=False,
    )


@router.post(
    "/trade-plan-candidates/{trade_plan_candidate_id}/capital-objective-fits",
    response_model=CapitalObjectiveFitCreateResponse,
)
async def create_capital_objective_fit(
    trade_plan_candidate_id: str,
    request: CapitalObjectiveFitCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    _write_capability: WriteCapabilityDependency,
    response: Response,
) -> CapitalObjectiveFitCreateResponse:
    mark_legacy_surface(response, ACTION_INTENT_SUPERSEDED_BY)
    try:
        write = create_governed_capital_objective_fit(
            trade_plan_candidate_id=trade_plan_candidate_id,
            expected_trade_plan_candidate_receipt_ref=(
                request.expected_trade_plan_candidate_receipt_ref
            ),
            expected_action_intent_receipt_ref=request.expected_action_intent_receipt_ref,
            expected_action_preflight_report_hash=(
                request.expected_action_preflight_report_hash
            ),
            expected_simulation_report_receipt_ref=(
                request.expected_simulation_report_receipt_ref
            ),
            objective_alignment=request.objective_alignment,
            objective_basis=request.objective_basis,
            benefit_thesis=request.benefit_thesis,
            risk_budget_impact=request.risk_budget_impact,
            liquidity_impact=request.liquidity_impact,
            concentration_impact=request.concentration_impact,
            reversibility=request.reversibility,
            opportunity_cost=request.opportunity_cost,
            alternatives_considered=request.alternatives_considered,
            major_uncertainties=request.major_uncertainties,
            user_questions=request.user_questions,
            recommended_next_safe_path=request.recommended_next_safe_path,
            source_refs=request.source_refs,
            engine=engine,
            receipt_root=receipt_root,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"trade plan candidate not found: {trade_plan_candidate_id}",
        ) from exc
    except CapitalObjectiveFitStaleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except CapitalObjectiveFitValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return CapitalObjectiveFitCreateResponse(
        objective_fit=write.objective_fit,
        receipt_ref=write.receipt_ref,
        execution_allowed=False,
        authority_transition=False,
        submitted_to_broker=False,
        creates_order_ticket=False,
        suitability_certified=False,
        approval_granted=False,
    )


@router.get(
    "/capital-objective-fits/{capital_objective_fit_id}",
    response_model=CapitalObjectiveFitResponse,
)
async def get_capital_objective_fit(
    capital_objective_fit_id: str,
    engine: EngineDependency,
    response: Response,
) -> CapitalObjectiveFitResponse:
    mark_legacy_surface(response, ACTION_INTENT_SUPERSEDED_BY)
    with Session(engine) as session:
        objective_fit = session.get(CapitalObjectiveFit, capital_objective_fit_id)
    if objective_fit is None:
        raise HTTPException(
            status_code=404,
            detail=f"capital objective fit not found: {capital_objective_fit_id}",
        )
    return CapitalObjectiveFitResponse(
        objective_fit=objective_fit,
        execution_allowed=False,
        authority_transition=False,
        submitted_to_broker=False,
        creates_order_ticket=False,
        suitability_certified=False,
        approval_granted=False,
    )


@router.post(
    "/trade-plan-candidates/{trade_plan_candidate_id}/review-gates",
    response_model=TradePlanReviewGateCreateResponse,
)
async def create_trade_plan_review_gate(
    trade_plan_candidate_id: str,
    request: TradePlanReviewGateCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
    _write_capability: WriteCapabilityDependency,
    response: Response,
) -> TradePlanReviewGateCreateResponse:
    mark_legacy_surface(response, ACTION_INTENT_SUPERSEDED_BY)
    try:
        write = create_governed_trade_plan_review_gate(
            trade_plan_candidate_id=trade_plan_candidate_id,
            expected_trade_plan_candidate_receipt_ref=(
                request.expected_trade_plan_candidate_receipt_ref
            ),
            expected_action_intent_receipt_ref=request.expected_action_intent_receipt_ref,
            expected_action_preflight_report_hash=(
                request.expected_action_preflight_report_hash
            ),
            expected_simulation_report_receipt_ref=(
                request.expected_simulation_report_receipt_ref
            ),
            review_decision=request.review_decision,
            reviewer_type=request.reviewer_type,
            reviewer_id=request.reviewer_id,
            review_reason=request.review_reason,
            review_context=request.review_context,
            review_findings=request.review_findings,
            deny_reasons=request.deny_reasons,
            source_refs=request.source_refs,
            engine=engine,
            receipt_root=receipt_root,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"trade plan candidate not found: {trade_plan_candidate_id}",
        ) from exc
    except TradePlanReviewGateStaleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TradePlanReviewGateValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TradePlanReviewGateCreateResponse(
        review_gate=write.review_gate,
        receipt_ref=write.receipt_ref,
        execution_allowed=False,
        authority_transition=False,
        submitted_to_broker=False,
        creates_order_ticket=False,
    )


@router.get(
    "/trade-plan-review-gates/{review_gate_id}",
    response_model=TradePlanReviewGateResponse,
)
async def get_trade_plan_review_gate(
    review_gate_id: str,
    engine: EngineDependency,
    response: Response,
) -> TradePlanReviewGateResponse:
    mark_legacy_surface(response, ACTION_INTENT_SUPERSEDED_BY)
    with Session(engine) as session:
        review_gate = session.get(TradePlanReviewGate, review_gate_id)
    if review_gate is None:
        raise HTTPException(
            status_code=404,
            detail=f"trade plan review gate not found: {review_gate_id}",
        )
    return TradePlanReviewGateResponse(
        review_gate=review_gate,
        execution_allowed=False,
        authority_transition=False,
        submitted_to_broker=False,
        creates_order_ticket=False,
    )
