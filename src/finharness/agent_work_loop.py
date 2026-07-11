"""Deterministic Agent Work Orchestrator scaffold.

Agentic-space dimension: All Spaces.
Operating surface: Track G — Agent Work Loop.

The current entry point accepts an AgentWorkRequest, freezes context, lets a
provider-neutral decision port choose typed tool requests from the preceding
observation, enforces Harness autonomy admission and independent budgets, then
runs a deterministic cognition bridge and persists the terminal receipt/result/
search/workspace chain. Cross-cycle session and resume remain separate layers.

Work loop is NOT: session, scheduler, execution, or multi-agent.
"""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from finharness.autonomy_control import (
    AdmissionDisposition,
    AgentActionClass,
    AgentActionRequest,
    AgentAutonomyLevel,
    AutonomyMandate,
    AutonomyRuntimeState,
    WorldFidelityLevel,
    evaluate_autonomy_admission,
    write_autonomy_admission_report,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Engine

NON_CLAIMS: tuple[str, ...] = (
    "Agent Work Loop produces review artifacts, not execution orders.",
    "Results require human review before any downstream action.",
    "Not investment advice.",
)

AgentWorkType = Literal[
    "research_review",
    "ips_drift_review",
    "proposal_review",
    "evidence_triage",
    "planning_review",
]

AgentWorkStopReason = Literal[
    "completed",
    "max_steps_reached",
    "max_tool_calls_reached",
    "tool_unavailable",
    "missing_required_context",
    "evaluation_blocked",
    "human_review_required",
    "data_gap_unresolved",
    "internal_error",
]

AgentWorkOutcome = Literal[
    "succeeded",
    "partial",
    "failed",
    "stopped",
]


class AgentWorkToolRequest(BaseModel):
    """One caller/model-selected tool invocation with concrete arguments."""

    model_config = ConfigDict(frozen=True)

    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("tool_name")
    @classmethod
    def require_tool_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("tool_name must not be blank")
        return value.strip()


class AgentWorkRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    work_id: str = Field(default_factory=lambda: _new_id("awr"))
    agent_id: str = "agent:unbound"
    goal: str
    profile_name: str
    objective: str
    work_type: AgentWorkType
    playbook_name: str | None = None
    requested_tools: list[str] = Field(default_factory=list)
    tool_requests: list[AgentWorkToolRequest] = Field(default_factory=list)
    context_pack_names: list[str] = Field(default_factory=list)
    max_tool_calls: int = Field(default=5, ge=1)
    max_steps: int = Field(default=8, ge=1)
    receipt_root: str
    requested_autonomy: AgentAutonomyLevel = AgentAutonomyLevel.AUT1_TOOL_REVIEWER
    world_fidelity: WorldFidelityLevel = WorldFidelityLevel.W0_CAPITAL_FACTS
    capital_mandate_id: str | None = None
    agent_authority_grant_id: str | None = None
    execution_allowed: Literal[False] = False

    @model_validator(mode="after")
    def reject_ambiguous_tool_inputs(self) -> AgentWorkRequest:
        if self.requested_tools and self.tool_requests:
            raise ValueError("use requested_tools or tool_requests, not both")
        return self

    def normalized_tool_requests(self) -> tuple[AgentWorkToolRequest, ...]:
        if self.tool_requests:
            return tuple(self.tool_requests)
        return tuple(AgentWorkToolRequest(tool_name=name) for name in self.requested_tools)


class AgentWorkResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    work_id: str
    agent_id: str = "agent:unbound"
    goal: str
    profile_name: str
    work_type: AgentWorkType
    outcome: AgentWorkOutcome
    stop_reason: str
    created_at_utc: str = Field(default_factory=lambda: _now_utc())
    work_result_ref: str | None = None
    tool_result_refs: list[str] = Field(default_factory=list)
    agent_run_receipt_ref: str | None = None
    evaluation_report_ref: str | None = None
    authority_transition_ref: str | None = None
    review_workspace_ref: str | None = None
    search_index_ref: str | None = None
    data_gaps: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    autonomy_admission_refs: list[str] = Field(default_factory=list)
    requested_autonomy: AgentAutonomyLevel = AgentAutonomyLevel.AUT1_TOOL_REVIEWER
    world_fidelity: WorldFidelityLevel = WorldFidelityLevel.W0_CAPITAL_FACTS
    capital_mandate_id: str | None = None
    agent_authority_grant_id: str | None = None
    execution_allowed: Literal[False] = False


class AgentWorkContextSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    snapshot_id: str = Field(default_factory=lambda: _new_id("ctxsnap"))
    work_id: str
    profile_name: str
    context_projection_payload: dict[str, object] = Field(default_factory=dict)
    context_trust_by_ref: dict[str, object] = Field(default_factory=dict)
    context_refs: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    created_at_utc: str = Field(default_factory=lambda: _now_utc())
    findings: list[dict[str, object]] = Field(default_factory=list)
    execution_allowed: Literal[False] = False


class AgentWorkPlaybookBinding(BaseModel):
    model_config = ConfigDict(frozen=True)
    playbook_name: str
    version: str
    required_context_packs: list[str] = Field(default_factory=list)
    recommended_evaluators: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    bound: bool = False


AgentWorkObservationKind = Literal[
    "work_started",
    "tool_result",
    "tool_unavailable",
    "admission_denied",
]


class AgentWorkObservation(BaseModel):
    """The preceding runtime observation consumed by the next-action port."""

    model_config = ConfigDict(frozen=True)

    sequence: int = 0
    kind: AgentWorkObservationKind = "work_started"
    tool_name: str | None = None
    ok: bool | None = None
    error_code: str | None = None
    artifact_ref: str | None = None
    autonomy_admission_ref: str | None = None
    data_gaps: tuple[str, ...] = ()


class AgentWorkDecisionState(BaseModel):
    """Bounded state presented to an Agentic next-action decision port."""

    model_config = ConfigDict(frozen=True)

    work_id: str
    goal: str
    objective: str
    step_count: int
    tool_call_count: int
    max_steps: int
    max_tool_calls: int
    observation: AgentWorkObservation


class AgentWorkDecision(BaseModel):
    """Provider-neutral next action selected from goal plus observation."""

    model_config = ConfigDict(frozen=True)

    action: Literal["dispatch", "complete"]
    tool_request: AgentWorkToolRequest | None = None

    @model_validator(mode="after")
    def require_dispatch_request(self) -> AgentWorkDecision:
        if (self.action == "dispatch") != (self.tool_request is not None):
            raise ValueError("dispatch requires one tool_request; complete requires none")
        return self


AgentWorkDecisionPort = Callable[[AgentWorkDecisionState], AgentWorkDecision]


def bind_playbook_to_work(playbook_name: str) -> AgentWorkPlaybookBinding:
    from finharness.evaluator_registry import evaluator_ids
    from finharness.playbook_loader import load_cognition_playbook

    pb = load_cognition_playbook(playbook_name)
    if pb is None:
        return AgentWorkPlaybookBinding(
            playbook_name=playbook_name,
            version="unknown",
            findings=[f"playbook '{playbook_name}' not found"],
            bound=False,
        )

    finding_msgs: list[str] = []
    bound = True
    registered_ids = set(evaluator_ids())
    for eid in pb.recommended_evaluators:
        if eid not in registered_ids:
            finding_msgs.append(f"recommended evaluator '{eid}' not registered")
            bound = False

    return AgentWorkPlaybookBinding(
        playbook_name=playbook_name,
        version=pb.version,
        required_context_packs=pb.required_context_packs,
        recommended_evaluators=pb.recommended_evaluators,
        findings=finding_msgs,
        bound=bound,
    )


def freeze_work_context(
    *,
    work_id: str,
    profile_name: str,
    context_projection_payload: dict[str, object] | None = None,
) -> AgentWorkContextSnapshot:
    from finharness.agent_context_trust_map import extract_context_trust_map

    payload = context_projection_payload or {}
    extraction = extract_context_trust_map(payload)
    context_refs: list[str] = []
    source_refs: list[str] = []
    packs = payload.get("packs")
    if isinstance(packs, list):
        for pack in packs:
            if isinstance(pack, dict):
                cp_refs = pack.get("context_pack_refs")
                if isinstance(cp_refs, list):
                    context_refs.extend(str(r) for r in cp_refs)
                src_refs = pack.get("source_refs")
                if isinstance(src_refs, list):
                    source_refs.extend(str(r) for r in src_refs)
    trust_dict: dict[str, object] = {}
    for ref, trust in extraction.trust_by_ref.items():
        trust_dict[ref] = trust.model_dump()
    findings_list: list[dict[str, object]] = [f.model_dump() for f in extraction.findings]
    return AgentWorkContextSnapshot(
        work_id=work_id,
        profile_name=profile_name,
        context_projection_payload=payload,
        context_trust_by_ref=trust_dict,
        context_refs=list(dict.fromkeys(context_refs)),
        source_refs=list(dict.fromkeys(source_refs)),
        findings=findings_list,
    )


def run_bounded_tool_dispatch_loop(  # noqa: C901
    *,
    request: AgentWorkRequest,
    context_snapshot: AgentWorkContextSnapshot,
    decision_port: AgentWorkDecisionPort | None = None,
    observation: AgentWorkObservation | None = None,
    autonomy_mandate: AutonomyMandate | None = None,
    runtime_autonomy_ceiling: AgentAutonomyLevel = AgentAutonomyLevel.AUT1_TOOL_REVIEWER,
    runtime_world_fidelity: WorldFidelityLevel = WorldFidelityLevel.W0_CAPITAL_FACTS,
) -> tuple[list[dict[str, object]], str, list[str]]:
    # One explicit reducer owns budget, decision, admission, dispatch, observation,
    # and terminal reduction so those state transitions cannot drift apart.
    from finharness.agent_runtime_receipts import AgentRuntimeTraceSink
    from finharness.agent_tool_result_envelope import build_tool_result_envelope
    from finharness.agent_tools import AGENT_TOOL_ENTRIES
    from finharness.statecore.receipt_io import atomic_write_json, resolve_under

    sink = AgentRuntimeTraceSink(
        goal=request.goal,
        profile_name=request.profile_name,
        receipt_root=Path(request.receipt_root),
        context_refs=context_snapshot.context_refs,
    )
    envelopes: list[dict[str, object]] = []
    data_gaps: list[str] = []
    admission_refs: list[str] = []
    tool_count = 0
    step_count = 0
    pending = deque(request.normalized_tool_requests())
    using_default_port = decision_port is None

    def queued_port(state: AgentWorkDecisionState) -> AgentWorkDecision:
        del state
        if not pending:
            return AgentWorkDecision(action="complete")
        return AgentWorkDecision(action="dispatch", tool_request=pending.popleft())

    port = decision_port or queued_port
    current_observation = observation or AgentWorkObservation()
    stop_reason: str = "completed"

    while True:
        if step_count >= request.max_steps:
            stop_reason = (
                ("data_gap_unresolved" if data_gaps else "completed")
                if using_default_port and not pending
                else "max_steps_reached"
            )
            break
        if tool_count >= request.max_tool_calls:
            stop_reason = (
                ("data_gap_unresolved" if data_gaps else "completed")
                if using_default_port and not pending
                else "max_tool_calls_reached"
            )
            break

        state = AgentWorkDecisionState(
            work_id=request.work_id,
            goal=request.goal,
            objective=request.objective,
            step_count=step_count,
            tool_call_count=tool_count,
            max_steps=request.max_steps,
            max_tool_calls=request.max_tool_calls,
            observation=current_observation,
        )
        try:
            decision = port(state)
        except Exception as exc:  # decision providers are an explicit failure boundary
            data_gaps.append(f"decision_port_error: {type(exc).__name__}: {exc}")
            stop_reason = "internal_error"
            break
        if decision.action == "complete":
            stop_reason = "data_gap_unresolved" if data_gaps else "completed"
            break

        tool_request = decision.tool_request
        if tool_request is None:  # guarded by the model; defensive for custom ports
            data_gaps.append("decision_port_error: dispatch decision omitted tool_request")
            stop_reason = "internal_error"
            break
        step_count += 1

        entry = AGENT_TOOL_ENTRIES.get(tool_request.tool_name)
        action_class = (
            AgentActionClass.PREPARE_REVIEW_PACKET
            if entry is not None and entry.side_effect == "append_only_review_write"
            else AgentActionClass.GATHER_EVIDENCE
        )
        action_request = AgentActionRequest(
            work_id=request.work_id,
            agent_id=request.agent_id,
            objective=request.objective,
            action_class=action_class,
            requested_autonomy=request.requested_autonomy,
            tool_name=tool_request.tool_name,
            arguments=tool_request.arguments,
            target_scope={
                key: tool_request.arguments[key]
                for key in ("action_type", "asset_class")
                if key in tool_request.arguments
            },
        )
        admission = evaluate_autonomy_admission(
            request=action_request,
            runtime=AutonomyRuntimeState(
                world_fidelity=runtime_world_fidelity,
                runtime_autonomy_ceiling=runtime_autonomy_ceiling,
                world_state_ref=context_snapshot.snapshot_id,
            ),
            mandate=autonomy_mandate,
        )
        admission_ref = write_autonomy_admission_report(
            admission,
            receipt_root=request.receipt_root,
        )
        admission_refs.append(admission_ref)
        if admission.disposition != AdmissionDisposition.EFFECTIVE:
            finding_codes = ",".join(finding.code for finding in admission.findings)
            data_gaps.append(
                f"autonomy_admission_{admission.disposition}: "
                f"{tool_request.tool_name} ({finding_codes or 'no_finding'})"
            )
            current_observation = AgentWorkObservation(
                sequence=step_count,
                kind="admission_denied",
                tool_name=tool_request.tool_name,
                ok=False,
                autonomy_admission_ref=admission_ref,
                data_gaps=tuple(data_gaps),
            )
            work_fingerprint = sha256(request.work_id.encode("utf-8")).hexdigest()[:16]
            relative_artifact = Path("agent-tool-results") / (
                f"work-{work_fingerprint}-step-{step_count}-denied.json"
            )
            denied_envelope: dict[str, object] = {
                "tool_name": tool_request.tool_name,
                "toolset": entry.toolset if entry is not None else "unknown",
                "ok": False,
                "error_code": "AUTONOMY_ADMISSION_DENIED",
                "side_effect": entry.side_effect if entry is not None else "unknown",
                "output_kind": "diagnostic",
                "data_gaps": list(data_gaps),
                "request_argument_keys": sorted(tool_request.arguments),
                "autonomy_admission_ref": admission_ref,
                "autonomy_disposition": admission.disposition,
                "artifact_ref": relative_artifact.as_posix(),
                "execution_allowed": False,
                "authority_transition": False,
            }
            atomic_write_json(
                resolve_under(request.receipt_root, relative_artifact),
                denied_envelope,
            )
            envelopes.append(denied_envelope)
            stop_reason = (
                "evaluation_blocked"
                if admission.disposition == AdmissionDisposition.BLOCKED
                else "human_review_required"
            )
            break

        result = sink.dispatch(
            profile_name=request.profile_name,
            tool_name=tool_request.tool_name,
            arguments=tool_request.arguments,
        )
        env = build_tool_result_envelope(result)
        canonical_arguments = json.dumps(
            tool_request.arguments,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        env = env.model_copy(
            update={
                "request_argument_keys": sorted(tool_request.arguments),
                "request_arguments_sha256": sha256(
                    canonical_arguments.encode("utf-8")
                ).hexdigest(),
                "autonomy_admission_ref": admission_ref,
                "autonomy_disposition": admission.disposition,
            }
        )
        work_fingerprint = sha256(request.work_id.encode("utf-8")).hexdigest()[:16]
        relative_artifact = Path("agent-tool-results") / (
            f"work-{work_fingerprint}-step-{step_count}.json"
        )
        artifact_path = resolve_under(request.receipt_root, relative_artifact)
        env = env.model_copy(update={"artifact_ref": relative_artifact.as_posix()})
        atomic_write_json(artifact_path, env.model_dump(mode="json"))
        envelopes.append(env.model_dump(mode="json"))
        data_gaps.extend(env.data_gaps)
        tool_count += 1
        unavailable = env.error_code in {"TOOL_UNAVAILABLE", "TOOL_UNREGISTERED"}
        current_observation = AgentWorkObservation(
            sequence=step_count,
            kind="tool_unavailable" if unavailable else "tool_result",
            tool_name=tool_request.tool_name,
            ok=env.ok,
            error_code=env.error_code,
            artifact_ref=relative_artifact.as_posix(),
            autonomy_admission_ref=admission_ref,
            data_gaps=tuple(env.data_gaps),
        )
        if unavailable:
            stop_reason = "tool_unavailable"
            break

    if sink.result_count:
        run_receipt = sink.finalize()
        run_ref = f"agent-runs/{run_receipt.receipt_id}.json"
        for index, env_dict in enumerate(envelopes):
            updated = {**env_dict, "agent_run_receipt_ref": run_ref}
            envelopes[index] = updated
            artifact_ref = updated.get("artifact_ref")
            if isinstance(artifact_ref, str):
                atomic_write_json(
                    resolve_under(request.receipt_root, artifact_ref),
                    updated,
                )
    # Admission refs for denied attempts are carried in data gaps and persisted;
    # admitted refs are also attached to each result artifact.
    del admission_refs
    return envelopes, stop_reason, data_gaps


def run_cognition_flow_from_work_result(
    *,
    request: AgentWorkRequest,
    context_snapshot: AgentWorkContextSnapshot,
    tool_envelopes: list[dict[str, object]],
    receipt_root: str | Path,
) -> dict[str, object]:
    """Run cognition flow from a work loop's tool results."""
    from finharness.agent_cognition_flow import run_agent_cognition_flow

    source_refs: list[str] = []
    for env_dict in tool_envelopes:
        src = env_dict.get("source_refs", [])
        if isinstance(src, list):
            source_refs.extend(str(r) for r in src)
    context_refs = context_snapshot.context_refs
    all_source_refs = list(dict.fromkeys([*source_refs, *context_snapshot.source_refs]))

    flow = run_agent_cognition_flow(
        goal=request.goal,
        profile_name=request.profile_name,
        objective=request.objective,
        option_claims=[f"Tool result analysis for: {request.goal}"],
        plan_steps=[f"Review results from {len(tool_envelopes)} tool calls"],
        receipt_root=Path(receipt_root),
        context_refs=context_refs if context_refs else None,
        source_refs=all_source_refs if all_source_refs else None,
    )
    return {
        "flow_id": flow.flow_id,
        "goal": flow.goal,
        "evaluation_report_ref": flow.evaluation_report_ref,
        "authority_transition_ref": flow.authority_transition_ref,
        "plan_draft_ref": flow.plan_draft_ref,
        "option_set_ref": flow.option_set_ref,
        "agent_run_receipt_ref": flow.agent_run_receipt_ref,
        "execution_allowed": False,
    }


def write_agent_work_result(
    result: AgentWorkResult,
    *,
    receipt_root: str | Path,
) -> str:
    """Persist the terminal work result and return its root-relative reference."""

    from finharness.statecore.receipt_io import atomic_write_json, resolve_under

    fingerprint = sha256(result.work_id.encode("utf-8")).hexdigest()[:20]
    relative = Path("agent-work-results") / f"work-result-{fingerprint}.json"
    atomic_write_json(
        resolve_under(receipt_root, relative),
        result.model_dump(mode="json"),
    )
    return relative.as_posix()


def _write_work_review_workspace(
    *,
    request: AgentWorkRequest,
    flow: dict[str, object],
    tool_result_refs: list[str],
    admission_refs: list[str],
    agent_run_receipt_ref: str | None,
    data_gaps: list[str],
) -> str:
    from finharness.agent_cognition_flow import AgentCognitionFlowResult
    from finharness.review_workspace import (
        ReviewWorkspaceProjection,
        build_review_workspace_projection_from_receipts,
        write_review_workspace_projection,
    )

    if flow:
        flow_result = AgentCognitionFlowResult.model_validate(flow)
        projection = build_review_workspace_projection_from_receipts(
            flow_result=flow_result,
            receipt_root=request.receipt_root,
            subject_type="agent_work",
            subject_id=request.work_id,
        )
        projection = projection.model_copy(
            update={
                "data_gaps": list(dict.fromkeys([*projection.data_gaps, *data_gaps])),
                "receipt_refs": list(
                    dict.fromkeys(
                        [
                            *projection.receipt_refs,
                            *tool_result_refs,
                            *admission_refs,
                            *([agent_run_receipt_ref] if agent_run_receipt_ref else []),
                        ]
                    )
                ),
            }
        )
    else:
        projection = ReviewWorkspaceProjection(
            workspace_id=f"rwp_{uuid4().hex[:12]}",
            subject_type="agent_work",
            subject_id=request.work_id,
            goal=request.goal,
            open_findings=[],
            data_gaps=data_gaps,
            receipt_refs=list(
                dict.fromkeys(
                    [
                        *tool_result_refs,
                        *admission_refs,
                        *([agent_run_receipt_ref] if agent_run_receipt_ref else []),
                    ]
                )
            ),
        )
    return write_review_workspace_projection(
        projection,
        receipt_root=request.receipt_root,
    )


def _persist_preflight_stop(
    *,
    request: AgentWorkRequest,
    stop_reason: AgentWorkStopReason,
    data_gaps: list[str],
    findings: list[str],
    runtime_world_fidelity: WorldFidelityLevel,
) -> AgentWorkResult:
    from finharness.agent_receipt_search import write_receipt_search_index
    from finharness.agent_run_receipts import write_agent_run_receipt

    run_receipt = write_agent_run_receipt(
        goal=request.goal,
        profile_name=request.profile_name,
        tool_calls=[],
        outcome="failed" if stop_reason == "internal_error" else "blocked",
        stop_reason=stop_reason,
        receipt_root=request.receipt_root,
        data_gaps=data_gaps,
    )
    run_ref = f"agent-runs/{run_receipt.receipt_id}.json"

    workspace_ref = _write_work_review_workspace(
        request=request,
        flow={},
        tool_result_refs=[],
        admission_refs=[],
        agent_run_receipt_ref=run_ref,
        data_gaps=data_gaps,
    )
    root = Path(request.receipt_root)
    fingerprint = sha256(request.work_id.encode("utf-8")).hexdigest()[:20]
    result = AgentWorkResult(
        work_id=request.work_id,
        agent_id=request.agent_id,
        goal=request.goal,
        profile_name=request.profile_name,
        work_type=request.work_type,
        outcome="stopped",
        stop_reason=stop_reason,
        work_result_ref=f"agent-work-results/work-result-{fingerprint}.json",
        agent_run_receipt_ref=run_ref,
        review_workspace_ref=workspace_ref,
        search_index_ref=str(root / "receipt-index.jsonl"),
        data_gaps=data_gaps,
        findings=findings,
        requested_autonomy=request.requested_autonomy,
        world_fidelity=runtime_world_fidelity,
        capital_mandate_id=request.capital_mandate_id,
        agent_authority_grant_id=request.agent_authority_grant_id,
    )
    write_agent_work_result(result, receipt_root=root)
    write_receipt_search_index(root)
    return result


def run_agent_work_loop(
    *,
    request: AgentWorkRequest,
    context_projection_payload: dict[str, object] | None = None,
    decision_port: AgentWorkDecisionPort | None = None,
    autonomy_mandate: AutonomyMandate | None = None,
    authority_engine: Engine | None = None,
    runtime_autonomy_ceiling: AgentAutonomyLevel = AgentAutonomyLevel.AUT1_TOOL_REVIEWER,
    runtime_world_fidelity: WorldFidelityLevel = WorldFidelityLevel.W0_CAPITAL_FACTS,
) -> AgentWorkResult:
    """Run the deterministic work-orchestration scaffold.

    1. Freeze context snapshot
    2. Run bounded tool dispatch loop
    3. Run cognition flow from tool results
    4. Persist AgentRunReceipt, WorkResult, and hydrated review workspace
    5. Rebuild the receipt search index and return the terminal result
    """
    from finharness.agent_receipt_search import write_receipt_search_index

    authority_findings: list[str] = []
    if autonomy_mandate is None and request.agent_authority_grant_id:
        if authority_engine is None:
            return _persist_preflight_stop(
                request=request,
                stop_reason="missing_required_context",
                data_gaps=[
                    "authority_engine is required to resolve agent_authority_grant_id"
                ],
                findings=authority_findings,
                runtime_world_fidelity=runtime_world_fidelity,
            )
        from finharness.statecore.autonomy_adapter import (
            resolve_runtime_autonomy_mandate,
        )

        resolution = resolve_runtime_autonomy_mandate(
            request.agent_authority_grant_id,
            engine=authority_engine,
        )
        authority_findings.extend(resolution.warnings)
        if not resolution.resolved or resolution.mandate is None:
            return _persist_preflight_stop(
                request=request,
                stop_reason="evaluation_blocked",
                data_gaps=[
                    f"authority_resolution_denied: {reason}"
                    for reason in resolution.deny_reasons
                ],
                findings=authority_findings,
                runtime_world_fidelity=runtime_world_fidelity,
            )
        autonomy_mandate = resolution.mandate

    if request.playbook_name:
        binding = bind_playbook_to_work(request.playbook_name)
        missing_packs = sorted(
            set(binding.required_context_packs) - set(request.context_pack_names)
        )
        if not binding.bound or missing_packs:
            gaps = list(binding.findings)
            gaps.extend(f"missing_required_context_pack: {name}" for name in missing_packs)
            return _persist_preflight_stop(
                request=request,
                stop_reason="missing_required_context",
                data_gaps=gaps,
                findings=authority_findings,
                runtime_world_fidelity=runtime_world_fidelity,
            )

    # 1. Freeze context
    snap = freeze_work_context(
        work_id=request.work_id,
        profile_name=request.profile_name,
        context_projection_payload=context_projection_payload,
    )

    # 2. Dispatch tools
    envelopes, stop_reason, data_gaps = run_bounded_tool_dispatch_loop(
        request=request,
        context_snapshot=snap,
        decision_port=decision_port,
        autonomy_mandate=autonomy_mandate,
        runtime_autonomy_ceiling=runtime_autonomy_ceiling,
        runtime_world_fidelity=runtime_world_fidelity,
    )

    # 3. Run cognition flow
    flow: dict[str, object] = {}
    if stop_reason not in {
        "tool_unavailable",
        "missing_required_context",
        "evaluation_blocked",
        "human_review_required",
        "internal_error",
    }:
        flow = run_cognition_flow_from_work_result(
            request=request,
            context_snapshot=snap,
            tool_envelopes=envelopes,
            receipt_root=request.receipt_root,
        )

    # 4. Determine outcome
    outcome: AgentWorkOutcome = "succeeded"
    if stop_reason in {"evaluation_blocked", "human_review_required", "internal_error"}:
        outcome = "stopped"
    elif stop_reason == "tool_unavailable":
        outcome = "failed"
    elif data_gaps or stop_reason in {"max_steps_reached", "max_tool_calls_reached"}:
        outcome = "partial" if envelopes else "failed"

    # 5. Link and persist the terminal work package, then rebuild search.
    root = Path(request.receipt_root)
    tool_result_refs = [
        str(ref)
        for envelope in envelopes
        if (ref := envelope.get("artifact_ref")) is not None
    ]
    admission_refs = list(
        dict.fromkeys(
            str(ref)
            for envelope in envelopes
            if (ref := envelope.get("autonomy_admission_ref")) is not None
        )
    )
    dispatch_run_ref = next(
        (
            str(ref)
            for envelope in envelopes
            if (ref := envelope.get("agent_run_receipt_ref")) is not None
        ),
        None,
    )
    if dispatch_run_ref is None:
        from finharness.agent_run_receipts import write_agent_run_receipt

        terminal_run = write_agent_run_receipt(
            goal=request.goal,
            profile_name=request.profile_name,
            tool_calls=[],
            outcome=(
                "failed"
                if stop_reason in {"internal_error", "tool_unavailable"}
                else "blocked"
            ),
            stop_reason=stop_reason,
            receipt_root=root,
            artifact_refs=tool_result_refs,
            evidence_refs=admission_refs,
            data_gaps=data_gaps,
        )
        dispatch_run_ref = f"agent-runs/{terminal_run.receipt_id}.json"
    workspace_ref = _write_work_review_workspace(
        request=request,
        flow=flow,
        tool_result_refs=tool_result_refs,
        admission_refs=admission_refs,
        agent_run_receipt_ref=dispatch_run_ref,
        data_gaps=data_gaps,
    )
    work_fingerprint = sha256(request.work_id.encode("utf-8")).hexdigest()[:20]
    work_result_ref = f"agent-work-results/work-result-{work_fingerprint}.json"
    index_path = root / "receipt-index.jsonl"
    result = AgentWorkResult(
        work_id=request.work_id,
        agent_id=request.agent_id,
        goal=request.goal,
        profile_name=request.profile_name,
        work_type=request.work_type,
        outcome=outcome,
        stop_reason=stop_reason,
        work_result_ref=work_result_ref,
        tool_result_refs=tool_result_refs,
        agent_run_receipt_ref=dispatch_run_ref,
        evaluation_report_ref=flow.get("evaluation_report_ref"),
        authority_transition_ref=flow.get("authority_transition_ref"),
        review_workspace_ref=workspace_ref,
        search_index_ref=str(index_path),
        data_gaps=data_gaps,
        findings=[
            *authority_findings,
            *(json.dumps(finding, sort_keys=True, default=str) for finding in snap.findings),
        ],
        autonomy_admission_refs=admission_refs,
        requested_autonomy=request.requested_autonomy,
        world_fidelity=runtime_world_fidelity,
        capital_mandate_id=request.capital_mandate_id,
        agent_authority_grant_id=request.agent_authority_grant_id,
    )
    write_agent_work_result(result, receipt_root=root)
    write_receipt_search_index(root)
    return result


def _new_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid4().hex[:8]}"


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def propose_memory_from_completed_work(
    *,
    result: AgentWorkResult,
    context_snapshot: AgentWorkContextSnapshot,
    receipt_root: str | Path,
) -> str | None:
    """Propose a domain memory draft from completed work.

    Only proposes memory when the work outcome suggests a learnable
    pattern: partial or failed outcome, data gaps present, or context
    trust findings exist. Memory remains draft — never auto-promoted.
    """
    if result.outcome not in ("partial", "failed"):
        return None
    if not result.data_gaps:
        return None

    from finharness.domain_memory import propose_domain_memory

    draft = propose_domain_memory(
        proposed_by=f"agent:{result.profile_name}",
        memory_type="planning_lesson",
        content=(
            f"Work '{result.goal}' ({result.work_type}) "
            f"stopped with {result.outcome}: {result.stop_reason}. "
            f"Data gaps: {'; '.join(result.data_gaps[:3])}"
        ),
        receipt_root=Path(receipt_root),
        source_refs=context_snapshot.source_refs,
        receipt_refs=result.tool_result_refs,
    )
    return draft.memory_id
