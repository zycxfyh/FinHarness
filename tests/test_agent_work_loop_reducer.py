"""Behavioral contracts for typed, observation-driven Agent work dispatch."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finharness.agent_runtime import AgentToolRuntimeResult
from finharness.agent_work_loop import (
    AgentWorkDecision,
    AgentWorkDecisionState,
    AgentWorkRequest,
    AgentWorkToolRequest,
    freeze_work_context,
    run_bounded_tool_dispatch_loop,
)
from finharness.autonomy_control import AgentAutonomyLevel, WorldFidelityLevel


class AgentWorkLoopReducerTest(unittest.TestCase):
    def _request(self, root: str, **overrides: object) -> AgentWorkRequest:
        payload: dict[str, object] = {
            "work_id": "work_reducer_test",
            "agent_id": "agent:capital",
            "goal": "inspect the current capital state",
            "profile_name": "default",
            "objective": "gather bounded evidence",
            "work_type": "evidence_triage",
            "receipt_root": root,
        }
        payload.update(overrides)
        return AgentWorkRequest(**payload)

    def test_typed_arguments_reach_dispatch_and_are_bound_to_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = self._request(
                tmp,
                tool_requests=[
                    AgentWorkToolRequest(
                        tool_name="get_quote_snapshot",
                        arguments={"symbol": "SPY"},
                    )
                ],
            )
            snapshot = freeze_work_context(
                work_id=request.work_id,
                profile_name=request.profile_name,
            )
            runtime_result = AgentToolRuntimeResult(
                ok=True,
                tool_name="get_quote_snapshot",
                side_effect="read",
                result={"status": "ok", "symbol": "SPY"},
            )
            with patch(
                "finharness.agent_runtime_receipts.AgentRuntimeTraceSink.dispatch",
                return_value=runtime_result,
            ) as dispatch:
                envelopes, stop_reason, _ = run_bounded_tool_dispatch_loop(
                    request=request,
                    context_snapshot=snapshot,
                )

            dispatch.assert_called_once_with(
                profile_name="default",
                tool_name="get_quote_snapshot",
                arguments={"symbol": "SPY"},
            )
            self.assertEqual(stop_reason, "completed")
            self.assertEqual(envelopes[0]["request_argument_keys"], ["symbol"])
            artifact = Path(tmp) / str(envelopes[0]["artifact_ref"])
            self.assertTrue(artifact.is_file())
            stored = json.loads(artifact.read_text(encoding="utf-8"))
            self.assertEqual(
                stored["request_arguments_sha256"],
                envelopes[0]["request_arguments_sha256"],
            )

    def test_next_decision_consumes_preceding_tool_observation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = self._request(tmp, max_steps=3)
            snapshot = freeze_work_context(
                work_id=request.work_id,
                profile_name=request.profile_name,
            )
            seen_kinds: list[str] = []

            def decision_port(state: AgentWorkDecisionState) -> AgentWorkDecision:
                seen_kinds.append(state.observation.kind)
                if state.observation.kind == "work_started":
                    return AgentWorkDecision(
                        action="dispatch",
                        tool_request=AgentWorkToolRequest(
                            tool_name="get_quote_snapshot",
                            arguments={"symbol": "SPY"},
                        ),
                    )
                self.assertEqual(state.observation.tool_name, "get_quote_snapshot")
                self.assertTrue(state.observation.ok)
                self.assertIsNotNone(state.observation.artifact_ref)
                return AgentWorkDecision(action="complete")

            runtime_result = AgentToolRuntimeResult(
                ok=True,
                tool_name="get_quote_snapshot",
                side_effect="read",
                result={"status": "ok"},
            )
            with patch(
                "finharness.agent_runtime_receipts.AgentRuntimeTraceSink.dispatch",
                return_value=runtime_result,
            ):
                envelopes, stop_reason, _ = run_bounded_tool_dispatch_loop(
                    request=request,
                    context_snapshot=snapshot,
                    decision_port=decision_port,
                )

            self.assertEqual(seen_kinds, ["work_started", "tool_result"])
            self.assertEqual(len(envelopes), 1)
            self.assertEqual(stop_reason, "completed")

    def test_admission_denial_precedes_review_write_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = self._request(
                tmp,
                profile_name="review-draft",
                requested_autonomy=AgentAutonomyLevel.AUT2_DURABLE_LOOP,
                tool_requests=[
                    AgentWorkToolRequest(
                        tool_name="draft_governed_proposal_from_context",
                        arguments={},
                    )
                ],
            )
            snapshot = freeze_work_context(
                work_id=request.work_id,
                profile_name=request.profile_name,
            )
            with patch(
                "finharness.agent_runtime_receipts.AgentRuntimeTraceSink.dispatch"
            ) as dispatch:
                envelopes, stop_reason, gaps = run_bounded_tool_dispatch_loop(
                    request=request,
                    context_snapshot=snapshot,
                    runtime_autonomy_ceiling=AgentAutonomyLevel.AUT2_DURABLE_LOOP,
                    runtime_world_fidelity=WorldFidelityLevel.W1_VERSIONED_DECISIONS,
                )

            dispatch.assert_not_called()
            self.assertEqual(len(envelopes), 1)
            self.assertEqual(envelopes[0]["error_code"], "AUTONOMY_ADMISSION_DENIED")
            self.assertEqual(stop_reason, "human_review_required")
            self.assertTrue(any("candidate" in gap for gap in gaps))
            reports = list((Path(tmp) / "autonomy-admissions").glob("*.json"))
            self.assertEqual(len(reports), 1)
            payload = json.loads(reports[0].read_text(encoding="utf-8"))
            self.assertEqual(payload["disposition"], "candidate")
            self.assertFalse(payload["execution_allowed"])

    def test_agent_request_cannot_raise_harness_runtime_ceiling(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            request = self._request(
                tmp,
                requested_autonomy=AgentAutonomyLevel.AUT6_CONTINUOUS_AGENT,
                tool_requests=[
                    AgentWorkToolRequest(
                        tool_name="get_quote_snapshot",
                        arguments={"symbol": "SPY"},
                    )
                ],
            )
            snapshot = freeze_work_context(
                work_id=request.work_id,
                profile_name=request.profile_name,
            )
            with patch(
                "finharness.agent_runtime_receipts.AgentRuntimeTraceSink.dispatch"
            ) as dispatch:
                envelopes, stop_reason, gaps = run_bounded_tool_dispatch_loop(
                    request=request,
                    context_snapshot=snapshot,
                )

            dispatch.assert_not_called()
            self.assertEqual(len(envelopes), 1)
            self.assertEqual(envelopes[0]["error_code"], "AUTONOMY_ADMISSION_DENIED")
            self.assertEqual(stop_reason, "evaluation_blocked")
            self.assertTrue(any("blocked" in gap for gap in gaps))


if __name__ == "__main__":
    unittest.main()
