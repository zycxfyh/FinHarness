"""Tests for CognitionPlaybook loader."""

from __future__ import annotations

from finharness.playbook_loader import (
    list_cognition_playbooks,
    load_cognition_playbook,
)


class TestPlaybookLoader:

    def test_list_returns_playbooks(self) -> None:
        summaries = list_cognition_playbooks()
        assert len(summaries) >= 1
        names = {s.name for s in summaries}
        assert "ips-drift-review" in names

    def test_summary_has_no_procedure(self) -> None:
        """Level 0 summaries do not include procedure body."""
        summaries = list_cognition_playbooks()
        for s in summaries:
            assert not hasattr(s, "procedure")

    def test_load_returns_full_playbook(self) -> None:
        pb = load_cognition_playbook("ips-drift-review")
        assert pb is not None
        assert pb.name == "ips-drift-review"
        assert "Procedure" in pb.procedure
        assert len(pb.required_context_packs) >= 1
        assert pb.execution_allowed is False

    def test_load_missing_returns_none(self) -> None:
        pb = load_cognition_playbook("nonexistent")
        assert pb is None

    def test_loaded_playbook_is_frozen(self) -> None:
        import pytest
        from pydantic import ValidationError

        pb = load_cognition_playbook("ips-drift-review")
        assert pb is not None
        with pytest.raises(ValidationError, match="frozen"):
            pb.name = "hijacked"  # type: ignore[misc]
