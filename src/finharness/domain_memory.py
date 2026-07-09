"""Domain memory draft — agent-proposed, human-attested memory.

Agentic-space dimension: Feedback Space / Memory.
Operating surface: Track C — Memory / Search.

Agent proposes memory → DomainMemoryDraftReceipt → human attests →
promoted to PlanningPolicyView or context pack. Not auto-injected,
not agent-mutable after creation.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

DomainMemoryType = Literal[
    "user_preference",
    "architecture_fact",
    "planning_lesson",
    "market_observation",
]

DomainMemoryStatus = Literal["draft", "attested", "rejected"]

NON_CLAIMS: tuple[str, ...] = (
    "Domain memory drafts are agent proposals, not system facts.",
    "Memory must be human-attested before entering planning policy.",
    "Not investment advice.",
)


class DomainMemoryDraftReceipt(BaseModel):
    """Receipt-only domain memory draft proposed by an agent."""

    model_config = ConfigDict(frozen=True)

    memory_id: str
    proposed_by: str
    memory_type: DomainMemoryType
    content: str
    source_refs: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    created_at_utc: str
    status: DomainMemoryStatus = "draft"
    attested_by: str | None = None
    attested_at_utc: str | None = None
    attested_reason: str | None = None
    execution_allowed: bool = False
    authority_transition: bool = False


def _new_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid4().hex[:8]}"


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def propose_domain_memory(
    *,
    proposed_by: str,
    memory_type: DomainMemoryType,
    content: str,
    receipt_root: str | Path,
    source_refs: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    receipt_refs: list[str] | None = None,
) -> DomainMemoryDraftReceipt:
    """Propose a domain memory draft.

    Creates a receipt-only draft with status='draft'. Memory is NOT
    auto-injected into prompt or planning policy. It must be human-attested.
    """
    if not content.strip():
        raise ValueError("domain memory content must not be empty")

    memory_id = _new_id("dmem")
    draft = DomainMemoryDraftReceipt(
        memory_id=memory_id,
        proposed_by=proposed_by.strip(),
        memory_type=memory_type,
        content=content.strip(),
        source_refs=_dedupe(source_refs or []),
        evidence_refs=_dedupe(evidence_refs or []),
        receipt_refs=_dedupe(receipt_refs or []),
        created_at_utc=_now_utc(),
        status="draft",
    )

    root = Path(receipt_root)
    target_dir = root / "domain-memory"
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / f"{memory_id}.json"
    file_path.write_text(
        draft.model_dump_json(indent=2, exclude_none=True),
        encoding="utf-8",
    )

    return draft


def attest_domain_memory(
    *,
    memory_id: str,
    attested_by: str,
    attested_reason: str,
    receipt_root: str | Path,
) -> DomainMemoryDraftReceipt:
    """Attest a previously proposed domain memory draft.

    Promotes status from 'draft' to 'attested'. Returns a new frozen receipt.
    The original draft file is overwritten with the attested version.
    """
    root = Path(receipt_root) / "domain-memory"
    file_path = root / f"{memory_id}.json"

    if not file_path.exists():
        raise FileNotFoundError(f"domain memory draft not found: {memory_id}")

    import json

    payload = json.loads(file_path.read_text(encoding="utf-8"))
    if payload.get("status") != "draft":
        raise ValueError(
            f"memory {memory_id} has status {payload.get('status')}, expected 'draft'"
        )

    attested = DomainMemoryDraftReceipt(
        memory_id=payload["memory_id"],
        proposed_by=payload["proposed_by"],
        memory_type=payload["memory_type"],
        content=payload["content"],
        source_refs=payload.get("source_refs", []),
        evidence_refs=payload.get("evidence_refs", []),
        receipt_refs=payload.get("receipt_refs", []),
        created_at_utc=payload["created_at_utc"],
        status="attested",
        attested_by=attested_by.strip(),
        attested_at_utc=_now_utc(),
        attested_reason=attested_reason.strip(),
    )

    file_path.write_text(
        attested.model_dump_json(indent=2, exclude_none=True),
        encoding="utf-8",
    )

    return attested


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out
