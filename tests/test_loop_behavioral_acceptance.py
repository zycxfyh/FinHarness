"""Behavioral acceptance tests using fakes instead of source-code inspection.

LOOP-01B: These tests prove that acceptance contracts can be verified
through execution behavior rather than string-matching on source code.
"""

from __future__ import annotations

import unittest

from tests.fakes import (
    FailingArtifactStore,
    FailingTool,
    RecordingTool,
    ScriptedDecisionPort,
)


class RecordingToolBehavioralTest(unittest.TestCase):
    """RecordingTool captures arguments at call time."""

    def test_captures_string_argument(self) -> None:
        tool = RecordingTool()
        tool(symbol="SPY")
        self.assertEqual(tool.call_count, 1)
        self.assertEqual(tool.last_arguments, {"symbol": "SPY"})

    def test_captures_numeric_argument(self) -> None:
        tool = RecordingTool()
        tool(quantity=100)
        self.assertEqual(tool.last_arguments, {"quantity": 100})

    def test_captures_nested_argument(self) -> None:
        tool = RecordingTool()
        tool(filters={"sector": "tech", "limit": 10})
        self.assertEqual(
            tool.last_arguments,
            {"filters": {"sector": "tech", "limit": 10}},
        )

    def test_call_count_multiple_invocations(self) -> None:
        tool = RecordingTool()
        for i in range(5):
            tool(step=i)
        self.assertEqual(tool.call_count, 5)

    def test_last_arguments_unchanged_after_read(self) -> None:
        """Reading last_arguments returns the same content each call."""
        tool = RecordingTool()
        tool(x=1)
        first_read = tool.last_arguments
        second_read = tool.last_arguments
        self.assertEqual(first_read, second_read)


class FailingToolBehavioralTest(unittest.TestCase):
    """FailingTool always returns error status."""

    def test_returns_error_status(self) -> None:
        tool = FailingTool()
        result = tool(symbol="UNKNOWN")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error_code"], "tool_error")

    def test_custom_error_code(self) -> None:
        tool = FailingTool(error_code="bad_symbol")
        result = tool(symbol="???")
        self.assertEqual(result["error_code"], "bad_symbol")


class ScriptedDecisionPortBehavioralTest(unittest.TestCase):
    """ScriptedDecisionPort follows a predetermined sequence."""

    def test_returns_scripted_decisions_in_order(self) -> None:
        port = ScriptedDecisionPort([
            {"kind": "call_tool", "decision_summary": "first"},
            {"kind": "call_tool", "decision_summary": "second"},
            {"kind": "finish", "decision_summary": "done"},
        ])
        self.assertEqual(port.decide(
            request=None, snapshot=None, state=None, observation=None,
        )["kind"], "call_tool")
        self.assertEqual(port.decide(
            request=None, snapshot=None, state=None, observation=None,
        )["kind"], "call_tool")
        self.assertEqual(port.decide(
            request=None, snapshot=None, state=None, observation=None,
        )["kind"], "finish")

    def test_exhausted_script_returns_finish(self) -> None:
        port = ScriptedDecisionPort([{"kind": "finish", "decision_summary": "done"}])
        port.decide(request=None, snapshot=None, state=None, observation=None)
        result = port.decide(request=None, snapshot=None, state=None, observation=None)
        self.assertEqual(result["kind"], "finish")
        self.assertIn("exhausted", result["decision_summary"])

    def test_captures_observations(self) -> None:
        port = ScriptedDecisionPort([
            {"kind": "call_tool", "decision_summary": "a"},
        ])

        class FakeObservation:
            ok = True

        port.decide(request=None, snapshot=None, state=None, observation=FakeObservation())
        self.assertEqual(len(port.observations), 1)
        self.assertEqual(port.observations[0], {"ok": True})


class FailingArtifactStoreTest(unittest.TestCase):
    """FailingArtifactStore raises on write."""

    def test_raises_on_write(self) -> None:
        store = FailingArtifactStore()
        with self.assertRaises(OSError):
            store.write_artifact(work_id="test-1")

    def test_records_write_attempts_even_on_failure(self) -> None:
        import contextlib

        store = FailingArtifactStore()
        with contextlib.suppress(OSError):
            store.write_artifact(work_id="test-2")
        self.assertEqual(len(store.write_attempts), 1)
        self.assertEqual(store.write_attempts[0]["work_id"], "test-2")


if __name__ == "__main__":
    unittest.main()
