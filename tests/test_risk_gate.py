from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

import finharness.portfolio_risk as portfolio_risk
from finharness import events, hypotheses, interpretation, proposal, risk_gate, validation
from finharness.portfolio_risk import (
    RISKFOLIO_BACKEND,
    RiskfolioAllocationSummary,
    concentration_request_from_allocation,
    optimize_riskfolio_allocation,
)
from finharness.proposal import (
    ProposalCandidate,
    build_proposal_bundle_from_validation_snapshot,
)
from finharness.risk_gate import (
    RiskGateContext,
    build_risk_gate_bundle_from_proposal_snapshot,
    build_risk_gate_quality,
    risk_context_for_candidate,
)
from finharness.risk_gate_graph import risk_gate_graph, run_risk_gate_graph
from tests.test_proposal import build_sample_validation_bundle


def sample_riskfolio_returns() -> pd.DataFrame:
    rng = np.random.default_rng(20260615)
    return pd.DataFrame(
        {
            "NVDA": rng.normal(0.0007, 0.014, size=120),
            "SPY": rng.normal(0.0005, 0.010, size=120),
            "QQQ": rng.normal(0.0006, 0.012, size=120),
        }
    )


def manual_allocation(
    *,
    nvda_weight: float,
    concentration_ok: bool = True,
) -> RiskfolioAllocationSummary:
    return RiskfolioAllocationSummary(
        backend=RISKFOLIO_BACKEND,
        model="Classic",
        risk_measure="MV",
        objective="Sharpe",
        weights={"NVDA": nvda_weight, "SPY": 1.0 - nvda_weight},
        weight_sum=1.0,
        max_weight=max(nvda_weight, 1.0 - nvda_weight),
        concentration_cap=0.80,
        concentration_ok=concentration_ok,
        execution_allowed=False,
    )


