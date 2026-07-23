# finharness-test-runner: pytest
from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from finharness.decision_ontology import (
    CASE_VERSION_TRIGGER_MATRIX,
    CaseVersionTrigger,
    DecisionCaseBasis,
    DecisionCaseVersion,
    DecisionLifecycle,
    DecisionRecord,
    ScenarioVersion,
    canonical_basis_hash,
    lifecycle_transition_allowed,
    new_decision_case_version,
    new_scenario_version,
    requires_new_case_version,
)


def basis(**changes: object) -> DecisionCaseBasis:
    values: dict[str, object] = {
        "decision_problem_id": "problem_rebalance",
        "proposal_version_id": "proposal_version_3",
        "evidence_set_version_id": "evidence_set_version_8",
        "capital_state_version_id": "capital_state_version_12",
        "policy_version_id": "policy_version_2",
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
    "forbidden",
    ["scenario_versions", "scenario_version_id", "selected_scenario"],
)
def test_scenario_identity_cannot_enter_case_basis(forbidden: str) -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        basis(**{forbidden: "forbidden"})


def test_case_basis_fields_match_the_canonical_pre_comparison_inputs() -> None:
    assert tuple(DecisionCaseBasis.model_fields) == (
        "decision_problem_id",
        "proposal_version_id",
        "evidence_set_version_id",
        "capital_state_version_id",
        "policy_version_id",
    )


def test_scenario_and_decision_citation_fields_are_exact() -> None:
    assert tuple(ScenarioVersion.model_fields) == (
        "scenario_id",
        "scenario_version_id",
        "decision_case_version_id",
        "verified_capital_projection_ref",
        "capital_world_id",
        "capital_world_basis_digest",
        "capital_world_status",
        "assumption_set_version_id",
        "calculator_version_id",
        "evidence_bundle_version_id",
    )
    assert tuple(DecisionRecord.model_fields) == (
        "decision_record_id",
        "decision_case_version_id",
        "decision",
        "decided_by",
        "considered_scenarios",
        "selected_scenario",
    )


@pytest.mark.parametrize(
    ("contract", "field"),
    [
        (ScenarioVersion, "case_basis"),
        (ScenarioVersion, "scenario_versions"),
        (DecisionRecord, "scenario_version_id"),
        (DecisionRecord, "selected_scenario_version_id"),
    ],
)
def test_parallel_identity_fields_are_rejected(
    contract: type[ScenarioVersion] | type[DecisionRecord],
    field: str,
) -> None:
    case = new_decision_case_version(decision_case_id="case_1", basis=basis())
    scenario = scenario_version(
        decision_case_version_id=case.decision_case_version_id
    )
    values = (
        scenario.model_dump()
        if contract is ScenarioVersion
        else DecisionRecord(
            decision_record_id="decision_1",
            decision_case_version_id=case.decision_case_version_id,
            decision="defer",
            decided_by="operator:alice",
        ).model_dump()
    )
    values[field] = "parallel"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        contract.model_validate(values)


