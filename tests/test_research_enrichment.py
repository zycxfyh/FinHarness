from __future__ import annotations

import json
import unittest
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from finharness.research_enrichment import (
    RESEARCH_TIME_WINDOW,
    NoopResearchEnricher,
    ProviderResearchEnricher,
    ResearchEvidenceAttachment,
    build_research_request,
    sanitize_gap,
)
from finharness.research_evidence import (
    REQUIRED_NON_CLAIMS,
    ResearchEvidence,
    ResearchEvidenceRequest,
    ResearchEvidenceResult,
)


@dataclass
class _Candidate:
    """Duck-typed stand-in: the subsystem only reads detector_kind + evidence."""

    detector_kind: str
    evidence: dict[str, Any]


def _evidence_item(*, source_refs: tuple[str, ...] = ()) -> ResearchEvidence:
    return ResearchEvidence(
        kind="historical_risk_profile",
        claim="Over the trailing 3 years, SPY's observed realized volatility was 18%.",
        evidence_grade="historical_market_data",
        value={
            "realized_volatility": 0.18,
            "max_drawdown": -0.34,
            "conditional_var": -0.03,
            "average_volume": 1_000_000.0,
        },
        time_window="trailing_3y",
        source_refs=source_refs,
        non_claims=REQUIRED_NON_CLAIMS["historical_market_data"],
    )


@dataclass
class _SpyProvider:
    result: ResearchEvidenceResult | None = None
    exc: Exception | None = None

    def __post_init__(self) -> None:
        self.calls: list[ResearchEvidenceRequest] = []

    def provide(self, request: ResearchEvidenceRequest) -> ResearchEvidenceResult:
        self.calls.append(request)
        if self.exc is not None:
            raise self.exc
        return self.result if self.result is not None else ResearchEvidenceResult()


def _concentration(symbol: str = "SPY") -> _Candidate:
    return _Candidate(detector_kind="concentration_high", evidence={"top_symbol": symbol})


class CapabilityRoutingTest(unittest.TestCase):
    def test_concentration_with_top_symbol_builds_request(self) -> None:
        request = build_research_request(_concentration("MSFT"))
        assert request is not None
        self.assertEqual(request.detector_kind, "concentration_high")
        self.assertEqual(request.subject, "MSFT")
        self.assertEqual(request.question, "historical_risk_profile")
        self.assertEqual(request.time_window, RESEARCH_TIME_WINDOW)

    def test_non_concentration_detector_is_not_routed(self) -> None:
        for kind in ("cash_buffer_low", "cash_overweight", "rate_exposure_high", "tax_window"):
            self.assertIsNone(build_research_request(_Candidate(kind, {"top_symbol": "SPY"})))

    def test_concentration_without_top_symbol_is_not_routed(self) -> None:
        self.assertIsNone(build_research_request(_Candidate("concentration_high", {})))
        self.assertIsNone(
            build_research_request(_Candidate("concentration_high", {"top_symbol": "  "}))
        )


class NoopEnricherTest(unittest.TestCase):
    def test_noop_returns_empty_attachment(self) -> None:
        attachment = NoopResearchEnricher().enrich(_concentration())
        self.assertEqual(attachment.items, ())
        self.assertEqual(attachment.data_gaps, ())
        self.assertEqual(attachment.source_refs, ())
        self.assertEqual(attachment.to_evidence_payload(), [])


class ProviderEnricherTest(unittest.TestCase):
    def test_routed_candidate_calls_provider_and_wraps_result(self) -> None:
        item = _evidence_item(source_refs=("data/receipts/market-data/spy.json",))
        spy = _SpyProvider(result=ResearchEvidenceResult(items=(item,)))
        attachment = ProviderResearchEnricher(provider=spy).enrich(_concentration("SPY"))
        self.assertEqual(len(spy.calls), 1)
        self.assertEqual(spy.calls[0].subject, "SPY")
        self.assertEqual(len(attachment.items), 1)
        self.assertEqual(attachment.source_refs, ("data/receipts/market-data/spy.json",))

    def test_unrouted_candidate_never_calls_provider(self) -> None:
        spy = _SpyProvider(result=ResearchEvidenceResult())
        attachment = ProviderResearchEnricher(provider=spy).enrich(
            _Candidate("cash_buffer_low", {"top_symbol": "SPY"})
        )
        self.assertEqual(spy.calls, [])  # routing short-circuits before the provider
        self.assertEqual(attachment.items, ())
        self.assertEqual(attachment.data_gaps, ())

    def test_provider_exception_becomes_sanitized_gap_candidate_still_usable(self) -> None:
        secret = "boom at /home/user/secret/path.py line 42"
        spy = _SpyProvider(exc=RuntimeError(secret))
        attachment = ProviderResearchEnricher(provider=spy).enrich(_concentration())
        self.assertEqual(attachment.items, ())
        self.assertEqual(len(attachment.data_gaps), 1)
        self.assertNotIn(secret, attachment.data_gaps[0])  # raw text never leaks
        self.assertNotIn("/home/user", attachment.data_gaps[0])

    def test_sanitized_gap_passes_re1_redline(self) -> None:
        # The gap must be constructible into a result (RE1 narrow redline holds).
        result = ResearchEvidenceResult(data_gaps=(sanitize_gap(RuntimeError("x")),))
        self.assertTrue(result.data_gaps)


class AttachmentTest(unittest.TestCase):
    def test_payload_is_json_safe_no_pydantic_objects(self) -> None:
        item = _evidence_item()
        attachment = ResearchEvidenceAttachment.from_result(
            ResearchEvidenceResult(items=(item,))
        )
        payload = attachment.to_evidence_payload()
        self.assertIsInstance(payload[0], dict)
        json.dumps(payload)  # must not raise (no pydantic objects leak through)

    def test_advice_gap_is_rejected_at_construction(self) -> None:
        # A rogue/buggy enricher must not be able to smuggle advice text into
        # research_evidence_gaps: the attachment owns the RE1 redline at construction.
        with self.assertRaises((ValueError, ValidationError)):
            ResearchEvidenceAttachment(data_gaps=("buy SPY now",))
        with self.assertRaises((ValueError, ValidationError)):
            ResearchEvidenceAttachment(data_gaps=("execution plan is ready",))

    def test_free_form_source_refs_not_derived_from_items_are_rejected(self) -> None:
        # source_refs may only come from validated item source_refs, never free-form.
        with self.assertRaises(ValueError):
            ResearchEvidenceAttachment(source_refs=("buy SPY now",))
        item = _evidence_item(source_refs=("data/receipts/market-data/spy.json",))
        with self.assertRaises(ValueError):
            ResearchEvidenceAttachment(
                items=(item,), source_refs=("data/receipts/market-data/other.json",)
            )

    def test_data_gap_describing_missing_data_is_allowed(self) -> None:
        # The redline blocks advice, not disclosure: a plain gap constructs fine.
        attachment = ResearchEvidenceAttachment(
            data_gaps=("market history unavailable for SPY.",)
        )
        self.assertTrue(attachment.data_gaps)

    def test_from_result_dedups_source_refs_in_order(self) -> None:
        ref = "data/receipts/market-data/spy.json"
        two = ResearchEvidenceResult(
            items=(_evidence_item(source_refs=(ref,)), _evidence_item(source_refs=(ref,)))
        )
        attachment = ResearchEvidenceAttachment.from_result(two)
        self.assertEqual(attachment.source_refs, (ref,))


if __name__ == "__main__":
    unittest.main()
