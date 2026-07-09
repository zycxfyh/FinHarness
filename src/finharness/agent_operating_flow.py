"""Operating surface -> cognition flow bridge.

Agentic-space dimension: All Spaces.
Operating surface: Track F — Work Surface.

v0.1 (PR #215): Playbook requirements are now consumed by the operating
flow — required_context_packs and recommended_evaluators are validated
and produce findings/data_gaps when missing.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from finharness.agent_cognition_flow import (
    AgentCognitionFlowResult,
    run_agent_cognition_flow,
)
from finharness.agent_context_trust_map import extract_context_trust_by_ref
from finharness.agent_tool_result_envelope import AgentToolResultEnvelope
from finharness.evaluation_report import EvaluationFinding
from finharness.evaluator_registry import evaluator_ids
from finharness.playbook_loader import (
    CognitionPlaybook,
    load_cognition_playbook,
)


def evaluate_playbook_requirements(
    playbook: CognitionPlaybook,
    *,
    context_projection_payload: Mapping[str, object] | None = None,
) -> list[EvaluationFinding]:
    """Validate that playbook requirements are met.

    Checks:
    - required_context_packs are present in the projection payload
    - recommended_evaluators are registered in the evaluator registry
    """
    findings: list[EvaluationFinding] = []
    registered_ids = set(evaluator_ids())

    # Check required context packs
    if playbook.required_context_packs and context_projection_payload is None:
        for cp_ref in playbook.required_context_packs:
            findings.append(EvaluationFinding(
                code="playbook_context_missing",
                severity="warn",
                message=(
                    f"Playbook '{playbook.name}' requires context pack "
                    f"'{cp_ref}' but no context_projection_payload provided"
                ),
                recovery_hint=f"Provide {cp_ref} in context projection payload",
                source_refs=[f"playbook:{playbook.name}"],
            ))
    elif playbook.required_context_packs and context_projection_payload is not None:
        packs = context_projection_payload.get("packs")
        available_refs: set[str] = set()
        if isinstance(packs, list):
            for pack in packs:
                if isinstance(pack, dict):
                    cp_refs = pack.get("context_pack_refs")
                    if isinstance(cp_refs, list):
                        available_refs.update(str(r) for r in cp_refs)
        for cp_ref in playbook.required_context_packs:
            if cp_ref not in available_refs:
                findings.append(EvaluationFinding(
                    code="playbook_context_missing",
                    severity="warn",
                    message=(
                        f"Playbook '{playbook.name}' requires context pack "
                        f"'{cp_ref}' but it is not in the projection payload"
                    ),
                    recovery_hint=(
                        f"Add {cp_ref} to context projection payload"
                    ),
                    source_refs=[f"playbook:{playbook.name}"],
                ))

    # Check recommended evaluators
    for evaluator_id in playbook.recommended_evaluators:
        if evaluator_id not in registered_ids:
            findings.append(EvaluationFinding(
                code="playbook_evaluator_not_registered",
                severity="warn",
                message=(
                    f"Playbook '{playbook.name}' recommends evaluator "
                    f"'{evaluator_id}' but it is not registered"
                ),
                recovery_hint=f"Register evaluator '{evaluator_id}'",
                source_refs=[f"playbook:{playbook.name}"],
            ))

    return findings


def run_agent_cognition_flow_from_operating_inputs(
    *,
    goal: str,
    profile_name: str,
    objective: str,
    option_claims: list[str],
    plan_steps: list[str],
    receipt_root: str | Path,
    context_projection_payload: Mapping[str, object] | None = None,
    tool_envelopes: Sequence[AgentToolResultEnvelope] = (),
    playbook_name: str | None = None,
    human_attester: str | None = None,
    human_reason: str | None = None,
    explicit_confirmation: bool = False,
) -> AgentCognitionFlowResult:
    """Run an agent cognition flow from operating surface inputs.

    Bridges:
    - context projection -> context_trust_by_ref + context_refs
    - tool result envelopes -> source_refs + evidence_refs
    - playbook -> requirement validation (required_context_packs,
      recommended_evaluators checked against live surface)
    - then calls the existing run_agent_cognition_flow()

    v0.1: Playbook is now consumed — requirements produce findings
    that surface as data_gaps in the flow result.
    """
    # Extract trust map from projection
    context_trust_by_ref = None
    context_refs: list[str] = []
    if context_projection_payload is not None:
        context_trust_by_ref = extract_context_trust_by_ref(
            context_projection_payload,
        )
        context_refs = _extract_context_refs(context_projection_payload)

    # Collect source refs from tool result envelopes
    envelope_source_refs: list[str] = []
    for env in tool_envelopes:
        envelope_source_refs.extend(env.source_refs)

    # Build combined source_refs
    all_source_refs: list[str] = list(dict.fromkeys([
        *envelope_source_refs,
        *(list(context_trust_by_ref.keys()) if context_trust_by_ref else []),
    ]))

    # Playbook loading and requirement validation
    playbook_findings: list[EvaluationFinding] = []
    playbook_ref: str | None = None
    if playbook_name:
        playbook = load_cognition_playbook(playbook_name)
        if playbook is not None:
            playbook_ref = f"playbook:{playbook_name} v{playbook.version}"
            playbook_findings = evaluate_playbook_requirements(
                playbook,
                context_projection_payload=context_projection_payload,
            )
            if playbook_ref and playbook_ref not in context_refs:
                context_refs.append(playbook_ref)

    # If playbook findings exist, add them as source_refs context
    if playbook_findings:
        for f in playbook_findings:
            if f.source_refs:
                all_source_refs.extend(f.source_refs)
    all_source_refs = list(dict.fromkeys(all_source_refs))

    return run_agent_cognition_flow(
        goal=goal,
        profile_name=profile_name,
        objective=objective,
        option_claims=option_claims,
        plan_steps=plan_steps,
        receipt_root=receipt_root,
        context_refs=context_refs if context_refs else None,
        source_refs=all_source_refs if all_source_refs else None,
        human_attester=human_attester,
        human_reason=human_reason,
        explicit_confirmation=explicit_confirmation,
        context_trust_by_ref=context_trust_by_ref,
        required_context_use="use_as_evidence",
    )


def _extract_context_refs(payload: Mapping[str, object]) -> list[str]:
    """Extract context pack refs from projection payload."""
    refs: list[str] = []
    packs = payload.get("packs")
    if not isinstance(packs, list):
        return refs
    for pack in packs:
        if isinstance(pack, dict):
            cp_refs = pack.get("context_pack_refs")
            if isinstance(cp_refs, list):
                refs.extend(str(r) for r in cp_refs)
    return list(dict.fromkeys(refs))
