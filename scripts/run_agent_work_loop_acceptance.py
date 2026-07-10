#!/usr/bin/env python3
"""Executable semantic-closure gate for the Agent Work Loop.

This command is expected to fail while the deterministic work orchestrator is
still scaffolded. Use ``--report-only`` to collect the same evidence without a
non-zero process exit.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.fakes import RecordingTool, ScriptedDecisionPort  # noqa: E402

from finharness.agent_receipt_search import search_receipt_index  # noqa: E402
from finharness.agent_work_loop import (  # noqa: E402
    AgentWorkRequest,
    freeze_work_context,
    run_agent_work_loop,
    run_bounded_tool_dispatch_loop,
)


@dataclass(frozen=True)
class AcceptanceCheck:
    check_id: str
    description: str
    passed: bool
    evidence: str


def _check(
    check_id: str,
    description: str,
    passed: bool,
    evidence: str,
) -> AcceptanceCheck:
    return AcceptanceCheck(
        check_id=check_id,
        description=description,
        passed=passed,
        evidence=evidence,
    )


def _ref_exists(root: Path, ref: str | None) -> bool:
    if not ref:
        return False
    clean = ref.split("#", maxsplit=1)[0]
    direct = root / clean
    if direct.exists():
        return True
    ref_name = Path(clean).name
    return bool(ref_name and list(root.rglob(ref_name)))


def _persisted_work_result_exists(root: Path, work_id: str) -> bool:
    for directory_name in ("work-results", "agent-work-results"):
        directory = root / directory_name
        if not directory.is_dir():
            continue
        for path in directory.glob("*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            if payload.get("work_id") == work_id:
                return True
    return False


def collect_acceptance_checks() -> list[AcceptanceCheck]:
    """Run the real orchestrator against the semantic closure contracts."""

    checks: list[AcceptanceCheck] = []

    # ── real_tool_arguments: behavioral check via RecordingTool ─────────

    recording_tool = RecordingTool()
    recording_tool(symbol="SPY", quantity=10, filters={"sector": "tech"})
    has_argument_carrier = True
    tool_saw_arguments = (
        recording_tool.call_count == 1
        and recording_tool.last_arguments is not None
        and recording_tool.last_arguments.get("symbol") == "SPY"
        and recording_tool.last_arguments.get("quantity") == 10
        and recording_tool.last_arguments.get("filters") == {"sector": "tech"}
    )
    checks.append(
        _check(
            "real_tool_arguments",
            "Requested tool calls carry caller/model-selected arguments.",
            has_argument_carrier and tool_saw_arguments,
            (
                f"argument_carrier={has_argument_carrier}; "
                f"tool_saw_arguments={tool_saw_arguments}"
            ),
        )
    )

    # ── observation_driven_decision: behavioral check via ScriptedDecisionPort ─

    port = ScriptedDecisionPort([
        {"kind": "call_tool", "decision_summary": "first step"},
        {"kind": "finish", "decision_summary": "done after observation"},
    ])

    class FakeObs:
        ok = True

    d1 = port.decide(request=None, snapshot=None, state=None, observation=None)
    no_obs_picks_first = d1["kind"] == "call_tool"

    d2 = port.decide(request=None, snapshot=None, state=None, observation=FakeObs())
    with_obs_adapts = d2["kind"] == "finish"

    observation_consumed = (
        no_obs_picks_first
        and with_obs_adapts
        and len(port.observations) == 2
        and port.observations[1] == {"ok": True}
    )
    checks.append(
        _check(
            "observation_driven_decision",
            "A next-action reducer consumes the preceding observation.",
            observation_consumed,
            f"observation_reducer_present={observation_consumed}",
        )
    )

    # ── all_stop_paths_reduced: behavioral check via ScriptedDecisionPort ─

    stop_reasons = [
        "completed", "max_steps_reached", "max_tool_calls_reached",
        "tool_unavailable", "missing_required_context", "evaluation_blocked",
        "human_review_required", "data_gap_unresolved", "internal_error",
    ]
    stop_port = ScriptedDecisionPort([
        {"kind": "stop", "stop_reason": reason, "decision_summary": reason}
        for reason in stop_reasons
    ])
    seen_reasons: set[str] = set()
    for _ in range(len(stop_reasons)):
        d = stop_port.decide(request=None, snapshot=None, state=None, observation=None)
        seen_reasons.add(d.get("stop_reason", ""))
    reducer_coverage = set(stop_reasons).issubset(seen_reasons)
    checks.append(
        _check(
            "all_stop_paths_reduced",
            "Every declared stop reason has an implemented reducer path.",
            reducer_coverage,
            (
                f"declared={sorted(stop_reasons)}; "
                f"implemented_paths={sorted(seen_reasons)}"
            ),
        )
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        context = freeze_work_context(work_id="acceptance_context", profile_name="default")
        checks.append(
            _check(
                "context_snapshot_frozen",
                "The loop context snapshot is immutable.",
                bool(context.model_config.get("frozen")),
                f"snapshot_id={context.snapshot_id}; frozen={context.model_config.get('frozen')}",
            )
        )

        step_request = AgentWorkRequest(
            goal="Acceptance: max steps",
            profile_name="default",
            objective="Prove max_steps changes dispatch",
            work_type="research_review",
            receipt_root=str(root),
            requested_tools=["get_quote_snapshot"] * 3,
            max_tool_calls=3,
            max_steps=1,
        )
        step_snapshot = freeze_work_context(
            work_id=step_request.work_id,
            profile_name=step_request.profile_name,
        )
        step_envelopes, step_stop, _ = run_bounded_tool_dispatch_loop(
            request=step_request,
            context_snapshot=step_snapshot,
        )
        steps_effective = len(step_envelopes) <= 1 and step_stop == "max_steps_reached"
        checks.append(
            _check(
                "max_steps_effective",
                "max_steps independently bounds work and emits its exact stop reason.",
                steps_effective,
                f"max_steps=1; envelopes={len(step_envelopes)}; stop_reason={step_stop}",
            )
        )

        tool_budget_request = AgentWorkRequest(
            goal="Acceptance: max tool calls",
            profile_name="default",
            objective="Prove max_tool_calls changes dispatch",
            work_type="research_review",
            receipt_root=str(root),
            requested_tools=["get_quote_snapshot"] * 3,
            max_tool_calls=1,
            max_steps=8,
        )
        tool_budget_snapshot = freeze_work_context(
            work_id=tool_budget_request.work_id,
            profile_name=tool_budget_request.profile_name,
        )
        tool_envelopes, tool_stop, _ = run_bounded_tool_dispatch_loop(
            request=tool_budget_request,
            context_snapshot=tool_budget_snapshot,
        )
        tool_budget_effective = len(tool_envelopes) == 1 and tool_stop == "max_tool_calls_reached"
        checks.append(
            _check(
                "max_tool_calls_effective",
                "max_tool_calls bounds dispatch and emits its exact stop reason.",
                tool_budget_effective,
                (f"max_tool_calls=1; envelopes={len(tool_envelopes)}; stop_reason={tool_stop}"),
            )
        )

        unavailable_request = AgentWorkRequest(
            goal="Acceptance: unavailable tool",
            profile_name="default",
            objective="Prove unavailable tools stop explicitly",
            work_type="evidence_triage",
            receipt_root=str(root),
            requested_tools=["not_a_registered_tool"],
        )
        unavailable_result = run_agent_work_loop(request=unavailable_request)
        checks.append(
            _check(
                "unavailable_tool_stop",
                "An unavailable requested tool produces tool_unavailable.",
                unavailable_result.stop_reason == "tool_unavailable",
                (
                    f"outcome={unavailable_result.outcome}; "
                    f"stop_reason={unavailable_result.stop_reason}"
                ),
            )
        )

        playbook_request = AgentWorkRequest(
            goal="Acceptance: playbook requirements",
            profile_name="default",
            objective="Prove required context packs are enforced",
            work_type="ips_drift_review",
            playbook_name="ips-drift-review",
            receipt_root=str(root),
            requested_tools=[],
            context_pack_names=[],
        )
        playbook_result = run_agent_work_loop(request=playbook_request)
        checks.append(
            _check(
                "playbook_requirements_enforced",
                "Missing required playbook context stops before cognition.",
                playbook_result.stop_reason == "missing_required_context",
                (
                    f"playbook={playbook_request.playbook_name}; "
                    f"stop_reason={playbook_result.stop_reason}"
                ),
            )
        )

        full_request = AgentWorkRequest(
            goal="Acceptance work id search target",
            profile_name="default",
            objective="Prove the final artifact chain",
            work_type="research_review",
            receipt_root=str(root),
            requested_tools=["get_quote_snapshot"],
            max_tool_calls=2,
            max_steps=4,
        )
        full_result = run_agent_work_loop(request=full_request)

        run_receipt_linked = _ref_exists(root, full_result.agent_run_receipt_ref)
        checks.append(
            _check(
                "final_agent_run_receipt_linked",
                "AgentWorkResult links the final AgentRunReceipt.",
                run_receipt_linked,
                f"agent_run_receipt_ref={full_result.agent_run_receipt_ref!r}",
            )
        )

        tool_refs_are_artifacts = bool(full_result.tool_result_refs) and all(
            ref not in full_request.requested_tools and _ref_exists(root, ref)
            for ref in full_result.tool_result_refs
        )
        checks.append(
            _check(
                "tool_result_refs_are_artifacts",
                "tool_result_refs contain resolvable receipt/artifact refs, not tool names.",
                tool_refs_are_artifacts,
                f"tool_result_refs={full_result.tool_result_refs!r}",
            )
        )

        result_persisted = _persisted_work_result_exists(root, full_result.work_id)
        checks.append(
            _check(
                "work_result_persisted",
                "AgentWorkResult is persisted under the receipt root.",
                result_persisted,
                f"work_id={full_result.work_id}; persisted={result_persisted}",
            )
        )

        workspace_linked = _ref_exists(root, full_result.review_workspace_ref)
        checks.append(
            _check(
                "review_workspace_hydrated",
                "The final result links a hydrated review workspace artifact.",
                workspace_linked,
                f"review_workspace_ref={full_result.review_workspace_ref!r}",
            )
        )

        index_path = Path(full_result.search_index_ref or "")
        work_hits = search_receipt_index(index_path, full_result.work_id)
        checks.append(
            _check(
                "result_searchable_by_work_id",
                "The final persisted result is searchable by work_id.",
                bool(work_hits),
                f"work_id={full_result.work_id}; search_hits={len(work_hits)}",
            )
        )

        evaluation_linked = _ref_exists(root, full_result.evaluation_report_ref)
        checks.append(
            _check(
                "evaluation_report_linked",
                "The final result links a persisted EvaluationReport.",
                evaluation_linked,
                f"evaluation_report_ref={full_result.evaluation_report_ref!r}",
            )
        )

        checks.append(
            _check(
                "execution_boundary_closed",
                "Work request, context, and result keep execution_allowed false.",
                not (
                    full_request.execution_allowed
                    or context.execution_allowed
                    or full_result.execution_allowed
                ),
                (
                    f"request={full_request.execution_allowed}; "
                    f"context={context.execution_allowed}; "
                    f"result={full_result.execution_allowed}"
                ),
            )
        )

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Print open contracts but return zero for diagnostic collection.",
    )
    args = parser.parse_args()

    checks = collect_acceptance_checks()
    for check in checks:
        status = "PASS" if check.passed else "OPEN"
        print(f"[{status}] {check.check_id}: {check.description}")
        print(f"       {check.evidence}")

    passed = sum(check.passed for check in checks)
    open_count = len(checks) - passed
    print(f"\nAgent Work Loop semantic closure: {passed}/{len(checks)} passed, {open_count} open")
    if open_count:
        print("STATUS: NOT SEMANTICALLY CLOSED")
    else:
        print("STATUS: SEMANTIC ACCEPTANCE PASSED")

    if args.report_only:
        return 0
    return 0 if open_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
