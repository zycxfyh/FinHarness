from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finharness import events, hypotheses, interpretation, validation
from finharness.events import CIK_BY_SYMBOL, build_sec_edgar_event_bundle_from_raw
from finharness.hypotheses import build_hypothesis_bundle_from_interpretation_snapshot
from finharness.interpretation import build_interpretation_bundle_from_event_snapshot
from finharness.validation import (
    ValidationCheckResult,
    build_validation_bundle_from_hypothesis_snapshot,
    build_validation_quality,
)
from finharness.validation_graph import run_validation_graph, validation_graph


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
                ],
                "filingDate": ["2026-05-30", "2026-05-20"],
                "reportDate": ["2026-05-30", "2026-03-31"],
                "acceptanceDateTime": [
                    "2026-05-30T16:05:00.000Z",
                    "2026-05-20T16:05:00.000Z",
                ],
                "act": ["34", "34"],
                "form": ["8-K", "10-Q"],
                "fileNumber": ["001", "001"],
                "filmNumber": ["1", "2"],
                "items": ["2.02", ""],
                "primaryDocument": ["filing-8k.htm", "filing-10q.htm"],
                "primaryDocDescription": ["Current report", "Quarterly report"],
            }
        },
    }


def build_sample_hypothesis_bundle(root: Path):
    event_bundle = build_sec_edgar_event_bundle_from_raw(
        {"NVDA": sample_payload("NVDA")},
        universe=["NVDA", "SPY", "QQQ"],
        per_symbol_limit=3,
    )
    interpretation_bundle = build_interpretation_bundle_from_event_snapshot(
        event_bundle.snapshot,
        max_records=2,
        market_snapshot_refs=["market-ref"],
        indicator_snapshot_refs=["indicator-ref"],
    )
    return build_hypothesis_bundle_from_interpretation_snapshot(
        interpretation_bundle.snapshot,
        max_hypotheses=2,
        llm_enabled=True,
        hermes_root="/root/projects/hermes-agent",
    )


class ValidationLayerTest(unittest.TestCase):
    def test_bundle_persists_validation_snapshot_and_receipt(self) -> None:
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
                patch.object(validation, "VALIDATION_NORMALIZED_ROOT", root / "vals"),
                patch.object(validation, "VALIDATION_RECEIPT_ROOT", root / "val_receipts"),
            ):
                hypothesis_bundle = build_sample_hypothesis_bundle(root)
                bundle = build_validation_bundle_from_hypothesis_snapshot(
                    hypothesis_bundle.snapshot,
                    llm_enabled=True,
                    hermes_root="/root/projects/hermes-agent",
                )

                self.assertEqual(bundle.snapshot.job_count, 2)
                self.assertGreater(bundle.snapshot.result_count, 2)
                self.assertTrue(bundle.snapshot.quality.ok)
                self.assertFalse(bundle.snapshot.execution_allowed)
                self.assertEqual(
                    bundle.snapshot.lineage.input_hypothesis_snapshot_id,
                    hypothesis_bundle.snapshot.hypothesis_snapshot_id,
                )
                self.assertEqual(bundle.snapshot.lineage.source.llm_provider, "hermes-agent")
                self.assertTrue(Path(bundle.snapshot.payload_ref).exists())
                self.assertTrue(Path(bundle.snapshot.receipt_ref).exists())

    def test_quality_blocks_execution_language(self) -> None:
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
                hypothesis_bundle = build_sample_hypothesis_bundle(root)
                validation_bundle = build_validation_bundle_from_hypothesis_snapshot(
                    hypothesis_bundle.snapshot,
                )

        bad = validation_bundle.results[0].model_copy(
            update={"limitations": ["ready to trade after this validation"]}
        )
        quality = build_validation_quality(
            snapshot=hypothesis_bundle.snapshot,
            jobs=validation_bundle.jobs,
            results=[bad, *validation_bundle.results[1:]],
        )
        self.assertFalse(quality.ok)
        self.assertFalse(quality.no_proposal_or_execution_language)
        self.assertIn(bad.check_id, quality.blocked_language_hits)

    def test_quality_fails_without_limitations(self) -> None:
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
                hypothesis_bundle = build_sample_hypothesis_bundle(root)
                validation_bundle = build_validation_bundle_from_hypothesis_snapshot(
                    hypothesis_bundle.snapshot,
                )

        bad = ValidationCheckResult.model_validate(
            validation_bundle.results[0].model_dump(mode="json") | {"limitations": []}
        )
        quality = build_validation_quality(
            snapshot=hypothesis_bundle.snapshot,
            jobs=validation_bundle.jobs,
            results=[bad, *validation_bundle.results[1:]],
        )
        self.assertFalse(quality.ok)
        self.assertFalse(quality.limitations_present)
        self.assertIn("limitations", quality.missing_required_fields[bad.check_id])

    def test_validation_graph_compiles(self) -> None:
        self.assertIsNotNone(validation_graph)

    def test_validation_graph_runs_with_hypothesis_snapshot(self) -> None:
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
                patch.object(validation, "VALIDATION_NORMALIZED_ROOT", root / "vals"),
                patch.object(validation, "VALIDATION_RECEIPT_ROOT", root / "val_receipts"),
            ):
                hypothesis_bundle = build_sample_hypothesis_bundle(root)
                result = run_validation_graph(
                    hypothesis_snapshot=hypothesis_bundle.snapshot.model_dump(mode="json"),
                    llm_enabled=True,
                    hermes_root="/root/projects/hermes-agent",
                )

                final = result["final"]
                self.assertEqual(final["workflow"], "langgraph_validation_v1")
                self.assertEqual(final["job_count"], 2)
                self.assertTrue(final["quality_ok"])
                self.assertFalse(final["execution_allowed"])
                self.assertTrue(final["proposal_handoff"])
                self.assertEqual(final["consumer_handoff"]["consumer"], "proposal_review")
                self.assertTrue(final["llm_enabled"])
                self.assertEqual(final["hermes_root"], "/root/projects/hermes-agent")


if __name__ == "__main__":
    unittest.main()
