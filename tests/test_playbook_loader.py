"""Tests for CognitionPlaybook loader v0.1.

v0.1 (PR #213): Real YAML parser replaces hand-rolled parser.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from finharness.playbook_loader import (
    PlaybookFrontmatterError,
    _parse_frontmatter,
    _validate_frontmatter,
    list_cognition_playbooks,
    load_cognition_playbook,
    parse_frontmatter_text,
)


class TestPlaybookLoader:

    def test_list_returns_playbooks(self) -> None:
        summaries = list_cognition_playbooks()
        assert len(summaries) >= 1
        names = {s.name for s in summaries}
        assert "ips-drift-review" in names

    def test_summary_has_no_procedure(self) -> None:
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
        pb = load_cognition_playbook("ips-drift-review")
        assert pb is not None
        with pytest.raises(ValidationError, match="frozen"):
            pb.name = "hijacked"  # type: ignore[misc]

    # ── YAML parser (new in v0.1) ─────────────────────────────────

    def test_multi_line_yaml_lists_parsed_correctly(self) -> None:
        """ips-drift-review has multi-line YAML lists — must parse correctly."""
        pb = load_cognition_playbook("ips-drift-review")
        assert pb is not None
        # These were the bug: multi-line lists weren't parsed
        assert pb.required_context_packs == ["current_ips", "capital_summary"]
        assert pb.recommended_evaluators == ["plan_draft_evaluator"]
        assert pb.side_effects == ["read"]

    def test_yaml_execution_allowed_parsed_as_bool(self) -> None:
        pb = load_cognition_playbook("ips-drift-review")
        assert pb is not None
        assert pb.execution_allowed is False

    def test_frontmatter_validation_strict_fails_on_bad_data(self) -> None:
        """Strict mode raises PlaybookFrontmatterError on missing required fields."""
        bad_fm: dict[str, object] = {"name": "test"}
        with pytest.raises(PlaybookFrontmatterError, match="validation failed"):
            _validate_frontmatter(bad_fm, strict=True)

    def test_frontmatter_validation_nonstrict_uses_defaults(self) -> None:
        """Non-strict mode fills defaults for missing fields."""
        bad_fm: dict[str, object] = {"name": "test"}
        result = _validate_frontmatter(bad_fm, strict=False)
        assert result.name == "test"

    def test_parse_real_yaml_frontmatter(self) -> None:
        """Real playbook frontmatter with multi-line lists parses correctly."""
        text = """---
name: test-pb
version: "0.1.0"
space: Eval
description: Test playbook
when_to_use: When testing
required_context_packs:
  - ctx_a
  - ctx_b
recommended_evaluators:
  - eval_x
side_effects:
  - read
execution_allowed: false
---
## Procedure
1. Do something
"""
        fm = _parse_frontmatter(text)
        assert fm["name"] == "test-pb"
        assert fm["required_context_packs"] == ["ctx_a", "ctx_b"]
        assert fm["recommended_evaluators"] == ["eval_x"]
        assert fm["side_effects"] == ["read"]
        assert fm["execution_allowed"] is False

    def test_parse_empty_text(self) -> None:
        assert _parse_frontmatter("") == {}

    def test_parse_no_frontmatter(self) -> None:
        assert _parse_frontmatter("# just markdown") == {}

    def test_parse_invalid_yaml(self) -> None:
        # Invalid YAML returns empty dict (graceful fallback)
        fm = _parse_frontmatter("---\n: bad: yaml: here\n---")
        assert fm == {}

    def test_parse_frontmatter_text_public_api(self) -> None:
        """parse_frontmatter_text returns validated model or None."""
        text = """---
name: test-pb
version: "0.1.0"
space: Eval
description: Test
when_to_use: When testing
---
"""
        result = parse_frontmatter_text(text)
        assert result is not None
        assert result.name == "test-pb"
        assert result.version == "0.1.0"

    def test_parse_frontmatter_text_bad_input_returns_none(self) -> None:
        assert parse_frontmatter_text("") is None

    def test_frontmatter_model_is_frozen(self) -> None:
        from finharness.playbook_loader import CognitionPlaybookFrontmatter

        fm = CognitionPlaybookFrontmatter(
            name="t", version="1.0", space="s", description="d", when_to_use="w",
        )
        with pytest.raises(ValidationError, match="frozen"):
            fm.name = "x"  # type: ignore[misc]

    def test_frontmatter_defaults(self) -> None:
        from finharness.playbook_loader import CognitionPlaybookFrontmatter

        fm = CognitionPlaybookFrontmatter(
            name="t", version="1.0", space="s", description="d", when_to_use="w",
        )
        assert fm.required_context_packs == []
        assert fm.recommended_evaluators == []
        assert fm.side_effects == []
        assert fm.execution_allowed is False

    def test_str_list_helper(self) -> None:
        from finharness.playbook_loader import _str_list

        assert _str_list({}, "x") == []
        assert _str_list({"x": ["a", "b"]}, "x") == ["a", "b"]
        assert _str_list({"x": "single"}, "x") == ["single"]
