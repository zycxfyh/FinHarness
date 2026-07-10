"""Current-fact tests for Execution Kernel abstraction classification."""

from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
INVENTORY_PATH = ROOT / "docs" / "engineering" / "abstraction-inventory.yml"

CANONICAL_EXECUTION_OBJECTS = {
    "ApprovalRecord",
    "BrokerConnection",
    "ExecutionAccount",
    "ExecutionOrder",
    "ExecutionReport",
    "OrderDraft",
    "PositionDelta",
    "PreTradeCheck",
    "ReconciliationReport",
}

EXECUTION_ARTIFACTS = {
    "BrokerAdapter Registry",
    "Execution Capabilities",
    "Execution Legacy Bridge",
    "Execution Services",
    "SimulatedBrokerAdapter",
}

LEGACY_EXECUTION_OBJECTS = {
    "ActionIntent",
    "ActionIntentAuthorityBinding",
    "ActionIntentSimulationReport",
    "CapitalObjectiveFit",
    "PaperAccount",
    "PaperExecutionReceipt",
    "PaperOrderTicketCandidate",
    "PaperPosition",
    "TradePlanCandidate",
    "TradePlanReviewGate",
}


def _inventory() -> dict:
    return yaml.safe_load(INVENTORY_PATH.read_text(encoding="utf-8"))


def _by_name(entries: list[dict]) -> dict[str, dict]:
    return {entry["name"]: entry for entry in entries}


class TestExecutionAbstractionInventory(unittest.TestCase):
    def test_inventory_is_rebased_on_current_execution_kernel(self) -> None:
        inventory = _inventory()
        assert inventory["status"] == "current"
        assert str(inventory["updated"]) == "2026-07-10"

    def test_all_canonical_execution_objects_are_classified(self) -> None:
        objects = _by_name(_inventory()["objects"])
        assert CANONICAL_EXECUTION_OBJECTS.issubset(objects)
        for name in CANONICAL_EXECUTION_OBJECTS:
            entry = objects[name]
            assert "object" in entry["target_layer"]
            assert "canonical" in entry["target_form"].lower()
            assert entry["migration_path"] == "none_needed"

    def test_classical_execution_artifacts_are_separate_from_agent_artifacts(self) -> None:
        inventory = _inventory()
        execution = _by_name(inventory["execution_artifacts"])
        agent = _by_name(inventory["agent_artifacts"])
        assert set(execution) == EXECUTION_ARTIFACTS
        assert EXECUTION_ARTIFACTS.isdisjoint(agent)
        for name, entry in execution.items():
            layers = " ".join(entry["target_layer"])
            assert "classical" in layers or name == "Execution Legacy Bridge"

    def test_runtime_refs_for_execution_entries_exist(self) -> None:
        inventory = _inventory()
        entries = [
            *_by_name(inventory["objects"]).values(),
            *inventory["execution_artifacts"],
            *_by_name(inventory["api_routes"]).values(),
        ]
        execution_names = CANONICAL_EXECUTION_OBJECTS | EXECUTION_ARTIFACTS | {"execution_routes"}
        for entry in entries:
            if entry["name"] not in execution_names:
                continue
            assert entry.get("runtime_refs"), f"missing runtime_refs: {entry['name']}"
            for ref in entry["runtime_refs"]:
                assert (ROOT / ref).exists(), f"missing runtime ref for {entry['name']}: {ref}"

    def test_execution_routes_are_canonical_and_legacy_routes_are_not(self) -> None:
        routes = _by_name(_inventory()["api_routes"])
        canonical = routes["execution_routes"]
        assert "canonical" in canonical["target_form"].lower()
        assert canonical["migration_path"] == "none_needed"
        for name in ("action_intent_routes", "paper_validation_routes"):
            entry = routes[name]
            assert "legacy_internal" in entry["target_form"]
            assert entry["migration_path"] != "none_needed"
            assert entry["risk_level"] == "high"

    def test_legacy_objects_point_to_existing_bridge_or_canonical_facts(self) -> None:
        objects = _by_name(_inventory()["objects"])
        for name in LEGACY_EXECUTION_OBJECTS:
            entry = objects[name]
            target = entry["target_form"].lower()
            assert "legacy_internal" in target
            assert entry["migration_path"] != "none_needed"
        text = INVENTORY_PATH.read_text(encoding="utf-8")
        assert "/execution/pretrade-packets/" not in text
        assert "execution/paper/" not in text
        assert "wrapper_first" not in text
        assert "bridge_read_model_first" not in text


if __name__ == "__main__":
    unittest.main()
