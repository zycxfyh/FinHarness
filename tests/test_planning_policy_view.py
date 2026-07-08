"""Tests for PlanningPolicyView v0."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from finharness.planning_policy_view import (
    PlanningPolicyView,
    build_planning_policy_view,
)


def _write_rule_change(
    root: Path,
    rule_change_id: str,
    rule_target: str,
    change_kind: str,
    new_value: object,
    rationale: str = "test rationale",
    attester: str = "test_ops",
    lesson_draft_id: str | None = "lesson_001",
    lesson_doc_ref: str | None = "docs/lessons/lesson_001.md",
    receipt_refs: list[str] | None = None,
    status: str = "active",
) -> Path:
    refs = receipt_refs if receipt_refs is not None else ["r_test"]
    payload = {
        "schema_version": "finharness.rule_change.v1",
        "rule_change_id": rule_change_id,
        "created_at_utc": "2026-07-08T00:00:00Z",
        "rule_target": rule_target,
        "change_kind": change_kind,
        "new_value": new_value,
        "rationale": rationale,
        "attester": attester,
        "lesson_draft_id": lesson_draft_id,
        "lesson_doc_ref": lesson_doc_ref,
        "receipt_refs": refs,
        "status": status,
    }
    root.mkdir(parents=True, exist_ok=True)
    file_path = root / f"{rule_change_id}.json"
    file_path.write_text(json.dumps(payload), encoding="utf-8")
    return file_path


class TestPlanningPolicyView:
    """Unit tests for PlanningPolicyView read model."""

    def test_builds_view_from_rule_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_rule_change(
                root, "rc_001", "guard.max_position_pct",
                "threshold", 25.0, receipt_refs=["r_rc1"],
            )
            _write_rule_change(
                root, "rc_002", "checklist.verify_source_refs",
                "checklist", "Always verify source refs exist",
                receipt_refs=["r_rc2"],
            )
            _write_rule_change(
                root, "rc_003", "prompt.risk_disclosure",
                "prompt_template", "Disclose: {{data_source}}",
                receipt_refs=["r_rc3"],
            )

            view = build_planning_policy_view(state_root=root)
            assert len(view.active_rules) == 3
            assert len(view.checklist_items) == 1
            assert "Always verify source refs exist" in view.checklist_items
            assert view.thresholds["guard.max_position_pct"] == 25.0
            assert "Disclose: {{data_source}}" in view.prompt_template_rules

    def test_excludes_reverted_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_rule_change(root, "rc_active", "guard.drawdown", "threshold", 10.0)
            _write_rule_change(
                root, "rc_reverted", "guard.leverage", "threshold", 3.0,
                status="reverted",
            )
            view = build_planning_policy_view(state_root=root)
            assert len(view.active_rules) == 1
            assert "guard.leverage" in view.stale_or_untraceable_rules

    def test_excludes_untraceable_rules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_rule_change(
                root, "rc_traceable", "guard.stop_loss", "threshold", 5.0,
                lesson_draft_id="lesson_001",
            )
            _write_rule_change(
                root, "rc_untraceable", "guard.unknown_rule", "threshold", 99.0,
                lesson_draft_id=None,
            )
            view = build_planning_policy_view(state_root=root)
            assert len(view.active_rules) == 1
            active_targets = [r.rule_target for r in view.active_rules]
            assert "guard.stop_loss" in active_targets
            assert "guard.unknown_rule" in view.stale_or_untraceable_rules

    def test_empty_root_returns_empty_view(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            view = build_planning_policy_view(state_root=Path(tmp))
            assert view.active_rules == []
            assert view.checklist_items == []
            assert view.thresholds == {}
            assert view.execution_allowed is False

    def test_allowlists_are_captured(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_rule_change(
                root, "rc_al", "allowlist.allowed_symbols",
                "allowlist", ["SPY", "QQQ", "AAPL"],
            )
            view = build_planning_policy_view(state_root=root)
            assert "allowlist.allowed_symbols" in view.allowlists
            assert view.allowlists["allowlist.allowed_symbols"] == ["SPY", "QQQ", "AAPL"]

    def test_skips_unreadable_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "corrupt.json").write_text("not json", encoding="utf-8")
            _write_rule_change(root, "rc_ok", "guard.test", "threshold", 1.0)
            view = build_planning_policy_view(state_root=root)
            assert len(view.active_rules) == 1

    def test_view_is_frozen(self) -> None:
        import pytest
        from pydantic import ValidationError

        view = PlanningPolicyView()
        with pytest.raises(ValidationError, match="frozen"):
            view.active_rules = []  # type: ignore[misc]

    def test_not_execution_authority(self) -> None:
        view = PlanningPolicyView()
        assert view.execution_allowed is False
        assert view.authority_transition is False

    def test_incomplete_rule_change_does_not_enter_active_rules(self) -> None:
        """A RuleChange missing lesson_doc_ref/receipt_refs/rationale/attester
        is NOT traceable per rule_change_ledger.is_traceable()."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Has lesson_draft_id but missing lesson_doc_ref → not traceable
            payload = {
                "schema_version": "finharness.rule_change.v1",
                "rule_change_id": "rc_incomplete",
                "created_at_utc": "2026-07-08T00:00:00Z",
                "rule_target": "guard.test",
                "change_kind": "threshold",
                "new_value": 5.0,
                "rationale": "",
                "attester": "",
                "lesson_draft_id": "lesson_001",
                "lesson_doc_ref": None,
                "receipt_refs": [],
                "status": "active",
            }
            root.mkdir(parents=True, exist_ok=True)
            (root / "rc_incomplete.json").write_text(json.dumps(payload), encoding="utf-8")
            view = build_planning_policy_view(state_root=root)
            assert len(view.active_rules) == 0
            assert "guard.test" in view.stale_or_untraceable_rules
