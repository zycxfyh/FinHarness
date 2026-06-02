from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finharness import events
from finharness.events import (
    CIK_BY_SYMBOL,
    build_event_quality,
    build_sec_edgar_event_bundle_from_raw,
    normalize_sec_edgar_records,
)
from finharness.events_graph import events_graph, run_events_graph


def sample_payload(symbol: str) -> dict[str, object]:
    cik = CIK_BY_SYMBOL[symbol]
    return {
        "cik": cik,
        "name": f"{symbol} Sample Company",
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0000000000-26-000001",
                    "0000000000-26-000002",
                    "0000000000-26-000003",
                    "0000000000-26-000004",
                ],
                "filingDate": ["2026-05-30", "2026-05-20", "2026-05-10", "2026-05-01"],
                "reportDate": ["2026-05-30", "2026-03-31", "2025-12-31", "2026-05-01"],
                "acceptanceDateTime": [
                    "2026-05-30T16:05:00.000Z",
                    "2026-05-20T16:05:00.000Z",
                    "2026-05-10T16:05:00.000Z",
                    "2026-05-01T16:05:00.000Z",
                ],
                "act": ["34", "34", "34", "34"],
                "form": ["8-K", "10-Q", "10-K", "4"],
                "fileNumber": ["001", "001", "001", "001"],
                "filmNumber": ["1", "2", "3", "4"],
                "items": ["2.02", "", "", ""],
                "primaryDocument": ["aapl-8k.htm", "aapl-10q.htm", "aapl-10k.htm", "aapl-4.htm"],
                "primaryDocDescription": [
                    "Current report",
                    "Quarterly report",
                    "Annual report",
                    "Insider filing",
                ],
            }
        },
    }


class EventsLayerTest(unittest.TestCase):
    def test_normalizes_sec_records_and_filters_forms(self) -> None:
        records = normalize_sec_edgar_records(
            {"AAPL": sample_payload("AAPL")},
            forms=["8-K", "10-Q", "10-K"],
        )

        self.assertEqual([record.event_type for record in records], ["8-K", "10-Q", "10-K"])
        self.assertEqual(records[0].entities[0].ticker, "AAPL")
        self.assertEqual(records[0].entities[0].cik, CIK_BY_SYMBOL["AAPL"])
        self.assertFalse(records[0].parsed_ref)
        self.assertIn("Archives/edgar/data", records[0].source_url)

    def test_quality_enforces_execution_boundary(self) -> None:
        records = normalize_sec_edgar_records({"MSFT": sample_payload("MSFT")})
        quality = build_event_quality(records)

        self.assertTrue(quality.ok)
        self.assertEqual(quality.record_count, 3)
        self.assertEqual(quality.duplicate_count, 0)
        self.assertFalse(quality.execution_allowed)
        self.assertEqual(quality.mapping_confidence_min, 1.0)

    def test_bundle_persists_snapshot_receipt_and_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(events, "EVENT_RAW_ROOT", root / "raw"),
                patch.object(events, "EVENT_NORMALIZED_ROOT", root / "normalized"),
                patch.object(events, "EVENT_RECEIPT_ROOT", root / "receipts"),
            ):
                bundle = build_sec_edgar_event_bundle_from_raw(
                    {"AAPL": sample_payload("AAPL")},
                    universe=["AAPL", "SPY", "QQQ"],
                    per_symbol_limit=4,
                )

                self.assertEqual(bundle.snapshot.filing_symbols, ["AAPL"])
                self.assertEqual(bundle.snapshot.context_symbols, ["SPY", "QQQ"])
                self.assertFalse(bundle.snapshot.execution_allowed)
                self.assertTrue(Path(bundle.snapshot.payload_ref).exists())
                receipt_path = root / "receipts" / f"{bundle.receipt.receipt_id}.json"
                self.assertTrue(receipt_path.exists())
                self.assertTrue(bundle.snapshot.review_questions)

    def test_bundle_records_linked_market_and_indicator_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(events, "EVENT_RAW_ROOT", root / "raw"),
                patch.object(events, "EVENT_NORMALIZED_ROOT", root / "normalized"),
                patch.object(events, "EVENT_RECEIPT_ROOT", root / "receipts"),
            ):
                records = normalize_sec_edgar_records({"AAPL": sample_payload("AAPL")})
                source = events.EventSourceSpec(fetch_config={"universe": ["AAPL", "SPY"]})
                bundle = events.persist_event_bundle(
                    source=source,
                    raw_payloads={"AAPL": sample_payload("AAPL")},
                    records=records,
                    universe=["AAPL", "SPY"],
                    filing_symbols=["AAPL"],
                    context_symbols=["SPY"],
                    linked_market_snapshot_refs=["market-ref"],
                    linked_indicator_snapshot_refs=["indicator-ref"],
                )

        self.assertEqual(bundle.snapshot.lineage.linked_market_snapshot_refs, ["market-ref"])
        self.assertEqual(
            bundle.snapshot.lineage.linked_indicator_snapshot_refs,
            ["indicator-ref"],
        )

    def test_events_graph_compiles(self) -> None:
        self.assertIsNotNone(events_graph)

    def test_events_graph_runs_with_mocked_fetch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(events, "EVENT_RAW_ROOT", root / "raw"),
                patch.object(events, "EVENT_NORMALIZED_ROOT", root / "normalized"),
                patch.object(events, "EVENT_RECEIPT_ROOT", root / "receipts"),
                patch(
                    "finharness.events_graph.fetch_sec_edgar_raw_payloads",
                    return_value={"AAPL": sample_payload("AAPL")},
                ),
            ):
                result = run_events_graph(
                    universe=["AAPL", "SPY", "QQQ"],
                    forms=["8-K", "10-Q", "10-K"],
                    per_symbol_limit=4,
                )

                final = result["final"]
                self.assertEqual(final["workflow"], "langgraph_events_sec_edgar_v1")
                self.assertEqual(final["filing_symbols"], ["AAPL"])
                self.assertEqual(final["context_symbols"], ["SPY", "QQQ"])
                self.assertEqual(final["event_count"], 3)
                self.assertFalse(final["execution_allowed"])
                self.assertTrue(final["receipt_ref"])
                self.assertEqual(
                    final["consumer_handoff"]["consumer"],
                    "daily_virtual_training_review",
                )
                self.assertEqual(final["review_hook"]["status"], "open")


if __name__ == "__main__":
    unittest.main()
