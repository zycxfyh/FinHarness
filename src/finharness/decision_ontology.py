"""Canonical Decision ontology and version-trigger contract.

UUIDv7 mechanics are delegated to ``uuid6``. FinHarness owns only the domain
boundaries, canonical basis hash, lifecycle, and trigger matrix.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from uuid6 import uuid7


class DecisionLifecycle(StrEnum):
    DRAFT = "draft"
    EVIDENCE_OPEN = "evidence_open"
    REVIEW_READY = "review_ready"
    DECIDED = "decided"
    SUPERSEDED = "superseded"


ALLOWED_LIFECYCLE_TRANSITIONS: frozenset[tuple[DecisionLifecycle, DecisionLifecycle]] = (
    frozenset(
        {
            (DecisionLifecycle.DRAFT, DecisionLifecycle.EVIDENCE_OPEN),
            (DecisionLifecycle.EVIDENCE_OPEN, DecisionLifecycle.REVIEW_READY),
            (DecisionLifecycle.REVIEW_READY, DecisionLifecycle.EVIDENCE_OPEN),
            (DecisionLifecycle.REVIEW_READY, DecisionLifecycle.DECIDED),
            (DecisionLifecycle.DECIDED, DecisionLifecycle.SUPERSEDED),
        }
    )
)


class CaseVersionTrigger(StrEnum):
    PROPOSAL_REVISION = "proposal_revision"
    EVIDENCE_ADMISSION = "evidence_admission"
    EVIDENCE_WITHDRAWAL = "evidence_withdrawal"
    ADOPTED_CAPITAL_STATE_VERSION = "adopted_capital_state_version"
    EFFECTIVE_POLICY_VERSION = "effective_policy_version"
    SCENARIO_VERSION = "scenario_version"
    REVIEW_EVENT = "review_event"
    ATTESTATION = "attestation"
    DECISION_RECORD = "decision_record"
    REVIEW_STATE = "review_state"


CASE_VERSION_TRIGGER_MATRIX: dict[CaseVersionTrigger, bool] = {
    CaseVersionTrigger.PROPOSAL_REVISION: True,
    CaseVersionTrigger.EVIDENCE_ADMISSION: True,
    CaseVersionTrigger.EVIDENCE_WITHDRAWAL: True,
    CaseVersionTrigger.ADOPTED_CAPITAL_STATE_VERSION: True,
    CaseVersionTrigger.EFFECTIVE_POLICY_VERSION: True,
    CaseVersionTrigger.SCENARIO_VERSION: False,
    CaseVersionTrigger.REVIEW_EVENT: False,
    CaseVersionTrigger.ATTESTATION: False,
    CaseVersionTrigger.DECISION_RECORD: False,
    CaseVersionTrigger.REVIEW_STATE: False,
}


class FrozenContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DecisionProblem(FrozenContract):
    """Stable logical question; distinct from any Proposal revision."""

    decision_problem_id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    owner_ref: str = Field(min_length=1)


class ScenarioVersionRef(FrozenContract):
    scenario_id: str = Field(min_length=1)
    scenario_version_id: UUID
    decision_case_version_id: UUID

    @field_validator("scenario_version_id", "decision_case_version_id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("scenario references require RFC 9562 UUIDv7 identities")
        return value


class DecisionCaseBasis(FrozenContract):
    """Only evidence that can change the question's decision basis."""

    decision_problem_id: str = Field(min_length=1)
    proposal_version_id: str = Field(min_length=1)
    evidence_set_version_id: str = Field(min_length=1)
    capital_state_version_id: str = Field(min_length=1)
    policy_version_id: str = Field(min_length=1)