class RiskGateLayerTest(unittest.TestCase):
    def test_bundle_persists_risk_gate_snapshot_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(events, "EVENT_RAW_ROOT", root / "events_raw"),
                patch.object(events, "EVENT_NORMALIZED_ROOT", root / "events_normalized"),
                patch.object(events, "EVENT_RECEIPT_ROOT", root / "events_receipts"),
                patch.object(interpretation, "INTERPRETATION_NORMALIZED_ROOT", root / "ints"),
                patch.object(interpretation, "INTERPRETATION_RECEIPT_ROOT", root / "int_receipts"),
                patch.object(hypotheses, "HYPOTHESIS_NORMALIZED_ROOT", root / "hyps"),
                patch.object(hypotheses, "HYPOTHESIS_RECEIPT_ROOT", root / "hyp_receipts"),
                patch.object(validation, "VALIDATION_NORMALIZED_ROOT", root / "vals"),
                patch.object(validation, "VALIDATION_RECEIPT_ROOT", root / "val_receipts"),
                patch.object(proposal, "PROPOSAL_NORMALIZED_ROOT", root / "props"),
                patch.object(proposal, "PROPOSAL_RECEIPT_ROOT", root / "prop_receipts"),
                patch.object(risk_gate, "RISK_GATE_NORMALIZED_ROOT", root / "rgates"),
                patch.object(risk_gate, "RISK_GATE_RECEIPT_ROOT", root / "rgate_receipts"),
            ):
                validation_bundle = build_sample_validation_bundle()
                proposal_bundle = build_proposal_bundle_from_validation_snapshot(
                    validation_bundle.snapshot,
                )
                bundle = build_risk_gate_bundle_from_proposal_snapshot(
                    proposal_bundle.snapshot,
                    context={"human_review_attested": True},
                    llm_enabled=True,
                    hermes_root="/root/projects/hermes-agent",
                )

                self.assertEqual(
                    bundle.snapshot.candidate_count,
                    proposal_bundle.snapshot.candidate_count,
                )
                self.assertEqual(
                    bundle.snapshot.decision_count,
                    proposal_bundle.snapshot.candidate_count,
                )
                self.assertTrue(bundle.snapshot.quality.ok)
                self.assertFalse(bundle.snapshot.execution_allowed)
                self.assertTrue(bundle.snapshot.execution_handoff)
                self.assertEqual(
                    bundle.snapshot.lineage.input_proposal_snapshot_id,
                    proposal_bundle.snapshot.proposal_snapshot_id,
                )
                self.assertEqual(bundle.snapshot.lineage.source.llm_provider, "hermes-agent")
                self.assertTrue(Path(bundle.snapshot.payload_ref).exists())
                self.assertTrue(Path(bundle.snapshot.receipt_ref).exists())
                for decision in bundle.snapshot.decisions:
                    self.assertEqual(decision.decision, "approved_for_paper_review")
                    self.assertTrue(decision.paper_review_allowed)
                    self.assertFalse(decision.live_execution_allowed)

    def test_riskfolio_allocation_sets_requested_concentration_only(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(
            validation_bundle.snapshot,
        )
        candidate = proposal_bundle.snapshot.candidates[0]
        with patch(
            "finharness.portfolio_risk.rp.Portfolio",
            wraps=portfolio_risk.rp.Portfolio,
        ) as portfolio:
            allocation = optimize_riskfolio_allocation(
                sample_riskfolio_returns(),
                concentration_cap=0.70,
            )

        context = RiskGateContext(
            human_review_attested=True,
            max_symbol_concentration_pct=1.0,
        )
        candidate_context = risk_context_for_candidate(
            context=context,
            candidate=candidate,
            allocation_summary=allocation,
        )
        bundle = build_risk_gate_bundle_from_proposal_snapshot(
            proposal_bundle.snapshot,
            context=context,
            allocation_summary=allocation,
        )
        concentration_check = next(
            check
            for check in bundle.decisions[0].checks
            if check.check_type == "concentration_check"
        )

        self.assertTrue(portfolio.called)
        self.assertAlmostEqual(
            candidate_context.requested_symbol_concentration_pct,
            concentration_request_from_allocation(allocation, candidate.symbol),
        )
        self.assertEqual(candidate_context.max_symbol_concentration_pct, 1.0)
        self.assertEqual(bundle.snapshot.context.max_symbol_concentration_pct, 1.0)
        self.assertTrue(
            any(RISKFOLIO_BACKEND in ref for ref in concentration_check.evidence_refs)
        )
        self.assertEqual(
            risk_gate.find_blocked_language("\n".join(concentration_check.evidence_refs)),
            [],
        )
        self.assertFalse(allocation.execution_allowed)
        self.assertFalse(bundle.snapshot.execution_allowed)

    def test_riskfolio_weight_above_mandate_cap_blocks_without_widening_cap(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(
            validation_bundle.snapshot,
        )
        allocation = manual_allocation(nvda_weight=0.25, concentration_ok=True)
        bundle = build_risk_gate_bundle_from_proposal_snapshot(
            proposal_bundle.snapshot,
            context={
                "human_review_attested": True,
                "max_symbol_concentration_pct": 0.10,
            },
            allocation_summary=allocation,
        )

        self.assertEqual(bundle.snapshot.context.max_symbol_concentration_pct, 0.10)
        self.assertTrue(all(decision.decision == "blocked" for decision in bundle.decisions))
        for decision in bundle.decisions:
            concentration_check = next(
                check for check in decision.checks if check.check_type == "concentration_check"
            )
            self.assertEqual(concentration_check.status, "failed")
            self.assertTrue(concentration_check.blocking)
        self.assertFalse(bundle.snapshot.execution_allowed)

    def test_riskfolio_concentration_ok_is_not_gate_authority(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(
            validation_bundle.snapshot,
        )
        allocation = manual_allocation(nvda_weight=0.30, concentration_ok=True)
        bundle = build_risk_gate_bundle_from_proposal_snapshot(
            proposal_bundle.snapshot,
            context={
                "human_review_attested": True,
                "max_symbol_concentration_pct": 0.20,
            },
            allocation_summary=allocation,
        )

        self.assertTrue(allocation.concentration_ok)
        self.assertTrue(all(decision.decision == "blocked" for decision in bundle.decisions))
        self.assertFalse(any(decision.paper_review_allowed for decision in bundle.decisions))

    def test_in_cap_riskfolio_weight_still_requires_human_review(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(
            validation_bundle.snapshot,
        )
        allocation = manual_allocation(nvda_weight=0.05, concentration_ok=True)
        bundle = build_risk_gate_bundle_from_proposal_snapshot(
            proposal_bundle.snapshot,
            context={"max_symbol_concentration_pct": 0.10},
            allocation_summary=allocation,
        )

        self.assertTrue(
            all(decision.decision == "needs_human_review" for decision in bundle.decisions)
        )
        self.assertTrue(all(decision.human_review_required for decision in bundle.decisions))
        self.assertFalse(bundle.snapshot.execution_allowed)

    def test_live_request_is_hard_blocked_but_quality_passes(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(validation_bundle.snapshot)
        bundle = build_risk_gate_bundle_from_proposal_snapshot(
            proposal_bundle.snapshot,
            context={"requested_execution_mode": "live"},
        )

        self.assertTrue(bundle.snapshot.quality.ok)
        self.assertTrue(bundle.snapshot.quality.hard_blocks_enforced)
        self.assertFalse(bundle.snapshot.execution_allowed)
        self.assertTrue(all(decision.decision == "blocked" for decision in bundle.decisions))

    def test_missing_human_review_requests_human_review(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(validation_bundle.snapshot)
        bundle = build_risk_gate_bundle_from_proposal_snapshot(
            proposal_bundle.snapshot,
            context={"human_review_attested": False},
        )

        self.assertTrue(bundle.snapshot.quality.ok)
        self.assertTrue(
            all(decision.decision == "needs_human_review" for decision in bundle.decisions)
        )

    def test_typed_authorization_is_recorded_on_risk_gate_decisions(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(validation_bundle.snapshot)
        bundle = build_risk_gate_bundle_from_proposal_snapshot(
            proposal_bundle.snapshot,
            context={"human_review_attested": True},
        )

        for decision in bundle.snapshot.decisions:
            self.assertTrue(decision.authorization.allowed)
            self.assertEqual(decision.authorization.operator_id, "paper_operator")
            self.assertEqual(decision.authorization.account_id, "paper_account")
            self.assertEqual(decision.authorization.scope, "risk_review")
            authorization_check = next(
                check for check in decision.checks if check.check_type == "authorization_check"
            )
            self.assertEqual(authorization_check.status, "passed")
            self.assertFalse(decision.authorization.execution_allowed)
        self.assertFalse(bundle.snapshot.execution_allowed)

    def test_unregistered_risk_operator_blocks_fail_closed(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(validation_bundle.snapshot)
        bundle = build_risk_gate_bundle_from_proposal_snapshot(
            proposal_bundle.snapshot,
            context={
                "human_review_attested": True,
                "operator_id": "unknown_operator",
            },
        )

        self.assertTrue(bundle.snapshot.quality.ok)
        self.assertTrue(all(decision.decision == "blocked" for decision in bundle.decisions))
        for decision in bundle.snapshot.decisions:
            self.assertFalse(decision.authorization.allowed)
            authorization_check = next(
                check for check in decision.checks if check.check_type == "authorization_check"
            )
            self.assertEqual(authorization_check.status, "failed")
            self.assertTrue(authorization_check.blocking)
        self.assertFalse(bundle.snapshot.execution_allowed)

    def test_restricted_symbol_denies_even_when_symbol_is_allowed(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(validation_bundle.snapshot)
        candidate_symbol = proposal_bundle.snapshot.candidates[0].symbol
        with tempfile.TemporaryDirectory() as tmp:
            restricted_path = Path(tmp) / "restricted-symbols.json"
            restricted_path.write_text(
                json.dumps(
                    {
                        "schema_version": "finharness.restricted_symbols.v1",
                        "restricted_list_version": "deny-priority-v1",
                        "updated_at_utc": "2026-06-18T00:00:00+00:00",
                        "entries": [
                            {
                                "symbol": candidate_symbol,
                                "reason": "local deny-list test",
                                "added_utc": "2026-06-18T00:00:00+00:00",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            bundle = build_risk_gate_bundle_from_proposal_snapshot(
                proposal_bundle.snapshot,
                context={
                    "human_review_attested": True,
                    "allowed_symbols": [candidate_symbol],
                    "restricted_symbols_ref": str(restricted_path),
                },
            )

        self.assertTrue(bundle.snapshot.quality.ok)
        self.assertTrue(all(decision.decision == "blocked" for decision in bundle.decisions))
        for decision in bundle.snapshot.decisions:
            restricted_check = next(
                check for check in decision.checks if check.check_type == "restricted_symbol_check"
            )
            self.assertEqual(restricted_check.status, "failed")
            self.assertTrue(restricted_check.blocking)
            self.assertEqual(decision.restricted_symbol.restricted_list_version, "deny-priority-v1")
        self.assertFalse(bundle.snapshot.execution_allowed)

    def test_provider_not_tradable_or_unknown_blocks_risk_gate(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(validation_bundle.snapshot)
        candidate_symbol = proposal_bundle.snapshot.candidates[0].symbol
        symbols = sorted({candidate.symbol for candidate in proposal_bundle.snapshot.candidates})
        with tempfile.TemporaryDirectory() as tmp:
            receipt_path = Path(tmp) / "alpaca-assets.json"
            receipt_path.write_text(
                json.dumps(
                    {
                        "receipt_id": "receipt_assets",
                        "kind": "broker_read",
                        "assets": [
                            {"symbol": symbol, "tradable": symbol != candidate_symbol}
                            for symbol in symbols
                        ],
                    }
                ),
                encoding="utf-8",
            )
            not_tradable = build_risk_gate_bundle_from_proposal_snapshot(
                proposal_bundle.snapshot,
                context={
                    "human_review_attested": True,
                    "tradability_provider": "alpaca",
                    "tradability_receipt_ref": str(receipt_path),
                },
            )
            unknown = build_risk_gate_bundle_from_proposal_snapshot(
                proposal_bundle.snapshot,
                context={
                    "human_review_attested": True,
                    "tradability_provider": "alpaca",
                },
            )

        self.assertTrue(all(decision.decision == "blocked" for decision in not_tradable.decisions))
        self.assertTrue(
            any(
                decision.tradability.status == "not_tradable"
                for decision in not_tradable.decisions
            )
        )
        self.assertTrue(all(decision.decision == "blocked" for decision in unknown.decisions))
        self.assertTrue(
            all(decision.tradability.status == "unknown" for decision in unknown.decisions)
        )

    def test_clean_symbol_with_provider_tradability_can_pass(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(validation_bundle.snapshot)
        symbols = sorted({candidate.symbol for candidate in proposal_bundle.snapshot.candidates})
        with tempfile.TemporaryDirectory() as tmp:
            receipt_path = Path(tmp) / "alpaca-assets.json"
            receipt_path.write_text(
                json.dumps(
                    {
                        "receipt_id": "receipt_assets",
                        "kind": "broker_read",
                        "assets": [
                            {"symbol": symbol, "tradable": True}
                            for symbol in symbols
                        ],
                    }
                ),
                encoding="utf-8",
            )
            bundle = build_risk_gate_bundle_from_proposal_snapshot(
                proposal_bundle.snapshot,
                context={
                    "human_review_attested": True,
                    "tradability_provider": "alpaca",
                    "tradability_receipt_ref": str(receipt_path),
                },
            )

        self.assertTrue(all(decision.tradability.allowed for decision in bundle.decisions))
        self.assertTrue(
            all(
                decision.decision == "approved_for_paper_review"
                for decision in bundle.decisions
            )
        )
        self.assertFalse(bundle.snapshot.execution_allowed)

    def test_quality_records_blocked_order_language(self) -> None:
        validation_bundle = build_sample_validation_bundle()
        proposal_bundle = build_proposal_bundle_from_validation_snapshot(validation_bundle.snapshot)
        bad_candidate = ProposalCandidate.model_validate(
            proposal_bundle.snapshot.candidates[0].model_dump(mode="json")
            | {"rationale": "place order after risk gate"}
        )
        bad_snapshot = proposal_bundle.snapshot.model_copy(
            update={
                "candidates": [bad_candidate, *proposal_bundle.snapshot.candidates[1:]],
            }
        )
        bundle = build_risk_gate_bundle_from_proposal_snapshot(bad_snapshot)
        quality = build_risk_gate_quality(
            proposal_snapshot=bad_snapshot,
            context=RiskGateContext(),
            decisions=bundle.decisions,
        )

        self.assertFalse(quality.ok)
        self.assertFalse(quality.no_order_language)
        self.assertTrue(quality.blocked_language_hits)
        self.assertTrue(any(decision.decision == "blocked" for decision in bundle.decisions))

    def test_risk_gate_graph_compiles(self) -> None:
        self.assertIsNotNone(risk_gate_graph)

    def test_risk_gate_graph_runs_with_proposal_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(events, "EVENT_RAW_ROOT", root / "events_raw"),
                patch.object(events, "EVENT_NORMALIZED_ROOT", root / "events_normalized"),
                patch.object(events, "EVENT_RECEIPT_ROOT", root / "events_receipts"),
                patch.object(interpretation, "INTERPRETATION_NORMALIZED_ROOT", root / "ints"),
                patch.object(interpretation, "INTERPRETATION_RECEIPT_ROOT", root / "int_receipts"),
                patch.object(hypotheses, "HYPOTHESIS_NORMALIZED_ROOT", root / "hyps"),
                patch.object(hypotheses, "HYPOTHESIS_RECEIPT_ROOT", root / "hyp_receipts"),
                patch.object(validation, "VALIDATION_NORMALIZED_ROOT", root / "vals"),
                patch.object(validation, "VALIDATION_RECEIPT_ROOT", root / "val_receipts"),
                patch.object(proposal, "PROPOSAL_NORMALIZED_ROOT", root / "props"),
                patch.object(proposal, "PROPOSAL_RECEIPT_ROOT", root / "prop_receipts"),
                patch.object(risk_gate, "RISK_GATE_NORMALIZED_ROOT", root / "rgates"),
                patch.object(risk_gate, "RISK_GATE_RECEIPT_ROOT", root / "rgate_receipts"),
            ):
                validation_bundle = build_sample_validation_bundle()
                proposal_bundle = build_proposal_bundle_from_validation_snapshot(
                    validation_bundle.snapshot,
                )
                result = run_risk_gate_graph(
                    proposal_snapshot=proposal_bundle.snapshot.model_dump(mode="json"),
                    risk_context={"human_review_attested": True},
                    llm_enabled=True,
                    hermes_root="/root/projects/hermes-agent",
                )

                final = result["final"]
                self.assertEqual(final["workflow"], "langgraph_risk_gate_v1")
                self.assertEqual(final["decision_count"], proposal_bundle.snapshot.candidate_count)
                self.assertTrue(final["quality_ok"])
                self.assertFalse(final["execution_allowed"])
                self.assertTrue(final["execution_handoff"])
                self.assertEqual(final["consumer_handoff"]["consumer"], "execution_review")
                self.assertTrue(final["llm_enabled"])
                self.assertEqual(final["hermes_root"], "/root/projects/hermes-agent")


if __name__ == "__main__":
    unittest.main()
