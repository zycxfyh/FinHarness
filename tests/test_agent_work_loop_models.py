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


class TestBoundedDispatchLoop:

    def test_dispatch_loop_with_valid_tools(self) -> None:
        import tempfile

        from finharness.agent_work_loop import (
            AgentWorkRequest,
            freeze_work_context,
            run_bounded_tool_dispatch_loop,
        )
        with tempfile.TemporaryDirectory() as tmp:
            req = AgentWorkRequest(
                goal="Test dispatch", profile_name="default",
                objective="Test", work_type="research_review",
                receipt_root=tmp,
                tool_requests=[{
                    "tool_name": "get_capital_context_projection",
                    "arguments": {"open_proposals_limit": 2},
                }],
                max_tool_calls=5,
            )
            snap = freeze_work_context(work_id=req.work_id, profile_name="default")
            envelopes, _sr, _data_gaps = run_bounded_tool_dispatch_loop(
                request=req, context_snapshot=snap,
            )
            assert len(envelopes) == 1
            assert _sr == "completed"
            assert envelopes[0]["tool_name"] == "get_capital_context_projection"

    def test_dispatch_loop_respects_max_tool_calls(self) -> None:
        import tempfile

        from finharness.agent_work_loop import (
            AgentWorkRequest,
            freeze_work_context,
            run_bounded_tool_dispatch_loop,
        )
        with tempfile.TemporaryDirectory() as tmp:
            req = AgentWorkRequest(
                goal="Test budget", profile_name="default",
                objective="Test", work_type="research_review",
                receipt_root=tmp,
                requested_tools=["get_quote_snapshot", "get_quote_snapshot",
                                 "get_quote_snapshot"],
                max_tool_calls=2,
            )
            snap = freeze_work_context(work_id=req.work_id, profile_name="default")
            envelopes, stop_reason, _ = run_bounded_tool_dispatch_loop(
                request=req, context_snapshot=snap,
            )
            assert len(envelopes) == 2
            assert stop_reason == "max_tool_calls_reached"

    def test_dispatch_loop_unavailable_tool(self) -> None:
        import tempfile

        from finharness.agent_work_loop import (
            AgentWorkRequest,
            freeze_work_context,
            run_bounded_tool_dispatch_loop,
        )
        with tempfile.TemporaryDirectory() as tmp:
            req = AgentWorkRequest(
                goal="Test unavailable", profile_name="default",
                objective="Test", work_type="research_review",
                receipt_root=tmp,
                requested_tools=["nonexistent_tool"],
                max_tool_calls=5,
            )
            snap = freeze_work_context(work_id=req.work_id, profile_name="default")
            envelopes, _sr, _data_gaps = run_bounded_tool_dispatch_loop(
                request=req, context_snapshot=snap,
            )
            # Failed attempts are still traced and persisted as result artifacts.
            assert len(envelopes) == 1
            assert envelopes[0]["error_code"] == "TOOL_UNREGISTERED"
            assert envelopes[0]["artifact_ref"]
            assert envelopes[0]["autonomy_admission_ref"]
            assert _sr == "tool_unavailable"
            assert len(_data_gaps) > 0
            assert "TOOL_UNREGISTERED" in _data_gaps[0]

    def test_dispatch_loop_empty_tools(self) -> None:
        import tempfile

        from finharness.agent_work_loop import (
            AgentWorkRequest,
            freeze_work_context,
            run_bounded_tool_dispatch_loop,
        )
        with tempfile.TemporaryDirectory() as tmp:
            req = AgentWorkRequest(
                goal="Test empty", profile_name="default",
                objective="Test", work_type="research_review",
                receipt_root=tmp,
                requested_tools=[], max_tool_calls=5,
            )
            snap = freeze_work_context(work_id=req.work_id, profile_name="default")
            envelopes, stop_reason, _ = run_bounded_tool_dispatch_loop(
                request=req, context_snapshot=snap,
            )
            assert len(envelopes) == 0
            assert stop_reason == "completed"


class TestPlaybookBinding:

    def test_bind_valid_playbook(self) -> None:
        from finharness.agent_work_loop import bind_playbook_to_work

        binding = bind_playbook_to_work("ips-drift-review")
        assert binding.bound is True
        assert binding.playbook_name == "ips-drift-review"
        assert binding.version != "unknown"
        assert binding.required_context_packs == ["current_ips", "capital_summary"]
        assert binding.recommended_evaluators == ["plan_draft_evaluator"]
        assert binding.findings == []

    def test_bind_missing_playbook(self) -> None:
        from finharness.agent_work_loop import bind_playbook_to_work

        binding = bind_playbook_to_work("nonexistent_playbook")
        assert binding.bound is False
        assert binding.version == "unknown"
        assert len(binding.findings) > 0

    def test_binding_model_is_frozen(self) -> None:
        import pytest
        from pydantic import ValidationError

        from finharness.agent_work_loop import AgentWorkPlaybookBinding

        b = AgentWorkPlaybookBinding(playbook_name="test", version="1.0")
        with pytest.raises(ValidationError, match="frozen"):
            b.playbook_name = "x"  # type: ignore[misc]
