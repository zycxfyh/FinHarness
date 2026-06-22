from __future__ import annotations

import unittest
from typing import Any

from pydantic import ValidationError

from finharness.research_evidence import (
    REQUIRED_NON_CLAIMS,
    RESEARCH_EVIDENCE_FIELD_POLICIES,
    RESEARCH_EVIDENCE_RESULT_FIELD_POLICIES,
    NullResearchEvidenceProvider,
    ResearchEvidence,
    ResearchEvidenceProvider,
    ResearchEvidenceRequest,
    ResearchEvidenceResult,
)


def _evidence(**overrides: Any) -> ResearchEvidence:
    base: dict[str, Any] = {
        "kind": "historical_risk_profile",
        "claim": "SPY realized volatility was ~18% over the trailing 3 years.",
        "evidence_grade": "historical_market_data",
        "value": {"realized_volatility": 0.18, "max_drawdown": -0.34},
        "time_window": "trailing_3y",
        "source_refs": ("data/receipts/market-data/spy.json",),
        "non_claims": REQUIRED_NON_CLAIMS["historical_market_data"],
    }
    base.update(overrides)
    return ResearchEvidence(**base)


class ResearchEvidenceContractTest(unittest.TestCase):
    def test_output_field_policies_cover_every_model_field(self) -> None:
        self.assertEqual(
            set(ResearchEvidence.model_fields),
            set(RESEARCH_EVIDENCE_FIELD_POLICIES),
        )
        self.assertEqual(
            set(ResearchEvidenceResult.model_fields),
            set(RESEARCH_EVIDENCE_RESULT_FIELD_POLICIES),
        )

    def test_valid_historical_evidence_is_accepted(self) -> None:
        evidence = _evidence()
        self.assertEqual(evidence.evidence_grade, "historical_market_data")
        self.assertFalse(evidence.execution_allowed)

    def test_forbidden_key_top_level_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            _evidence(value={"target_price": 500.0})

    def test_forbidden_key_nested_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            _evidence(value={"details": {"sizing": {"order_size": 100}}})

    def test_forbidden_key_synonyms_are_rejected(self) -> None:
        for payload in (
            {"price_target": 500.0},
            {"recommendations": ["SPY"]},
            {"execution_plan": "market order"},
            {"position_size": 0.2},
            {"orders": [{"quantity": 100}]},
        ):
            with self.assertRaises(ValidationError):
                _evidence(value=payload)

    def test_structured_payload_string_advice_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            _evidence(value={"note": "buy SPY now"})
        with self.assertRaises(ValidationError):
            _evidence(lineage={"note": "execution plan is ready"})
        with self.assertRaises(ValidationError):
            _evidence(value={"notes": ["expected return unavailable"]})

    def test_execution_allowed_true_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            _evidence(execution_allowed=True)

    def test_grade_requires_its_non_claims(self) -> None:
        # backtest_descriptive needs the stronger disclaimers; missing them fails.
        with self.assertRaises(ValidationError):
            _evidence(
                evidence_grade="backtest_descriptive",
                non_claims=("Not investment advice.",),
            )
        # With the full required set it is accepted.
        ok = _evidence(
            evidence_grade="backtest_descriptive",
            non_claims=REQUIRED_NON_CLAIMS["backtest_descriptive"],
        )
        self.assertEqual(ok.evidence_grade, "backtest_descriptive")

    def test_llm_interpretation_requires_strong_non_claims(self) -> None:
        with self.assertRaises(ValidationError):
            _evidence(
                evidence_grade="llm_interpretation",
                non_claims=REQUIRED_NON_CLAIMS["historical_market_data"],
            )

    def test_question_is_a_closed_enum_not_free_text(self) -> None:
        with self.assertRaises(ValidationError):
            ResearchEvidenceRequest(
                detector_kind="concentration_high",
                subject="SPY",
                question="please predict the price",
                time_window="trailing_3y",
            )

    def test_evidence_grade_is_a_closed_enum(self) -> None:
        with self.assertRaises(ValidationError):
            _evidence(evidence_grade="insider_tip")

    def test_request_forbids_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            ResearchEvidenceRequest(
                detector_kind="concentration_high",
                subject="SPY",
                question="historical_risk_profile",
                time_window="trailing_3y",
                target_weights={"SPY": 0.2},  # type: ignore[call-arg]
            )

    def test_claim_advice_language_is_rejected(self) -> None:
        # claim is provider output; advice/target/prediction language is a redline
        # even though value/lineage keys are separately guarded.
        for bad in (
            "Buy SPY at target_price 500",
            "Sell now — strong recommendation",
            "Model recommendations are favorable for SPY",
            "Execution plan is ready for SPY",
            "Expected return is 12% next year",
            "Our forecast points higher",
        ):
            with self.assertRaises(ValidationError):
                _evidence(claim=bad)

    def test_kind_is_a_closed_enum(self) -> None:
        with self.assertRaises(ValidationError):
            _evidence(kind="target_price")

    def test_time_window_advice_language_is_rejected(self) -> None:
        # time_window is also free-text provider output; same redline as claim.
        with self.assertRaises(ValidationError):
            _evidence(time_window="buy window before earnings")

    def test_source_ref_advice_language_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            _evidence(source_refs=("data/receipts/buy-recommendation.json",))

    def test_source_ref_may_name_returns_or_forecast_data(self) -> None:
        # A ref path may legitimately name returns/forecast data files; only the
        # advice/execution redline applies to refs, not the prediction one.
        evidence = _evidence(
            source_refs=("data/receipts/market-data/returns_forecast_spy.json",)
        )
        self.assertTrue(evidence.source_refs)

    def test_result_execution_allowed_true_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ResearchEvidenceResult(execution_allowed=True)

    def test_data_gaps_advice_language_is_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            ResearchEvidenceResult(data_gaps=("buy SPY because the setup is favorable",))
        with self.assertRaises(ValidationError):
            ResearchEvidenceResult(data_gaps=("execution plan pending for SPY",))

    def test_data_gap_may_describe_missing_prediction_data(self) -> None:
        # A gap legitimately uses prediction words to say data is missing; the gap
        # redline only blocks advice/execution language, not "forecast"/"return".
        result = ResearchEvidenceResult(data_gaps=("price forecast data unavailable",))
        self.assertEqual(result.data_gaps, ("price forecast data unavailable",))

    def test_disclaimers_reject_advice_but_allow_disclaimer_terms(self) -> None:
        with self.assertRaises(ValidationError):
            _evidence(limitations=("Buy SPY now.",))
        with self.assertRaises(ValidationError):
            _evidence(
                non_claims=REQUIRED_NON_CLAIMS["historical_market_data"]
                + ("Sell SPY now.",)
            )
        evidence = _evidence(limitations=("This is not a forecast and not advice.",))
        self.assertEqual(evidence.limitations, ("This is not a forecast and not advice.",))

    def test_forbidden_key_in_lineage_is_rejected(self) -> None:
        # Advice/optimizer output must not hide under provenance metadata.
        with self.assertRaises(ValidationError):
            _evidence(lineage={"nested": {"target_weights": {"SPY": 1.0}}})
        with self.assertRaises(ValidationError):
            _evidence(lineage={"chain": [{"order_size": 5}]})

    def test_top_level_frozen_blocks_field_reassignment(self) -> None:
        # The guarantee is top-level frozen + construction-time redlines; reassigning
        # a field is blocked (nested mutation is the caller's responsibility, see
        # module docstring).
        evidence = _evidence()
        with self.assertRaises(ValidationError):
            evidence.execution_allowed = True  # type: ignore[misc]

    def test_null_provider_discloses_a_gap_not_silent_empty(self) -> None:
        provider: ResearchEvidenceProvider = NullResearchEvidenceProvider()
        self.assertIsInstance(provider, ResearchEvidenceProvider)
        result = provider.provide(
            ResearchEvidenceRequest(
                detector_kind="concentration_high",
                subject="SPY",
                question="historical_risk_profile",
                time_window="trailing_3y",
            )
        )
        self.assertIsInstance(result, ResearchEvidenceResult)
        self.assertEqual(result.items, ())
        self.assertTrue(result.data_gaps)
        self.assertFalse(result.execution_allowed)


if __name__ == "__main__":
    unittest.main()
