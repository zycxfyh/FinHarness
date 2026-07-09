"""AgentToolResultEnvelope — structured result wrapper for agent tool outputs.

Agentic-space dimension: Trace Space / Evidence Space.
Operating surface: Track B — Evidence / Runtime Envelope.

Wraps AgentToolRuntimeResult with typed ref channels (source, evidence,
artifact, receipt, context) and data gaps. Tool outputs become structured
operating objects, not bare JSON.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from finharness.agent_runtime import AgentToolRuntimeResult
from finharness.agent_tools import AGENT_TOOL_ENTRIES

NON_CLAIMS: tuple[str, ...] = (
    "AgentToolResultEnvelope records tool output metadata, not execution authority.",
    "source_refs are candidate evidence, not confirmed evidence.",
    "evidence_refs require ContextTrust validation before use_as_evidence.",
    "Not investment advice.",
)


class AgentToolResultEnvelope(BaseModel):
    """Structured result wrapper for one agent tool invocation.

    Converts raw AgentToolRuntimeResult into typed ref channels so
    downstream cognition flow can consume structured context/evidence
    metadata instead of bare JSON.
    """

    model_config = ConfigDict(frozen=True)

    tool_name: str
    toolset: str
    ok: bool
    result_summary: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    artifact_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    context_refs: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    side_effect: str
    output_kind: str
    error_code: str | None = None
    truncated: bool = False
    execution_allowed: bool = False
    authority_transition: bool = False


def build_tool_result_envelope(
    result: AgentToolRuntimeResult,
) -> AgentToolResultEnvelope:
    """Build an AgentToolResultEnvelope from a live AgentToolRuntimeResult.

    Maps runtime result fields into typed ref channels and derives
    toolset/output_kind from the tool registry.
    """
    entry = AGENT_TOOL_ENTRIES.get(result.tool_name)
    toolset = entry.toolset if entry else "unknown"

    # Extract refs from evidence envelope
    source_refs: list[str] = []
    evidence_refs: list[str] = []
    receipt_refs: list[str] = []
    context_refs: list[str] = []
    data_gaps: list[str] = []

    if result.evidence is not None:
        source_refs = _dedupe(
            list(result.evidence.source_refs)
            if result.evidence.source_refs
            else []
        )
        evidence_refs = _dedupe(
            [f"provider:{pid}" for pid in result.evidence.provider_ids]
        )
        receipt_refs = _dedupe(
            list(result.evidence.receipt_refs)
            if result.evidence.receipt_refs
            else []
        )
        context_refs = _dedupe(
            list(result.evidence.context_pack_refs)
            if result.evidence.context_pack_refs
            else []
        )
        data_gaps.extend(
            list(result.evidence.data_gaps) if result.evidence.data_gaps else []
        )

    # Add error-based data gaps
    if result.error is not None:
        data_gaps.append(f"{result.tool_name}: {result.error.code}")

    # Result summary
    result_summary: str | None = None
    if result.ok and result.result:
        status = result.result.get("status", "")
        result_summary = str(status) if status else None
    elif not result.ok and result.error:
        result_summary = result.error.code

    output_kind = _classify_output_kind(result.side_effect or "read")

    return AgentToolResultEnvelope(
        tool_name=result.tool_name,
        toolset=toolset,
        ok=result.ok,
        result_summary=result_summary,
        source_refs=source_refs,
        evidence_refs=evidence_refs,
        artifact_refs=[],
        receipt_refs=receipt_refs,
        context_refs=context_refs,
        data_gaps=_dedupe(data_gaps),
        side_effect=result.side_effect or "read",
        output_kind=output_kind,
        error_code=result.error.code if result.error else None,
        truncated=result.truncated,
    )


def build_tool_result_envelopes(
    results: list[AgentToolRuntimeResult],
) -> list[AgentToolResultEnvelope]:
    """Build envelopes for a batch of runtime results."""
    return [build_tool_result_envelope(r) for r in results]


_OUTPUT_KIND_MAP: dict[str, str] = {
    "read": "context",
    "local_eval": "evidence",
    "append_only_review_write": "artifact",
}


def _classify_output_kind(side_effect: str) -> str:
    return _OUTPUT_KIND_MAP.get(side_effect, "diagnostic")


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out
