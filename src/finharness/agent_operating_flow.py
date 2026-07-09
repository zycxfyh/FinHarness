"""Operating surface → cognition flow bridge.

Agentic-space dimension: All Spaces.
Operating surface: Track F — Work Surface.

Bridges the new operating surfaces (projection, envelopes, playbooks)
into the existing AgentCognitionFlow. This is the integration point
that proves the operating surfaces are real, not just isolated helpers.
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
from finharness.playbook_loader import load_cognition_playbook


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
    - context projection → context_trust_by_ref + context_refs
    - tool result envelopes → source_refs + evidence_refs
    - playbook → loaded procedure (contextual, not injected into flow)
    - then calls the existing run_agent_cognition_flow()

    This is the integration point for Wave 2 operating surfaces.
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

    # Playbook loading (loaded for context awareness, not injected into flow)
    if playbook_name:
        load_cognition_playbook(playbook_name)

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
