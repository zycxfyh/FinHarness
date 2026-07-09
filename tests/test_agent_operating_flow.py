"""Tests for operating surface → cognition flow bridge."""

import tempfile
from pathlib import Path

from finharness.agent_operating_flow import run_agent_cognition_flow_from_operating_inputs


class TestOperatingFlow:

    def test_flow_runs_with_minimal_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_agent_cognition_flow_from_operating_inputs(
                goal="Test operating flow",
                profile_name="default",
                objective="Verify integration",
                option_claims=["Option A"],
                plan_steps=["Step 1: check context", "Step 2: draft plan"],
                receipt_root=Path(tmp),
            )
            assert result.flow_id
            assert result.option_set_ref
            assert result.plan_draft_ref
            assert result.evaluation_report_ref
            assert result.agent_run_receipt_ref
            assert result.execution_allowed is False

    def test_flow_with_trust_map_from_projection(self) -> None:
        from finharness.context_trust import trust_for_system_computed

        trust = trust_for_system_computed(source_refs=["ref://ctx1"])
        payload = {
            "packs": [{
                "name": "capital_summary",
                "summary": {"trust": trust.model_dump()},
                "source_refs": ["ref://ctx1"],
                "context_pack_refs": ["context_pack://capital_summary"],
            }]
        }
        with tempfile.TemporaryDirectory() as tmp:
            result = run_agent_cognition_flow_from_operating_inputs(
                goal="Test with context",
                profile_name="default",
                objective="Verify context integration",
                option_claims=["Option A"],
                plan_steps=["Step 1"],
                receipt_root=Path(tmp),
                context_projection_payload=payload,
            )
            assert result.flow_id
            assert result.execution_allowed is False

    def test_flow_with_human_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_agent_cognition_flow_from_operating_inputs(
                goal="Test with human",
                profile_name="default",
                objective="Verify human flow",
                option_claims=["Option A"],
                plan_steps=["Step 1: review"],
                receipt_root=Path(tmp),
                human_attester="alice",
                human_reason="Looks good",
                explicit_confirmation=True,
            )
            assert result.authority_transition_ref is not None

    def test_flow_execution_allowed_always_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = run_agent_cognition_flow_from_operating_inputs(
                goal="Test",
                profile_name="default",
                objective="Verify invariant",
                option_claims=["A"],
                plan_steps=["S1"],
                receipt_root=Path(tmp),
            )
            assert result.execution_allowed is False
