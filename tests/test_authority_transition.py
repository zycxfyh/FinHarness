"""Tests for AuthorityTransitionRecord v0."""

# ruff: noqa: SIM117

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from pydantic import ValidationError

from finharness.authority_transition import (
    record_authority_transition,
)


class TestAuthorityTransitionRecord:
    """Unit tests for AuthorityTransitionRecord model and recorder."""

    def test_record_authority_transition_writes_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = record_authority_transition(
                subject_type="proposal",
                subject_id="p_001",
                from_state="reviewed",
                to_state="eligible_for_stage",
                eligibility="eligible",
                evaluation_report_refs=["er_report_001"],
                human_attester="ops_reviewer",
                human_reason="All pre-trade checks pass, risk is within mandate",
                explicit_confirmation=True,
                receipt_root=root,
            )
            assert record.transition_id.startswith("at_")
            assert record.eligibility == "eligible"
            assert record.authority_transition is True
            assert record.execution_allowed is False

            file_path = root / "authority-transitions" / f"{record.transition_id}.json"
            assert file_path.exists()
            payload = json.loads(file_path.read_text())
            assert payload["human_attester"] == "ops_reviewer"
            assert payload["eligibility"] == "eligible"

    def test_rejects_empty_human_attester(self) -> None:
        import pytest

        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="human_attester"):
                record_authority_transition(
                    subject_type="proposal",
                    subject_id="p_001",
                    from_state="draft",
                    to_state="reviewed",
                    eligibility="eligible",
                    evaluation_report_refs=["er_001"],
                    human_attester="   ",
                    human_reason="test",
                    explicit_confirmation=True,
                    receipt_root=Path(tmp),
                )

    def test_rejects_empty_human_reason(self) -> None:
        import pytest

        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="human_reason"):
                record_authority_transition(
                    subject_type="proposal",
                    subject_id="p_001",
                    from_state="draft",
                    to_state="reviewed",
                    eligibility="eligible",
                    evaluation_report_refs=["er_001"],
                    human_attester="ops",
                    human_reason="",
                    explicit_confirmation=True,
                    receipt_root=Path(tmp),
                )

    def test_rejects_missing_explicit_confirmation(self) -> None:
        import pytest

        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="explicit_confirmation"):
                record_authority_transition(
                    subject_type="proposal",
                    subject_id="p_001",
                    from_state="draft",
                    to_state="reviewed",
                    eligibility="eligible",
                    evaluation_report_refs=["er_001"],
                    human_attester="ops",
                    human_reason="test",
                    explicit_confirmation=False,
                    receipt_root=Path(tmp),
                )

    def test_rejects_empty_evaluation_report_refs(self) -> None:
        import pytest

        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="evaluation_report_ref"):
                record_authority_transition(
                    subject_type="proposal",
                    subject_id="p_001",
                    from_state="draft",
                    to_state="reviewed",
                    eligibility="eligible",
                    evaluation_report_refs=[],
                    human_attester="ops",
                    human_reason="test",
                    explicit_confirmation=True,
                    receipt_root=Path(tmp),
                )

    def test_rejects_invalid_eligibility(self) -> None:
        import pytest

        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="eligibility"):
                record_authority_transition(
                    subject_type="proposal",
                    subject_id="p_001",
                    from_state="draft",
                    to_state="reviewed",
                    eligibility="approved",
                    evaluation_report_refs=["er_001"],
                    human_attester="ops",
                    human_reason="test",
                    explicit_confirmation=True,
                    receipt_root=Path(tmp),
                )

    def test_records_all_three_eligibility_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for eligibility in ("eligible", "not_eligible", "deferred"):
                record = record_authority_transition(
                    subject_type="proposal",
                    subject_id=f"p_{eligibility}",
                    from_state="draft",
                    to_state="reviewed",
                    eligibility=eligibility,
                    evaluation_report_refs=["er_001"],
                    human_attester="ops",
                    human_reason="test",
                    explicit_confirmation=True,
                    receipt_root=Path(tmp),
                )
                assert record.eligibility == eligibility

    def test_includes_optional_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = record_authority_transition(
                subject_type="proposal",
                subject_id="p_001",
                from_state="draft",
                to_state="reviewed",
                eligibility="eligible",
                evaluation_report_refs=["er_001", "er_002"],
                human_attester="ops",
                human_reason="test with mandate",
                explicit_confirmation=True,
                receipt_root=Path(tmp),
                capital_mandate_id="cm_abc",
                agent_authority_grant_id="aag_xyz",
            )
            assert record.capital_mandate_id == "cm_abc"
            assert record.agent_authority_grant_id == "aag_xyz"
            assert len(record.evaluation_report_refs) == 2

    def test_authority_transition_is_true_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = record_authority_transition(
                subject_type="proposal",
                subject_id="p_001",
                from_state="pending",
                to_state="eligible",
                eligibility="eligible",
                evaluation_report_refs=["er_001"],
                human_attester="ops",
                human_reason="passed review",
                explicit_confirmation=True,
                receipt_root=Path(tmp),
            )
            assert record.authority_transition is True
            assert record.execution_allowed is False

    def test_strips_whitespace_from_string_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record = record_authority_transition(
                subject_type="  proposal  ",
                subject_id="  p_002  ",
                from_state="  draft  ",
                to_state="  reviewed  ",
                eligibility="eligible",
                evaluation_report_refs=["er_001", "  er_002  "],
                human_attester="  ops  ",
                human_reason="  looks good  ",
                explicit_confirmation=True,
                receipt_root=Path(tmp),
                capital_mandate_id="  cm_001  ",
            )
            assert record.subject_type == "proposal"
            assert record.subject_id == "p_002"
            assert record.human_attester == "ops"
            assert record.human_reason == "looks good"
            assert record.capital_mandate_id == "cm_001"

    def test_model_is_frozen(self) -> None:
        import pytest

        with tempfile.TemporaryDirectory() as tmp:
            record = record_authority_transition(
                subject_type="proposal",
                subject_id="p_001",
                from_state="draft",
                to_state="reviewed",
                eligibility="eligible",
                evaluation_report_refs=["er_001"],
                human_attester="ops",
                human_reason="test",
                explicit_confirmation=True,
                receipt_root=Path(tmp),
            )
            with pytest.raises(ValidationError, match="frozen"):
                record.eligibility = "deferred"  # type: ignore[misc]
