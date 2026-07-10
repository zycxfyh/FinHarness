"""Fakes for behavioral acceptance testing of the Agent Work Loop.

These fakes replace source-code string checks with real behavioral
observation, enabling contracts to be verified through execution
rather than string matching.
"""

from __future__ import annotations

from typing import Any


class RecordingTool:
    """A tool that records every call with its arguments.

    Does not execute any real work — only captures the invocation.
    """

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, **arguments: object) -> dict[str, object]:
        self.calls.append(dict(arguments))
        return {"status": "ok", "arguments": arguments, "tool": "RecordingTool"}

    @property
    def call_count(self) -> int:
        return len(self.calls)

    @property
    def last_arguments(self) -> dict[str, object] | None:
        return self.calls[-1] if self.calls else None


class FailingTool:
    """A tool that always fails with a given error code."""

    def __init__(self, error_code: str = "tool_error") -> None:
        self.error_code = error_code
        self.calls: list[dict[str, object]] = []

    def __call__(self, **arguments: object) -> dict[str, object]:
        self.calls.append(dict(arguments))
        return {"status": "error", "error_code": self.error_code, "tool": "FailingTool"}


class ScriptedDecisionPort:
    """A decision port that follows a scripted sequence of decisions.

    Each call to decide() returns the next decision in the script.
    """

    def __init__(self, decisions: list[dict[str, Any]]) -> None:
        self.decisions = decisions
        self.call_index = 0
        self.observations: list[dict[str, object] | None] = []

    def decide(
        self,
        *,
        request: object,
        snapshot: object,
        state: object,
        observation: object | None,
    ) -> dict[str, Any]:
        self.observations.append(
            None if observation is None
            else {"ok": getattr(observation, "ok", None)}
        )
        if self.call_index >= len(self.decisions):
            return {"kind": "finish", "decision_summary": "script exhausted"}
        decision = self.decisions[self.call_index]
        self.call_index += 1
        return decision


class FailingArtifactStore:
    """An artifact store that fails on write, for testing error paths."""

    def __init__(self, fail_on: str = "write") -> None:
        self.fail_on = fail_on
        self.write_attempts: list[dict[str, object]] = []

    def write_artifact(self, **kwargs: object) -> None:
        self.write_attempts.append(dict(kwargs))
        if self.fail_on == "write":
            raise OSError("Artifact store write failure (injected)")
