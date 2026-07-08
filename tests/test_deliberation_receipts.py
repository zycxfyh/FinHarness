"""Tests for DeliberationReceipts v0."""

# ruff: noqa: SIM117

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from pydantic import ValidationError

from finharness.deliberation_receipts import (
    OptionDraft,
    write_option_set_receipt,
    write_plan_draft_receipt,
)


class TestOptionSetReceipt:
    def test_writes_option_set_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = write_option_set_receipt(
                objective="Determine allocation approach for new capital",
                options=[
                    OptionDraft(
                        option_id="opt_1",
                        claim="Increase SPY allocation by 5%",
                        assumptions=["Fed holds rates steady"],
                        expected_outcomes=["Reduced cash drag"],
                        data_gaps=["Election outcome in Nov"],
                    ),
                    OptionDraft(
                        option_id="opt_2",
                        claim="Hold cash and wait",
                        assumptions=["Market overvalued"],
                        expected_outcomes=["Preserve dry powder"],
                    ),
                ],
                receipt_root=root,
                source_refs=["capital_summary"],
                receipt_refs=["r_ctx"],
            )
            assert receipt.receipt_id.startswith("os_")
            assert len(receipt.options) == 2
            assert receipt.options[0].claim == "Increase SPY allocation by 5%"
            assert receipt.execution_allowed is False
            assert receipt.authority_transition is False

            file_path = root / "deliberation" / f"{receipt.receipt_id}.json"
            assert file_path.exists()
            payload = json.loads(file_path.read_text())
            assert payload["execution_allowed"] is False

    def test_rejects_blank_objective(self) -> None:
        import pytest

        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="objective"):
                write_option_set_receipt(
                    objective="   ",
                    options=[OptionDraft(option_id="1", claim="test")],
                    receipt_root=Path(tmp),
                )

    def test_rejects_empty_options(self) -> None:
        import pytest

        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="option"):
                write_option_set_receipt(
                    objective="test",
                    options=[],
                    receipt_root=Path(tmp),
                )

    def test_model_is_frozen(self) -> None:
        import pytest

        with tempfile.TemporaryDirectory() as tmp:
            receipt = write_option_set_receipt(
                objective="test",
                options=[OptionDraft(option_id="1", claim="test")],
                receipt_root=Path(tmp),
            )
            with pytest.raises(ValidationError, match="frozen"):
                receipt.objective = "changed"  # type: ignore[misc]


class TestPlanDraftReceipt:
    def test_writes_plan_draft_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = write_plan_draft_receipt(
                objective="Execute rebalancing review",
                steps=[
                    "Review current allocation",
                    "Run IPS compliance check",
                    "Draft adjustment proposal",
                ],
                stop_conditions=[
                    "Allocation within mandate bands",
                    "Human approval received",
                ],
                required_evaluations=["ips_check", "risk_check"],
                related_option_set_id="os_set_001",
                receipt_root=root,
                source_refs=["capital_summary"],
                receipt_refs=["r_plan"],
            )
            assert receipt.receipt_id.startswith("pd_")
            assert len(receipt.steps) == 3
            assert len(receipt.stop_conditions) == 2
            assert receipt.related_option_set_id == "os_set_001"
            assert receipt.execution_allowed is False

            file_path = root / "deliberation" / f"{receipt.receipt_id}.json"
            assert file_path.exists()

    def test_rejects_blank_objective(self) -> None:
        import pytest

        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(ValueError, match="objective"):
                write_plan_draft_receipt(
                    objective="",
                    steps=["step 1"],
                    receipt_root=Path(tmp),
                )

    def test_rejects_empty_steps(self) -> None:
        import pytest

        with tempfile.TemporaryDirectory() as tmp, pytest.raises(ValueError, match="step"):
            write_plan_draft_receipt(
                objective="test",
                steps=[],
                receipt_root=Path(tmp),
            )

    def test_rejects_all_blank_steps(self) -> None:
        import pytest

        with tempfile.TemporaryDirectory() as tmp, pytest.raises(ValueError, match="step"):
            write_plan_draft_receipt(
                objective="test",
                steps=["   ", "\n", "\t"],
                receipt_root=Path(tmp),
            )

    def test_strips_whitespace_steps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = write_plan_draft_receipt(
                objective="test",
                steps=["  step 1  ", "", "  step 2  "],
                receipt_root=Path(tmp),
            )
            assert receipt.steps == ["step 1", "step 2"]

    def test_deduplicates_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            receipt = write_plan_draft_receipt(
                objective="test",
                steps=["s1"],
                receipt_root=Path(tmp),
                source_refs=["a", "a", "b"],
                receipt_refs=["r_a", "r_a"],
            )
            assert receipt.source_refs == ["a", "b"]
            assert receipt.receipt_refs == ["r_a"]

    def test_model_is_frozen(self) -> None:
        import pytest

        with tempfile.TemporaryDirectory() as tmp:
            receipt = write_plan_draft_receipt(
                objective="test",
                steps=["step 1"],
                receipt_root=Path(tmp),
            )
            with pytest.raises(ValidationError, match="frozen"):
                receipt.objective = "changed"  # type: ignore[misc]


class TestOptionDraftModel:
    def test_option_draft_fields(self) -> None:
        opt = OptionDraft(
            option_id="opt_x",
            claim="Reduce QQQ position",
            assumptions=["Tech sector overheated"],
            expected_outcomes=["Lower sector concentration"],
            data_gaps=["Timing of rotation"],
            evaluation_refs=["er_001"],
        )
        assert opt.option_id == "opt_x"
        assert len(opt.assumptions) == 1
        assert len(opt.expected_outcomes) == 1
        assert "er_001" in opt.evaluation_refs
