"""Tests for domain memory draft v0.1.

v0.1 (PR #212): Adds context pack promotion tests.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from finharness.domain_memory import (
    DomainMemoryContextPack,
    DomainMemoryDraftReceipt,
    attest_domain_memory,
    build_domain_memory_context_pack,
    list_domain_memories,
    propose_domain_memory,
)


class TestDomainMemoryDraft:

    def test_propose_creates_draft_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft = propose_domain_memory(
                proposed_by="agent:default",
                memory_type="planning_lesson",
                content="SPY allocation should stay under 30%",
                receipt_root=root,
            )
            assert draft.status == "draft"
            assert draft.execution_allowed is False
            file_path = root / "domain-memory" / f"{draft.memory_id}.json"
            assert file_path.exists()

    def test_attest_promotes_to_attested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft = propose_domain_memory(
                proposed_by="agent:default",
                memory_type="user_preference",
                content="Prefer conservative allocations",
                receipt_root=root,
            )
            attested = attest_domain_memory(
                memory_id=draft.memory_id,
                attested_by="human:alice",
                attested_reason="Matches user preference",
                receipt_root=root,
            )
            assert attested.status == "attested"
            assert attested.attested_by == "human:alice"

    def test_propose_rejects_empty_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, pytest.raises(ValueError):
            propose_domain_memory(
                proposed_by="agent", memory_type="planning_lesson",
                content="   ", receipt_root=Path(tmp),
            )

    def test_attest_missing_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, pytest.raises(FileNotFoundError):
            attest_domain_memory(
                memory_id="nonexistent", attested_by="human:alice",
                attested_reason="test", receipt_root=Path(tmp),
            )

    def test_model_is_frozen(self) -> None:
        r = DomainMemoryDraftReceipt(
            memory_id="dmem_test", proposed_by="agent",
            memory_type="planning_lesson", content="test",
            created_at_utc="2026-01-01T00:00:00Z",
        )
        with pytest.raises(ValidationError, match="frozen"):
            r.content = "hijacked"  # type: ignore[misc]

    def test_execution_allowed_always_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            draft = propose_domain_memory(
                proposed_by="agent", memory_type="market_observation",
                content="VIX above 30 indicates elevated fear",
                receipt_root=Path(tmp),
            )
            assert draft.execution_allowed is False


class TestDomainMemoryPromotion:
    """Tests for context pack promotion (new in v0.1)."""

    def test_list_domain_memories_filters_by_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            propose_domain_memory(
                proposed_by="agent", memory_type="planning_lesson",
                content="Lesson A", receipt_root=root,
            )
            attest_domain_memory(
                memory_id=list_domain_memories(root, status_filter="draft")[0].memory_id,
                attested_by="human:alice", attested_reason="ok", receipt_root=root,
            )
            attested = list_domain_memories(root, status_filter="attested")
            assert len(attested) == 1
            drafts = list_domain_memories(root, status_filter="draft")
            assert len(drafts) == 0

    def test_build_context_pack_includes_only_attested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Create a draft (not attested)
            propose_domain_memory(
                proposed_by="agent", memory_type="planning_lesson",
                content="Draft lesson — should be excluded", receipt_root=root,
            )
            # Create and attest one
            d = propose_domain_memory(
                proposed_by="agent", memory_type="user_preference",
                content="Attested preference", receipt_root=root,
            )
            attest_domain_memory(
                memory_id=d.memory_id, attested_by="human:alice",
                attested_reason="ok", receipt_root=root,
            )
            pack = build_domain_memory_context_pack(receipt_root=root)
            assert len(pack.memories) == 1  # Only attested
            assert pack.truncated is False
            assert pack.total_chars <= pack.budget_chars

    def test_build_context_pack_respects_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(5):
                d = propose_domain_memory(
                    proposed_by="agent", memory_type="market_observation",
                    content=f"Market observation {i}: " + "x" * 500,
                    receipt_root=root,
                )
                attest_domain_memory(
                    memory_id=d.memory_id, attested_by="human:alice",
                    attested_reason="ok", receipt_root=root,
                )
            pack = build_domain_memory_context_pack(receipt_root=root, budget_chars=1000)
            assert len(pack.memories) < 5
            assert pack.truncated is True
            assert pack.total_chars <= 1000

    def test_build_context_pack_filters_by_memory_type(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            d1 = propose_domain_memory(
                proposed_by="agent", memory_type="user_preference",
                content="Pref", receipt_root=root,
            )
            attest_domain_memory(
                memory_id=d1.memory_id, attested_by="human:alice",
                attested_reason="ok", receipt_root=root,
            )
            d2 = propose_domain_memory(
                proposed_by="agent", memory_type="planning_lesson",
                content="Lesson", receipt_root=root,
            )
            attest_domain_memory(
                memory_id=d2.memory_id, attested_by="human:alice",
                attested_reason="ok", receipt_root=root,
            )
            pack = build_domain_memory_context_pack(
                receipt_root=root, memory_types=["user_preference"],
            )
            assert len(pack.memories) == 1
            assert pack.memories[0].memory_type == "user_preference"

    def test_context_pack_is_frozen(self) -> None:
        pack = DomainMemoryContextPack(pack_id="test")
        with pytest.raises(ValidationError, match="frozen"):
            pack.budget_chars = 5000  # type: ignore[misc]

    def test_list_memories_handles_missing_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = list_domain_memories(Path(tmp))
            assert result == []

    def test_empty_receipt_root_produces_empty_pack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            pack = build_domain_memory_context_pack(receipt_root=Path(tmp))
            assert len(pack.memories) == 0
            assert pack.truncated is False
