"""Tests for DataCatalog v0 — read-only visibility over market-data receipts."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finharness.data_catalog import (
    DataCatalogEntry,
    DataGap,
    build_data_catalog,
    default_data_source_registry,
    get_catalog_entry,
)


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


class DataCatalogUnitTest(unittest.TestCase):
    """Pure unit tests — no filesystem, no network."""

    def test_default_registry_includes_yfinance(self) -> None:
        registry = default_data_source_registry()
        providers = {entry.provider for entry in registry}
        self.assertIn("yfinance", providers)

    def test_registry_discloses_bias_controls(self) -> None:
        registry = default_data_source_registry()
        yfinance_entry = next(e for e in registry if e.provider == "yfinance")
        self.assertIn("survivorship_uncontrolled", yfinance_entry.bias_controls)
        self.assertIn("point_in_time_uncontrolled", yfinance_entry.bias_controls)

    def test_registry_execution_allowed_always_false(self) -> None:
        registry = default_data_source_registry()
        for entry in registry:
            self.assertFalse(
                entry.execution_allowed,
                f"{entry.data_source_id} has execution_allowed=True",
            )

    def test_registry_distinct_data_source_ids(self) -> None:
        registry = default_data_source_registry()
        ids = [entry.data_source_id for entry in registry]
        self.assertEqual(len(ids), len(set(ids)))

    def test_gap_model_fields(self) -> None:
        gap = DataGap(
            gap_id="dg_0001",
            severity="critical",
            scope="test",
            message="test gap",
            source_ref="path/here.json",
            blocks=["quality_inspection"],
        )
        self.assertEqual(gap.severity, "critical")
        self.assertIn("quality_inspection", gap.blocks)

    def test_catalog_entry_execution_allowed_always_false(self) -> None:
        entry = DataCatalogEntry(
            dataset_key="yfinance/ohlcv_history/SPY",
            data_source_id="yfinance_equity",
            provider="yfinance",
            asset_class="equity",
            dataset="ohlcv_history",
            symbols=["SPY"],
            fields=["date", "close"],
            timeframe="1-DAY",
            latest_snapshot_id="snap_test",
            latest_as_of_utc="2026-07-01T00:00:00Z",
            latest_receipt_ref="receipts/test.json",
            quality_summary={},
            reconciliation_status="single_source_unreconciled",
            bias_controls=[],
            data_gaps=[],
        )
        self.assertFalse(entry.execution_allowed)


class DataCatalogDiscoveryTest(unittest.TestCase):
    """Tests that exercise receipt discovery with temp directories."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.receipt_root = Path(self.tmp.name) / "receipts"
        self.receipt_root.mkdir(parents=True)
        self.addCleanup(self.tmp.cleanup)

    def _write_receipt(self, filename: str, payload: dict) -> Path:
        path = self.receipt_root / filename
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def test_catalog_read_without_receipt_directory(self) -> None:
        """build_data_catalog gracefully handles missing receipt directory."""
        nonexistent = Path(self.tmp.name) / "nonexistent"
        view = build_data_catalog(nonexistent)
        self.assertEqual(len(view.catalog_entries), 0)
        self.assertTrue(
            any("does not exist" in gap.message for gap in view.data_gaps),
            f"Expected critical gap for missing directory, got: {view.data_gaps}",
        )

    def test_catalog_read_without_receipt_files(self) -> None:
        """build_data_catalog returns gaps when receipt root has no files."""
        view = build_data_catalog(self.receipt_root)
        self.assertEqual(len(view.catalog_entries), 0)
        self.assertTrue(
            any("No market-data receipts found" in g.message for g in view.data_gaps)
        )

    def test_valid_receipt_becomes_catalog_entry(self) -> None:
        payload = _make_receipt_json()
        self._write_receipt("receipt_mds_20260701T000000Z_00000001.json", payload)

        view = build_data_catalog(self.receipt_root)
        self.assertGreaterEqual(len(view.catalog_entries), 1)

        entry = next(
            (e for e in view.catalog_entries if e.provider == "yfinance"),
            None,
        )
        self.assertIsNotNone(entry)
        if entry is not None:
            self.assertEqual(entry.symbols, ["SPY"])
            self.assertEqual(entry.dataset_key, "yfinance/ohlcv_history/SPY")
            self.assertFalse(entry.execution_allowed)

    def test_malformed_receipt_becomes_data_gap(self) -> None:
        bad_path = self.receipt_root / "receipt_mds_20260701T000000Z_bad.json"
        bad_path.write_text("not valid json {{{", encoding="utf-8")

        view = build_data_catalog(self.receipt_root)
        self.assertGreaterEqual(len(view.data_gaps), 1)
        self.assertTrue(
            any("Malformed receipt JSON" in gap.message for gap in view.data_gaps),
            f"Expected malformed receipt gap, got: {view.data_gaps}",
        )

    def test_single_source_unreconciled_is_surfaced_as_gap(self) -> None:
        payload = _make_receipt_json(reconciliation_status="single_source_unreconciled")
        self._write_receipt("receipt_mds_20260701T000000Z_00000001.json", payload)

        view = build_data_catalog(self.receipt_root)
        entry = next(e for e in view.catalog_entries if e.provider == "yfinance")
        self.assertTrue(
            any("unreconciled" in g for g in entry.data_gaps),
            f"Expected unreconciled gap, got: {entry.data_gaps}",
        )

    def test_quality_issues_are_surfaced_as_entry_gaps(self) -> None:
        payload = _make_receipt_json(quality_ok=False)
        self._write_receipt("receipt_mds_20260701T000000Z_00000001.json", payload)

        view = build_data_catalog(self.receipt_root)
        entry = next(e for e in view.catalog_entries if e.provider == "yfinance")
        self.assertTrue(
            any("quality check failed" in g for g in entry.data_gaps),
            f"Expected quality gap, got: {entry.data_gaps}",
        )

    def test_most_recent_receipt_wins_per_dataset_key(self) -> None:
        payload1 = _make_receipt_json(
            snapshot_id="mds_20260701T000000Z_00000001",
            as_of_utc="2026-07-01T00:00:00+00:00",
        )
        payload2 = _make_receipt_json(
            snapshot_id="mds_20260702T000000Z_00000002",
            as_of_utc="2026-07-02T00:00:00+00:00",
        )

        self._write_receipt("receipt_mds_20260701T000000Z_00000001.json", payload1)
        self._write_receipt("receipt_mds_20260702T000000Z_00000002.json", payload2)

        view = build_data_catalog(self.receipt_root)
        entries = [e for e in view.catalog_entries if e.provider == "yfinance"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].latest_snapshot_id, "mds_20260702T000000Z_00000002")

    def test_get_catalog_entry_by_key(self) -> None:
        payload = _make_receipt_json()
        self._write_receipt("receipt_mds_20260701T000000Z_00000001.json", payload)

        entry = get_catalog_entry("yfinance/ohlcv_history/SPY", self.receipt_root)
        self.assertIsNotNone(entry)
        if entry is not None:
            self.assertEqual(entry.provider, "yfinance")

    def test_get_catalog_entry_missing_returns_none(self) -> None:
        entry = get_catalog_entry("nonexistent/key", self.receipt_root)
        self.assertIsNone(entry)

    def test_registry_coverage_gap_when_no_receipt_for_dataset(self) -> None:
        """When registry has entries but no receipts exist, coverage gaps are surfaced."""
        view = build_data_catalog(self.receipt_root)
        self.assertTrue(
            any("No receipt found in the registered dataset" in g.message
                for g in view.data_gaps),
            f"Expected registry coverage gap, got: {view.data_gaps}",
        )


