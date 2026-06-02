from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finharness import events, hypotheses, interpretation
from finharness.events import CIK_BY_SYMBOL, build_sec_edgar_event_bundle_from_raw
from finharness.hypotheses import (
    HypothesisRecord,
    build_hypothesis_bundle_from_interpretation_snapshot,
    build_hypothesis_quality,
    formulate_hypothesis_record,
)
from finharness.hypotheses_graph import hypotheses_graph, run_hypotheses_graph
from finharness.interpretation import build_interpretation_bundle_from_event_snapshot


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
                ],
                "filingDate": ["2026-05-30", "2026-05-20", "2026-05-10"],
                "reportDate": ["2026-05-30", "2026-03-31", "2025-12-31"],
                "acceptanceDateTime": [
                    "2026-05-30T16:05:00.000Z",
                    "2026-05-20T16:05:00.000Z",
                    "2026-05-10T16:05:00.000Z",
                ],
                "act": ["34", "34", "34"],
                "form": ["8-K", "10-Q", "10-K"],
                "fileNumber": ["001", "001", "001"],
                "filmNumber": ["1", "2", "3"],
                "items": ["2.02", "", ""],
                "primaryDocument": ["filing-8k.htm", "filing-10q.htm", "filing-10k.htm"],
                "primaryDocDescription": ["Current report", "Quarterly report", "Annual report"],
            }
        },
    }


class HypothesesLayerTest(unittest.TestCase):
    def test_quality_blocks_recommendation_language(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(events, "EVENT_RAW_ROOT", root / "events_raw"),
                patch.object(events, "EVENT_NORMALIZED_ROOT", root / "events_normalized"),
                patch.object(events, "EVENT_RECEIPT_ROOT", root / "events_receipts"),
                patch.object(interpretation, "INTERPRETATION_NORMALIZED_ROOT", root / "ints"),
                patch.object(interpretation, "INTERPRETATION_RECEIPT_ROOT", root / "int_receipts"),
            ):
                event_bundle = build_sec_edgar_event_bundle_from_raw(
                    {"NVDA": sample_payload("NVDA")},
                    universe=["NVDA", "SPY", "QQQ"],
                    per_symbol_limit=4,
                )
                interpretation_bundle = build_interpretation_bundle_from_event_snapshot(
                    event_bundle.snapshot,
                    max_records=1,
                )
                record = formulate_hypothesis_record(interpretation_bundle.records[0])

        bad = record.model_copy(update={"hypothesis": "This is a buy signal for NVDA."})
        quality = build_hypothesis_quality([bad])
        self.assertFalse(quality.ok)
        self.assertFalse(quality.no_recommendation_language)
        self.assertIn(bad.hypothesis_id, quality.blocked_language_hits)

    def test_quality_fails_without_disconfirming_observations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(events, "EVENT_RAW_ROOT", root / "events_raw"),
                patch.object(events, "EVENT_NORMALIZED_ROOT", root / "events_normalized"),
                patch.object(events, "EVENT_RECEIPT_ROOT", root / "events_receipts"),
                patch.object(interpretation, "INTERPRETATION_NORMALIZED_ROOT", root / "ints"),
                patch.object(interpretation, "INTERPRETATION_RECEIPT_ROOT", root / "int_receipts"),
            ):
                event_bundle = build_sec_edgar_event_bundle_from_raw(
                    {"AAPL": sample_payload("AAPL")},
                    universe=["AAPL", "SPY", "QQQ"],
                    per_symbol_limit=4,
                )
                interpretation_bundle = build_interpretation_bundle_from_event_snapshot(
                    event_bundle.snapshot,
                    max_records=1,
                )
                record = formulate_hypothesis_record(interpretation_bundle.records[0])

        bad = HypothesisRecord.model_validate(
            record.model_dump(mode="json") | {"disconfirming_observations": []}
        )
        quality = build_hypothesis_quality([bad])
        self.assertFalse(quality.ok)
        self.assertFalse(quality.disconfirming_evidence_present)
        self.assertIn(
            "disconfirming_observations",
            quality.missing_required_fields[bad.hypothesis_id],
        )

    def test_bundle_persists_hypothesis_snapshot_and_receipt(self) -> None:
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
            ):
                event_bundle = build_sec_edgar_event_bundle_from_raw(
                    {"NVDA": sample_payload("NVDA")},
                    universe=["NVDA", "SPY", "QQQ"],
                    per_symbol_limit=4,
                )
                interpretation_bundle = build_interpretation_bundle_from_event_snapshot(
                    event_bundle.snapshot,
                    max_records=2,
                    market_snapshot_refs=["market-ref"],
                    indicator_snapshot_refs=["indicator-ref"],
                )
                bundle = build_hypothesis_bundle_from_interpretation_snapshot(
                    interpretation_bundle.snapshot,
                    max_hypotheses=2,
                    llm_enabled=True,
                    hermes_root="/root/projects/hermes-agent",
                )

                self.assertEqual(bundle.snapshot.record_count, 2)
                self.assertTrue(bundle.snapshot.quality.ok)
                self.assertFalse(bundle.snapshot.execution_allowed)
                self.assertEqual(
                    bundle.snapshot.lineage.input_interpretation_snapshot_id,
                    interpretation_bundle.snapshot.interpretation_snapshot_id,
                )
                self.assertEqual(bundle.snapshot.lineage.market_snapshot_refs, ["market-ref"])
                self.assertEqual(bundle.snapshot.lineage.indicator_snapshot_refs, ["indicator-ref"])
                self.assertEqual(bundle.snapshot.lineage.source.llm_provider, "hermes-agent")
                self.assertTrue(Path(bundle.snapshot.payload_ref).exists())
                self.assertTrue(Path(bundle.snapshot.receipt_ref).exists())

    def test_hypotheses_graph_compiles(self) -> None:
        self.assertIsNotNone(hypotheses_graph)

    def test_hypotheses_graph_runs_with_interpretation_snapshot(self) -> None:
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
            ):
                event_bundle = build_sec_edgar_event_bundle_from_raw(
                    {"MSFT": sample_payload("MSFT")},
                    universe=["MSFT", "SPY", "QQQ"],
                    per_symbol_limit=4,
                )
                interpretation_bundle = build_interpretation_bundle_from_event_snapshot(
                    event_bundle.snapshot,
                    max_records=3,
                )
                result = run_hypotheses_graph(
                    interpretation_snapshot=interpretation_bundle.snapshot.model_dump(mode="json"),
                    max_hypotheses=3,
                    llm_enabled=True,
                    hermes_root="/root/projects/hermes-agent",
                )

                final = result["final"]
                self.assertEqual(final["workflow"], "langgraph_hypotheses_v1")
                self.assertEqual(final["record_count"], 3)
                self.assertTrue(final["quality_ok"])
                self.assertFalse(final["execution_allowed"])
                self.assertTrue(final["validation_handoff"])
                self.assertEqual(final["consumer_handoff"]["consumer"], "validation_layer")
                self.assertTrue(final["llm_enabled"])
                self.assertEqual(final["hermes_root"], "/root/projects/hermes-agent")


if __name__ == "__main__":
    unittest.main()
