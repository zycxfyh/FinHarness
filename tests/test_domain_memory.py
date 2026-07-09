"""Tests for domain memory draft."""

from __future__ import annotations

import tempfile
from pathlib import Path

from finharness.domain_memory import (
    attest_domain_memory,
    propose_domain_memory,
)


class TestDomainMemoryDraft:

    def test_propose_creates_draft_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            draft = propose_domain_memory(
                proposed_by="agent:default",
                memory_type="planning_lesson",
                content="SPY allocation should stay under 30% of portfolio",
                receipt_root=root,
            )
            assert draft.status == "draft"
            assert draft.memory_type == "planning_lesson"
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
                attested_reason="Matches user's stated preference",
                receipt_root=root,
            )
            assert attested.status == "attested"
            assert attested.attested_by == "human:alice"
            assert attested.attested_reason == "Matches user's stated preference"

    def test_propose_rejects_empty_content(self) -> None:
        import pytest
        with tempfile.TemporaryDirectory() as tmp, pytest.raises(ValueError):
            propose_domain_memory(
                proposed_by="agent",
                memory_type="planning_lesson",
                content="   ",
                receipt_root=Path(tmp),
            )

    def test_attest_missing_file_raises(self) -> None:
        import pytest
        with tempfile.TemporaryDirectory() as tmp, pytest.raises(FileNotFoundError):
            attest_domain_memory(
                memory_id="nonexistent",
                attested_by="human:alice",
                attested_reason="test",
                receipt_root=Path(tmp),
            )

    def test_model_is_frozen(self) -> None:
        import pytest
        from pydantic import ValidationError

        from finharness.domain_memory import DomainMemoryDraftReceipt

        r = DomainMemoryDraftReceipt(
            memory_id="dmem_test",
            proposed_by="agent",
            memory_type="planning_lesson",
            content="test content",
            created_at_utc="2026-01-01T00:00:00Z",
        )
        with pytest.raises(ValidationError, match="frozen"):
            r.content = "hijacked"  # type: ignore[misc]

    def test_execution_allowed_always_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            draft = propose_domain_memory(
                proposed_by="agent",
                memory_type="market_observation",
                content="VIX above 30 indicates elevated fear",
                receipt_root=Path(tmp),
            )
            assert draft.execution_allowed is False
            assert draft.authority_transition is False
