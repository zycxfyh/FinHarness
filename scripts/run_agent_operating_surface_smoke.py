#!/usr/bin/env python3
"""Agent Operating Surface smoke — end-to-end verification of Wave 2 surfaces.

Runs a deterministic chain through all operating surfaces:
tool registry → availability → projection trust map → tool envelopes →
playbook load → evaluator registry → cognition flow → evaluation →
authority → run receipt → review workspace projection.

No LLM. No broker. No Execution Kernel.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from finharness.agent_cognition_flow import run_agent_cognition_flow
from finharness.agent_operating_flow import run_agent_cognition_flow_from_operating_inputs
from finharness.agent_runtime import AgentToolRuntimeResult
from finharness.agent_tool_availability import capture_tool_availability_snapshots
from finharness.agent_tool_registry import build_registry, registry_summary
from finharness.agent_tool_result_envelope import build_tool_result_envelope
from finharness.context_trust import trust_for_system_computed
from finharness.evaluator_registry import list_evaluators
from finharness.playbook_loader import list_cognition_playbooks, load_cognition_playbook
from finharness.review_workspace import build_review_workspace_projection


def _check(description: str, ok: bool) -> int:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {description}")
    return 0 if ok else 1


def main() -> int:
    failures = 0
    print("Agent Operating Surface Smoke")
    print("=" * 50)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # 1. Tool Registry
        print("\n1. Tool Registry")
        regs = build_registry()
        failures += _check("Registry has tools", len(regs) > 0)
        summary = registry_summary()
        failures += _check("Registry summary consistent", summary["total_registered"] == len(regs))

        # 2. Tool Availability
        print("\n2. Tool Availability")
        snapset = capture_tool_availability_snapshots("default")
        failures += _check("Availability snapshots exist", len(snapset.snapshots) > 0)
        failures += _check("Available count in summary", int(snapset.summary["available_count"]) > 0)

        # 3. Tool Result Envelope
        print("\n3. Tool Result Envelope")
        rt = AgentToolRuntimeResult(
            ok=True,
            tool_name="get_quote_snapshot",
            side_effect="read",
        )
        env = build_tool_result_envelope(rt)
        failures += _check("Envelope built", env.tool_name == "get_quote_snapshot")
        failures += _check("execution_allowed=False", not env.execution_allowed)

        # 4. Playbooks
        print("\n4. Playbooks")
        summaries = list_cognition_playbooks()
        failures += _check("Playbooks listed", len(summaries) > 0)
        pb = load_cognition_playbook("ips-drift-review")
        failures += _check("Playbook loaded", pb is not None and "Procedure" in pb.procedure)

        # 5. Evaluator Registry
        print("\n5. Evaluator Registry")
        evals = list_evaluators()
        failures += _check("Evaluators listed", len(evals) > 0)

        # 6. Cognition Flow (direct)
        print("\n6. Cognition Flow (direct)")
        flow = run_agent_cognition_flow(
            goal="Smoke test: verify SPY exposure is within IPS bands",
            profile_name="default",
            objective="Verify that SPY allocation does not exceed IPS maximum",
            option_claims=["Stay at current allocation", "Reduce SPY to target"],
            plan_steps=[
                "Check current SPY allocation vs IPS target",
                "Evaluate drift",
                "Propose rebalance if needed",
                "Stop and await human confirmation",
            ],
            receipt_root=root,
        )
        failures += _check("Flow ID generated", bool(flow.flow_id))
        failures += _check("Option set ref", bool(flow.option_set_ref))
        failures += _check("Plan draft ref", bool(flow.plan_draft_ref))
        failures += _check("Evaluation report ref", bool(flow.evaluation_report_ref))
        failures += _check("Run receipt ref", bool(flow.agent_run_receipt_ref))
        failures += _check("execution_allowed=False", not flow.execution_allowed)

        # 7. Operating Surface Flow
        print("\n7. Operating Surface Flow")
        trust = trust_for_system_computed(source_refs=["ref://ctx1"])
        payload = {
            "packs": [{
                "name": "capital_summary",
                "summary": {"trust": trust.model_dump()},
                "source_refs": ["ref://ctx1"],
                "context_pack_refs": ["context_pack://capital_summary"],
            }]
        }
        os_flow = run_agent_cognition_flow_from_operating_inputs(
            goal="Smoke: operating surface integration test",
            profile_name="default",
            objective="Verify end-to-end operating surface integration",
            option_claims=["Option A", "Option B"],
            plan_steps=["Step 1: gather context", "Step 2: evaluate", "Step 3: stop"],
            receipt_root=root,
            context_projection_payload=payload,
            playbook_name="ips-drift-review",
        )
        failures += _check("OS Flow ID generated", bool(os_flow.flow_id))
        failures += _check("OS Flow execution_allowed=False", not os_flow.execution_allowed)

        # 8. Review Workspace
        print("\n8. Review Workspace")
        ws = build_review_workspace_projection(flow_result=flow)
        failures += _check("Workspace ID generated", bool(ws.workspace_id))
        failures += _check("Workspace has goal", bool(ws.goal))
        failures += _check("Workspace has receipt refs", len(ws.receipt_refs) > 0)

    print("\n" + "=" * 50)
    if failures == 0:
        print("ALL CHECKS PASSED — Agent Operating Surface is operational.")
    else:
        print(f"{failures} CHECK(S) FAILED")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