@pytest.mark.parametrize(
    "trigger",
    [
        CaseVersionTrigger.PROPOSAL_REVISION,
        CaseVersionTrigger.EVIDENCE_ADMISSION,
        CaseVersionTrigger.EVIDENCE_WITHDRAWAL,
        CaseVersionTrigger.ADOPTED_CAPITAL_STATE_VERSION,
        CaseVersionTrigger.EFFECTIVE_POLICY_VERSION,
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
        CaseVersionTrigger.SCENARIO_VERSION,
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


def scenario_version(
    *,
    decision_case_version_id: UUID,
    scenario_version_id: UUID | None = None,
) -> ScenarioVersion:
    created = new_scenario_version(
        scenario_id="scenario_drawdown",
        decision_case_version_id=decision_case_version_id,
        verified_capital_projection_ref="projection:verified:12",
        capital_world_id="capital_world_0123456789abcdef01234567",
        capital_world_basis_digest="0" * 64,
        capital_world_status="admitted",
        assumption_set_version_id="assumptions:4",
        calculator_version_id="calculator:2",
        evidence_bundle_version_id="bundle:7",
    )
    if scenario_version_id is None:
        return created
    return created.model_copy(update={"scenario_version_id": scenario_version_id})


def test_scenario_version_requires_one_exact_case_version() -> None:
    case = new_decision_case_version(decision_case_id="case_1", basis=basis())
    scenario = scenario_version(
        decision_case_version_id=case.decision_case_version_id
    )

    assert scenario.decision_case_version_id == case.decision_case_version_id
    assert scenario.reference().decision_case_version_id == case.decision_case_version_id


@pytest.mark.parametrize("field", ["scenario_version_id", "decision_case_version_id"])
def test_scenario_version_rejects_non_uuid7_identity(field: str) -> None:
    case = new_decision_case_version(decision_case_id="case_1", basis=basis())
    values = scenario_version(
        decision_case_version_id=case.decision_case_version_id
    ).model_dump()
    values[field] = uuid4()

    with pytest.raises(ValidationError, match="UUIDv7"):
        ScenarioVersion.model_validate(values)


def test_scenario_recalculation_does_not_change_case_identity_or_hash() -> None:
    case = new_decision_case_version(decision_case_id="case_1", basis=basis())
    first = scenario_version(decision_case_version_id=case.decision_case_version_id)
    recalculated = scenario_version(
        decision_case_version_id=case.decision_case_version_id
    )

    assert first.scenario_version_id != recalculated.scenario_version_id
    assert first.decision_case_version_id == recalculated.decision_case_version_id
    assert case.basis_hash == canonical_basis_hash(basis())
    assert requires_new_case_version(CaseVersionTrigger.SCENARIO_VERSION) is False


def test_decision_record_cites_considered_and_selected_scenarios() -> None:
    case = new_decision_case_version(decision_case_id="case_1", basis=basis())
    first = scenario_version(decision_case_version_id=case.decision_case_version_id)
    second = scenario_version(decision_case_version_id=case.decision_case_version_id)

    record = DecisionRecord(
        decision_record_id="decision_1",
        decision_case_version_id=case.decision_case_version_id,
        decision="select",
        decided_by="operator:alice",
        considered_scenarios=(first.reference(), second.reference()),
        selected_scenario=second.reference(),
    )

    assert record.selected_scenario == second.reference()
    assert record.considered_scenarios == (first.reference(), second.reference())


def test_decision_record_rejects_selected_scenario_not_considered() -> None:
    case = new_decision_case_version(decision_case_id="case_1", basis=basis())
    considered = scenario_version(
        decision_case_version_id=case.decision_case_version_id
    )
    selected = scenario_version(
        decision_case_version_id=case.decision_case_version_id
    )

    with pytest.raises(ValidationError, match="one of the considered"):
        DecisionRecord(
            decision_record_id="decision_1",
            decision_case_version_id=case.decision_case_version_id,
            decision="select",
            decided_by="operator:alice",
            considered_scenarios=(considered.reference(),),
            selected_scenario=selected.reference(),
        )


def test_decision_record_rejects_scenario_from_another_case() -> None:
    case = new_decision_case_version(decision_case_id="case_1", basis=basis())
    other_case = new_decision_case_version(decision_case_id="case_2", basis=basis())
    foreign = scenario_version(
        decision_case_version_id=other_case.decision_case_version_id
    )

    with pytest.raises(ValidationError, match="must evaluate the DecisionCaseVersion"):
        DecisionRecord(
            decision_record_id="decision_1",
            decision_case_version_id=case.decision_case_version_id,
            decision="select",
            decided_by="operator:alice",
            considered_scenarios=(foreign.reference(),),
        )


def test_decision_record_rejects_duplicate_scenario_citations() -> None:
    case = new_decision_case_version(decision_case_id="case_1", basis=basis())
    scenario = scenario_version(
        decision_case_version_id=case.decision_case_version_id
    )

    with pytest.raises(ValidationError, match="must be unique"):
        DecisionRecord(
            decision_record_id="decision_1",
            decision_case_version_id=case.decision_case_version_id,
            decision="select",
            decided_by="operator:alice",
            considered_scenarios=(scenario.reference(), scenario.reference()),
        )


def test_lifecycle_is_explicit_and_decision_cannot_skip_review() -> None:
    assert lifecycle_transition_allowed(
        DecisionLifecycle.REVIEW_READY, DecisionLifecycle.DECIDED
    )
    assert not lifecycle_transition_allowed(
        DecisionLifecycle.DRAFT, DecisionLifecycle.DECIDED
    )
