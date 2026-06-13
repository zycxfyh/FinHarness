"""Tests for the Hermes generator-seat hypothesis draft provider.

These tests never call the real hermes CLI; the bridge is mocked. The contract
under test: valid drafts are consumed field by field, any failure falls back
to the deterministic template, and unsafe LLM output is caught by the existing
quality gates downstream.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finharness import hypotheses
from finharness.hermes_bridge import HermesBridgeError, extract_json_object
from finharness.hypotheses import (
    HermesHypothesisDraftProvider,
    build_hermes_hypothesis_prompt,
    build_hypothesis_quality,
    formulate_hypothesis_record,
    sanitize_hermes_draft,
)
from finharness.interpretation import InterpretationRecord


def interpretation_fixture() -> InterpretationRecord:
    return InterpretationRecord(
        interpretation_id="interp_hermes_test",
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


GOOD_DRAFT = {
    "hypothesis": (
        "If the 10-Q discloses a revenue mix shift, then later filings and "
        "market reaction should show observable support or disconfirmation "
        "over a quarters horizon."
    ),
    "mechanism": "Revenue mix changes transmit through guidance revisions.",
    "expected_observations": [
        "Later filings repeat the revenue mix driver.",
        "Reaction persists relative to SPY and QQQ context.",
    ],
    "disconfirming_observations": [
        "Index moves explain the reaction.",
        "Later filings omit the driver.",
    ],
    "assumptions": [
        "The filing facts are accurate.",
        "Market reaction is interpreted relative to explicit event timing.",
    ],
}


class HermesProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.object(
            hypotheses, "HERMES_DRAFT_ROOT", Path(self.tmp.name)
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.interpretation = interpretation_fixture()

    def test_valid_llm_json_is_consumed_and_persisted(self) -> None:
        raw = "Here is the draft:\n```json\n" + json.dumps(GOOD_DRAFT) + "\n```"
        with patch(
            "finharness.hermes_bridge.run_hermes_single_query", return_value=raw
        ):
            provider = HermesHypothesisDraftProvider()
            record = formulate_hypothesis_record(
                self.interpretation, draft_provider=provider
            )
        self.assertEqual(record.draft_provider, "hermes-agent")
        self.assertEqual(record.hypothesis, GOOD_DRAFT["hypothesis"])
        self.assertEqual(record.mechanism, GOOD_DRAFT["mechanism"])
        self.assertIsNotNone(record.draft_ref)
        drafts = list(Path(self.tmp.name).glob("*.json"))
        self.assertEqual(len(drafts), 1)
        artifact = json.loads(drafts[0].read_text(encoding="utf-8"))
        self.assertIn("prompt", artifact)
        self.assertIn("raw_output", artifact)
        quality = build_hypothesis_quality([record])
        self.assertTrue(quality.ok)

    def test_bridge_failure_falls_back_to_deterministic_template(self) -> None:
        with patch(
            "finharness.hermes_bridge.run_hermes_single_query",
            side_effect=HermesBridgeError("timeout"),
        ):
            provider = HermesHypothesisDraftProvider()
            record = formulate_hypothesis_record(
                self.interpretation, draft_provider=provider
            )
        # Deterministic template content, but provenance still names the
        # provider and the failed exchange is persisted for review.
        self.assertEqual(record.draft_provider, "hermes-agent")
        self.assertIn("If source event", record.hypothesis)
        self.assertTrue(record.expected_observations)
        self.assertTrue(record.disconfirming_observations)
        quality = build_hypothesis_quality([record])
        self.assertTrue(quality.ok)

    def test_garbage_output_falls_back(self) -> None:
        with patch(
            "finharness.hermes_bridge.run_hermes_single_query",
            return_value="I cannot answer in JSON, sorry.",
        ):
            provider = HermesHypothesisDraftProvider()
            record = formulate_hypothesis_record(
                self.interpretation, draft_provider=provider
            )
        self.assertIn("If source event", record.hypothesis)

    def test_recommendation_language_from_llm_is_blocked_by_quality_gate(self) -> None:
        bad_draft = dict(GOOD_DRAFT)
        bad_draft["hypothesis"] = "Buy NVDA now because revenue will beat."
        with patch(
            "finharness.hermes_bridge.run_hermes_single_query",
            return_value=json.dumps(bad_draft),
        ):
            provider = HermesHypothesisDraftProvider()
            record = formulate_hypothesis_record(
                self.interpretation, draft_provider=provider
            )
        quality = build_hypothesis_quality([record])
        self.assertFalse(quality.ok)
        self.assertFalse(quality.no_recommendation_language)

    def test_industry_terms_are_not_false_positives(self) -> None:
        finance_draft = dict(GOOD_DRAFT)
        finance_draft["hypothesis"] = (
            "If sell-side analysts revise long-term estimates after the filing, "
            "then short-term reaction should show observable support."
        )
        with patch(
            "finharness.hermes_bridge.run_hermes_single_query",
            return_value=json.dumps(finance_draft),
        ):
            provider = HermesHypothesisDraftProvider()
            record = formulate_hypothesis_record(
                self.interpretation, draft_provider=provider
            )
        quality = build_hypothesis_quality([record])
        self.assertTrue(quality.ok, quality.blocked_language_hits)

    def test_sanitize_drops_unknown_keys_and_bad_validation_plan(self) -> None:
        payload = {
            **GOOD_DRAFT,
            "execute_order": "yes",
            "validation_plan": [{"check_type": "place_order"}],
        }
        draft = sanitize_hermes_draft(payload)
        self.assertNotIn("execute_order", draft)
        self.assertNotIn("validation_plan", draft)
        self.assertEqual(draft["hypothesis"], GOOD_DRAFT["hypothesis"])

    def test_prompt_contains_no_execution_authority(self) -> None:
        prompt = build_hermes_hypothesis_prompt(self.interpretation)
        self.assertIn("no trade recommendations", prompt)
        self.assertIn("falsifiable", prompt)

    def test_extract_json_object_tolerates_prose_and_fences(self) -> None:
        text = 'prefix {"a": 1} suffix'
        self.assertEqual(extract_json_object(text), {"a": 1})
        with self.assertRaises(HermesBridgeError):
            extract_json_object("no json here")


if __name__ == "__main__":
    unittest.main()
