"""AgentRuntime → AgentRunReceipt bridge.

Agentic-space dimension: Trace Space / Runtime Integration.

Bridges real AgentRuntime dispatch results into receipt-only AgentRunReceipt traces.
No StateCore table. No Execution Kernel change.
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
    """Convert a runtime result to a receipt-compatible tool call summary."""
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
    """Extract deduplicated evidence source refs from a runtime result."""
    if rt.evidence is None:
        return
    for ref in rt.evidence.source_refs:
        if ref not in evidence_refs:
            evidence_refs.append(ref)


def _collect_data_gaps(
    rt: AgentToolRuntimeResult,
    data_gaps: list[str],
) -> None:
    """Extract deduplicated data gaps from a runtime result."""
    if rt.error is not None:
        gap = f"{rt.tool_name}: {rt.error.code}"
        if gap not in data_gaps:
            data_gaps.append(gap)
    if rt.evidence is not None:
        for gap in rt.evidence.data_gaps:
            if gap not in data_gaps:
                data_gaps.append(gap)


def _derive_outcome(results: list[AgentToolRuntimeResult]) -> AgentRunOutcome:
    """Derive aggregate outcome from a list of runtime results.

    - All ok → succeeded
    - All failed → failed
    - Mixed → partial
    """
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
    """Derive a human-readable stop reason from runtime results."""
    failed = [r for r in results if not r.ok]
    codes = [r.error.code for r in failed if r.error]
    if outcome == "succeeded":
        return "runtime_dispatch_complete"
    if outcome == "failed":
        return f"dispatch_failed: {', '.join(codes)}"
    return f"partial_dispatch: {', '.join(codes)}"
