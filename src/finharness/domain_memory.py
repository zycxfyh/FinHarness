"""Domain memory draft — agent-proposed, human-attested memory.

Agentic-space dimension: Feedback Space / Memory.
Operating surface: Track C — Memory / Search.

v0.1 (PR #212): Adds domain memory context pack promotion — attested
memories can now be bundled into a context pack consumable by the
cognition flow.
"""

from __future__ import annotations

import json
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
    supersedes_memory_ids: list[str] = Field(default_factory=list)
    conflicts_with_memory_ids: list[str] = Field(default_factory=list)
    promoted_at_utc: str | None = None
    promotion_reason: str | None = None
    execution_allowed: bool = False
    authority_transition: bool = False


class DomainMemoryContextPack(BaseModel):
    """Context pack built from attested domain memories."""

    model_config = ConfigDict(frozen=True)

    pack_id: str
    name: str = "domain_memory"
    memories: list[DomainMemoryDraftReceipt] = Field(default_factory=list)
    budget_chars: int = 3000
    total_chars: int = 0
    truncated: bool = False
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
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


# ── context pack promotion (new in v0.1) ──────────────────────────────


def list_domain_memories(
    receipt_root: str | Path,
    *,
    status_filter: DomainMemoryStatus | None = None,
) -> list[DomainMemoryDraftReceipt]:
    """List all domain memory receipts under receipt_root."""
    root = Path(receipt_root) / "domain-memory"
    if not root.is_dir():
        return []
    memories: list[DomainMemoryDraftReceipt] = []
    for file_path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
            mem = DomainMemoryDraftReceipt(**payload)
            if status_filter is None or mem.status == status_filter:
                memories.append(mem)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return memories


def build_domain_memory_context_pack(
    *,
    receipt_root: str | Path,
    memory_types: list[DomainMemoryType] | None = None,
    budget_chars: int = 3000,
) -> DomainMemoryContextPack:
    """Build a context pack from attested domain memories.

    Only attested memories are included. Draft and rejected memories
    are excluded. A character budget is enforced; if memories exceed
    it, they are truncated and the pack is marked as truncated=True.
    """
    all_memories = list_domain_memories(receipt_root, status_filter="attested")

    if memory_types is not None:
        all_memories = [m for m in all_memories if m.memory_type in memory_types]

    source_refs: list[str] = []
    receipt_refs: list[str] = []
    included: list[DomainMemoryDraftReceipt] = []
    total_chars = 0

    for mem in all_memories:
        mem_len = len(mem.content)
        if total_chars + mem_len <= budget_chars:
            included.append(mem)
            total_chars += mem_len
            source_refs.extend(mem.source_refs)
            receipt_refs.append(mem.memory_id)
        else:
            break

    pack_id = _new_id("dmpack")
    return DomainMemoryContextPack(
        pack_id=pack_id,
        memories=included,
        budget_chars=budget_chars,
        total_chars=total_chars,
        truncated=len(included) < len(all_memories),
        source_refs=_dedupe(source_refs),
        receipt_refs=receipt_refs,
    )


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out
