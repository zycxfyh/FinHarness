"""Deterministic autonomy admission for the Agent-native capital runtime.

The Capital Agent owns objective strategy.  This module is the Harness membrane
that decides whether a requested Agent action is effective, remains a candidate,
must escalate, or is blocked by current world/runtime conditions.

It deliberately performs no financial calculation and no side effect.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WorldFidelityLevel(StrEnum):
    W0_CAPITAL_FACTS = "W0_capital_facts"
    W1_VERSIONED_DECISIONS = "W1_versioned_decisions"
    W2_SCENARIO_WORLD = "W2_scenario_world"
    W3_OUTCOME_RECONCILIATION = "W3_outcome_reconciliation"
    W4_LEARNING_POLICY = "W4_learning_policy"


class AgentAutonomyLevel(StrEnum):
    AUT0_CONTEXT_ASSISTANT = "AUT0_context_assistant"
    AUT1_TOOL_REVIEWER = "AUT1_tool_reviewer"
    AUT2_DURABLE_LOOP = "AUT2_durable_loop"
    AUT3_DELEGATED_REVIEW = "AUT3_delegated_review"
    AUT4_PAPER_MANAGER = "AUT4_paper_manager"
    AUT5_REAL_OPERATOR = "AUT5_real_operator"
    AUT6_CONTINUOUS_AGENT = "AUT6_continuous_agent"


class HumanControlMode(StrEnum):
    IN_THE_LOOP = "human_in_the_loop"
    IN_OR_ON_THE_LOOP = "human_in_or_on_the_loop"
    ON_THE_LOOP = "human_on_the_loop"
    ON_OR_OVER_THE_LOOP = "human_on_or_over_the_loop"
    OVER_THE_LOOP = "human_over_the_loop"


class AgentActionClass(StrEnum):
    OBSERVE_STATE = "observe_state"
    GATHER_EVIDENCE = "gather_evidence"
    PREPARE_REVIEW_PACKET = "prepare_review_packet"
    MAKE_PLANNING_DECISION = "make_planning_decision"
    TAKE_PAPER_ACTION = "take_paper_action"
    TAKE_REAL_ACTION = "take_real_action"
    CHANGE_CAPITAL_CONSTITUTION = "change_capital_constitution"


class AdmissionDisposition(StrEnum):
    EFFECTIVE = "effective"
    CANDIDATE = "candidate"
    ESCALATE = "escalate"
    BLOCKED = "blocked"


class AutonomyFindingCode(StrEnum):
    MANDATE_REQUIRED = "mandate_required"
    MANDATE_NOT_ACTIVE = "mandate_not_active"
    MANDATE_EXPIRED = "mandate_expired"
    KILL_SWITCH_ENGAGED = "kill_switch_engaged"
    AUTONOMY_EXCEEDS_MANDATE = "autonomy_exceeds_mandate"
    AUTONOMY_EXCEEDS_RUNTIME = "autonomy_exceeds_runtime"
    ACTION_OUTSIDE_MANDATE = "action_outside_mandate"
    FINANCIAL_ACTION_OUTSIDE_MANDATE = "financial_action_outside_mandate"
    ASSET_CLASS_OUTSIDE_MANDATE = "asset_class_outside_mandate"
    TOOL_OUTSIDE_MANDATE = "tool_outside_mandate"
    WORLD_FIDELITY_INSUFFICIENT = "world_fidelity_insufficient"
    REQUESTED_AUTONOMY_INSUFFICIENT = "requested_autonomy_insufficient"
    EXTERNAL_EFFECT_CLASS_MISMATCH = "external_effect_class_mismatch"
    CONSTITUTIONAL_CHANGE_REQUIRES_HUMAN = "constitutional_change_requires_human"


_WORLD_RANK = {level: rank for rank, level in enumerate(WorldFidelityLevel)}
_AUTONOMY_RANK = {level: rank for rank, level in enumerate(AgentAutonomyLevel)}

_ACTION_REQUIREMENTS: dict[
    AgentActionClass, tuple[WorldFidelityLevel, AgentAutonomyLevel]
] = {
    AgentActionClass.OBSERVE_STATE: (
        WorldFidelityLevel.W0_CAPITAL_FACTS,
        AgentAutonomyLevel.AUT0_CONTEXT_ASSISTANT,
    ),
    AgentActionClass.GATHER_EVIDENCE: (
        WorldFidelityLevel.W0_CAPITAL_FACTS,
        AgentAutonomyLevel.AUT1_TOOL_REVIEWER,
    ),
    AgentActionClass.PREPARE_REVIEW_PACKET: (
        WorldFidelityLevel.W1_VERSIONED_DECISIONS,
        AgentAutonomyLevel.AUT2_DURABLE_LOOP,
    ),
    AgentActionClass.MAKE_PLANNING_DECISION: (
        WorldFidelityLevel.W2_SCENARIO_WORLD,
        AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
    ),
    AgentActionClass.TAKE_PAPER_ACTION: (
        WorldFidelityLevel.W3_OUTCOME_RECONCILIATION,
        AgentAutonomyLevel.AUT4_PAPER_MANAGER,
    ),
    AgentActionClass.TAKE_REAL_ACTION: (
        WorldFidelityLevel.W4_LEARNING_POLICY,
        AgentAutonomyLevel.AUT5_REAL_OPERATOR,
    ),
    AgentActionClass.CHANGE_CAPITAL_CONSTITUTION: (
        WorldFidelityLevel.W4_LEARNING_POLICY,
        AgentAutonomyLevel.AUT6_CONTINUOUS_AGENT,
    ),
}


class AutonomyMandate(BaseModel):
    """Effective delegation contract consumed by the Harness admission gate."""

    model_config = ConfigDict(frozen=True)

    mandate_id: str
    authority_grant_id: str | None = None
    principal_id: str
    agent_id: str
    status: Literal["active", "suspended", "revoked", "expired"] = "active"
    granted_autonomy: AgentAutonomyLevel
    allowed_action_classes: tuple[AgentActionClass, ...]
    allowed_financial_action_types: tuple[str, ...] = ()
    allowed_asset_classes: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    constraints: dict[str, Any] = Field(default_factory=dict)
    kill_switch_engaged: bool = False
    expires_at_utc: str | None = None
    source_refs: tuple[str, ...] = ()

    @field_validator("mandate_id", "principal_id", "agent_id")
    @classmethod
    def require_identity(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("autonomy mandate identities must be non-blank")
        return value


class AgentActionRequest(BaseModel):
    """Typed Agent decision presented to the Harness for admission."""

    model_config = ConfigDict(frozen=True)

    action_id: str = Field(default_factory=lambda: f"agent_action_{uuid4().hex}")
    work_id: str
    agent_id: str
    objective: str
    action_class: AgentActionClass
    requested_autonomy: AgentAutonomyLevel
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    target_scope: dict[str, Any] = Field(default_factory=dict)
    external_effect: bool = False
    reversible: bool = True
    source_refs: tuple[str, ...] = ()

    @field_validator("work_id", "agent_id", "objective")
    @classmethod
    def require_context(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("agent action context must be non-blank")
        return value

    @model_validator(mode="after")
    def require_real_action_effect_shape(self) -> AgentActionRequest:
        is_real = self.action_class == AgentActionClass.TAKE_REAL_ACTION
        if self.external_effect != is_real:
            raise ValueError(
                "external_effect must be true exactly for take_real_action requests"
            )
        return self


class AutonomyRuntimeState(BaseModel):
    """Current Harness ceiling and financial-world fidelity."""

    model_config = ConfigDict(frozen=True)

    world_fidelity: WorldFidelityLevel
    runtime_autonomy_ceiling: AgentAutonomyLevel
    world_state_ref: str | None = None
    now_utc: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class AutonomyFinding(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: AutonomyFindingCode
    detail: str


class AutonomyAdmissionReport(BaseModel):
    """Deterministic decision about whether an Agent action is effective."""

    model_config = ConfigDict(frozen=True)

    action_id: str
    work_id: str
    disposition: AdmissionDisposition
    effective: bool
    human_control_mode: HumanControlMode
    requested_autonomy: AgentAutonomyLevel
    required_autonomy: AgentAutonomyLevel
    granted_autonomy: AgentAutonomyLevel | None
    runtime_autonomy_ceiling: AgentAutonomyLevel
    current_world_fidelity: WorldFidelityLevel
    required_world_fidelity: WorldFidelityLevel
    mandate_id: str | None = None
    world_state_ref: str | None = None
    findings: tuple[AutonomyFinding, ...] = ()
    effect_admitted: bool = False
    external_effect_admitted: bool = False
    execution_allowed: bool = False
    authority_transition: bool = False

    @model_validator(mode="after")
    def keep_effect_flags_consistent(self) -> AutonomyAdmissionReport:
        if self.effective != (self.disposition == AdmissionDisposition.EFFECTIVE):
            raise ValueError("effective must match the admission disposition")
        if self.external_effect_admitted and not self.effect_admitted:
            raise ValueError("external effect admission requires effect admission")
        if self.execution_allowed or self.authority_transition:
            raise ValueError(
                "admission reports are evidence, not execution or authority transitions"
            )
        return self


def action_requirements(
    action_class: AgentActionClass,
) -> tuple[WorldFidelityLevel, AgentAutonomyLevel]:
    """Return the minimum world fidelity and autonomy for an action class."""

    return _ACTION_REQUIREMENTS[action_class]


def human_control_mode(level: AgentAutonomyLevel) -> HumanControlMode:
    rank = _AUTONOMY_RANK[level]
    if rank <= _AUTONOMY_RANK[AgentAutonomyLevel.AUT2_DURABLE_LOOP]:
        return HumanControlMode.IN_THE_LOOP
    if level == AgentAutonomyLevel.AUT3_DELEGATED_REVIEW:
        return HumanControlMode.IN_OR_ON_THE_LOOP
    if level == AgentAutonomyLevel.AUT4_PAPER_MANAGER:
        return HumanControlMode.ON_THE_LOOP
    if level == AgentAutonomyLevel.AUT5_REAL_OPERATOR:
        return HumanControlMode.ON_OR_OVER_THE_LOOP
    return HumanControlMode.OVER_THE_LOOP


def evaluate_autonomy_admission(
    *,
    request: AgentActionRequest,
    runtime: AutonomyRuntimeState,
    mandate: AutonomyMandate | None,
) -> AutonomyAdmissionReport:
    """Evaluate a typed Agent action without performing the action."""

    required_world, required_autonomy = action_requirements(request.action_class)
    findings: list[AutonomyFinding] = []

    if request.action_class == AgentActionClass.CHANGE_CAPITAL_CONSTITUTION:
        findings.append(
            AutonomyFinding(
                code=AutonomyFindingCode.CONSTITUTIONAL_CHANGE_REQUIRES_HUMAN,
                detail="capital-constitution changes remain with the Human Principal",
            )
        )
        return _report(
            request=request,
            runtime=runtime,
            mandate=mandate,
            required_world=required_world,
            required_autonomy=required_autonomy,
            disposition=AdmissionDisposition.ESCALATE,
            findings=findings,
        )

    if _AUTONOMY_RANK[request.requested_autonomy] < _AUTONOMY_RANK[required_autonomy]:
        findings.append(
            AutonomyFinding(
                code=AutonomyFindingCode.REQUESTED_AUTONOMY_INSUFFICIENT,
                detail=f"{request.action_class} requires at least {required_autonomy}",
            )
        )
    if _WORLD_RANK[runtime.world_fidelity] < _WORLD_RANK[required_world]:
        findings.append(
            AutonomyFinding(
                code=AutonomyFindingCode.WORLD_FIDELITY_INSUFFICIENT,
                detail=f"{request.action_class} requires at least {required_world}",
            )
        )
    if _AUTONOMY_RANK[request.requested_autonomy] > _AUTONOMY_RANK[
        runtime.runtime_autonomy_ceiling
    ]:
        findings.append(
            AutonomyFinding(
                code=AutonomyFindingCode.AUTONOMY_EXCEEDS_RUNTIME,
                detail=(
                    f"requested {request.requested_autonomy} exceeds runtime ceiling "
                    f"{runtime.runtime_autonomy_ceiling}"
                ),
            )
        )

    hard_codes = {
        AutonomyFindingCode.REQUESTED_AUTONOMY_INSUFFICIENT,
        AutonomyFindingCode.WORLD_FIDELITY_INSUFFICIENT,
        AutonomyFindingCode.AUTONOMY_EXCEEDS_RUNTIME,
    }
    if any(finding.code in hard_codes for finding in findings):
        return _report(
            request=request,
            runtime=runtime,
            mandate=mandate,
            required_world=required_world,
            required_autonomy=required_autonomy,
            disposition=AdmissionDisposition.BLOCKED,
            findings=findings,
        )

    effective_without_mandate = request.action_class in {
        AgentActionClass.OBSERVE_STATE,
        AgentActionClass.GATHER_EVIDENCE,
    }
    if mandate is None:
        if effective_without_mandate:
            return _report(
                request=request,
                runtime=runtime,
                mandate=None,
                required_world=required_world,
                required_autonomy=required_autonomy,
                disposition=AdmissionDisposition.EFFECTIVE,
                findings=[],
            )
        findings.append(
            AutonomyFinding(
                code=AutonomyFindingCode.MANDATE_REQUIRED,
                detail="effective review, decision, and action require an active mandate",
            )
        )
        return _report(
            request=request,
            runtime=runtime,
            mandate=None,
            required_world=required_world,
            required_autonomy=required_autonomy,
            disposition=AdmissionDisposition.CANDIDATE,
            findings=findings,
        )

    _check_mandate(request=request, runtime=runtime, mandate=mandate, findings=findings)
    if findings:
        blocked_codes = {
            AutonomyFindingCode.MANDATE_NOT_ACTIVE,
            AutonomyFindingCode.MANDATE_EXPIRED,
            AutonomyFindingCode.KILL_SWITCH_ENGAGED,
        }
        disposition = (
            AdmissionDisposition.BLOCKED
            if any(finding.code in blocked_codes for finding in findings)
            else AdmissionDisposition.CANDIDATE
        )
        return _report(
            request=request,
            runtime=runtime,
            mandate=mandate,
            required_world=required_world,
            required_autonomy=required_autonomy,
            disposition=disposition,
            findings=findings,
        )

    return _report(
        request=request,
        runtime=runtime,
        mandate=mandate,
        required_world=required_world,
        required_autonomy=required_autonomy,
        disposition=AdmissionDisposition.EFFECTIVE,
        findings=[],
    )


def legacy_autonomy_level(level: str) -> AgentAutonomyLevel:
    """Map the current CapitalMandate L0-L3 vocabulary into AUT0-AUT3."""

    mapping = {
        "L0_read_only": AgentAutonomyLevel.AUT0_CONTEXT_ASSISTANT,
        "L1_candidate_only": AgentAutonomyLevel.AUT1_TOOL_REVIEWER,
        "L2_human_confirmed_apply": AgentAutonomyLevel.AUT2_DURABLE_LOOP,
        "L3_bounded_delegation_candidate": AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
    }
    try:
        return mapping[level]
    except KeyError as exc:
        raise ValueError(f"unknown legacy autonomy level: {level!r}") from exc


def write_autonomy_admission_report(
    report: AutonomyAdmissionReport,
    *,
    receipt_root: str | Path,
) -> str:
    """Persist admission evidence and return a receipt-root-relative reference."""

    from finharness.statecore.receipt_io import atomic_write_json, resolve_under

    fingerprint = sha256(report.action_id.encode("utf-8")).hexdigest()[:20]
    relative = Path("autonomy-admissions") / f"admission_{fingerprint}.json"
    target = resolve_under(receipt_root, relative)
    atomic_write_json(target, report.model_dump(mode="json"))
    return relative.as_posix()


def _check_mandate(
    *,
    request: AgentActionRequest,
    runtime: AutonomyRuntimeState,
    mandate: AutonomyMandate,
    findings: list[AutonomyFinding],
) -> None:
    if mandate.status != "active":
        findings.append(
            AutonomyFinding(
                code=AutonomyFindingCode.MANDATE_NOT_ACTIVE,
                detail=f"mandate status is {mandate.status}",
            )
        )
    if mandate.expires_at_utc and _parse_utc(runtime.now_utc) >= _parse_utc(
        mandate.expires_at_utc
    ):
        findings.append(
            AutonomyFinding(
                code=AutonomyFindingCode.MANDATE_EXPIRED,
                detail="mandate has expired",
            )
        )
    if mandate.kill_switch_engaged:
        findings.append(
            AutonomyFinding(
                code=AutonomyFindingCode.KILL_SWITCH_ENGAGED,
                detail="mandate kill switch is engaged",
            )
        )
    if mandate.agent_id != request.agent_id:
        findings.append(
            AutonomyFinding(
                code=AutonomyFindingCode.ACTION_OUTSIDE_MANDATE,
                detail="request agent does not match mandate agent",
            )
        )
    if _AUTONOMY_RANK[request.requested_autonomy] > _AUTONOMY_RANK[
        mandate.granted_autonomy
    ]:
        findings.append(
            AutonomyFinding(
                code=AutonomyFindingCode.AUTONOMY_EXCEEDS_MANDATE,
                detail=(
                    f"requested {request.requested_autonomy} exceeds mandate grant "
                    f"{mandate.granted_autonomy}"
                ),
            )
        )
    if request.action_class not in mandate.allowed_action_classes:
        findings.append(
            AutonomyFinding(
                code=AutonomyFindingCode.ACTION_OUTSIDE_MANDATE,
                detail=f"{request.action_class} is not allowed by the mandate",
            )
        )
    requested_financial_action = request.target_scope.get("action_type")
    if (
        requested_financial_action
        and mandate.allowed_financial_action_types
        and requested_financial_action not in mandate.allowed_financial_action_types
    ):
        findings.append(
            AutonomyFinding(
                code=AutonomyFindingCode.FINANCIAL_ACTION_OUTSIDE_MANDATE,
                detail=(
                    f"financial action {requested_financial_action!r} is not allowed "
                    "by the mandate"
                ),
            )
        )
    requested_asset_class = request.target_scope.get("asset_class")
    if (
        requested_asset_class
        and mandate.allowed_asset_classes
        and requested_asset_class not in mandate.allowed_asset_classes
    ):
        findings.append(
            AutonomyFinding(
                code=AutonomyFindingCode.ASSET_CLASS_OUTSIDE_MANDATE,
                detail=f"asset class {requested_asset_class!r} is not allowed by the mandate",
            )
        )
    if (
        request.tool_name
        and mandate.allowed_tools
        and request.tool_name not in mandate.allowed_tools
    ):
        findings.append(
            AutonomyFinding(
                code=AutonomyFindingCode.TOOL_OUTSIDE_MANDATE,
                detail=f"tool {request.tool_name!r} is not allowed by the mandate",
            )
        )


def _report(
    *,
    request: AgentActionRequest,
    runtime: AutonomyRuntimeState,
    mandate: AutonomyMandate | None,
    required_world: WorldFidelityLevel,
    required_autonomy: AgentAutonomyLevel,
    disposition: AdmissionDisposition,
    findings: list[AutonomyFinding],
) -> AutonomyAdmissionReport:
    effective = disposition == AdmissionDisposition.EFFECTIVE
    effect_admitted = effective and request.action_class in {
        AgentActionClass.TAKE_PAPER_ACTION,
        AgentActionClass.TAKE_REAL_ACTION,
    }
    return AutonomyAdmissionReport(
        action_id=request.action_id,
        work_id=request.work_id,
        disposition=disposition,
        effective=effective,
        human_control_mode=human_control_mode(request.requested_autonomy),
        requested_autonomy=request.requested_autonomy,
        required_autonomy=required_autonomy,
        granted_autonomy=mandate.granted_autonomy if mandate else None,
        runtime_autonomy_ceiling=runtime.runtime_autonomy_ceiling,
        current_world_fidelity=runtime.world_fidelity,
        required_world_fidelity=required_world,
        mandate_id=mandate.mandate_id if mandate else None,
        world_state_ref=runtime.world_state_ref,
        findings=tuple(findings),
        effect_admitted=effect_admitted,
        external_effect_admitted=(
            effect_admitted and request.action_class == AgentActionClass.TAKE_REAL_ACTION
        ),
        execution_allowed=False,
        authority_transition=False,
    )


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("autonomy timestamps must be timezone-aware")
    return parsed.astimezone(UTC)
