# finharness-test-runner: pytest
"""Tests for AgentCognitionFlow v0."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from finharness.agent_cognition_flow import (
    run_agent_cognition_flow,
)
from finharness.context_trust import (
    trust_for_agent_draft,
    trust_for_receipt_backed_state,
    trust_for_unknown,
)
from finharness.evaluation_report import (
    build_evaluation_report,
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

    def test_eval_status_parameter_removed(self) -> None:
        """Passing the old eval_status parameter must raise TypeError."""
        with tempfile.TemporaryDirectory() as tmp, pytest.raises(TypeError):
            run_agent_cognition_flow(
                goal="Test",
                profile_name="default",
                objective="Test",
                option_claims=["A"],
                plan_steps=["S1"],
                receipt_root=Path(tmp),
                eval_status="pass",  # type: ignore[call-arg]
            )

    def test_evaluator_override_without_allow_raises(self) -> None:
        """Override without explicit allow must raise ValueError."""
        with tempfile.TemporaryDirectory() as tmp:
            override_report = build_evaluation_report(
                evaluator_id="test",
                subject_type="plan_draft",
                subject_id="plan-1",
                status="pass",
                findings=[],
            )
            with pytest.raises(ValueError, match="allow_evaluation_override"):
                run_agent_cognition_flow(
                    goal="Test",
                    profile_name="default",
                    objective="Test",
                    option_claims=["A"],
                    plan_steps=["S1"],
                    receipt_root=Path(tmp),
                    evaluator_override=override_report,
                    allow_evaluation_override=False,
                )

    def test_evaluator_override_with_allow_works(self) -> None:
        """Override with explicit allow must use the provided report."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            override_report = build_evaluation_report(
                evaluator_id="test",
                subject_type="plan_draft",
                subject_id="plan-1",
                status="pass",
                findings=[],
            )
            result = run_agent_cognition_flow(
                goal="Test override",
                profile_name="default",
                objective="Test",
                option_claims=["A"],
                plan_steps=["S1"],
                receipt_root=root,
                human_attester="ops",
                human_reason="test",
                explicit_confirmation=True,
                evaluator_override=override_report,
                allow_evaluation_override=True,
            )
            # Authority transition must exist (pass → eligible)
            assert result.authority_transition_ref is not None

    def test_flow_block_cannot_become_pass_by_accident(self) -> None:
        """Plan with execution-like language must remain block by default."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_agent_cognition_flow(
                goal="Test block integrity",
                profile_name="default",
                objective="Test",
                option_claims=["A"],
                plan_steps=["execute order", "submit to broker"],
                receipt_root=root,
                human_attester="ops",
                human_reason="test",
                explicit_confirmation=True,
            )
            # Authority must be not_eligible (block)
            assert result.authority_transition_ref is not None
            at_path = root / result.authority_transition_ref  # type: ignore[arg-type]
            at_payload = json.loads(at_path.read_text())
            assert at_payload["eligibility"] == "not_eligible"

    # ── Context use policy flow integration tests (R-005 / RISK-2) ────

    def test_flow_receipt_backed_context_passes(self) -> None:
        """receipt_backed_state context refs must pass validation."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trust = trust_for_receipt_backed_state(receipt_refs=["r1"])
            # Use evaluator_override with pass so only context validation
            # determines the result (evaluator warns on minimal plans).
            pass_report = build_evaluation_report(
                evaluator_id="test",
                subject_type="plan_draft",
                subject_id="plan-1",
                status="pass",
                findings=[],
            )
            result = run_agent_cognition_flow(
                goal="Test receipt-backed context",
                profile_name="default",
                objective="Test",
                option_claims=["A"],
                plan_steps=["Review allocation"],
                receipt_root=root,
                source_refs=["ctx-1"],
                context_trust_by_ref={"ctx-1": trust},
                human_attester="ops",
                human_reason="test",
                explicit_confirmation=True,
                evaluator_override=pass_report,
                allow_evaluation_override=True,
            )
            assert result.authority_transition_ref is not None
            at_path = root / result.authority_transition_ref  # type: ignore[arg-type]
            at_payload = json.loads(at_path.read_text())
            assert at_payload["eligibility"] == "eligible"

    def test_flow_missing_context_trust_warns(self) -> None:
        """source_refs without context_trust_by_ref must warn."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_agent_cognition_flow(
                goal="Test missing trust metadata",
                profile_name="default",
                objective="Test",
                option_claims=["A"],
                plan_steps=["Review allocation"],
                receipt_root=root,
                source_refs=["ctx-1"],
                human_attester="ops",
                human_reason="test",
                explicit_confirmation=True,
            )
            # warn → deferred
            assert result.authority_transition_ref is not None
            at_path = root / result.authority_transition_ref  # type: ignore[arg-type]
            at_payload = json.loads(at_path.read_text())
            assert at_payload["eligibility"] == "deferred"

    def test_flow_agent_draft_context_blocked(self) -> None:
        """agent_draft source ref with use_as_evidence must block."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trust = trust_for_agent_draft(source_refs=["ctx-1"])
            result = run_agent_cognition_flow(
                goal="Test agent draft blocked",
                profile_name="default",
                objective="Test",
                option_claims=["A"],
                plan_steps=["Review allocation"],
                receipt_root=root,
                source_refs=["ctx-1"],
                context_trust_by_ref={"ctx-1": trust},
                human_attester="ops",
                human_reason="test",
                explicit_confirmation=True,
            )
            assert result.authority_transition_ref is not None
            at_path = root / result.authority_transition_ref  # type: ignore[arg-type]
            at_payload = json.loads(at_path.read_text())
            assert at_payload["eligibility"] == "not_eligible"

    def test_flow_unknown_context_blocked(self) -> None:
        """unknown source ref must block."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trust = trust_for_unknown()
            result = run_agent_cognition_flow(
                goal="Test unknown context blocked",
                profile_name="default",
                objective="Test",
                option_claims=["A"],
                plan_steps=["Review allocation"],
                receipt_root=root,
                source_refs=["ctx-1"],
                context_trust_by_ref={"ctx-1": trust},
                human_attester="ops",
                human_reason="test",
                explicit_confirmation=True,
            )
            assert result.authority_transition_ref is not None
            at_path = root / result.authority_transition_ref  # type: ignore[arg-type]
            at_payload = json.loads(at_path.read_text())
            assert at_payload["eligibility"] == "not_eligible"

    def test_flow_empty_context_trust_blocks_all(self) -> None:
        """context_trust_by_ref={} with source_refs must block all."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = run_agent_cognition_flow(
                goal="Test empty trust blocks all",
                profile_name="default",
                objective="Test",
                option_claims=["A"],
                plan_steps=["Review allocation"],
                receipt_root=root,
                source_refs=["ctx-1"],
                context_trust_by_ref={},
                human_attester="ops",
                human_reason="test",
                explicit_confirmation=True,
            )
            assert result.authority_transition_ref is not None
            at_path = root / result.authority_transition_ref  # type: ignore[arg-type]
            at_payload = json.loads(at_path.read_text())
            assert at_payload["eligibility"] == "not_eligible"

    def test_flow_context_finding_in_eval_receipt(self) -> None:
        """agent_draft ref must produce context_use_not_allowed in eval receipt."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            trust = trust_for_agent_draft(source_refs=["ctx-1"])
            result = run_agent_cognition_flow(
                goal="Test context finding in receipt",
                profile_name="default",
                objective="Test",
                option_claims=["A"],
                plan_steps=["Review allocation"],
                receipt_root=root,
                source_refs=["ctx-1"],
                context_trust_by_ref={"ctx-1": trust},
                human_attester="ops",
                human_reason="test",
                explicit_confirmation=True,
            )
            # Evaluation report ref is path#sha256:hash — strip anchor
            eval_path = root / result.evaluation_report_ref.split("#")[0]
            eval_payload = json.loads(eval_path.read_text())
            codes = {f["code"] for f in eval_payload["findings"]}
            assert "context_use_not_allowed" in codes
