"""Tests for review workspace projection."""

import tempfile
from pathlib import Path

from finharness.agent_cognition_flow import run_agent_cognition_flow
from finharness.review_workspace import build_review_workspace_projection


class TestReviewWorkspace:

    def test_build_from_flow_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow = run_agent_cognition_flow(
                goal="Check SPY exposure",
                profile_name="default",
                objective="Verify allocation",
                option_claims=["Keep", "Reduce"],
                plan_steps=["Step 1: read context", "Step 2: evaluate", "Step 3: stop"],
                receipt_root=Path(tmp),
            )
            ws = build_review_workspace_projection(flow_result=flow)
            assert ws.workspace_id
            assert ws.goal == "Check SPY exposure"
            assert ws.latest_plan_ref
            assert ws.latest_evaluation_ref
            assert ws.execution_allowed is False
            assert ws.authority_transition is False

    def test_projection_model_is_frozen(self) -> None:
        import pytest
        from pydantic import ValidationError

        from finharness.review_workspace import ReviewWorkspaceProjection
        ws = ReviewWorkspaceProjection(
            workspace_id="rwp_test",
            subject_type="plan_draft",
            subject_id="p1",
            goal="Test",
            open_findings=[],
            data_gaps=[],
            suggested_playbooks=[],
            receipt_refs=[],
        )
        with pytest.raises(ValidationError, match="frozen"):
            ws.goal = "hijacked"  # type: ignore[misc]

    def test_projection_includes_all_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow = run_agent_cognition_flow(
                goal="Test refs",
                profile_name="default",
                objective="Test",
                option_claims=["A"],
                plan_steps=["S1"],
                receipt_root=Path(tmp),
            )
            ws = build_review_workspace_projection(flow_result=flow)
            assert len(ws.receipt_refs) == 4  # option_set, plan_draft, eval, run