class DecisionCaseVersion(FrozenContract):
    decision_case_id: str = Field(min_length=1)
    decision_case_version_id: UUID
    basis: DecisionCaseBasis
    basis_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("decision_case_version_id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("decision_case_version_id must be an RFC 9562 UUIDv7")
        return value


class ScenarioVersion(FrozenContract):
    """Immutable Scenario inputs bound to one pre-existing CaseVersion."""

    scenario_id: str = Field(min_length=1)
    scenario_version_id: UUID
    decision_case_version_id: UUID
    verified_capital_projection_ref: str = Field(min_length=1)
    assumption_set_version_id: str = Field(min_length=1)
    calculator_version_id: str = Field(min_length=1)
    evidence_bundle_version_id: str | None = Field(default=None, min_length=1)

    @field_validator("scenario_version_id", "decision_case_version_id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("ScenarioVersion identities must be RFC 9562 UUIDv7")
        return value

    def reference(self) -> ScenarioVersionRef:
        return ScenarioVersionRef(
            scenario_id=self.scenario_id,
            scenario_version_id=self.scenario_version_id,
            decision_case_version_id=self.decision_case_version_id,
        )


class ReviewStateVersion(FrozenContract):
    review_state_version_id: UUID
    decision_case_version_id: UUID
    lifecycle: DecisionLifecycle
    review_event_ids: tuple[str, ...] = ()
    attestation_ids: tuple[str, ...] = ()


class DecisionRecord(FrozenContract):
    decision_record_id: str = Field(min_length=1)
    decision_case_version_id: UUID
    decision: str = Field(min_length=1)
    decided_by: str = Field(min_length=1)
    considered_scenarios: tuple[ScenarioVersionRef, ...] = ()
    selected_scenario: ScenarioVersionRef | None = None

    @field_validator("decision_case_version_id")
    @classmethod
    def require_uuid7(cls, value: UUID) -> UUID:
        if value.version != 7:
            raise ValueError("decision_case_version_id must be an RFC 9562 UUIDv7")
        return value

    @model_validator(mode="after")
    def validate_scenario_citations(self) -> DecisionRecord:
        scenario_version_ids = [
            reference.scenario_version_id for reference in self.considered_scenarios
        ]
        if len(scenario_version_ids) != len(set(scenario_version_ids)):
            raise ValueError("considered ScenarioVersion citations must be unique")
        if any(
            reference.decision_case_version_id != self.decision_case_version_id
            for reference in self.considered_scenarios
        ):
            raise ValueError(
                "considered ScenarioVersion citations must evaluate the DecisionCaseVersion"
            )
        if self.selected_scenario is not None:
            if (
                self.selected_scenario.decision_case_version_id
                != self.decision_case_version_id
            ):
                raise ValueError(
                    "selected ScenarioVersion must evaluate the DecisionCaseVersion"
                )
            if self.selected_scenario not in self.considered_scenarios:
                raise ValueError(
                    "selected ScenarioVersion must be one of the considered Scenarios"
                )
        return self


class DecisionValidity(FrozenContract):
    decision_record_id: str = Field(min_length=1)
    evidence_valid: bool
    policy_valid: bool
    authority_valid: bool
    superseded_by_case_version_id: UUID | None = None


def canonical_basis_hash(basis: DecisionCaseBasis) -> str:
    payload = json.dumps(
        basis.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def new_decision_case_version(
    *, decision_case_id: str, basis: DecisionCaseBasis
) -> DecisionCaseVersion:
    return DecisionCaseVersion(
        decision_case_id=decision_case_id,
        decision_case_version_id=uuid7(),
        basis=basis,
        basis_hash=canonical_basis_hash(basis),
    )


def new_scenario_version(
    *,
    scenario_id: str,
    decision_case_version_id: UUID,
    verified_capital_projection_ref: str,
    assumption_set_version_id: str,
    calculator_version_id: str,
    evidence_bundle_version_id: str | None = None,
) -> ScenarioVersion:
    return ScenarioVersion(
        scenario_id=scenario_id,
        scenario_version_id=uuid7(),
        decision_case_version_id=decision_case_version_id,
        verified_capital_projection_ref=verified_capital_projection_ref,
        assumption_set_version_id=assumption_set_version_id,
        calculator_version_id=calculator_version_id,
        evidence_bundle_version_id=evidence_bundle_version_id,
    )


def requires_new_case_version(trigger: CaseVersionTrigger) -> bool:
    return CASE_VERSION_TRIGGER_MATRIX[trigger]


def lifecycle_transition_allowed(
    current: DecisionLifecycle, target: DecisionLifecycle
) -> bool:
    return (current, target) in ALLOWED_LIFECYCLE_TRANSITIONS
