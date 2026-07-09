"""Tests for operating surface -> cognition flow bridge.

v0.1 (PR #215): Playbook requirement tests.
"""

import tempfile
from pathlib import Path

from finharness.agent_operating_flow import (
    evaluate_playbook_requirements,
    run_agent_cognition_flow_from_operating_inputs,
)
from finharness.playbook_loader import load_cognition_playbook


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
                goal="Test", profile_name="default",
                objective="Verify invariant",
                option_claims=["A"], plan_steps=["S1"],
                receipt_root=Path(tmp),
            )
            assert result.execution_allowed is False

    # ── playbook consumed by flow (new in v0.1) ──────────────────────

    def test_flow_with_playbook_runs(self) -> None:
        """Flow runs with playbook_name, playbook requirements evaluated."""
        with tempfile.TemporaryDirectory() as tmp:
            result = run_agent_cognition_flow_from_operating_inputs(
                goal="Test with playbook",
                profile_name="default",
                objective="Verify playbook integration",
                option_claims=["Option A"],
                plan_steps=["Step 1: load IPS", "Step 2: compare"],
                receipt_root=Path(tmp),
                playbook_name="ips-drift-review",
            )
            assert result.flow_id
            assert result.execution_allowed is False

    def test_evaluate_playbook_requirements_missing_context(self) -> None:
        """Missing required_context_packs produce findings."""
        pb = load_cognition_playbook("ips-drift-review")
        assert pb is not None
        # No context payload -> should warn about missing context packs
        findings = evaluate_playbook_requirements(pb, context_projection_payload=None)
        codes = {f.code for f in findings}
        assert "playbook_context_missing" in codes

    def test_evaluate_playbook_requirements_missing_in_empty_payload(self) -> None:
        """Empty projection payload also triggers missing context findings."""
        pb = load_cognition_playbook("ips-drift-review")
        assert pb is not None
        payload: dict[str, object] = {"packs": []}
        findings = evaluate_playbook_requirements(pb, context_projection_payload=payload)
        codes = {f.code for f in findings}
        assert "playbook_context_missing" in codes

    def test_evaluate_playbook_requirements_context_present(self) -> None:
        """When context packs are present, no missing-context findings."""
        pb = load_cognition_playbook("ips-drift-review")
        assert pb is not None
        payload: dict[str, object] = {
            "packs": [{
                "name": "capital_summary",
                "context_pack_refs": ["current_ips", "capital_summary"],
            }]
        }
        findings = evaluate_playbook_requirements(pb, context_projection_payload=payload)
        codes = {f.code for f in findings}
        # No missing-context findings when packs are present
        assert "playbook_context_missing" not in codes

    def test_evaluate_playbook_requirements_evaluators_registered(self) -> None:
        """Recommended evaluators that ARE registered produce no findings."""
        pb = load_cognition_playbook("ips-drift-review")
        assert pb is not None
        payload: dict[str, object] = {
            "packs": [{"context_pack_refs": ["current_ips", "capital_summary"]}]
        }
        findings = evaluate_playbook_requirements(pb, context_projection_payload=payload)
        codes = {f.code for f in findings}
        # plan_draft_evaluator is registered -> no finding
        assert "playbook_evaluator_not_registered" not in codes
