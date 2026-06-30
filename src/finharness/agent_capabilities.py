"""Agent capability profiles for FinHarness L5 tools.

Profiles are product postures, not permission bypasses. They determine which
existing Agent tools are visible for a posture; new write capabilities still
need explicit tools, tests, and receipt-backed command paths.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, field_validator

AGENT_CAPABILITY_NON_CLAIMS = (
    "Agent capability profiles select visible tools; they do not grant authority.",
    "Future append-only capabilities require explicit tools, tests, and receipts.",
    "Not execution authorization.",
    "Not investment advice.",
)

CAPITAL_CONTEXT_TOOL_NAMES = (
    "get_capital_context_projection",
    "get_capital_summary_context",
    "get_current_ips_context",
    "get_ips_check_context",
    "get_open_proposals_context",
    "get_proposal_timeline_context",
)

DRAFT_PROPOSAL_TOOL_NAMES = (
    "draft_governed_proposal_from_context",
)

CURRENT_AGENT_TOOL_NAMES = (
    "get_quote_snapshot",
    "get_historical_risk_metrics",
    "evaluate_latest_risk_note",
    *CAPITAL_CONTEXT_TOOL_NAMES,
)


class AgentCapability(StrEnum):
    CAPITAL_READ = "capital-read"
    CAPITAL_EXPLAIN = "capital-explain"
    CAPITAL_PROPOSE = "capital-propose"
    CAPITAL_REVIEW_NOTE = "capital-review-note"
    CAPITAL_SCAFFOLD_REVISION = "capital-scaffold-revision"
    CAPITAL_SIMULATE = "capital-simulate"
    CAPITAL_ATTEST = "capital-attest"
    CAPITAL_EXECUTE = "capital-execute"


class AgentCapabilityProfile(BaseModel):
    """Declared L5 tool posture for an Agent runtime."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    capabilities: tuple[AgentCapability, ...]
    planned_capabilities: tuple[AgentCapability, ...] = ()
    tool_names: tuple[str, ...]
    non_claims: tuple[str, ...] = AGENT_CAPABILITY_NON_CLAIMS
    execution_allowed: bool = False

    @field_validator("execution_allowed")
    @classmethod
    def reject_execution_authority(cls, value: bool) -> bool:
        if value:
            raise ValueError("agent capability profiles never grant execution authority")
        return False


DEFAULT_AGENT_PROFILE = AgentCapabilityProfile(
    name="default",
    description=(
        "Default read/explain posture with current read-only context, market-data, "
        "risk-metric, and eval tools."
    ),
    capabilities=(AgentCapability.CAPITAL_READ, AgentCapability.CAPITAL_EXPLAIN),
    tool_names=CURRENT_AGENT_TOOL_NAMES,
)

REVIEW_DRAFT_AGENT_PROFILE = AgentCapabilityProfile(
    name="review-draft",
    description=(
        "Append-only proposal draft posture. It exposes the existing read/explain "
        "tools plus a receipt-backed governed proposal draft tool."
    ),
    capabilities=(
        AgentCapability.CAPITAL_READ,
        AgentCapability.CAPITAL_EXPLAIN,
        AgentCapability.CAPITAL_PROPOSE,
    ),
    planned_capabilities=(
        AgentCapability.CAPITAL_REVIEW_NOTE,
    ),
    tool_names=(*CURRENT_AGENT_TOOL_NAMES, *DRAFT_PROPOSAL_TOOL_NAMES),
)

SIMULATION_AGENT_PROFILE = AgentCapabilityProfile(
    name="simulation",
    description=(
        "Future simulation posture. Today it exposes only existing read/explain tools; "
        "ActionIntent and PreTradeImpactReport tools are not implemented."
    ),
    capabilities=(
        AgentCapability.CAPITAL_READ,
        AgentCapability.CAPITAL_EXPLAIN,
    ),
    planned_capabilities=(
        AgentCapability.CAPITAL_SIMULATE,
    ),
    tool_names=CURRENT_AGENT_TOOL_NAMES,
)

AGENT_PROFILES = (
    DEFAULT_AGENT_PROFILE,
    REVIEW_DRAFT_AGENT_PROFILE,
    SIMULATION_AGENT_PROFILE,
)

_PROFILE_BY_NAME = {profile.name: profile for profile in AGENT_PROFILES}


def get_agent_profile(name: str = "default") -> AgentCapabilityProfile:
    try:
        return _PROFILE_BY_NAME[name]
    except KeyError as exc:
        names = ", ".join(sorted(_PROFILE_BY_NAME))
        message = f"unknown agent capability profile {name!r}; expected one of {names}"
        raise ValueError(message) from exc


def list_agent_profiles() -> tuple[AgentCapabilityProfile, ...]:
    return AGENT_PROFILES


def tool_names_for_profile(name: str = "default") -> tuple[str, ...]:
    return get_agent_profile(name).tool_names


def profile_allows_capability(
    profile_name: str, capability: AgentCapability
) -> bool:
    profile = get_agent_profile(profile_name)
    return capability in profile.capabilities
