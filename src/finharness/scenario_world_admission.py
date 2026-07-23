"""Fail-closed admission of immutable ScenarioVersion inputs to one Capital World."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from finharness.decision_ontology import ScenarioVersion
from finharness.statecore.capital_world import CapitalWorld


@dataclass(frozen=True)
class ScenarioWorldAdmission:
    status: Literal["admitted", "blocked"]
    expected_world_id: str
    current_world_id: str
    blockers: tuple[str, ...] = ()


def evaluate_scenario_world_admission(
    scenario: ScenarioVersion,
    current_world: CapitalWorld,
) -> ScenarioWorldAdmission:
    blockers: list[str] = []
    if scenario.capital_world_id != current_world.world_id:
        blockers.append("stale_capital_world")
    if scenario.capital_world_basis_digest != current_world.basis_digest:
        blockers.append("capital_world_basis_mismatch")
    if current_world.trust.status != "admitted":
        blockers.append("capital_world_not_admitted")
    return ScenarioWorldAdmission(
        status="blocked" if blockers else "admitted",
        expected_world_id=scenario.capital_world_id,
        current_world_id=current_world.world_id,
        blockers=tuple(blockers),
    )
