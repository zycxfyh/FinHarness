"""Tests for Data Quality API v0 — read-only quality and gaps endpoints."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


def _make_receipt_json(
    *,
    snapshot_id: str = "mds_20260701T000000Z_00000001",
    provider: str = "yfinance",
    upstream_source: str = "Yahoo Finance",
    asset_class: str = "equity",
    dataset: str = "ohlcv_history",
    symbols: list[str] | None = None,
    reconciliation_status: str = "single_source_unreconciled",
    quality_ok: bool = True,
    as_of_utc: str = "2026-07-01T00:00:00+00:00",
) -> dict:
    """Build a minimal valid DataReceipt payload dict."""
    symbols = symbols or ["SPY"]
    return {
        "receipt_id": f"receipt_{snapshot_id}",
        "created_at_utc": "2026-07-01T00:00:00+00:00",
        "kind": "market_data_ingestion",
        "eight_layer_map": {
            "source": provider,
            "ingestion": "api_pull",
            "normalization": "FinHarness OHLCV contract + Nautilus Bar adapter",
            "quality": "MarketDataQuality",
            "storage": "raw JSON + normalized JSON",
            "snapshot": "MarketDataSnapshot",
            "lineage": "MarketDataLineage",
            "consumer": "research",
        },
        "snapshot": {
            "snapshot_id": snapshot_id,
            "as_of_utc": as_of_utc,
            "symbols": symbols,
            "fields": ["date", "open", "high", "low", "close", "volume"],
            "timeframe": "1-DAY",
            "adjusted": False,
            "quality": {
                "ok": quality_ok,
                "row_count": 2,
                "missing_required_columns": [],
                "duplicate_timestamps": 0,
                "null_counts": {},
                "stale": False,
                "outlier_flags": [],
                "notes": [],
                "reconciliation": {
                    "status": reconciliation_status,
                    "reason": "test" if reconciliation_status != "reconciled" else "",
                },
            },
            "lineage": {
                "source": {
                    "provider": provider,
                    "upstream_source": upstream_source,
                    "asset_class": asset_class,
                    "dataset": dataset,
                    "access_method": "api_pull",
                    "wheel": "yfinance",
                    "wheel_version": "test",
                    "adjustment": "raw",
                },
                "fetched_at_utc": "2026-07-01T00:00:00+00:00",
                "fetch_config": {"symbol": symbols[0], "adjustment": "raw"},
                "raw_hash": "abc123",
                "normalized_hash": "def456",
                "transform_version": "finharness.market_data.v1",
                "quality_backend": "pandera",
                "quality_backend_version": "0.31.1",
                "raw_ref": "data/raw/market-data/test.json",
                "normalized_ref": "data/normalized/market-data/test.json",
                "catalog_ref": None,
                "data_bias_controls": [
                    "survivorship_uncontrolled",
                    "point_in_time_uncontrolled",
                ],
            },
            "payload_ref": "data/normalized/market-data/test.json",
            "receipt_ref": f"data/receipts/market-data/receipt_{snapshot_id}.json",
        },
    }


class DataQualityApiTest(unittest.TestCase):
    """API-level tests for /data/quality endpoints."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.receipt_root = Path(self.tmp.name) / "receipts"
        self.receipt_root.mkdir(parents=True)

        from finharness.api.app import create_app

        self.app = create_app(
            market_data_receipt_root=str(self.receipt_root),
        )
        from tests.asgi_test_client import AsgiTestClient

        self.client = AsgiTestClient(self.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.tmp.cleanup)

    def _write_receipt(self, filename: str, payload: dict) -> Path:
        path = self.receipt_root / filename
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def test_quality_list_returns_200(self) -> None:
        payload = _make_receipt_json()
        self._write_receipt("receipt_mds_20260701T000000Z_00000001.json", payload)

        response = self.client.get("/data/quality")
        self.assertEqual(response.status_code, 200)

    def test_quality_list_has_reports_and_gaps(self) -> None:
        payload = _make_receipt_json()
        self._write_receipt("receipt_mds_20260701T000000Z_00000001.json", payload)

        response = self.client.get("/data/quality")
        body = response.json()
        self.assertFalse(body["execution_allowed"])
        self.assertIn("reports", body)
        self.assertIn("data_gaps", body)
        self.assertIn("source_refs", body)

    def test_quality_list_reports_have_required_fields(self) -> None:
        payload = _make_receipt_json()
        self._write_receipt("receipt_mds_20260701T000000Z_00000001.json", payload)

        response = self.client.get("/data/quality")
        body = response.json()
        self.assertGreater(len(body["reports"]), 0)
        report = body["reports"][0]
        for field in (
            "dataset_key", "freshness_status", "quality_status",
            "reconciliation_status", "bias_status", "readiness_status",
            "findings", "blocks",
        ):
            self.assertIn(field, report)
        self.assertFalse(report["execution_allowed"])

    def test_quality_detail_returns_one_report(self) -> None:
        payload = _make_receipt_json()
        self._write_receipt("receipt_mds_20260701T000000Z_00000001.json", payload)

        response = self.client.get("/data/quality/yfinance/ohlcv_history/SPY")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["execution_allowed"])
        self.assertIn("report", body)
        self.assertEqual(
            body["report"]["dataset_key"],
            "yfinance/ohlcv_history/SPY",
        )

    def test_quality_detail_missing_returns_404(self) -> None:
        response = self.client.get("/data/quality/nonexistent/key")
        self.assertEqual(response.status_code, 404)

    def test_missing_receipt_dir_returns_no_reports_not_crash(self) -> None:
        from finharness.api.app import create_app
        from tests.asgi_test_client import AsgiTestClient

        nonexistent = Path(self.tmp.name) / "nonexistent"
        app2 = create_app(market_data_receipt_root=str(nonexistent))
        client2 = AsgiTestClient(app2)
        try:
            response = client2.get("/data/quality")
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["reports"], [])
            self.assertTrue(
                any("does not exist" in g.get("message", "")
                    for g in body["data_gaps"]),
            )
        finally:
            client2.close()

    def test_malformed_receipt_produces_gap_not_crash(self) -> None:
        bad_path = self.receipt_root / "receipt_mds_20260701T000000Z_bad.json"
        bad_path.write_text("not valid json {{{", encoding="utf-8")

        response = self.client.get("/data/quality")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(
            any("Malformed receipt JSON" in g.get("message", "")
                for g in body["data_gaps"]),
        )

    def test_quality_post_returns_405(self) -> None:
        response = self.client.post("/data/quality", json={})
        self.assertEqual(response.status_code, 405)

    def test_quality_patch_returns_405(self) -> None:
        response = self.client.patch("/data/quality", json={})
        self.assertEqual(response.status_code, 405)

    def test_gaps_severity_filter(self) -> None:
        """Malformed receipt produces critical gaps; filter matches."""
        bad_path = self.receipt_root / "receipt_mds_20260701T000000Z_bad.json"
        bad_path.write_text("not valid json {{{", encoding="utf-8")

        response = self.client.get("/data/gaps", params={"severity": "critical"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["execution_allowed"])
        gaps = body["data_gaps"]
        self.assertGreater(len(gaps), 0)
        for gap in gaps:
            self.assertEqual(gap["severity"], "critical")

    def test_gaps_blocks_filter(self) -> None:
        """Malformed receipt produces gaps with catalog_population/quality_inspection blocks."""
        bad_path = self.receipt_root / "receipt_mds_20260701T000000Z_bad.json"
        bad_path.write_text("not valid json {{{", encoding="utf-8")

        response = self.client.get(
            "/data/gaps", params={"blocks": "catalog_population"}
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        gaps = body["data_gaps"]
        self.assertGreater(len(gaps), 0)
        for gap in gaps:
            self.assertIn("catalog_population", gap["blocks"])

    def test_no_network_imports_in_quality_routes(self) -> None:
        import inspect

        import finharness.api.routes_data_quality as r

        source = inspect.getsource(r)
        forbidden = ["yfinance", "openbb", "httpx", "requests", "urllib.request"]
        for token in forbidden:
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
