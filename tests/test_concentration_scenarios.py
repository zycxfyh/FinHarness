"""Deterministic concentration Scenario v0 contracts."""

from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from finharness.concentration_scenarios import (
    ConcentrationScenarioInputs,
    build_concentration_scenario_set,
)
from finharness.delegated_review import build_decision_case
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import init_state_core


class ConcentrationScenarioSetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.engine = init_state_core(root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        proposal = create_governed_proposal(
            proposal_id="prop_scenario_v0",
            kind="concentration_review",
            claim="Compare transparent concentration responses.",
            evidence={"position_symbol": "ACME"},
            decision_scaffold={
                "decision_intent": "Compare concentration responses.",
                "thesis": "The largest position warrants material review.",
                "do_nothing_case": "Hold the current allocation.",
                "risk_if_wrong": "A reduction can create cost and tax consequences.",
            },
            source_refs=["capital-state://v1"],
            engine=self.engine,
            receipt_root=root / "receipts",
        ).proposal
        self.case = build_decision_case(proposal_id=proposal.proposal_id, engine=self.engine)

    def _inputs(self, **changes: object) -> ConcentrationScenarioInputs:
        values: dict[str, object] = {
            "capital_state_ref": "capital-state://v1",
            "valued_at_utc": "2026-07-12T00:00:00+00:00",
            "base_currency": "USD",
            "position_symbol": "ACME",
            "position_value": Decimal("400"),
            "other_position_values": (Decimal("400"),),
            "cash": Decimal("200"),
            "total_assets": Decimal("1000"),
            "monthly_expenses": Decimal("100"),
            "future_cashflow": Decimal("200"),
            "reduction_amount": Decimal("100"),
            "estimated_cost": Decimal("10"),
            "single_stock_shock": Decimal("-0.25"),
            "market_shock": Decimal("-0.10"),
            "tax_status": "known",
            "uncertainty": Decimal("0.20"),
            "source_refs": ("evidence-pack://v1",),
        }
        values.update(changes)
        return ConcentrationScenarioInputs(**values)

    def test_builds_three_replayable_scenarios_with_exact_metrics(self) -> None:
        result = build_concentration_scenario_set(
            decision_case=self.case,
            inputs=self._inputs(),
            created_at_utc="2026-07-12T01:00:00+00:00",
        )

        self.assertEqual(result.status, "complete")
        self.assertEqual([item.kind for item in result.scenarios], [
            "do_nothing",
            "future_cashflow_dilution",
            "operator_sized_reduction",
        ])
        do_nothing, cashflow, reduction = result.scenarios
        self.assertEqual(do_nothing.metrics["position_weight"], "0.4")
        self.assertEqual(do_nothing.metrics["hhi"], "0.36")
        self.assertEqual(do_nothing.metrics["single_stock_shock_contribution"], "-100.00")
        self.assertEqual(cashflow.metrics["position_weight"], str(Decimal("400") / Decimal("1200")))
        self.assertEqual(reduction.metrics["position_value"], "300")
        self.assertEqual(reduction.metrics["cash"], "290")
        self.assertEqual(reduction.metrics["total_assets"], "990")
        self.assertFalse(result.execution_allowed)

    def test_missing_input_blocks_without_zero_filled_scenarios(self) -> None:
        result = build_concentration_scenario_set(
            decision_case=self.case,
            inputs=self._inputs(monthly_expenses=None),
            created_at_utc="2026-07-12T01:00:00+00:00",
        )

        self.assertEqual(result.status, "blocked")
        self.assertEqual(result.scenarios, ())
        self.assertIn("missing:monthly_expenses", result.data_gaps)

    def test_unreconciled_components_block_precision(self) -> None:
        result = build_concentration_scenario_set(
            decision_case=self.case,
            inputs=self._inputs(total_assets=Decimal("1100")),
            created_at_utc="2026-07-12T01:00:00+00:00",
        )
        self.assertEqual(result.status, "blocked")
        self.assertIn("unreconciled:asset_components", result.data_gaps)

    def test_unknown_tax_state_is_partial_and_propagates_to_every_scenario(self) -> None:
        result = build_concentration_scenario_set(
            decision_case=self.case,
            inputs=self._inputs(tax_status="not_computable"),
            created_at_utc="2026-07-12T01:00:00+00:00",
        )

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.data_gaps, ("tax:not_computable",))
        self.assertTrue(all(item.data_gaps == result.data_gaps for item in result.scenarios))

    def test_reduction_cannot_exceed_position(self) -> None:
        result = build_concentration_scenario_set(
            decision_case=self.case,
            inputs=self._inputs(reduction_amount=Decimal("500")),
            created_at_utc="2026-07-12T01:00:00+00:00",
        )
        self.assertEqual(result.status, "blocked")
        self.assertIn("invalid:reduction_exceeds_position", result.data_gaps)


if __name__ == "__main__":
    unittest.main()
