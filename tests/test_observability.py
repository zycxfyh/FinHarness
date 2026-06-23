from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finharness.observability import (
    OBSERVABILITY_RECEIPT_KIND,
    TRACE_HEADER,
    build_trace_index_receipt,
    is_safe_trace_id,
    local_tracing_config,
    new_trace_id,
    start_local_span,
    trace_context_from_value,
    trace_metadata,
    write_trace_index_receipt,
)


class TraceContextContractTest(unittest.TestCase):
    def test_generated_trace_id_is_bounded(self) -> None:
        trace_id = new_trace_id()

        self.assertTrue(is_safe_trace_id(trace_id))
        self.assertTrue(trace_id.startswith("trace_"))

    def test_safe_supplied_trace_id_is_accepted(self) -> None:
        context = trace_context_from_value(" trace_operator_123 ")

        self.assertEqual(context.trace_id, "trace_operator_123")
        self.assertTrue(context.accepted_supplied)

    def test_malformed_or_secret_like_trace_id_is_replaced(self) -> None:
        for supplied in (
            "trace_bad\nInjected: yes",
            "../trace_escape",
            "Bearer sk-1234567890abcdef",
            "api_key=abc123",
            "",
        ):
            with self.subTest(supplied=supplied):
                context = trace_context_from_value(supplied)
                self.assertTrue(is_safe_trace_id(context.trace_id))
                self.assertNotEqual(context.trace_id, supplied.strip())
                self.assertFalse(context.accepted_supplied)

    def test_trace_metadata_is_json_safe_and_non_authoritative(self) -> None:
        metadata = trace_metadata("trace_test_meta")

        json.dumps(metadata)
        self.assertEqual(metadata["trace_id"], "trace_test_meta")
        self.assertFalse(metadata["execution_allowed"])
        self.assertIn("Not execution authorization.", metadata["non_claims"])


class TraceReceiptIndexTest(unittest.TestCase):
    def test_trace_index_receipt_links_receipts_without_replacing_them(self) -> None:
        payload = build_trace_index_receipt(
            trace_id="trace_receipt_test",
            run_kind="decisions:golden-path",
            receipt_refs=("data/receipts/a.json", "data/receipts/b.json"),
            created_at_utc="2026-06-23T00:00:00+00:00",
        )

        self.assertEqual(payload["kind"], OBSERVABILITY_RECEIPT_KIND)
        self.assertEqual(payload["trace"]["trace_id"], "trace_receipt_test")
        self.assertEqual(
            payload["trace"]["receipt_refs"],
            ["data/receipts/a.json", "data/receipts/b.json"],
        )
        self.assertEqual(payload["source_refs"], payload["trace"]["receipt_refs"])
        self.assertTrue(payload["content_hash"])
        self.assertFalse(payload["governance"]["execution_allowed"])
        self.assertIn("Trace indexes receipts", payload["governance"]["non_claims"][0])

    def test_trace_index_receipt_sanitizes_secret_like_gaps(self) -> None:
        payload = build_trace_index_receipt(
            trace_id="trace_gap_test",
            run_kind="decisions:golden-path",
            receipt_refs=(),
            data_gaps=("api_key=abc123 leaked in upstream error",),
            created_at_utc="2026-06-23T00:00:00+00:00",
        )

        self.assertEqual(
            payload["trace"]["data_gaps"],
            ["sensitive-looking observability detail redacted"],
        )

    def test_write_trace_index_receipt_persists_bounded_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt_ref = write_trace_index_receipt(
                trace_id="trace_write_test",
                run_kind="decisions:golden-path",
                receipt_refs=("data/receipts/a.json",),
                receipt_root=Path(tmp) / "observability",
            )
            payload = json.loads(Path(receipt_ref).read_text(encoding="utf-8"))

        self.assertEqual(payload["kind"], OBSERVABILITY_RECEIPT_KIND)
        self.assertEqual(payload["trace"]["trace_id"], "trace_write_test")
        self.assertEqual(payload["trace"]["receipt_refs"], ["data/receipts/a.json"])


class LocalOpenTelemetryAdapterTest(unittest.TestCase):
    def test_local_tracing_config_has_no_exporter_or_network(self) -> None:
        config = local_tracing_config()

        self.assertEqual(config["provider"], "opentelemetry-sdk-local")
        self.assertFalse(config["exporter_configured"])
        self.assertFalse(config["network_export_allowed"])
        self.assertFalse(config["execution_allowed"])

    def test_local_span_uses_bounded_finharness_attributes(self) -> None:
        with start_local_span(
            "finharness.test",
            trace_id="trace_span_test",
            attributes={
                "http.request.method": "GET",
                "url.path": "/health",
                "payload": {"raw": "ignored"},
                "finharness.note": "Bearer sk-1234567890abcdef",
            },
        ) as span:
            attributes = dict(span.attributes or {})
            self.assertTrue(span.is_recording())

        self.assertEqual(attributes["finharness.trace_id"], "trace_span_test")
        self.assertEqual(attributes["http.request.method"], "GET")
        self.assertEqual(attributes["url.path"], "/health")
        self.assertNotIn("payload", attributes)
        self.assertEqual(
            attributes["finharness.note"],
            "sensitive-looking attribute redacted",
        )


class TraceHeaderConstantTest(unittest.TestCase):
    def test_trace_header_constant_is_stable(self) -> None:
        self.assertEqual(TRACE_HEADER, "X-FinHarness-Trace-Id")


if __name__ == "__main__":
    unittest.main()
