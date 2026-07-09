"""Tests for context use policy v0."""

from __future__ import annotations

from finharness.context_trust import (
    trust_for_agent_draft,
    trust_for_human_attested,
    trust_for_receipt_backed_state,
    trust_for_unknown,
)
from finharness.context_use_policy import (
    validate_context_refs_for_use,
)


class TestContextUsePolicy:
    def test_receipt_backed_state_allows_evidence(self) -> None:
        trust = trust_for_receipt_backed_state(
            receipt_refs=["r_a"],
            source_refs=["s_a"],
        )
        result = validate_context_refs_for_use(
            refs=["r_a"],
            trust_by_ref={"r_a": trust},
            required_use="use_as_evidence",
        )
        assert result.valid
        assert "r_a" in result.passed_refs
        assert result.blocked_refs == []

    def test_agent_draft_blocks_evidence(self) -> None:
        trust = trust_for_agent_draft(source_refs=["draft_1"])
        result = validate_context_refs_for_use(
            refs=["draft_1"],
            trust_by_ref={"draft_1": trust},
            required_use="use_as_evidence",
        )
        assert not result.valid
        assert "draft_1" in result.blocked_refs
        assert "agent_draft" in result.blocked_reasons[0]

    def test_agent_draft_allows_draft_review(self) -> None:
        trust = trust_for_agent_draft(source_refs=["draft_1"])
        result = validate_context_refs_for_use(
            refs=["draft_1"],
            trust_by_ref={"draft_1": trust},
            required_use="draft_review",
        )
        assert result.valid

    def test_unknown_blocks_all_except_read(self) -> None:
        trust = trust_for_unknown()
        for use in ("cite", "plan_from", "use_as_evidence", "draft_review", "explain"):
            result = validate_context_refs_for_use(
                refs=["u_1"],
                trust_by_ref={"u_1": trust},
                required_use=use,  # type: ignore[arg-type]
            )
            assert not result.valid, f"unknown should block {use}"

    def test_missing_trust_is_blocked(self) -> None:
        result = validate_context_refs_for_use(
            refs=["no_trust_ref"],
            trust_by_ref={},
            required_use="read",
        )
        assert not result.valid
        assert "no_trust_ref" in result.blocked_refs

    def test_human_attested_allows_all(self) -> None:
        trust = trust_for_human_attested(source_refs=["h_1"])
        for use in ("read", "cite", "plan_from", "use_as_evidence"):
            result = validate_context_refs_for_use(
                refs=["h_1"],
                trust_by_ref={"h_1": trust},
                required_use=use,  # type: ignore[arg-type]
            )
            assert result.valid, f"human_attested should allow {use}"

    def test_mixed_refs_partial_block(self) -> None:
        result = validate_context_refs_for_use(
            refs=["r_good", "r_bad"],
            trust_by_ref={
                "r_good": trust_for_receipt_backed_state(receipt_refs=["r_good"]),
                "r_bad": trust_for_agent_draft(source_refs=["r_bad"]),
            },
            required_use="use_as_evidence",
        )
        assert not result.valid
        assert "r_good" in result.passed_refs
        assert "r_bad" in result.blocked_refs
