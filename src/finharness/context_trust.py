"""ContextTrust v0 — epistemological metadata for agent context items.

Agentic-space dimension: Context Space.

Upgrades context packs from plain DTOs to items that carry source,
trust level, verification status, and allowed uses. This is not a
prompt-injection patch; it is a structural upgrade for agent reasoning
materials.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

SourceType = Literal[
    "receipt_backed_state",
    "system_computed",
    "human_attested",
    "agent_draft",
    "user_supplied",
    "external_provider",
    "unknown",
]

TrustLevel = Literal["high", "medium", "low", "untrusted"]

VerificationStatus = Literal["verified", "derived", "unverified", "stale", "unknown"]


class ContextTrust(BaseModel):
    """Epistemological metadata for one piece of agent context.

    Attached to context items to tell the agent where the data came from,
    how trustworthy it is, whether it was verified, and what it may be
    used for.
    """

    model_config = ConfigDict(frozen=True)

    source_type: SourceType
    trust_level: TrustLevel
    verification_status: VerificationStatus
    allowed_uses: list[str]
    source_refs: list[str]
    receipt_refs: list[str]


def _dedupe_refs(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


# ── Pre-built trust profiles ─────────────────────────────────────────────────


def trust_for_receipt_backed_state(
    *,
    receipt_refs: list[str],
    source_refs: list[str] | None = None,
) -> ContextTrust:
    """StateCore objects backed by receipts — highest trust."""
    return ContextTrust(
        source_type="receipt_backed_state",
        trust_level="high",
        verification_status="verified",
        allowed_uses=["read", "cite", "plan_from", "use_as_evidence"],
        source_refs=_dedupe_refs(source_refs or []),
        receipt_refs=_dedupe_refs(receipt_refs),
    )


def trust_for_system_computed(
    *,
    source_refs: list[str] | None = None,
    receipt_refs: list[str] | None = None,
) -> ContextTrust:
    """System-computed projections and derived metrics."""
    return ContextTrust(
        source_type="system_computed",
        trust_level="high",
        verification_status="derived",
        allowed_uses=["read", "cite", "plan_from", "use_as_evidence"],
        source_refs=_dedupe_refs(source_refs or []),
        receipt_refs=_dedupe_refs(receipt_refs or []),
    )


def trust_for_human_attested(
    *,
    source_refs: list[str] | None = None,
    receipt_refs: list[str] | None = None,
) -> ContextTrust:
    """Data explicitly attested by a human operator."""
    return ContextTrust(
        source_type="human_attested",
        trust_level="high",
        verification_status="verified",
        allowed_uses=["read", "cite", "plan_from", "use_as_evidence"],
        source_refs=_dedupe_refs(source_refs or []),
        receipt_refs=_dedupe_refs(receipt_refs or []),
    )


def trust_for_agent_draft(
    *,
    source_refs: list[str] | None = None,
    receipt_refs: list[str] | None = None,
) -> ContextTrust:
    """Agent-generated draft content — must be human-reviewed before action."""
    return ContextTrust(
        source_type="agent_draft",
        trust_level="low",
        verification_status="unverified",
        allowed_uses=["read", "explain", "draft_review"],
        source_refs=_dedupe_refs(source_refs or []),
        receipt_refs=_dedupe_refs(receipt_refs or []),
    )


def trust_for_user_supplied(
    *,
    source_refs: list[str] | None = None,
) -> ContextTrust:
    """User-supplied content — not system-verified."""
    return ContextTrust(
        source_type="user_supplied",
        trust_level="medium",
        verification_status="unverified",
        allowed_uses=["read", "explain"],
        source_refs=_dedupe_refs(source_refs or []),
        receipt_refs=[],
    )


def trust_for_external_provider(
    *,
    source_refs: list[str] | None = None,
    receipt_refs: list[str] | None = None,
) -> ContextTrust:
    """Data from an external provider — trust depends on provider."""
    return ContextTrust(
        source_type="external_provider",
        trust_level="medium",
        verification_status="derived",
        allowed_uses=["read", "cite", "plan_from"],
        source_refs=_dedupe_refs(source_refs or []),
        receipt_refs=_dedupe_refs(receipt_refs or []),
    )


def trust_for_unknown() -> ContextTrust:
    """Fallback trust profile for items with no known provenance."""
    return ContextTrust(
        source_type="unknown",
        trust_level="untrusted",
        verification_status="unknown",
        allowed_uses=["read"],
        source_refs=[],
        receipt_refs=[],
    )
