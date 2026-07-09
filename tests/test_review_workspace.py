"""Tests for review workspace projection v0.1.

v0.1 (PR #216): Adds hydrated workspace from receipts.
"""

import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from finharness.agent_cognition_flow import run_agent_cognition_flow
from finharness.review_workspace import (
    ReviewWorkspaceProjection,
    build_review_workspace_projection,
    build_review_workspace_projection_from_receipts,
)


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
            assert ws.execution_allowed is False

    def test_projection_model_is_frozen(self) -> None:
        ws = ReviewWorkspaceProjection(
            workspace_id="rwp_test", subject_type="plan_draft",
            subject_id="p1", goal="Test",
            open_findings=[], data_gaps=[], suggested_playbooks=[], receipt_refs=[],
        )
        with pytest.raises(ValidationError, match="frozen"):
            ws.goal = "hijacked"  # type: ignore[misc]

    def test_projection_includes_all_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow = run_agent_cognition_flow(
                goal="Test refs", profile_name="default",
                objective="Test", option_claims=["A"], plan_steps=["S1"],
                receipt_root=Path(tmp),
            )
            ws = build_review_workspace_projection(flow_result=flow)
            assert len(ws.receipt_refs) == 4


class TestHydratedReviewWorkspace:
    """Tests for receipt-hydrated workspace (new in v0.1)."""

    def test_hydrated_from_receipts_has_evaluation_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow = run_agent_cognition_flow(
                goal="Test eval status",
                profile_name="default",
                objective="Test", option_claims=["A"], plan_steps=["S1"],
                receipt_root=Path(tmp),
            )
            ws = build_review_workspace_projection_from_receipts(
                flow_result=flow, receipt_root=Path(tmp),
            )
            assert ws.evaluation_status is not None
            assert ws.evaluation_status in ("pass", "warn", "block")

    def test_hydrated_has_open_findings_from_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow = run_agent_cognition_flow(
                goal="Bad plan — no stop condition",
                profile_name="default",
                objective="Test block", option_claims=["A"], plan_steps=["Step 1"],
                receipt_root=Path(tmp),
            )
            ws = build_review_workspace_projection_from_receipts(
                flow_result=flow, receipt_root=Path(tmp),
            )
            # "Step 1" is too short, no stop condition -> should warn/block
            assert ws.evaluation_status in ("warn", "block")
            assert len(ws.open_findings) > 0

    def test_hydrated_has_data_gaps_from_run_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow = run_agent_cognition_flow(
                goal="Test data gaps",
                profile_name="default",
                objective="Test", option_claims=["A"],
                plan_steps=["Step 1: read context", "Step 2: evaluate", "Step 3: stop"],
                receipt_root=Path(tmp),
            )
            ws = build_review_workspace_projection_from_receipts(
                flow_result=flow, receipt_root=Path(tmp),
            )
            assert isinstance(ws.data_gaps, list)

    def test_hydrated_with_human_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow = run_agent_cognition_flow(
                goal="Test authority",
                profile_name="default",
                objective="Test",
                option_claims=["A"],
                plan_steps=["Step 1: read context", "Step 2: evaluate", "Step 3: stop"],
                receipt_root=Path(tmp),
                human_attester="alice",
                human_reason="Looks good",
                explicit_confirmation=True,
            )
            ws = build_review_workspace_projection_from_receipts(
                flow_result=flow, receipt_root=Path(tmp),
            )
            assert ws.authority_eligibility is not None

    def test_hydrated_evaluation_findings_are_structured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            flow = run_agent_cognition_flow(
                goal="Test findings",
                profile_name="default",
                objective="Test", option_claims=["A"], plan_steps=["Step 1"],
                receipt_root=Path(tmp),
            )
            ws = build_review_workspace_projection_from_receipts(
                flow_result=flow, receipt_root=Path(tmp),
            )
            assert len(ws.evaluation_findings) > 0
            f0 = ws.evaluation_findings[0]
            assert f0.code
            assert f0.severity in ("warn", "block")
