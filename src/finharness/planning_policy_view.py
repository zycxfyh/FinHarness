"""PlanningPolicyView v0 — read model from traceable RuleChange records.

Agentic-space dimension: Feedback Space.

Reads active, traceable RuleChange records from the filesystem and
exposes them as a planner-readable policy context. Active traceable
rules enter active_rules. Untraceable or reverted changes surface
as stale_or_untraceable_rules.

This is a read model only — no planner runtime, no auto-rule
application, no StateCore table.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from finharness.rule_change_ledger import RULE_CHANGE_STATE_ROOT, RuleChange, is_traceable

NON_CLAIMS: tuple[str, ...] = (
    "PlanningPolicyView is a read model, not a rule engine.",
    "Rules are advisory until a human promotes them into policy.",
    "Not execution authorization.",
    "Not investment advice.",
)


class PlanningPolicyRule(BaseModel):
    """One rule from the traceable RuleChange ledger."""

    model_config = ConfigDict(frozen=True)

    rule_change_id: str
    rule_target: str
    change_kind: str
    new_value: Any = None
    rationale: str = ""
    attester: str = ""
    receipt_refs: list[str] = Field(default_factory=list)
    traceable: bool = False


class PlanningPolicyView(BaseModel):
    """Read model of planner-relevant policy state."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "finharness.planning_policy_view.v1"
    active_rules: list[PlanningPolicyRule] = Field(default_factory=list)
    checklist_items: list[str] = Field(default_factory=list)
    thresholds: dict[str, Any] = Field(default_factory=dict)
    prompt_template_rules: list[str] = Field(default_factory=list)
    allowlists: dict[str, list[str]] = Field(default_factory=dict)
    stale_or_untraceable_rules: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    execution_allowed: bool = False
    authority_transition: bool = False


def _load_rule_change(file_path: Path) -> RuleChange | None:
    """Load a single RuleChange from a JSON file. Returns None if unreadable."""
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        return RuleChange.model_validate(payload)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def build_planning_policy_view(
    state_root: Path | None = None,
) -> PlanningPolicyView:
    """Build a PlanningPolicyView from the filesystem RuleChange ledger.

    Reads all JSON files under state_root (default: RULE_CHANGE_STATE_ROOT).
    Only active rules are included in active_rules.
    Rules without traceable lesson lineage or reverted rules go to
    stale_or_untraceable_rules.
    """
    root = state_root or RULE_CHANGE_STATE_ROOT
    if not root.exists():
        return PlanningPolicyView(
            source_refs=[],
            receipt_refs=[],
        )

    rules: list[PlanningPolicyRule] = []
    stale: list[str] = []

    for file_path in sorted(root.glob("*.json")):
        rule = _load_rule_change(file_path)
        if rule is None:
            continue

        traceable = is_traceable(rule)
        pr = PlanningPolicyRule(
            rule_change_id=rule.rule_change_id,
            rule_target=rule.rule_target,
            change_kind=rule.change_kind,
            new_value=rule.new_value,
            rationale=rule.rationale,
            attester=rule.attester,
            receipt_refs=rule.receipt_refs,
            traceable=traceable,
        )

        if rule.status == "reverted" or not traceable:
            stale.append(rule.rule_target)
            continue

        rules.append(pr)

    # Classify by change_kind
    checklist_items: list[str] = []
    thresholds: dict[str, Any] = {}
    prompt_template_rules: list[str] = []
    allowlists: dict[str, list[str]] = {}

    for pr in rules:
        if pr.change_kind == "checklist":
            checklist_items.append(str(pr.new_value))
        elif pr.change_kind == "threshold":
            thresholds[pr.rule_target] = pr.new_value
        elif pr.change_kind == "prompt_template":
            prompt_template_rules.append(str(pr.new_value))
        elif pr.change_kind == "allowlist":
            allowlists[pr.rule_target] = (
                list(pr.new_value) if isinstance(pr.new_value, list) else [str(pr.new_value)]
            )

    receipt_refs = _dedupe_refs(
        [ref for pr in rules for ref in pr.receipt_refs]
    )

    return PlanningPolicyView(
        active_rules=rules,
        checklist_items=_dedupe_refs(checklist_items),
        thresholds=thresholds,
        prompt_template_rules=_dedupe_refs(prompt_template_rules),
        allowlists=allowlists,
        stale_or_untraceable_rules=_dedupe_refs(stale),
        source_refs=[str(root)],
        receipt_refs=receipt_refs,
    )


def _dedupe_refs(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out