class DataCatalogApiTest(unittest.TestCase):
    """API-level tests via FastAPI ASGI transport."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.receipt_root = Path(self.tmp.name) / "receipts"
        self.receipt_root.mkdir(parents=True)
        self.addCleanup(self.tmp.cleanup)

        from finharness.api.app import create_app

        self.app = create_app(
            market_data_receipt_root=str(self.receipt_root),
        )
        from tests.asgi_test_client import AsgiTestClient

        self.client = AsgiTestClient(self.app)
        self.addCleanup(self.client.close)

    def _write_receipt(self, filename: str, payload: dict) -> Path:
        path = self.receipt_root / filename
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def test_sources_endpoint_returns_registry(self) -> None:
        response = self.client.get("/data/sources")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("sources", body)
        self.assertFalse(body["execution_allowed"])
        sources = body["sources"]
        self.assertGreater(len(sources), 0)
        self.assertEqual(sources[0]["provider"], "yfinance")

    def test_catalog_endpoint_returns_entries(self) -> None:
        payload = _make_receipt_json()
        self._write_receipt("receipt_mds_20260701T000000Z_00000001.json", payload)

        response = self.client.get("/data/catalog")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["execution_allowed"])
        self.assertIn("catalog_entries", body)
        self.assertIn("data_gaps", body)
        self.assertIn("source_refs", body)

    def test_catalog_detail_endpoint(self) -> None:
        payload = _make_receipt_json()
        self._write_receipt("receipt_mds_20260701T000000Z_00000001.json", payload)

        response = self.client.get("/data/catalog/yfinance/ohlcv_history/SPY")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["execution_allowed"])
        self.assertIsNotNone(body["entry"])

    def test_catalog_detail_missing_returns_404(self) -> None:
        response = self.client.get("/data/catalog/nonexistent/key")
        self.assertEqual(response.status_code, 404)

    def test_gaps_endpoint_returns_gaps(self) -> None:
        response = self.client.get("/data/gaps")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["execution_allowed"])
        self.assertIn("data_gaps", body)

    def test_all_data_endpoints_are_read_only(self) -> None:
        """POST should not be allowed on any /data/ path."""
        post_response = self.client.post("/data/catalog", json={})
        self.assertEqual(post_response.status_code, 405)

        patch_response = self.client.patch("/data/catalog", json={})
        self.assertIn(patch_response.status_code, {404, 405})


if __name__ == "__main__":
    unittest.main()
