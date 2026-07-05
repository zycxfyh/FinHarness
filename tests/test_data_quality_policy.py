"""Tests for DataQualityPolicy v0 — structured quality, freshness, bias, readiness."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from finharness.data_quality_policy import (
    DataQualityFinding,
    DataQualityReport,
    FreshnessPolicy,
    assess_bias,
    assess_freshness,
    assess_quality,
    assess_reconciliation,
    build_quality_report,
    compute_readiness,
)
from finharness.market_data import MarketDataQuality


def _fresh_quality() -> MarketDataQuality:
    return MarketDataQuality(
        ok=True,
        row_count=100,
        missing_required_columns=[],
        duplicate_timestamps=0,
        null_counts={},
        stale=False,
        outlier_flags=[],
        notes=[],
    )


def _degraded_quality() -> MarketDataQuality:
    return MarketDataQuality(
        ok=False,
        row_count=10,
        missing_required_columns=["volume"],
        duplicate_timestamps=3,
        null_counts={"close": 2},
        stale=False,
        outlier_flags=["high_below_low"],
        notes=["multiple quality issues"],
    )


class FreshnessAssessmentTest(unittest.TestCase):
    def test_fresh_data_is_fresh(self) -> None:
        recent = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        status, findings, blocks = assess_freshness(recent)
        self.assertEqual(status, "fresh")
        self.assertEqual(findings, [])
        self.assertEqual(blocks, [])

    def test_stale_data_returns_warning(self) -> None:
        old = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        policy = FreshnessPolicy(stale_after_days=5, critical_after_days=30)
        status, findings, blocks = assess_freshness(old, policy=policy)
        self.assertEqual(status, "stale")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "warning")
        self.assertEqual(findings[0].code, "stale")
        self.assertEqual(blocks, [])

    def test_critically_stale_data_returns_critical_and_blocks(self) -> None:
        ancient = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        policy = FreshnessPolicy(stale_after_days=5, critical_after_days=30)
        status, findings, blocks = assess_freshness(ancient, policy=policy)
        self.assertEqual(status, "critically_stale")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "critical")
        self.assertEqual(findings[0].code, "critically_stale")
        self.assertIn("research", blocks)
        self.assertIn("execution", blocks)

    def test_unparseable_as_of_utc_returns_unknown(self) -> None:
        status, findings, blocks = assess_freshness("not-a-date")
        self.assertEqual(status, "unknown")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].code, "freshness_unknown")
        self.assertIn("freshness_assessment", blocks)

    def test_default_policy_used_when_none_provided(self) -> None:
        old = (datetime.now(UTC) - timedelta(days=7)).isoformat()
        status, findings, _blocks = assess_freshness(old)
        self.assertEqual(status, "stale")
        self.assertEqual(findings[0].severity, "warning")

    def test_future_as_of_utc_returns_critical_finding_and_blocks(self) -> None:
        future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
        status, findings, blocks = assess_freshness(future)
        self.assertEqual(status, "unknown")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "critical")
        self.assertEqual(findings[0].code, "future_timestamp")
        self.assertIn("freshness_assessment", blocks)


class QualityAssessmentTest(unittest.TestCase):
    def test_ok_quality_returns_ok(self) -> None:
        status, findings = assess_quality(_fresh_quality())
        self.assertEqual(status, "ok")
        self.assertEqual(findings, [])

    def test_degraded_quality_returns_degraded_with_finding(self) -> None:
        status, findings = assess_quality(_degraded_quality())
        self.assertEqual(status, "degraded")
        self.assertGreaterEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "warning")
        self.assertEqual(findings[0].code, "quality_degraded")


class ReconciliationAssessmentTest(unittest.TestCase):
    def test_single_source_unreconciled_returns_warning(self) -> None:
        status, findings = assess_reconciliation("single_source_unreconciled")
        self.assertEqual(status, "single_source_unreconciled")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, "warning")
        self.assertEqual(findings[0].code, "single_source_unreconciled")

    def test_reconciled_returns_no_findings(self) -> None:
        status, findings = assess_reconciliation("reconciled")
        self.assertEqual(status, "reconciled")
        self.assertEqual(findings, [])

    def test_unknown_status_passes_through(self) -> None:
        status, findings = assess_reconciliation("unknown")
        self.assertEqual(status, "unknown")
        self.assertEqual(findings, [])


class BiasAssessmentTest(unittest.TestCase):
    def test_no_bias_controls_returns_controlled(self) -> None:
        status, findings = assess_bias([])
        self.assertEqual(status, "controlled")
        self.assertEqual(findings, [])

    def test_survivorship_uncontrolled_returns_warning(self) -> None:
        status, findings = assess_bias(["survivorship_uncontrolled"])
        self.assertEqual(status, "uncontrolled")
        self.assertEqual(len(findings), 1)
        self.assertIn("survivorship", findings[0].message)

    def test_point_in_time_uncontrolled_returns_warning(self) -> None:
        status, findings = assess_bias(["point_in_time_uncontrolled"])
        self.assertEqual(status, "uncontrolled")
        self.assertEqual(len(findings), 1)
        self.assertIn("point-in-time", findings[0].message)

    def test_both_uncontrolled_returns_two_findings(self) -> None:
        status, findings = assess_bias(
            ["survivorship_uncontrolled", "point_in_time_uncontrolled"]
        )
        self.assertEqual(status, "uncontrolled")
        self.assertEqual(len(findings), 2)


class ReadinessTest(unittest.TestCase):
    def test_all_clear_returns_usable(self) -> None:
        status = compute_readiness("fresh", "ok", "controlled", "reconciled")
        self.assertEqual(status, "usable")

    def test_stale_only_returns_usable_with_warnings(self) -> None:
        status = compute_readiness(
            "stale", "ok", "controlled", "reconciled"
        )
        self.assertEqual(status, "usable_with_warnings")

    def test_unreconciled_only_returns_usable_with_warnings(self) -> None:
        status = compute_readiness(
            "fresh", "ok", "controlled", "single_source_unreconciled"
        )
        self.assertEqual(status, "usable_with_warnings")

    def test_critically_stale_returns_not_ready(self) -> None:
        status = compute_readiness(
            "critically_stale", "ok", "controlled", "reconciled"
        )
        self.assertEqual(status, "not_ready")

    def test_unknown_freshness_returns_not_ready(self) -> None:
        status = compute_readiness("unknown", "ok", "controlled", "reconciled")
        self.assertEqual(status, "not_ready")

    def test_degraded_quality_returns_usable_with_warnings(self) -> None:
        status = compute_readiness("fresh", "degraded", "controlled", "reconciled")
        self.assertEqual(status, "usable_with_warnings")


class QualityReportTest(unittest.TestCase):
    def test_build_report_integrates_all_dimensions(self) -> None:
        q = _fresh_quality()
        report = build_quality_report(
            dataset_key="yfinance/ohlcv_history/SPY",
            as_of_utc=(datetime.now(UTC) - timedelta(hours=2)).isoformat(),
            latest_receipt_ref="data/receipts/market-data/test.json",
            quality=q,
            reconciliation_status="reconciled",
            bias_controls=[],
        )
        self.assertEqual(report.freshness_status, "fresh")
        self.assertEqual(report.quality_status, "ok")
        self.assertEqual(report.bias_status, "controlled")
        self.assertEqual(report.reconciliation_status, "reconciled")
        self.assertEqual(report.readiness_status, "usable")
        self.assertEqual(report.findings, [])

    def test_build_report_with_warnings(self) -> None:
        q = _fresh_quality()
        report = build_quality_report(
            dataset_key="yfinance/ohlcv_history/SPY",
            as_of_utc=(datetime.now(UTC) - timedelta(days=7)).isoformat(),
            latest_receipt_ref="data/receipts/market-data/test.json",
            quality=q,
            reconciliation_status="single_source_unreconciled",
            bias_controls=["survivorship_uncontrolled"],
        )
        self.assertEqual(report.freshness_status, "stale")
        self.assertEqual(report.readiness_status, "usable_with_warnings")
        self.assertGreater(len(report.findings), 1)

    def test_build_report_critically_stale_blocks(self) -> None:
        q = _fresh_quality()
        report = build_quality_report(
            dataset_key="yfinance/ohlcv_history/SPY",
            as_of_utc=(datetime.now(UTC) - timedelta(days=60)).isoformat(),
            latest_receipt_ref="data/receipts/market-data/test.json",
            quality=q,
            reconciliation_status="reconciled",
            bias_controls=[],
        )
        self.assertEqual(report.freshness_status, "critically_stale")
        self.assertEqual(report.readiness_status, "not_ready")
        self.assertIn("research", report.blocks)


class ModelInvariantTest(unittest.TestCase):
    """All new models must have execution_allowed=False."""

    def test_freshness_policy_execution_allowed_false(self) -> None:
        self.assertFalse(FreshnessPolicy().execution_allowed)

    def test_data_quality_finding_has_no_execution_allowed(self) -> None:
        finding = DataQualityFinding(
            finding_id="f_0001",
            severity="info",
            code="test",
            message="test",
        )
        self.assertNotIn("execution_allowed", finding.model_fields)

    def test_data_quality_report_execution_allowed_false(self) -> None:
        report = DataQualityReport(
            report_id="qr_test",
            dataset_key="test/key",
            as_of_utc="2026-01-01T00:00:00Z",
            latest_receipt_ref="test.json",
        )
        self.assertFalse(report.execution_allowed)


class NoNetworkTest(unittest.TestCase):
    """New module must not import network libraries."""

    def test_no_network_imports(self) -> None:
        import inspect

        import finharness.data_quality_policy as dqp

        source = inspect.getsource(dqp)
        forbidden = ["yfinance", "openbb", "httpx", "requests", "urllib.request"]
        for token in forbidden:
            self.assertNotIn(
                token,
                source,
                f"Network library '{token}' found in data_quality_policy.py",
            )


if __name__ == "__main__":
    unittest.main()
