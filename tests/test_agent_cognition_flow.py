"""Tests for AgentCognitionFlow v0."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from finharness.agent_cognition_flow import (
    run_agent_cognition_flow,
)


class TestAgentCognitionFlow:
    def test_full_flow_with_human_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_agent_cognition_flow(
                goal="Evaluate rebalancing options for current portfolio",
                profile_name="review-draft",
                objective="Determine whether to increase SPY allocation",
                option_claims=[
                    "Increase SPY by 5%",
                    "Hold current allocation",
                    "Reduce SPY by 3%",
                ],
                plan_steps=[
                    "Review current exposure",
                    "Check IPS compliance",
                    "Draft adjustment proposal",
                ],
                receipt_root=root,
                source_refs=["capital_summary", "current_ips"],
                human_attester="ops_reviewer",
                human_reason="Pre-trade checks pass, risk within mandate",
                explicit_confirmation=True,
            )
            assert result.flow_id.startswith("acf_")
            assert result.option_set_ref is not None
            assert result.plan_draft_ref is not None
            assert result.evaluation_report_ref is not None
            assert result.authority_transition_ref is not None
            assert result.agent_run_receipt_ref is not None
            assert result.execution_allowed is False

    def test_all_artifacts_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_agent_cognition_flow(
                goal="Test artifact persistence",
                profile_name="default",
                objective="Test objective",
                option_claims=["Option A"],
                plan_steps=["Step 1"],
                receipt_root=root,
                human_attester="ops",
                human_reason="test",
                explicit_confirmation=True,
            )
            assert (root / result.option_set_ref).exists()
            assert (root / result.plan_draft_ref).exists()
            assert root.joinpath("evaluation-reports").exists()
            assert (root / result.authority_transition_ref).exists()  # type: ignore[arg-type]
            assert (root / result.agent_run_receipt_ref).exists()

    def test_agent_run_receipt_captures_artifact_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_agent_cognition_flow(
                goal="Test artifact trace",
                profile_name="default",
                objective="Test trace",
                option_claims=["Option A"],
                plan_steps=["Step 1"],
                receipt_root=root,
                human_attester="ops",
                human_reason="test",
                explicit_confirmation=True,
            )
            ar_path = root / result.agent_run_receipt_ref
            payload = json.loads(ar_path.read_text())
            artifact_refs = set(payload["artifact_refs"])
            assert result.option_set_ref in artifact_refs
            assert result.plan_draft_ref in artifact_refs
            assert result.evaluation_report_ref in artifact_refs
            assert result.authority_transition_ref in artifact_refs  # type: ignore[arg-type]

    def test_execution_allowed_false_throughout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_agent_cognition_flow(
                goal="Test no execution",
                profile_name="default",
                objective="Test",
                option_claims=["A"],
                plan_steps=["S1"],
                receipt_root=root,
                human_attester="ops",
                human_reason="test",
                explicit_confirmation=True,
            )
            assert result.execution_allowed is False
            # Spot-check: agent run receipt
            ar_path = root / result.agent_run_receipt_ref
            ar = json.loads(ar_path.read_text())
            assert ar["execution_allowed"] is False

    def test_flow_without_human_confirmation_skips_authority(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_agent_cognition_flow(
                goal="Test without human",
                profile_name="default",
                objective="Test",
                option_claims=["A"],
                plan_steps=["S1"],
                receipt_root=Path(tmp),
            )
            assert result.authority_transition_ref is None
            ar_path = Path(tmp) / result.agent_run_receipt_ref
            ar = json.loads(ar_path.read_text())
            assert ar["outcome"] == "partial"
            assert any("Human confirmation" in dg for dg in ar["data_gaps"])

    def test_plan_draft_links_to_option_set(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_agent_cognition_flow(
                goal="Test linking",
                profile_name="default",
                objective="Test link",
                option_claims=["A"],
                plan_steps=["S1"],
                receipt_root=root,
                human_attester="ops",
                human_reason="test",
                explicit_confirmation=True,
            )
            pd_path = root / result.plan_draft_ref
            pd = json.loads(pd_path.read_text())
            # PlanDraft has related_option_set_id
            assert pd.get("related_option_set_id") is not None

    def test_evaluation_ref_in_authority_transition(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_agent_cognition_flow(
                goal="Test eval→auth link",
                profile_name="default",
                objective="Test link",
                option_claims=["A"],
                plan_steps=["S1"],
                receipt_root=root,
                human_attester="ops",
                human_reason="test",
                explicit_confirmation=True,
            )
            at_path = root / result.authority_transition_ref  # type: ignore[arg-type]
            at_payload = json.loads(at_path.read_text())
            eval_refs = at_payload["evaluation_report_refs"]
            assert len(eval_refs) >= 1
            assert result.evaluation_report_ref in eval_refs
