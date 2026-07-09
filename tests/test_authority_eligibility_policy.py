"""Tests for authority eligibility policy v0."""

from __future__ import annotations

from finharness.authority_eligibility_policy import eligibility_from_evaluation_status


class TestAuthorityEligibilityPolicy:
    def test_pass_maps_to_eligible(self) -> None:
        assert eligibility_from_evaluation_status("pass") == "eligible"

    def test_warn_maps_to_deferred(self) -> None:
        assert eligibility_from_evaluation_status("warn") == "deferred"

    def test_block_maps_to_not_eligible(self) -> None:
        assert eligibility_from_evaluation_status("block") == "not_eligible"

    def test_deferred_does_not_allow_execution(self) -> None:
        result = eligibility_from_evaluation_status("warn")
        assert result != "eligible"
