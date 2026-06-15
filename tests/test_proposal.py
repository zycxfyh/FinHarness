from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finharness import events, hypotheses, interpretation, proposal, validation
from finharness.events import CIK_BY_SYMBOL, build_sec_edgar_event_bundle_from_raw
from finharness.hypotheses import build_hypothesis_bundle_from_interpretation_snapshot
from finharness.interpretation import build_interpretation_bundle_from_event_snapshot
from finharness.proposal import (
    ProposalCandidate,
    build_proposal_bundle_from_validation_snapshot,
    build_proposal_quality,
    classify_action_type,
)
from finharness.proposal_graph import proposal_graph, run_proposal_graph
from finharness.validation import (
    ValidationCheckResult,
    build_validation_bundle_from_hypothesis_snapshot,
)


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


def build_sample_validation_bundle():
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
    hypothesis_bundle = build_hypothesis_bundle_from_interpretation_snapshot(
        interpretation_bundle.snapshot,
        max_hypotheses=2,
    )
    return build_validation_bundle_from_hypothesis_snapshot(hypothesis_bundle.snapshot)


class ProposalLayerTest(unittest.TestCase):
    def test_backtest_result_does_not_drive_action_classification(self) -> None:
        base = ValidationCheckResult(
            check_id="valchk_source",
            validation_job_id="valjob_1",
            hypothesis_id="hyp_1",
            check_type="source_validity",
            input_refs=["source-ref"],
            method="source_ref_presence_check",
            window="2026",
            metrics={},
            result="supported",
            supports_hypothesis=True,
            disconfirms_hypothesis=False,
            confidence="medium",
            limitations=["Source-link presence does not prove materiality."],
            created_at_utc="2026-06-15T00:00:00+00:00",
        )
        missing_market = base.model_copy(
            update={
                "check_id": "valchk_market",
                "check_type": "event_reaction",
                "input_refs": [],
                "method": "event_reaction_input_availability_check",
                "result": "not_testable",
                "supports_hypothesis": False,
                "confidence": "low",
            }
        )
        backtest = base.model_copy(
            update={
                "check_id": "valchk_backtest",
                "check_type": "backtest",
                "method": "vectorbt.Portfolio.from_signals",
                "result": "supported",
                "confidence": "low",
            }
        )

        self.assertEqual(
            classify_action_type([base, missing_market, backtest]),
            "watch_only",
        )

    def test_bundle_persists_proposal_snapshot_and_receipt(self) -> None:
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
                patch.object(proposal, "PROPOSAL_NORMALIZED_ROOT", root / "props"),
                patch.object(proposal, "PROPOSAL_RECEIPT_ROOT", root / "prop_receipts"),
            ):
                validation_bundle = build_sample_validation_bundle()
                bundle = build_proposal_bundle_from_validation_snapshot(
                    validation_bundle.snapshot,
                    llm_enabled=True,
                    hermes_root="/root/projects/hermes-agent",
                )

                self.assertGreater(bundle.snapshot.candidate_count, 0)
                self.assertTrue(bundle.snapshot.quality.ok)
                self.assertFalse(bundle.snapshot.execution_allowed)
                self.assertTrue(bundle.snapshot.risk_gate_handoff)
                self.assertEqual(
                    bundle.snapshot.lineage.input_validation_snapshot_id,
                    validation_bundle.snapshot.validation_snapshot_id,
                )
                self.assertEqual(bundle.snapshot.lineage.source.llm_provider, "hermes-agent")
                self.assertTrue(Path(bundle.snapshot.payload_ref).exists())
                self.assertTrue(Path(bundle.snapshot.receipt_ref).exists())
                for candidate in bundle.snapshot.candidates:
                    self.assertIn(
                        candidate.action_type,
                        {
                            "watch_only",
                            "research_more",
                            "paper_trade_candidate",
                            "avoid_or_reject",
                        },
                    )
                    self.assertTrue(candidate.risk_gate_request.human_review_required)

    def test_quality_blocks_order_language(self) -> None:
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
                validation_bundle = build_sample_validation_bundle()
                bundle = build_proposal_bundle_from_validation_snapshot(
                    validation_bundle.snapshot,
                )

        bad = ProposalCandidate.model_validate(
            bundle.candidates[0].model_dump(mode="json")
            | {"rationale": "place order after validation evidence"}
        )
        quality = build_proposal_quality(
            validation_snapshot=validation_bundle.snapshot,
            candidates=[bad, *bundle.candidates[1:]],
        )
        self.assertFalse(quality.ok)
        self.assertFalse(quality.no_order_language)
        self.assertIn(bad.proposal_id, quality.blocked_language_hits)

    def test_quality_fails_without_do_nothing_case(self) -> None:
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
                validation_bundle = build_sample_validation_bundle()
                bundle = build_proposal_bundle_from_validation_snapshot(
                    validation_bundle.snapshot,
                )

        bad = ProposalCandidate.model_validate(
            bundle.candidates[0].model_dump(mode="json") | {"do_nothing_case": ""}
        )
        quality = build_proposal_quality(
            validation_snapshot=validation_bundle.snapshot,
            candidates=[bad, *bundle.candidates[1:]],
        )
        self.assertFalse(quality.ok)
        self.assertFalse(quality.do_nothing_case_present)
        self.assertIn("do_nothing_case", quality.missing_required_fields[bad.proposal_id])

    def test_proposal_graph_compiles(self) -> None:
        self.assertIsNotNone(proposal_graph)

    def test_proposal_graph_runs_with_validation_snapshot(self) -> None:
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
                patch.object(proposal, "PROPOSAL_NORMALIZED_ROOT", root / "props"),
                patch.object(proposal, "PROPOSAL_RECEIPT_ROOT", root / "prop_receipts"),
            ):
                validation_bundle = build_sample_validation_bundle()
                result = run_proposal_graph(
                    validation_snapshot=validation_bundle.snapshot.model_dump(mode="json"),
                    llm_enabled=True,
                    hermes_root="/root/projects/hermes-agent",
                )

                final = result["final"]
                self.assertEqual(final["workflow"], "langgraph_proposal_v1")
                self.assertGreater(final["candidate_count"], 0)
                self.assertTrue(final["quality_ok"])
                self.assertFalse(final["execution_allowed"])
                self.assertTrue(final["risk_gate_handoff"])
                self.assertEqual(final["consumer_handoff"]["consumer"], "risk_gate")
                self.assertTrue(final["llm_enabled"])
                self.assertEqual(final["hermes_root"], "/root/projects/hermes-agent")


if __name__ == "__main__":
    unittest.main()
