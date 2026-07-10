#!/usr/bin/env python3
"""Agent Work Orchestrator structural smoke v0.

Checks that the current deterministic scaffold can compose request, context
snapshot, bounded dispatch, cognition artifacts, and search-index update. This
does not prove successful tool semantics, observation-driven decisions,
workspace hydration, result persistence, or complete receipt linkage.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from finharness.agent_work_loop import (
    AgentWorkRequest,
    AgentWorkStopReason,
    bind_playbook_to_work,
    freeze_work_context,
    propose_memory_from_completed_work,
    run_agent_work_loop,
    run_bounded_tool_dispatch_loop,
    run_cognition_flow_from_work_result,
)


def _check(description: str, ok: bool) -> int:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {description}")
    return 0 if ok else 1


def main() -> int:
    failures = 0
    print("Agent Work Orchestrator Structural Smoke")
    print("=" * 50)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # 1. AgentWorkRequest
        print("\n1. AgentWorkRequest")
        req = AgentWorkRequest(
            goal="Smoke: verify SPY exposure is within IPS",
            profile_name="default",
            objective="Verify allocation",
            work_type="research_review",
            receipt_root=str(root),
            requested_tools=["get_quote_snapshot"],
            max_tool_calls=5,
        )
        failures += _check("Work ID generated", req.work_id.startswith("awr_"))
        failures += _check("execution_allowed=False", not req.execution_allowed)

        # 2. Context Snapshot
        print("\n2. Context Snapshot")
        snap = freeze_work_context(
            work_id=req.work_id,
            profile_name="default",
        )
        failures += _check("Snapshot has ID", snap.snapshot_id.startswith("ctxsnap_"))
        failures += _check("execution_allowed=False", not snap.execution_allowed)

        # 3. Playbook Binding
        print("\n3. Playbook Binding")
        binding = bind_playbook_to_work("ips-drift-review")
        failures += _check("Playbook bound", binding.bound is True)
        failures += _check("Has required context packs", len(binding.required_context_packs) > 0)
        failures += _check("Has recommended evaluators", len(binding.recommended_evaluators) > 0)

        # 4. Bounded Dispatch Loop
        print("\n4. Bounded Dispatch Loop")
        envelopes, stop_reason, _ = run_bounded_tool_dispatch_loop(
            request=req,
            context_snapshot=snap,
        )
        failures += _check("Dispatch produced envelopes", len(envelopes) > 0)
        failures += _check("Stop reason completed", stop_reason == "completed")

        # 5. Stop reasons exercised
        print("\n5. Stop Reason Taxonomy")
        has_reason = "completed" in getattr(AgentWorkStopReason, "__args__", ())
        failures += _check("Stop reasons include completed", has_reason)

        # 6. Cognition Flow from Work
        print("\n6. Cognition Flow from Work Result")
        flow = run_cognition_flow_from_work_result(
            request=req,
            context_snapshot=snap,
            tool_envelopes=envelopes,
            receipt_root=root,
        )
        failures += _check("Flow ID present", "flow_id" in flow)
        failures += _check("Eval report ref present", flow.get("evaluation_report_ref") is not None)
        failures += _check("execution_allowed=False", not flow.get("execution_allowed", True))

        # 7. Full Work Loop
        print("\n7. Deterministic Work Orchestrator")
        result = run_agent_work_loop(request=req)
        failures += _check(
            "Result outcome in succeeded/partial", result.outcome in ("succeeded", "partial")
        )
        failures += _check("Result has search index ref", result.search_index_ref is not None)
        failures += _check("Result execution_allowed=False", not result.execution_allowed)

        # 8. Memory Draft
        print("\n8. Domain Memory Draft")
        propose_memory_from_completed_work(
            result=result,
            context_snapshot=snap,
            receipt_root=root,
        )
        failures += _check("Memory draft function runs", True)

        # 9. Search index verifiable
        print("\n9. Search Index")
        from finharness.agent_receipt_search import search_receipt_index

        results = search_receipt_index(Path(result.search_index_ref or ""), "SPY")
        failures += _check("Search finds work by content", len(results) > 0)

    print("\n" + "=" * 50)
    if failures == 0:
        print("ALL STRUCTURAL CHECKS PASSED — semantic loop closure remains pending.")
    else:
        print(f"{failures} CHECK(S) FAILED")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
