"""Tests for AgentWorkRequest / AgentWorkResult / ContextSnapshot models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from finharness.agent_work_loop import (
    AgentWorkRequest,
    AgentWorkResult,
    freeze_work_context,
)


class TestAgentWorkRequest:

    def test_minimal_request(self) -> None:
        req = AgentWorkRequest(
            goal="Test goal",
            profile_name="default",
            objective="Test objective",
            work_type="research_review",
            receipt_root="/tmp/test",
        )
        assert req.work_id.startswith("awr_")
        assert req.max_tool_calls == 5
        assert req.max_steps == 8
        assert req.execution_allowed is False
        assert req.requested_tools == []
        assert req.playbook_name is None

    def test_request_is_frozen(self) -> None:
        req = AgentWorkRequest(
            goal="Test", profile_name="default", objective="Test",
            work_type="research_review", receipt_root="/tmp/test",
        )
        with pytest.raises(ValidationError, match="frozen"):
            req.goal = "hijacked"  # type: ignore[misc]

    def test_execution_allowed_cannot_be_true(self) -> None:
        with pytest.raises(ValidationError):
            AgentWorkRequest(
                goal="Test", profile_name="default", objective="Test",
                work_type="research_review", receipt_root="/tmp/test",
                execution_allowed=True,  # type: ignore[arg-type]
            )

    def test_custom_budget(self) -> None:
        req = AgentWorkRequest(
            goal="Test", profile_name="default", objective="Test",
            work_type="ips_drift_review", receipt_root="/tmp/test",
            max_tool_calls=3, max_steps=5,
        )
        assert req.max_tool_calls == 3
        assert req.max_steps == 5

    def test_with_playbook_and_tools(self) -> None:
        req = AgentWorkRequest(
            goal="IPS check", profile_name="default",
            objective="Verify allocation", work_type="ips_drift_review",
            receipt_root="/tmp/test", playbook_name="ips-drift-review",
            requested_tools=["get_quote_snapshot", "get_capital_context_projection"],
            context_pack_names=["current_ips", "capital_summary"],
        )
        assert req.playbook_name == "ips-drift-review"
        assert len(req.requested_tools) == 2


class TestAgentWorkResult:

    def test_minimal_result(self) -> None:
        result = AgentWorkResult(
            work_id="awr_test", goal="Test", profile_name="default",
            work_type="research_review", outcome="succeeded",
            stop_reason="completed",
        )
        assert result.outcome == "succeeded"
        assert result.stop_reason == "completed"
        assert result.execution_allowed is False
        assert result.data_gaps == []

    def test_result_is_frozen(self) -> None:
        result = AgentWorkResult(
            work_id="awr_test", goal="Test", profile_name="default",
            work_type="research_review", outcome="succeeded",
            stop_reason="completed",
        )
        with pytest.raises(ValidationError, match="frozen"):
            result.outcome = "failed"  # type: ignore[misc]

    def test_execution_allowed_cannot_be_true(self) -> None:
        with pytest.raises(ValidationError):
            AgentWorkResult(
                work_id="awr_test", goal="Test", profile_name="default",
                work_type="research_review", outcome="succeeded",
                stop_reason="completed",
                execution_allowed=True,  # type: ignore[arg-type]
            )

    def test_partial_result_with_gaps(self) -> None:
        result = AgentWorkResult(
            work_id="awr_test", goal="Test", profile_name="default",
            work_type="evidence_triage", outcome="partial",
            stop_reason="tool_unavailable",
            data_gaps=["missing provider data"],
            findings=["proposal quality: warn"],
        )
        assert len(result.data_gaps) == 1
        assert len(result.findings) == 1


class TestAgentWorkContextSnapshot:

    def test_freeze_empty_context(self) -> None:
        snap = freeze_work_context(work_id="awr_test", profile_name="default")
        assert snap.work_id == "awr_test"
        assert snap.context_trust_by_ref == {}
        assert snap.context_refs == []
        assert snap.findings == []
        assert snap.execution_allowed is False

    def test_freeze_with_payload_extracts_trust(self) -> None:
        from finharness.context_trust import trust_for_system_computed

        trust = trust_for_system_computed(source_refs=["ref://ctx1"])
        payload: dict[str, object] = {
            "packs": [{
                "name": "capital_summary",
                "summary": {"trust": trust.model_dump()},
                "source_refs": ["ref://ctx1"],
                "context_pack_refs": ["context_pack://capital_summary"],
            }]
        }
        snap = freeze_work_context(
            work_id="awr_test", profile_name="default",
            context_projection_payload=payload,
        )
        assert snap.context_refs == ["context_pack://capital_summary"]
        assert snap.source_refs == ["ref://ctx1"]
        assert len(snap.context_trust_by_ref) > 0

    def test_snapshot_is_frozen(self) -> None:
        snap = freeze_work_context(work_id="awr_test", profile_name="default")
        with pytest.raises(ValidationError, match="frozen"):
            snap.work_id = "hijacked"  # type: ignore[misc]

    def test_snapshot_has_snapshot_id(self) -> None:
        snap = freeze_work_context(work_id="awr_test", profile_name="default")
        assert snap.snapshot_id.startswith("ctxsnap_")

    def test_malformed_context_produces_finding(self) -> None:
        payload: dict[str, object] = {
            "packs": [{"summary": {"trust": {"source_type": 999}}}],
        }
        snap = freeze_work_context(
            work_id="awr_test", profile_name="default",
            context_projection_payload=payload,
        )
        assert len(snap.findings) > 0  # malformed trust captured
