"""Tests for evaluator registry v0."""

from __future__ import annotations

from finharness.evaluator_registry import (
    evaluator_ids,
    evaluators_for_subject,
    get_evaluator,
    list_evaluators,
)


class TestEvaluatorRegistry:

    def test_list_returns_evaluators(self) -> None:
        evals = list_evaluators()
        assert len(evals) == 1
        assert evals[0].evaluator_id == "plan_draft_evaluator"

    def test_get_evaluator_finds_known(self) -> None:
        e = get_evaluator("plan_draft_evaluator")
        assert e is not None
        assert e.subject_type == "PlanDraft"
        assert e.deterministic is True

    def test_get_evaluator_returns_none_for_unknown(self) -> None:
        assert get_evaluator("nonexistent") is None

    def test_evaluator_ids_returns_sorted(self) -> None:
        ids = evaluator_ids()
        assert "plan_draft_evaluator" in ids
        assert ids == sorted(ids)

    def test_evaluators_for_subject_filters(self) -> None:
        matches = evaluators_for_subject("PlanDraft")
        assert len(matches) == 1
        assert matches[0].evaluator_id == "plan_draft_evaluator"

    def test_no_match_subject_returns_empty(self) -> None:
        matches = evaluators_for_subject("OrderDraft")
        assert matches == []

    def test_all_evaluators_have_execution_allowed_false(self) -> None:
        for e in list_evaluators():
            assert e.execution_allowed is False
            assert e.authority_transition is False

    def test_model_is_frozen(self) -> None:
        import pytest
        from pydantic import ValidationError

        e = list_evaluators()[0]
        with pytest.raises(ValidationError, match="frozen"):
            e.evaluator_id = "hijacked"  # type: ignore[misc]
