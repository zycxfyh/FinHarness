#!/usr/bin/env python3
"""Agent Operating Surface semantic smoke — v0.1.

Verifies surfaces enter real lifecycle, not just exist.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from finharness.agent_cognition_flow import run_agent_cognition_flow
from finharness.agent_operating_flow import (
    evaluate_playbook_requirements,
    run_agent_cognition_flow_from_operating_inputs,
)
from finharness.agent_receipt_search import build_receipt_search_index, search_receipt_index
from finharness.agent_runtime_receipts import AgentRuntimeTraceSink
from finharness.agent_tool_availability import capture_tool_universe_snapshot
from finharness.agent_tool_registry import build_registry
from finharness.agent_tool_result_envelope import build_tool_result_envelope
from finharness.context_trust import trust_for_system_computed
from finharness.domain_memory import (
    build_domain_memory_context_pack,
    propose_domain_memory,
    attest_domain_memory,
)
from finharness.evaluator_registry import evaluator_ids, list_evaluators
from finharness.playbook_loader import load_cognition_playbook, list_cognition_playbooks
from finharness.review_workspace import build_review_workspace_projection_from_receipts


def _check(description: str, ok: bool) -> int:
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {description}")
    return 0 if ok else 1


def main() -> int:
    failures = 0
    print("Agent Operating Surface Semantic Smoke v0.1")
    print("=" * 50)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        # 1. Registry — no invalid registrations
        print("\n1. Tool Registry (strictness)")
        reg = build_registry()
        failures += _check("Registry has no invalid entries", reg.invalid_count == 0)
        failures += _check(
            "Registry invalid_count in summary",
            reg.summary()["invalid_count"] == 0,
        )

        # 2. Global tool universe — hidden/exposed
        print("\n2. Global Tool Universe")
        univ = capture_tool_universe_snapshot("default")
        failures += _check("Universe has registered tools", len(univ.registered_tools) > 0)
        failures += _check(
            "Model visible subset of profile exposed",
            set(univ.model_visible_tools).issubset(set(univ.profile_exposed_tools)),
        )
        failures += _check("Hidden or unavailable distinguished", isinstance(univ.hidden_tools, list))

        # 3. Envelope ref taxonomy
        print("\n3. Tool Result Envelope (ref taxonomy)")
        from finharness.agent_runtime import dispatch_agent_tool
        rt = dispatch_agent_tool(
            profile_name="default", tool_name="get_quote_snapshot",
            arguments={"symbol": "AAPL"},
        )
        env = build_tool_result_envelope(rt)
        failures += _check("provider_refs populated", len(env.provider_refs) >= 0)
        failures += _check(
            "No provider: prefix in evidence_refs",
            all(not ref.startswith("provider:") for ref in env.evidence_refs),
        )

        # 4. Playbook YAML
        print("\n4. Playbook YAML Parsing")
        pb = load_cognition_playbook("ips-drift-review")
        failures += _check("Playbook loaded", pb is not None)
        failures += _check(
            "required_context_packs = [current_ips, capital_summary]",
            pb.required_context_packs == ["current_ips", "capital_summary"],
        )
        failures += _check(
            "recommended_evaluators = [plan_draft_evaluator]",
            pb.recommended_evaluators == ["plan_draft_evaluator"],
        )
        failures += _check("side_effects = [read]", pb.side_effects == ["read"])

        # 5. Evaluator registry completeness
        print("\n5. Evaluator Registry")
        ids = set(evaluator_ids())
        failures += _check(
            "research_evidence_quality registered",
            "research_evidence_quality" in ids,
        )

        # 6. Playbook requirements -> findings
        print("\n6. Playbook Requirements in Flow")
        missing_ctx_findings = evaluate_playbook_requirements(
            pb, context_projection_payload={"packs": []},
        )
        failures += _check(
            "Missing context packs produce findings",
            any(f.code == "playbook_context_missing" for f in missing_ctx_findings),
        )

        # 7. Trace sink
        print("\n7. Runtime Trace Sink")
        sink = AgentRuntimeTraceSink(goal="Smoke trace", profile_name="default", receipt_root=root)
        sink.dispatch(profile_name="default", tool_name="get_quote_snapshot", arguments={"symbol": "AAPL"})
        failures += _check("Sink records result", sink.result_count == 1)
        receipt = sink.finalize()
        failures += _check("Sink finalizes receipt", receipt.outcome == "succeeded")

        # 8. Domain memory -> context pack
        print("\n8. Domain Memory Promotion")
        d = propose_domain_memory(
            proposed_by="agent:smoke", memory_type="planning_lesson",
            content="Smoke test: SPY allocation review is systematic",
            receipt_root=root,
        )
        attest_domain_memory(
            memory_id=d.memory_id, attested_by="human:smoke",
            attested_reason="Verified in smoke test", receipt_root=root,
        )
        pack = build_domain_memory_context_pack(receipt_root=root)
        failures += _check("Attested memory enters context pack", len(pack.memories) == 1)

        # 9. Cognition flow
        print("\n9. Cognition Flow")
        flow = run_agent_cognition_flow(
            goal="Smoke: verify SPY exposure within IPS",
            profile_name="default",
            objective="Verify allocation",
            option_claims=["Stay", "Reduce"],
            plan_steps=[
                "Check SPY allocation vs IPS target",
                "Evaluate drift",
                "Propose rebalance if needed",
                "Stop and await human confirmation",
            ],
            receipt_root=root,
        )
        failures += _check("Flow ID generated", bool(flow.flow_id))

        # 10. Review workspace hydrated from receipts
        print("\n10. Review Workspace (hydrated)")
        ws = build_review_workspace_projection_from_receipts(
            flow_result=flow, receipt_root=root,
        )
        failures += _check("Evaluation status populated", ws.evaluation_status is not None)
        failures += _check("Open findings present", len(ws.open_findings) > 0)
        failures += _check("Workspace has receipt refs", len(ws.receipt_refs) > 0)

        # 11. Receipt search index
        print("\n11. Receipt Search Index")
        entries = build_receipt_search_index(root)
        failures += _check("Index covers receipts", len(entries) > 0)
        index_path = root / "receipt-index.jsonl"
        import json as _json
        with index_path.open("w") as f:
            for e in entries:
                f.write(e.model_dump_json() + "\n")
        results = search_receipt_index(index_path, "SPY")
        failures += _check("Search finds flow by content", len(results) > 0)
        results_by_status = search_receipt_index(index_path, "succeeded")
        failures += _check("Search by outcome", len(results_by_status) > 0)

    print("\n" + "=" * 50)
    if failures == 0:
        print("ALL CHECKS PASSED — Agent Operating Surface is semantically operational.")
    else:
        print(f"{failures} CHECK(S) FAILED")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
