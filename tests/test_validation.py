from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import finharness.vectorbt_runner as vectorbt_runner
from finharness import events, hypotheses, interpretation, validation
from finharness.events import CIK_BY_SYMBOL, build_sec_edgar_event_bundle_from_raw
from finharness.hypotheses import build_hypothesis_bundle_from_interpretation_snapshot
from finharness.interpretation import build_interpretation_bundle_from_event_snapshot
from finharness.validation import (
    ValidationCheckResult,
    VectorbtBacktestEvidenceProvider,
    build_validation_bundle_from_hypothesis_snapshot,
    build_validation_quality,
    build_validation_results,
    create_validation_jobs,
)
from finharness.validation_graph import run_validation_graph, validation_graph
from finharness.vectorbt_runner import VECTORBT_BACKEND


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


def sample_history(rows: int = 80) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "date": f"2026-01-{index % 28 + 1:02d}",
                "open": 100.0 + index * 0.5,
                "high": 101.0 + index * 0.5,
                "low": 99.0 + index * 0.5,
                "close": 100.5 + index * 0.5,
                "volume": 1_000_000 + index,
            }
            for index in range(rows)
        ]
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

    def test_null_backtest_evidence_is_added_without_changing_existing_checks(
        self,
    ) -> None:
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
                )

        backtests = [
            result for result in bundle.results if result.check_type == "backtest"
        ]
        non_backtests = [
            result for result in bundle.results if result.check_type != "backtest"
        ]
        self.assertEqual(bundle.snapshot.result_count, 20)
        self.assertEqual(len(non_backtests), 18)
        self.assertEqual(len(backtests), bundle.snapshot.job_count)
        self.assertTrue(all(result.result == "not_testable" for result in backtests))
        self.assertTrue(all(result.method == VECTORBT_BACKEND for result in backtests))
        self.assertTrue(bundle.snapshot.quality.ok)

    def test_vectorbt_provider_shapes_backtest_evidence(self) -> None:
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
                snapshot = hypothesis_bundle.snapshot
                jobs = create_validation_jobs(snapshot)
                provider = VectorbtBacktestEvidenceProvider(
                    history_by_symbol={"NVDA": sample_history()},
                    fast=5,
                    slow=10,
                )
                with patch(
                    "finharness.vectorbt_runner.vbt.Portfolio.from_signals",
                    wraps=vectorbt_runner.vbt.Portfolio.from_signals,
                ) as from_signals:
                    results = build_validation_results(
                        snapshot=snapshot,
                        jobs=jobs,
                        backtest_provider=provider,
                    )

        backtests = [result for result in results if result.check_type == "backtest"]
        self.assertTrue(from_signals.called)
        self.assertEqual(len(backtests), len(jobs))
        for result in backtests:
            self.assertEqual(result.method, VECTORBT_BACKEND)
            self.assertIn("total_return", result.metrics)
            self.assertIn("trade_count", result.metrics)
            self.assertEqual(result.metrics["fast"], 5)
            self.assertEqual(result.metrics["slow"], 10)
            self.assertEqual(result.confidence, "low")
            self.assertTrue(result.limitations)

    def test_backtest_evidence_keeps_validation_boundary(self) -> None:
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
                provider = VectorbtBacktestEvidenceProvider(
                    history_by_symbol={"NVDA": sample_history()},
                    fast=5,
                    slow=10,
                )
                bundle = build_validation_bundle_from_hypothesis_snapshot(
                    hypothesis_bundle.snapshot,
                    backtest_provider=provider,
                )

        self.assertFalse(bundle.snapshot.execution_allowed)
        for result in bundle.results:
            if result.check_type != "backtest":
                continue
            self.assertFalse(
                result.supports_hypothesis and result.disconfirms_hypothesis
            )
            self.assertEqual(validation.find_blocked_language(
                validation.result_text_for_guard(result)
            ), [])

    def test_vectorbt_provider_too_short_history_is_not_testable(self) -> None:
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
                snapshot = hypothesis_bundle.snapshot
                jobs = create_validation_jobs(snapshot)
                provider = VectorbtBacktestEvidenceProvider(
                    history_by_symbol={"NVDA": sample_history(rows=8)},
                    fast=5,
                    slow=10,
                )
                results = build_validation_results(
                    snapshot=snapshot,
                    jobs=jobs,
                    backtest_provider=provider,
                )

        backtests = [result for result in results if result.check_type == "backtest"]
        self.assertTrue(backtests)
        self.assertTrue(all(result.result == "not_testable" for result in backtests))
        self.assertTrue(all(result.limitations for result in backtests))

    def test_quality_accepts_backtest_evidence_result(self) -> None:
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
                snapshot = hypothesis_bundle.snapshot
                jobs = create_validation_jobs(snapshot)
                results = build_validation_results(snapshot=snapshot, jobs=jobs)

        quality = build_validation_quality(snapshot=snapshot, jobs=jobs, results=results)
        self.assertTrue(quality.ok)
        self.assertTrue(quality.limitations_present)
        self.assertTrue(quality.result_not_overclaimed)
        self.assertTrue(quality.lineage_complete)

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

    def test_event_reaction_uses_cached_prices_to_weaken_hypothesis(self) -> None:
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
                patch.object(
                    validation,
                    "load_cached_close_series",
                    return_value=[100.0, 100.1, 100.0],
                ),
            ):
                hypothesis_bundle = build_sample_hypothesis_bundle(root)
                bundle = build_validation_bundle_from_hypothesis_snapshot(
                    hypothesis_bundle.snapshot
                )

        event_results = [
            result for result in bundle.results if result.check_type == "event_reaction"
        ]
        self.assertTrue(event_results)
        self.assertTrue(
            all(result.method == "realized_move_over_window" for result in event_results)
        )
        self.assertTrue(all(result.result == "weakened" for result in event_results))
        self.assertTrue(all(result.disconfirms_hypothesis for result in event_results))

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
