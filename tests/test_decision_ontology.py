from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from finharness.decision_ontology import (
    CASE_VERSION_TRIGGER_MATRIX,
    CaseVersionTrigger,
    DecisionCaseBasis,
    DecisionCaseVersion,
    DecisionLifecycle,
    ScenarioVersionRef,
    canonical_basis_hash,
    lifecycle_transition_allowed,
    new_decision_case_version,
    requires_new_case_version,
)


def basis(**changes: object) -> DecisionCaseBasis:
    values: dict[str, object] = {
        "decision_problem_id": "problem_rebalance",
        "proposal_version_id": "proposal_version_3",
        "evidence_set_version_id": "evidence_set_version_8",
        "capital_state_version_id": "capital_state_version_12",
        "policy_version_id": "policy_version_2",
        "scenario_versions": (
            ScenarioVersionRef(
                scenario_id="scenario_drawdown",
                scenario_version_id="scenario_version_5",
            ),
        ),
    }
    values.update(changes)
    return DecisionCaseBasis.model_validate(values)


@pytest.mark.parametrize(
    "forbidden",
    ["review_event_ids", "attestation_ids", "decision_record_id", "review_state_version_id"],
)
def test_review_and_decision_state_cannot_enter_case_basis(forbidden: str) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        basis(**{forbidden: "forbidden"})


@pytest.mark.parametrize(
    "trigger",
    [
        CaseVersionTrigger.PROPOSAL_REVISION,
        CaseVersionTrigger.EVIDENCE_ADMISSION,
        CaseVersionTrigger.EVIDENCE_WITHDRAWAL,
        CaseVersionTrigger.ADOPTED_CAPITAL_STATE_VERSION,
        CaseVersionTrigger.EFFECTIVE_POLICY_VERSION,
        CaseVersionTrigger.SCENARIO_VERSION,
    ],
)
def test_basis_changes_create_a_case_version(trigger: CaseVersionTrigger) -> None:
    assert requires_new_case_version(trigger) is True


@pytest.mark.parametrize(
    "trigger",
    [
        CaseVersionTrigger.REVIEW_EVENT,
        CaseVersionTrigger.ATTESTATION,
        CaseVersionTrigger.DECISION_RECORD,
        CaseVersionTrigger.REVIEW_STATE,
    ],
)
def test_review_and_record_changes_do_not_create_case_version(
    trigger: CaseVersionTrigger,
) -> None:
    assert requires_new_case_version(trigger) is False


def test_trigger_matrix_is_total() -> None:
    assert set(CASE_VERSION_TRIGGER_MATRIX) == set(CaseVersionTrigger)


def test_reverting_to_old_content_keeps_hash_but_creates_new_identity() -> None:
    original = new_decision_case_version(decision_case_id="case_1", basis=basis())
    changed = new_decision_case_version(
        decision_case_id="case_1",
        basis=basis(proposal_version_id="proposal_version_4"),
    )
    reverted = new_decision_case_version(decision_case_id="case_1", basis=basis())

    assert original.basis_hash != changed.basis_hash
    assert original.basis_hash == reverted.basis_hash
    assert original.decision_case_version_id != reverted.decision_case_version_id
    assert original.decision_case_version_id.int < reverted.decision_case_version_id.int


def test_content_hash_is_integrity_not_version_identity() -> None:
    first = new_decision_case_version(decision_case_id="case_1", basis=basis())
    second = new_decision_case_version(decision_case_id="case_1", basis=basis())

    assert first.basis_hash == second.basis_hash == canonical_basis_hash(basis())
    assert first.decision_case_version_id != second.decision_case_version_id


def test_non_uuid7_case_version_identity_is_rejected() -> None:
    with pytest.raises(ValidationError, match="UUIDv7"):
        DecisionCaseVersion(
            decision_case_id="case_1",
            decision_case_version_id=uuid4(),
            basis=basis(),
            basis_hash=canonical_basis_hash(basis()),
        )


def test_lifecycle_is_explicit_and_decision_cannot_skip_review() -> None:
    assert lifecycle_transition_allowed(
        DecisionLifecycle.REVIEW_READY, DecisionLifecycle.DECIDED
    )
    assert not lifecycle_transition_allowed(
        DecisionLifecycle.DRAFT, DecisionLifecycle.DECIDED
    )
