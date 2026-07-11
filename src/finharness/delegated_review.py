"""Version-bound delegated decision review foundation for AUT3.

The module deliberately adds no execution surface and no parallel decision
database.  A :class:`DecisionCase` is a deterministic projection over the
current proposal receipt revision plus existing review state.  Scenario and
delegated-review artifacts are immutable, receipt-backed evidence bound to that
exact proposal version.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import Engine
from sqlmodel import Session, select

from finharness.autonomy_control import (
    AdmissionDisposition,
    AgentActionClass,
    AgentActionRequest,
    AgentAutonomyLevel,
    AutonomyAdmissionReport,
    AutonomyMandate,
    AutonomyRuntimeState,
    WorldFidelityLevel,
    evaluate_autonomy_admission,
)
from finharness.statecore.decision_scaffold import REQUIRED_FIELDS
from finharness.statecore.models import Attestation, Proposal, ReviewEvent
from finharness.statecore.proposal_revisions import RevisionRecord, walk_proposal_revisions
from finharness.statecore.receipt_io import atomic_write_json, resolve_under

PlanningDecision = Literal["accept_for_planning", "reject", "defer"]
ScenarioKind = Literal["do_nothing", "future_cashflow_dilution", "operator_sized_reduction"]
ReviewDisposition = Literal["effective", "candidate", "escalated", "blocked"]


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


class ProposalVersionRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    proposal_id: str
    proposal_version_id: str
    proposal_receipt_ref: str
    proposal_content_hash: str
    created_at_utc: str


class DecisionCase(BaseModel):
    """Version-addressed review projection; never a new source of write truth."""

    model_config = ConfigDict(frozen=True)

    decision_case_id: str
    case_version_id: str
    proposal_version: ProposalVersionRef
    kind: str
    claim: str
    evidence: dict[str, Any]
    assumptions: dict[str, Any]
    limitations: dict[str, Any]
    decision_scaffold: dict[str, Any]
    source_refs: tuple[str, ...]
    review_event_refs: tuple[str, ...]
    legacy_unbound_decision_refs: tuple[str, ...]
    readiness: Literal["ready_for_scenario", "needs_evidence"]
    data_gaps: tuple[str, ...]
    execution_allowed: bool = False
    authority_transition: bool = False

    @model_validator(mode="after")
    def remain_a_projection(self) -> DecisionCase:
        if self.execution_allowed or self.authority_transition:
            raise ValueError("DecisionCase is review projection, not effect authority")
        return self


class Scenario(BaseModel):
    """Immutable scenario evidence bound to one DecisionCase version."""

    model_config = ConfigDict(frozen=True)

    scenario_id: str = Field(default_factory=lambda: f"scenario_{uuid4().hex}")
    scenario_version_id: str
    decision_case_id: str
    decision_case_version_id: str
    proposal_version_id: str
    kind: ScenarioKind
    assumptions: dict[str, Any]
    metrics: dict[str, Any]
    uncertainty: float = Field(ge=0.0, le=1.0)
    notional_implication: float = Field(ge=0.0)
    data_gaps: tuple[str, ...] = ()
    source_refs: tuple[str, ...]
    calculation_version: str
    created_at_utc: str
    execution_allowed: bool = False

    @field_validator("calculation_version")
    @classmethod
    def require_calculation_version(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("scenario requires a calculation version")
        return value

    @field_validator("execution_allowed")
    @classmethod
    def reject_execution(cls, value: bool) -> bool:
        if value:
            raise ValueError("Scenario never carries execution authority")
        return False


class DelegatedReviewRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_id: str = Field(default_factory=lambda: f"delegated_review_{uuid4().hex}")
    work_id: str
    agent_id: str
    decision_case_id: str
    decision_case_version_id: str
    proposal_version_id: str
    scenario_ids: tuple[str, ...]
    selected_scenario_id: str
    decision: PlanningDecision
    rationale: str
    uncertainty: float = Field(ge=0.0, le=1.0)
    notional_implication: float = Field(ge=0.0)
    next_review_condition: str | None = None
    source_refs: tuple[str, ...] = ()

    @field_validator("work_id", "agent_id", "rationale")
    @classmethod
    def require_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("delegated review context must be non-blank")
        return value

    @model_validator(mode="after")
    def require_selected_and_defer_condition(self) -> DelegatedReviewRequest:
        if self.selected_scenario_id not in self.scenario_ids:
            raise ValueError("selected scenario must be in scenario_ids")
        if self.decision == "defer" and not (self.next_review_condition or "").strip():
            raise ValueError("defer requires a next review condition")
        return self


class DelegatedReviewResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    review_id: str
    decision_case_id: str
    decision_case_version_id: str
    proposal_version_id: str
    selected_scenario_id: str
    proposed_decision: PlanningDecision
    disposition: ReviewDisposition
    effective_planning_decision: bool
    escalation_reasons: tuple[str, ...]
    admission: AutonomyAdmissionReport
    source_refs: tuple[str, ...]
    created_at_utc: str
    execution_allowed: bool = False
    authority_transition: bool = False

    @model_validator(mode="after")
    def keep_authority_closed(self) -> DelegatedReviewResult:
        if self.execution_allowed or self.authority_transition:
            raise ValueError("delegated review cannot authorize or execute")
        if self.effective_planning_decision != (self.disposition == "effective"):
            raise ValueError("effective planning flag must match disposition")
        return self


def _latest_revision(proposal: Proposal) -> RevisionRecord:
    walk = walk_proposal_revisions(proposal.proposal_id, proposal.receipt_ref)
    if not walk.ok or not walk.revisions:
        detail = walk.anomalies[0].detail if walk.anomalies else "empty revision chain"
        raise ValueError(f"proposal version is not trustworthy: {detail}")
    latest = walk.revisions[0]
    if not latest.content_hash:
        raise ValueError("proposal version lacks a content hash")
    return latest


def build_decision_case(*, proposal_id: str, engine: Engine) -> DecisionCase:
    """Project an exact proposal version and its existing review state."""
    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
        if proposal is None:
            raise KeyError(proposal_id)
        attestations = tuple(
            session.exec(select(Attestation).where(Attestation.proposal_id == proposal_id)).all()
        )
        events = tuple(
            session.exec(select(ReviewEvent).where(ReviewEvent.proposal_id == proposal_id)).all()
        )
    revision = _latest_revision(proposal)
    proposal_version_id = f"pv_{revision.content_hash}"
    version = ProposalVersionRef(
        proposal_id=proposal_id,
        proposal_version_id=proposal_version_id,
        proposal_receipt_ref=revision.receipt_ref,
        proposal_content_hash=revision.content_hash,
        created_at_utc=revision.created_at_utc,
    )
    scaffold = revision.proposal.get("decision_scaffold") or {}
    gaps = tuple(f"decision_scaffold.{key}" for key in REQUIRED_FIELDS if not scaffold.get(key))
    review_refs = tuple(sorted(f"review_event:{event.review_event_id}" for event in events))
    legacy_refs = tuple(sorted(f"attestation:{item.attestation_id}" for item in attestations))
    case_core = {
        "proposal_version_id": proposal_version_id,
        "review_event_refs": review_refs,
        "legacy_unbound_decision_refs": legacy_refs,
    }
    return DecisionCase(
        decision_case_id=f"decision_case_{proposal_id}",
        case_version_id=f"dcv_{_canonical_hash(case_core)}",
        proposal_version=version,
        kind=str(revision.proposal.get("kind") or ""),
        claim=str(revision.proposal.get("claim") or ""),
        evidence=dict(revision.proposal.get("evidence") or {}),
        assumptions=dict(revision.proposal.get("assumptions") or {}),
        limitations=dict(revision.proposal.get("limitations") or {}),
        decision_scaffold=dict(scaffold),
        source_refs=tuple(revision.proposal.get("source_refs") or ()),
        review_event_refs=review_refs,
        legacy_unbound_decision_refs=legacy_refs,
        readiness="ready_for_scenario" if not gaps else "needs_evidence",
        data_gaps=gaps,
    )


def create_scenario(
    *,
    decision_case: DecisionCase,
    kind: ScenarioKind,
    assumptions: dict[str, Any],
    metrics: dict[str, Any],
    uncertainty: float,
    notional_implication: float,
    calculation_version: str,
    source_refs: tuple[str, ...] = (),
    data_gaps: tuple[str, ...] = (),
    created_at_utc: str | None = None,
) -> Scenario:
    """Create immutable in-memory scenario evidence; use ``write_scenario`` to persist."""
    created_at = created_at_utc or _now_utc()
    core = {
        "decision_case_version_id": decision_case.case_version_id,
        "proposal_version_id": decision_case.proposal_version.proposal_version_id,
        "kind": kind,
        "assumptions": assumptions,
        "metrics": metrics,
        "uncertainty": uncertainty,
        "notional_implication": notional_implication,
        "data_gaps": data_gaps,
        "source_refs": source_refs,
        "calculation_version": calculation_version,
    }
    scenario_version_id = f"sv_{_canonical_hash(core)}"
    return Scenario(
        scenario_id=f"scenario_{scenario_version_id[3:27]}",
        scenario_version_id=scenario_version_id,
        decision_case_id=decision_case.decision_case_id,
        decision_case_version_id=decision_case.case_version_id,
        proposal_version_id=decision_case.proposal_version.proposal_version_id,
        kind=kind,
        assumptions=assumptions,
        metrics=metrics,
        uncertainty=uncertainty,
        notional_implication=notional_implication,
        data_gaps=data_gaps,
        source_refs=source_refs,
        calculation_version=calculation_version,
        created_at_utc=created_at,
    )


def write_scenario(scenario: Scenario, *, receipt_root: str | Path) -> str:
    relative = Path("decision-scenarios") / f"{scenario.scenario_version_id}.json"
    atomic_write_json(resolve_under(receipt_root, relative), scenario.model_dump(mode="json"))
    return relative.as_posix()


def evaluate_delegated_review(
    *,
    request: DelegatedReviewRequest,
    decision_case: DecisionCase,
    scenarios: tuple[Scenario, ...],
    mandate: AutonomyMandate | None,
    runtime: AutonomyRuntimeState,
) -> DelegatedReviewResult:
    """Evaluate an AUT3 planning decision without producing an external effect."""
    action = AgentActionRequest(
        work_id=request.work_id,
        agent_id=request.agent_id,
        objective=f"Review {request.decision_case_id}",
        action_class=AgentActionClass.MAKE_PLANNING_DECISION,
        requested_autonomy=AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
        target_scope={"decision_case_id": request.decision_case_id},
        source_refs=request.source_refs,
    )
    admission = evaluate_autonomy_admission(request=action, runtime=runtime, mandate=mandate)
    reasons = _delegated_review_reasons(
        request=request,
        decision_case=decision_case,
        scenarios=scenarios,
        mandate=mandate,
        runtime=runtime,
    )

    if admission.disposition == AdmissionDisposition.BLOCKED:
        disposition: ReviewDisposition = "blocked"
    elif admission.disposition != AdmissionDisposition.EFFECTIVE or reasons:
        disposition = "escalated" if reasons else "candidate"
    else:
        disposition = "effective"
    return DelegatedReviewResult(
        review_id=request.review_id,
        decision_case_id=decision_case.decision_case_id,
        decision_case_version_id=decision_case.case_version_id,
        proposal_version_id=decision_case.proposal_version.proposal_version_id,
        selected_scenario_id=request.selected_scenario_id,
        proposed_decision=request.decision,
        disposition=disposition,
        effective_planning_decision=disposition == "effective",
        escalation_reasons=tuple(reasons),
        admission=admission,
        source_refs=request.source_refs,
        created_at_utc=runtime.now_utc,
    )


def _delegated_review_reasons(
    *,
    request: DelegatedReviewRequest,
    decision_case: DecisionCase,
    scenarios: tuple[Scenario, ...],
    mandate: AutonomyMandate | None,
    runtime: AutonomyRuntimeState,
) -> list[str]:
    reasons: list[str] = []
    if request.decision_case_id != decision_case.decision_case_id:
        reasons.append("decision_case_mismatch")
    if request.decision_case_version_id != decision_case.case_version_id:
        reasons.append("stale_decision_case_version")
    if request.proposal_version_id != decision_case.proposal_version.proposal_version_id:
        reasons.append("stale_proposal_version")
    by_id = {scenario.scenario_id: scenario for scenario in scenarios}
    if set(request.scenario_ids) - set(by_id):
        reasons.append("scenario_set_incomplete")
    selected = by_id.get(request.selected_scenario_id)
    reasons.extend(
        _scenario_binding_reasons(request=request, decision_case=decision_case, selected=selected)
    )
    if decision_case.readiness != "ready_for_scenario":
        reasons.append("decision_case_not_ready")
    if runtime.world_state_ref != decision_case.case_version_id:
        reasons.append("runtime_world_state_mismatch")
    constraints = mandate.constraints if mandate is not None else {}
    if request.decision not in tuple(constraints.get("allowed_decisions", ())):
        reasons.append("decision_kind_outside_mandate")
    effective_uncertainty = selected.uncertainty if selected is not None else request.uncertainty
    effective_notional = (
        selected.notional_implication if selected is not None else request.notional_implication
    )
    if effective_uncertainty > float(constraints.get("max_uncertainty", -1.0)):
        reasons.append("uncertainty_exceeds_mandate")
    if effective_notional > float(constraints.get("max_notional_implication", -1.0)):
        reasons.append("notional_exceeds_mandate")

    return reasons


def _scenario_binding_reasons(
    *,
    request: DelegatedReviewRequest,
    decision_case: DecisionCase,
    selected: Scenario | None,
) -> list[str]:
    if selected is None:
        return ["selected_scenario_missing"]
    reasons: list[str] = []
    if selected.decision_case_version_id != decision_case.case_version_id:
        reasons.append("scenario_case_version_mismatch")
    if selected.proposal_version_id != decision_case.proposal_version.proposal_version_id:
        reasons.append("scenario_proposal_version_mismatch")
    if selected.data_gaps:
        reasons.append("scenario_has_data_gaps")
    if (
        request.uncertainty != selected.uncertainty
        or request.notional_implication != selected.notional_implication
    ):
        reasons.append("scenario_limits_mismatch")
    return reasons


def write_delegated_review_result(
    result: DelegatedReviewResult, *, receipt_root: str | Path
) -> str:
    relative = Path("delegated-reviews") / f"{result.review_id}.json"
    atomic_write_json(resolve_under(receipt_root, relative), result.model_dump(mode="json"))
    return relative.as_posix()


def load_delegated_review_result(
    review_id: str, *, receipt_root: str | Path
) -> DelegatedReviewResult:
    relative = Path("delegated-reviews") / f"{review_id}.json"
    payload = json.loads(resolve_under(receipt_root, relative).read_text(encoding="utf-8"))
    return DelegatedReviewResult.model_validate(payload)


def aut3_runtime(*, world_state_ref: str, now_utc: str | None = None) -> AutonomyRuntimeState:
    """Explicit AUT3/W2 runtime constructor; callers cannot infer it from AUT2 state."""
    return AutonomyRuntimeState(
        world_fidelity=WorldFidelityLevel.W2_SCENARIO_WORLD,
        runtime_autonomy_ceiling=AgentAutonomyLevel.AUT3_DELEGATED_REVIEW,
        world_state_ref=world_state_ref,
        now_utc=now_utc or _now_utc(),
    )
