# finharness-test-runner: pytest
from __future__ import annotations

from dataclasses import replace
from typing import Literal

from finharness.decision_ontology import (
    DecisionCaseBasis,
    new_decision_case_version,
    new_scenario_version,
)
from finharness.scenario_world_admission import evaluate_scenario_world_admission
from finharness.statecore.capital_world import (
    CapitalWorld,
    CapitalWorldQuery,
    CapitalWorldTrust,
)


def basis() -> DecisionCaseBasis:
    return DecisionCaseBasis(
        decision_problem_id="problem_rebalance",
        proposal_version_id="proposal_version_3",
        evidence_set_version_id="evidence_set_version_8",
        capital_state_version_id="capital_state_version_12",
        policy_version_id="policy_version_2",
    )


def _world(
    *,
    world_id: str = "capital_world_0123456789abcdef01234567",
    status: Literal["admitted", "blocked"] = "admitted",
) -> CapitalWorld:
    return CapitalWorld(
        world_id=world_id,
        basis_digest="0" * 64,
        query=CapitalWorldQuery(
            as_of_utc="2026-07-23T00:00:00+00:00",
            known_at_utc="2026-07-23T00:00:00+00:00",
            base_currency="USD",
            use_case="scenario",
        ),
        selected_sources=(),
        records=(),
        trust=CapitalWorldTrust(
            status=status,
            evidence_integrity="intact",
            completeness="complete",
            valuation_status="admitted",
            blockers=(),
        ),
        recovery_refs=(),
    )


def _scenario(world: CapitalWorld):
    case = new_decision_case_version(decision_case_id="case_1", basis=basis())
    return new_scenario_version(
        scenario_id="scenario_drawdown",
        decision_case_version_id=case.decision_case_version_id,
        verified_capital_projection_ref="projection:verified:12",
        capital_world_id=world.world_id,
        capital_world_basis_digest=world.basis_digest,
        capital_world_status="admitted",
        assumption_set_version_id="assumptions:4",
        calculator_version_id="calculator:2",
    )


def test_scenario_is_admitted_only_against_the_exact_admitted_world() -> None:
    world = _world()
    result = evaluate_scenario_world_admission(_scenario(world), world)
    assert result.status == "admitted"
    assert result.blockers == ()


def test_world_change_makes_scenario_stale() -> None:
    original = _world()
    changed = _world(world_id="capital_world_abcdef0123456789abcdef01")
    result = evaluate_scenario_world_admission(_scenario(original), changed)
    assert result.status == "blocked"
    assert "stale_capital_world" in result.blockers


def test_basis_change_and_blocked_world_fail_closed() -> None:
    original = _world()
    changed = replace(
        original,
        basis_digest="1" * 64,
        trust=replace(original.trust, status="blocked", blockers=("fx_missing",)),
    )
    result = evaluate_scenario_world_admission(_scenario(original), changed)
    assert result.status == "blocked"
    assert result.blockers == (
        "capital_world_basis_mismatch",
        "capital_world_not_admitted",
    )
