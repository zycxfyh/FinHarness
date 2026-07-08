"""Tests for ContextTrust v0."""

from __future__ import annotations

from finharness.context_trust import (
    trust_for_agent_draft,
    trust_for_external_provider,
    trust_for_human_attested,
    trust_for_receipt_backed_state,
    trust_for_system_computed,
    trust_for_unknown,
    trust_for_user_supplied,
)


class TestContextTrust:
    """Unit tests for ContextTrust model and pre-built trust profiles."""

    def test_receipt_backed_state_trust(self) -> None:
        trust = trust_for_receipt_backed_state(
            receipt_refs=["r_abc123"],
            source_refs=["proposal_p_001"],
        )
        assert trust.source_type == "receipt_backed_state"
        assert trust.trust_level == "high"
        assert trust.verification_status == "verified"
        assert "plan_from" in trust.allowed_uses
        assert "r_abc123" in trust.receipt_refs
        assert "proposal_p_001" in trust.source_refs

    def test_system_computed_trust(self) -> None:
        trust = trust_for_system_computed(
            source_refs=["capital_summary"],
            receipt_refs=["r_xyz"],
        )
        assert trust.source_type == "system_computed"
        assert trust.trust_level == "high"
        assert trust.verification_status == "derived"
        assert "cite" in trust.allowed_uses

    def test_human_attested_trust(self) -> None:
        trust = trust_for_human_attested(
            source_refs=["review_event_re_001"],
            receipt_refs=["r_human"],
        )
        assert trust.source_type == "human_attested"
        assert trust.verification_status == "verified"
        assert "use_as_evidence" in trust.allowed_uses

    def test_agent_draft_trust(self) -> None:
        trust = trust_for_agent_draft(
            source_refs=["agent_review_note_001"],
            receipt_refs=["r_draft"],
        )
        assert trust.source_type == "agent_draft"
        assert trust.trust_level == "low"
        assert trust.verification_status == "unverified"
        assert "read" in trust.allowed_uses
        assert "draft_review" in trust.allowed_uses
        # Agent drafts must NOT be used as evidence without review
        assert "use_as_evidence" not in trust.allowed_uses

    def test_user_supplied_trust(self) -> None:
        trust = trust_for_user_supplied(source_refs=["user_input_001"])
        assert trust.source_type == "user_supplied"
        assert trust.trust_level == "medium"
        assert trust.verification_status == "unverified"
        assert len(trust.receipt_refs) == 0

    def test_external_provider_trust(self) -> None:
        trust = trust_for_external_provider(
            source_refs=["yfinance_AAPL_history"],
            receipt_refs=["r_market"],
        )
        assert trust.source_type == "external_provider"
        assert trust.trust_level == "medium"
        assert trust.verification_status == "derived"
        assert "plan_from" in trust.allowed_uses

    def test_unknown_trust_is_untrusted(self) -> None:
        trust = trust_for_unknown()
        assert trust.source_type == "unknown"
        assert trust.trust_level == "untrusted"
        assert trust.verification_status == "unknown"
        assert trust.allowed_uses == ["read"]
        assert trust.source_refs == []
        assert trust.receipt_refs == []

    def test_trust_deduplicates_refs(self) -> None:
        trust = trust_for_receipt_backed_state(
            receipt_refs=["r_a", "r_a", "r_b"],
            source_refs=["s_x", "s_x"],
        )
        assert trust.receipt_refs == ["r_a", "r_b"]
        assert trust.source_refs == ["s_x"]

    def test_trust_strips_whitespace_refs(self) -> None:
        trust = trust_for_receipt_backed_state(
            receipt_refs=["  r_clean  "],
            source_refs=["  s_trim  "],
        )
        assert "  " not in trust.receipt_refs[0]
        assert "  " not in trust.source_refs[0]

    def test_context_trust_model_is_frozen(self) -> None:
        import pytest
        from pydantic import ValidationError

        trust = trust_for_receipt_backed_state(receipt_refs=["r_001"])
        with pytest.raises(ValidationError, match="frozen"):
            trust.source_type = "unknown"  # type: ignore[misc]
