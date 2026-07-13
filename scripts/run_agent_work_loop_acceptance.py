#!/usr/bin/env python3
"""Executable semantic-closure gate for the Agent Work Loop.

This command is expected to fail while the deterministic work orchestrator is
still scaffolded. Use ``--report-only`` to collect the same evidence without a
non-zero process exit.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from finharness.agent_receipt_search import search_receipt_index
from finharness.agent_work_loop import (
    AgentWorkDecision,
    AgentWorkDecisionState,
    AgentWorkRequest,
    AgentWorkStopReason,
    AgentWorkToolRequest,
    freeze_work_context,
    run_agent_work_loop,
    run_bounded_tool_dispatch_loop,
)
from finharness.autonomy_control import (
    AgentAutonomyLevel,
    WorldFidelityLevel,
)
from finharness.config import load_settings
from finharness.statecore.store import (
    STATE_CORE_DB_ENV_VAR,
    init_state_core,
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


@contextmanager
def _isolated_acceptance_state_core():
    """Create a temporary StateCore database so acceptance checks are hermetic.

    Production tools (e.g. get_capital_context_projection) require a
    StateCore database to pass availability checks.  Without this context
    manager, clean checkout environments (no developer database) return
    TOOL_UNAVAILABLE and the acceptance gate breaks.
    """
    prev = os.environ.get(STATE_CORE_DB_ENV_VAR)
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "state-core.sqlite"
        engine = init_state_core(db_path)
        engine.dispose()
        os.environ[STATE_CORE_DB_ENV_VAR] = str(db_path)
        load_settings.cache_clear()
        try:
            yield
        finally:
            if prev is None:
                os.environ.pop(STATE_CORE_DB_ENV_VAR, None)
            else:
                os.environ[STATE_CORE_DB_ENV_VAR] = prev
            load_settings.cache_clear()


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
    """Run the real orchestrator against the semantic closure contracts.

    Always wraps execution in an isolated StateCore database so the
    acceptance gate is hermetic and does not leak a developer-local
    state-core dependency into CI or transient environments.
    """
    with _isolated_acceptance_state_core():
        return _collect_acceptance_checks()


def _collect_acceptance_checks() -> list[AcceptanceCheck]:
    """Run the real orchestrator against the semantic closure contracts."""

    checks: list[AcceptanceCheck] = []

    with tempfile.TemporaryDirectory() as typed_tmp:
        typed_root = Path(typed_tmp)
        typed_request = AgentWorkRequest(
            goal="Acceptance: typed arguments",
            profile_name="default",
            objective="Prove arguments reach a production tool dispatch",
            work_type="research_review",
            receipt_root=str(typed_root),
            tool_requests=[
                AgentWorkToolRequest(
                    tool_name="get_capital_context_projection",
                    arguments={"open_proposals_limit": 3},
                )
            ],
        )
        typed_snapshot = freeze_work_context(
            work_id=typed_request.work_id,
            profile_name=typed_request.profile_name,
        )
        typed_envelopes, typed_stop, _ = run_bounded_tool_dispatch_loop(
            request=typed_request,
            context_snapshot=typed_snapshot,
        )
        arguments_transported = (
            len(typed_envelopes) == 1
            and typed_envelopes[0].get("request_argument_keys")
            == ["open_proposals_limit"]
            and typed_envelopes[0].get("request_arguments_sha256")
            and typed_envelopes[0].get("error_code") != "SCHEMA_VALIDATION_FAILED"
            and typed_stop == "completed"
        )
        argument_keys = (
            typed_envelopes[0].get("request_argument_keys") if typed_envelopes else []
        )
        argument_error = (
            typed_envelopes[0].get("error_code") if typed_envelopes else None
        )
        checks.append(
            _check(
                "real_tool_arguments",
                "Requested tool calls carry caller/model-selected arguments.",
                bool(arguments_transported),
                (
                    f"argument_keys={argument_keys}; "
                    f"error={argument_error}; "
                    f"stop_reason={typed_stop}"
                ),
            )
        )

        observed_kinds: list[str] = []

        def observation_port(state: AgentWorkDecisionState) -> AgentWorkDecision:
            observed_kinds.append(state.observation.kind)
            if state.observation.kind == "work_started":
                return AgentWorkDecision(
                    action="dispatch",
                    tool_request=AgentWorkToolRequest(
                        tool_name="get_capital_context_projection",
                        arguments={"open_proposals_limit": 2},
                    ),
                )
            return AgentWorkDecision(action="complete")

        observation_request = AgentWorkRequest(
            goal="Acceptance: observation reducer",
            profile_name="default",
            objective="Choose the next action from the preceding observation",
            work_type="research_review",
            receipt_root=str(typed_root),
            max_steps=3,
        )
        observation_snapshot = freeze_work_context(
            work_id=observation_request.work_id,
            profile_name=observation_request.profile_name,
        )
        observation_envelopes, observation_stop, _ = run_bounded_tool_dispatch_loop(
            request=observation_request,
            context_snapshot=observation_snapshot,
            decision_port=observation_port,
        )
        observation_consumed = (
            observed_kinds == ["work_started", "tool_result"]
            and len(observation_envelopes) == 1
            and observation_stop == "completed"
        )
        checks.append(
            _check(
                "observation_driven_decision",
                "A next-action reducer consumes the preceding observation.",
                observation_consumed,
                (
                    f"observed_kinds={observed_kinds}; "
                    f"envelopes={len(observation_envelopes)}; "
                    f"stop_reason={observation_stop}"
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

        completed_result = run_agent_work_loop(
            request=AgentWorkRequest(
                goal="Acceptance: explicit completion",
                profile_name="default",
                objective="Complete after no further tool is needed",
                work_type="research_review",
                receipt_root=str(root),
            )
        )
        data_gap_result = run_agent_work_loop(
            request=AgentWorkRequest(
                goal="Acceptance: unresolved data gap",
                profile_name="default",
                objective="Reduce a schema data gap",
                work_type="evidence_triage",
                receipt_root=str(root),
                tool_requests=[
                    AgentWorkToolRequest(
                        tool_name="get_quote_snapshot",
                        arguments={},
                    )
                ],
            )
        )
        evaluation_blocked_result = run_agent_work_loop(
            request=AgentWorkRequest(
                goal="Acceptance: runtime autonomy ceiling",
                profile_name="default",
                objective="Fail closed above the Harness ceiling",
                work_type="evidence_triage",
                receipt_root=str(root),
                requested_autonomy=AgentAutonomyLevel.AUT6_CONTINUOUS_AGENT,
                tool_requests=[
                    AgentWorkToolRequest(
                        tool_name="get_capital_context_projection",
                        arguments={"open_proposals_limit": 1},
                    )
                ],
            )
        )
        human_review_result = run_agent_work_loop(
            request=AgentWorkRequest(
                goal="Acceptance: mandate-required review write",
                profile_name="review-draft",
                objective="Keep an out-of-mandate write as a candidate",
                work_type="proposal_review",
                receipt_root=str(root),
                requested_autonomy=AgentAutonomyLevel.AUT2_DURABLE_LOOP,
                tool_requests=[
                    AgentWorkToolRequest(
                        tool_name="draft_governed_proposal_from_context",
                        arguments={},
                    )
                ],
            ),
            runtime_autonomy_ceiling=AgentAutonomyLevel.AUT2_DURABLE_LOOP,
            runtime_world_fidelity=WorldFidelityLevel.W1_VERSIONED_DECISIONS,
        )

        def failing_decision_port(state: AgentWorkDecisionState) -> AgentWorkDecision:
            del state
            raise RuntimeError("acceptance decision failure")

        internal_error_result = run_agent_work_loop(
            request=AgentWorkRequest(
                goal="Acceptance: decision failure",
                profile_name="default",
                objective="Reduce a decision-provider exception",
                work_type="research_review",
                receipt_root=str(root),
            ),
            decision_port=failing_decision_port,
        )

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

    declared_reasons = set(getattr(AgentWorkStopReason, "__args__", ()))
    observed_reasons = {
        step_stop,
        tool_stop,
        unavailable_result.stop_reason,
        playbook_result.stop_reason,
        full_result.stop_reason,
        completed_result.stop_reason,
        data_gap_result.stop_reason,
        evaluation_blocked_result.stop_reason,
        human_review_result.stop_reason,
        internal_error_result.stop_reason,
    }
    reducer_coverage = declared_reasons.issubset(observed_reasons)
    checks.append(
        _check(
            "all_stop_paths_reduced",
            "Every declared stop reason has an exercised production reducer path.",
            reducer_coverage,
            (
                f"declared={sorted(declared_reasons)}; "
                f"observed_production_paths={sorted(observed_reasons)}"
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
