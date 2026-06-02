from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finharness import events, interpretation
from finharness.events import CIK_BY_SYMBOL, build_sec_edgar_event_bundle_from_raw
from finharness.interpretation import (
    InterpretationRecord,
    build_interpretation_bundle_from_event_snapshot,
    build_interpretation_quality,
    find_execution_language,
)
from finharness.interpretation_graph import interpretation_graph, run_interpretation_graph


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


class InterpretationLayerTest(unittest.TestCase):
    def test_quality_blocks_execution_language(self) -> None:
        record = InterpretationRecord(
            interpretation_id="interp_test",
            event_ids=["event_1"],
            symbol="NVDA",
            source_facts=["NVDA filed 10-Q."],
            claim="This event may affect revenue over a quarters horizon.",
            evidence_refs=["event_1", "raw.json"],
            inference="Source-backed filing metadata points to a review question.",
            impact_paths=["revenue"],
            affected_exposures=["single_name:NVDA"],
            horizon="quarters",
            sentiment_label="unknown",
            confidence="low",
            materiality="medium",
            expectation_status="needs_human_review",
            counterevidence=["The filing may not introduce new information."],
            watch_questions=["What later filing would falsify this?"],
            scenario_base="Monitor the filing as context.",
            scenario_bull="Confirming evidence would strengthen the interpretation.",
            scenario_bear="Weak follow-through would weaken the interpretation.",
            created_at_utc="2026-06-01T00:00:00+00:00",
        )
        bad = record.model_copy(update={"claim": "This says buy NVDA."})

        self.assertEqual(find_execution_language(record.claim), [])
        quality = build_interpretation_quality([bad])
        self.assertFalse(quality.ok)
        self.assertFalse(quality.no_execution_language)

    def test_bundle_persists_source_backed_interpretation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(events, "EVENT_RAW_ROOT", root / "events_raw"),
                patch.object(events, "EVENT_NORMALIZED_ROOT", root / "events_normalized"),
                patch.object(events, "EVENT_RECEIPT_ROOT", root / "events_receipts"),
                patch.object(interpretation, "INTERPRETATION_NORMALIZED_ROOT", root / "normalized"),
                patch.object(interpretation, "INTERPRETATION_RECEIPT_ROOT", root / "receipts"),
            ):
                event_bundle = build_sec_edgar_event_bundle_from_raw(
                    {"NVDA": sample_payload("NVDA")},
                    universe=["NVDA", "SPY", "QQQ"],
                    per_symbol_limit=4,
                )
                bundle = build_interpretation_bundle_from_event_snapshot(
                    event_bundle.snapshot,
                    max_records=2,
                )

                self.assertEqual(bundle.snapshot.record_count, 2)
                self.assertTrue(bundle.snapshot.quality.ok)
                self.assertFalse(bundle.snapshot.execution_allowed)
                self.assertEqual(
                    bundle.snapshot.lineage.input_event_snapshot_id,
                    event_bundle.snapshot.snapshot_id,
                )
                self.assertTrue(Path(bundle.snapshot.payload_ref).exists())
                receipt_path = root / "receipts" / f"{bundle.receipt.receipt_id}.json"
                self.assertTrue(receipt_path.exists())
                self.assertTrue(bundle.snapshot.hypothesis_candidates)

    def test_bundle_records_linked_market_and_indicator_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(events, "EVENT_RAW_ROOT", root / "events_raw"),
                patch.object(events, "EVENT_NORMALIZED_ROOT", root / "events_normalized"),
                patch.object(events, "EVENT_RECEIPT_ROOT", root / "events_receipts"),
                patch.object(interpretation, "INTERPRETATION_NORMALIZED_ROOT", root / "normalized"),
                patch.object(interpretation, "INTERPRETATION_RECEIPT_ROOT", root / "receipts"),
            ):
                event_bundle = build_sec_edgar_event_bundle_from_raw(
                    {"NVDA": sample_payload("NVDA")},
                    universe=["NVDA", "SPY", "QQQ"],
                    per_symbol_limit=4,
                )
                bundle = build_interpretation_bundle_from_event_snapshot(
                    event_bundle.snapshot,
                    max_records=1,
                    market_snapshot_refs=["market-ref"],
                    indicator_snapshot_refs=["indicator-ref"],
                )

        self.assertEqual(bundle.snapshot.lineage.market_snapshot_refs, ["market-ref"])
        self.assertEqual(bundle.snapshot.lineage.indicator_snapshot_refs, ["indicator-ref"])

    def test_interpretation_graph_compiles(self) -> None:
        self.assertIsNotNone(interpretation_graph)

    def test_interpretation_graph_runs_with_event_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (
                patch.object(events, "EVENT_RAW_ROOT", root / "events_raw"),
                patch.object(events, "EVENT_NORMALIZED_ROOT", root / "events_normalized"),
                patch.object(events, "EVENT_RECEIPT_ROOT", root / "events_receipts"),
                patch.object(interpretation, "INTERPRETATION_NORMALIZED_ROOT", root / "normalized"),
                patch.object(interpretation, "INTERPRETATION_RECEIPT_ROOT", root / "receipts"),
            ):
                event_bundle = build_sec_edgar_event_bundle_from_raw(
                    {"AAPL": sample_payload("AAPL")},
                    universe=["AAPL", "SPY", "QQQ"],
                    per_symbol_limit=4,
                )
                result = run_interpretation_graph(
                    event_snapshot=event_bundle.snapshot.model_dump(mode="json"),
                    max_records=3,
                )

                final = result["final"]
                self.assertEqual(final["workflow"], "langgraph_interpretation_v1")
                self.assertEqual(final["record_count"], 3)
                self.assertTrue(final["quality_ok"])
                self.assertFalse(final["execution_allowed"])
                self.assertEqual(
                    final["consumer_handoff"]["consumer"],
                    "hypothesis_review_risk_note",
                )
                self.assertEqual(final["review_hook"]["status"], "open")


if __name__ == "__main__":
    unittest.main()
