"""Tests for PlanDraft semantic evaluator v0."""

from __future__ import annotations

from finharness.deliberation_receipts import PlanDraftReceipt
from finharness.plan_draft_evaluator import evaluate_plan_draft_receipt


def _plan(*, steps=None, source_refs=None, stop_conditions=None,
          related_option_set_id=None, required_evaluations=None, receipt_refs=None):
    def _d(v, d):
        return v if v is not None else d
    return PlanDraftReceipt(
        receipt_id="r_test",
        plan_id="plan_test",
        objective="Test plan",
        steps=_d(steps, ["Review allocation"]),
        source_refs=_d(source_refs, ["src_1"]),
        stop_conditions=_d(stop_conditions, ["Allocation within bands"]),
        receipt_refs=_d(receipt_refs, ["r_1"]),
        related_option_set_id=_d(related_option_set_id, "os_1"),
        required_evaluations=_d(required_evaluations, ["ips_check"]),
    )


class TestPlanDraftEvaluator:
    def test_well_formed_plan_passes(self) -> None:
        status, findings = evaluate_plan_draft_receipt(plan_draft=_plan())
        assert status == "pass"
        assert findings == []

    def test_no_steps_is_block(self) -> None:
        status, findings = evaluate_plan_draft_receipt(
            plan_draft=_plan(steps=[]),
        )
        assert status == "block"
        assert any(f.code == "plan_no_steps" for f in findings)

    def test_action_language_is_block(self) -> None:
        status, findings = evaluate_plan_draft_receipt(
            plan_draft=_plan(steps=["Execute trade for SPY"]),
        )
        assert status == "block"
        assert any(f.code == "plan_action_language" for f in findings)

    def test_submit_language_is_block(self) -> None:
        status, findings = evaluate_plan_draft_receipt(
            plan_draft=_plan(steps=["Submit order to broker"]),
        )
        assert status == "block"
        codes = {f.code for f in findings}
        assert "plan_action_language" in codes

    def test_broker_language_is_block(self) -> None:
        status, _findings = evaluate_plan_draft_receipt(
            plan_draft=_plan(steps=["Contact broker for execution"]),
        )
        assert status == "block"

    def test_no_source_refs_is_warn(self) -> None:
        status, findings = evaluate_plan_draft_receipt(
            plan_draft=_plan(source_refs=[]),
        )
        assert status == "warn"
        assert any(f.code == "plan_no_source_refs" for f in findings)

    def test_no_stop_conditions_is_warn(self) -> None:
        status, findings = evaluate_plan_draft_receipt(
            plan_draft=_plan(stop_conditions=[]),
        )
        assert status == "warn"
        assert any(f.code == "plan_no_stop_conditions" for f in findings)

    def test_no_option_set_link_is_warn(self) -> None:
        plan = PlanDraftReceipt(
            receipt_id="r_test",
            plan_id="plan_test",
            objective="Test",
            steps=["Review"],
            source_refs=["s1"],
            stop_conditions=["sc1"],
            related_option_set_id=None,
            required_evaluations=["ips"],
            receipt_refs=["r1"],
        )
        status, findings = evaluate_plan_draft_receipt(plan_draft=plan)
        assert status == "warn"
        assert any(f.code == "plan_no_option_set_link" for f in findings)

    def test_no_required_evaluations_is_warn(self) -> None:
        status, findings = evaluate_plan_draft_receipt(
            plan_draft=_plan(required_evaluations=[]),
        )
        assert status == "warn"
        assert any(f.code == "plan_no_required_evaluations" for f in findings)

    def test_multiple_warns_still_warn(self) -> None:
        status, findings = evaluate_plan_draft_receipt(
            plan_draft=_plan(source_refs=[], stop_conditions=[],
                             related_option_set_id=None),
        )
        assert status == "warn"
        warn_codes = {f.code for f in findings if f.severity == "warn"}
        assert len(warn_codes) >= 2

    def test_block_supersedes_warn(self) -> None:
        status, findings = evaluate_plan_draft_receipt(
            plan_draft=_plan(steps=[], source_refs=[], stop_conditions=[]),
        )
        assert status == "block"
        codes = {f.code for f in findings}
        assert "plan_no_steps" in codes
        assert "plan_no_source_refs" in codes

    def test_deduplicates_action_tokens(self) -> None:
        status, findings = evaluate_plan_draft_receipt(
            plan_draft=_plan(steps=["Execute trade", "Execute again"]),
        )
        assert status == "block"
        action_finding = next(f for f in findings if f.code == "plan_action_language")
        assert action_finding.message.count("execute") == 1
