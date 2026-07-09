"""Tests for research evidence quality evaluator."""

from finharness.research_evidence_evaluator import (
    ResearchEvidenceItem,
    evaluate_research_evidence_quality,
)


class TestResearchEvidenceEvaluator:

    def test_well_structured_evidence_passes(self) -> None:
        items = [
            ResearchEvidenceItem(
                ref="market_data://yfinance/history/AAPL",
                source_type="market_data",
                provider="yfinance",
                recency="2026-07-01",
                evidence_refs=["chart://aapl_daily"],
            )
        ]
        report = evaluate_research_evidence_quality(evidence_items=items)
        assert report.status == "pass"

    def test_missing_source_type_blocks(self) -> None:
        items = [
            ResearchEvidenceItem(ref="unknown://data"),
        ]
        report = evaluate_research_evidence_quality(evidence_items=items)
        assert report.status == "block"
        assert any("source_type" in f.code for f in report.findings)

    def test_missing_provider_warns(self) -> None:
        items = [
            ResearchEvidenceItem(
                ref="market_data://some/path",
                source_type="market_data",
                recency="2026-07-01",
            ),
        ]
        report = evaluate_research_evidence_quality(evidence_items=items)
        assert report.status == "warn"

    def test_unsupported_claim_warns(self) -> None:
        items = [
            ResearchEvidenceItem(
                ref="eval://test",
                source_type="local_eval",
                claim="This strategy beats the market",
                provider="promptfoo",
                recency="2026-07-01",
                evidence_refs=[],
            ),
        ]
        report = evaluate_research_evidence_quality(evidence_items=items)
        assert report.status == "warn"
        assert any("unsupported_claim" in f.code for f in report.findings)

    def test_external_provider_warns(self) -> None:
        items = [
            ResearchEvidenceItem(
                ref="ext://data",
                source_type="external_provider",
                provider="third_party",
                recency="2026-07-01",
            ),
        ]
        report = evaluate_research_evidence_quality(evidence_items=items)
        assert report.status == "warn"
        assert any("external_provider" in f.code for f in report.findings)

    def test_execution_allowed_always_false(self) -> None:
        items = [ResearchEvidenceItem(ref="ok", source_type="market_data")]
        report = evaluate_research_evidence_quality(evidence_items=items)
        assert report.execution_allowed is False
        assert report.authority_transition is False
