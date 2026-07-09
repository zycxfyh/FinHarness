"""AgentRuntime -> AgentRunReceipt bridge with trace sink.

Agentic-space dimension: Trace Space / Runtime Integration.

v0.1 (PR #209): Adds AgentRuntimeTraceSink — integrates directly with
dispatch_agent_tool() instead of requiring the caller to collect results
and pass them to a separate helper function.
"""

from __future__ import annotations

from pathlib import Path

from finharness.agent_run_receipts import (
    AgentRunOutcome,
    AgentRunReceipt,
    AgentToolCallSummary,
    write_agent_run_receipt,
)
from finharness.agent_runtime import AgentToolRuntimeResult


class AgentRuntimeTraceSink:
    """Live trace sink that records dispatch results during a run.

    Use sink.dispatch() instead of dispatch_agent_tool() to automatically
    record results. Call finalize() to produce an AgentRunReceipt.

    Usage:
        sink = AgentRuntimeTraceSink(goal="...", profile_name="...", receipt_root=...)
        sink.dispatch(profile_name="default", tool_name="...", arguments={...})
        sink.dispatch(profile_name="default", tool_name="...", arguments={...})
        receipt = sink.finalize()
    """

    def __init__(
        self,
        *,
        goal: str,
        profile_name: str,
        receipt_root: str | Path,
        context_refs: list[str] | None = None,
    ) -> None:
        if not goal.strip():
            raise ValueError("goal must not be empty")
        self._goal = goal.strip()
        self._profile_name = profile_name
        self._receipt_root = Path(receipt_root)
        self._context_refs = context_refs or []
        self._results: list[AgentToolRuntimeResult] = []
        self._finalized = False

    def record_result(self, result: AgentToolRuntimeResult) -> None:
        """Record a dispatch result. Safe to call for both success and failure."""
        if self._finalized:
            raise RuntimeError("cannot record_result after finalize()")
        self._results.append(result)

    def dispatch(
        self,
        *,
        profile_name: str,
        tool_name: str,
        arguments: dict[str, object],
    ) -> AgentToolRuntimeResult:
        """Dispatch a tool and record the result in this trace sink.

        Calls dispatch_agent_tool() and automatically records the result,
        whether it succeeds or fails.
        """
        from finharness.agent_runtime import dispatch_agent_tool

        result = dispatch_agent_tool(
            profile_name=profile_name,
            tool_name=tool_name,
            arguments=arguments,
        )
        self.record_result(result)
        return result

    def finalize(self) -> AgentRunReceipt:
        """Finalize the trace and write an AgentRunReceipt.

        Must be called exactly once. After finalize(), no more results
        can be recorded.
        """
        if self._finalized:
            raise RuntimeError("finalize() already called")
        self._finalized = True

        if not self._results:
            raise ValueError("no dispatch results recorded — cannot finalize")

        return build_agent_run_receipt_from_runtime_results(
            goal=self._goal,
            profile_name=self._profile_name,
            runtime_results=self._results,
            receipt_root=self._receipt_root,
            context_refs=self._context_refs,
        )

    @property
    def result_count(self) -> int:
        """Number of results recorded so far."""
        return len(self._results)


def build_agent_run_receipt_from_runtime_results(
    *,
    goal: str,
    profile_name: str,
    runtime_results: list[AgentToolRuntimeResult],
    receipt_root: str | Path,
    context_refs: list[str] | None = None,
) -> AgentRunReceipt:
    """Build an AgentRunReceipt from AgentRuntime dispatch results.

    Maps each AgentToolRuntimeResult to an AgentToolCallSummary,
    derives the aggregate outcome and stop reason, collects evidence
    refs and data gaps, and writes a receipt-only JSON file.

    Returns the frozen AgentRunReceipt. execution_allowed is always False.
    authority_transition is always False — this bridge only records trace.
    """
    if not runtime_results:
        raise ValueError("runtime_results must not be empty")

    tool_calls: list[AgentToolCallSummary] = []
    evidence_refs: list[str] = []
    data_gaps: list[str] = []

    for rt in runtime_results:
        tc = _to_tool_call_summary(rt)
        tool_calls.append(tc)
        _collect_evidence_refs(rt, evidence_refs)
        _collect_data_gaps(rt, data_gaps)

    outcome = _derive_outcome(runtime_results)
    stop_reason = _derive_stop_reason(runtime_results, outcome)

    return write_agent_run_receipt(
        goal=goal,
        profile_name=profile_name,
        tool_calls=tool_calls,
        outcome=outcome,
        stop_reason=stop_reason,
        receipt_root=receipt_root,
        context_refs=context_refs or [],
        evidence_refs=evidence_refs,
        data_gaps=data_gaps,
    )


def _to_tool_call_summary(rt: AgentToolRuntimeResult) -> AgentToolCallSummary:
    return AgentToolCallSummary(
        tool_name=rt.tool_name,
        side_effect=rt.side_effect,
        ok=rt.ok,
        evidence_refs=list(rt.evidence.source_refs) if rt.evidence else [],
        receipt_refs=list(rt.evidence.receipt_refs) if rt.evidence else [],
        error_code=rt.error.code if rt.error else None,
        result_truncated=rt.truncated,
    )


def _collect_evidence_refs(
    rt: AgentToolRuntimeResult,
    evidence_refs: list[str],
) -> None:
    if rt.evidence is None:
        return
    for ref in rt.evidence.source_refs:
        if ref not in evidence_refs:
            evidence_refs.append(ref)


def _collect_data_gaps(
    rt: AgentToolRuntimeResult,
    data_gaps: list[str],
) -> None:
    if rt.error is not None:
        gap = f"{rt.tool_name}: {rt.error.code}"
        if gap not in data_gaps:
            data_gaps.append(gap)
    if rt.evidence is not None:
        for gap in rt.evidence.data_gaps:
            if gap not in data_gaps:
                data_gaps.append(gap)


def _derive_outcome(results: list[AgentToolRuntimeResult]) -> AgentRunOutcome:
    ok_count = sum(1 for r in results if r.ok)
    if ok_count == 0:
        return "failed"
    if ok_count == len(results):
        return "succeeded"
    return "partial"


def _derive_stop_reason(
    results: list[AgentToolRuntimeResult],
    outcome: AgentRunOutcome,
) -> str:
    failed = [r for r in results if not r.ok]
    codes = [r.error.code for r in failed if r.error]
    if outcome == "succeeded":
        return "runtime_dispatch_complete"
    if outcome == "failed":
        return f"dispatch_failed: {', '.join(codes)}"
    return f"partial_dispatch: {', '.join(codes)}"
