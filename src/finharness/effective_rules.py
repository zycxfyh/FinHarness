"""B4 enforcement: resolve effective guard thresholds from the rule-change ledger.

B4 is a project term anchored in docs/reference/glossary.md.

B4 v1 (rule_change_ledger.py) proved that rule changes carry lineage. This turns
lineage into enforcement: the guard's effective thresholds are the defaults
overlaid with any active threshold-kind rule change targeting `guard.<field>`,
plus provenance pointing back to the rule change (and through it, the lesson and
receipts). A promoted change now actually changes behavior, and the effective
value is traceable — not a hand-edited constant.

Only `change_kind == "threshold"`, `status == "active"`, and `rule_target`
of the form `guard.<field>` are applied; the latest change per field wins.
Unknown fields or uncoercible values are ignored (fail-safe: fall back to the
default), and an ignored change is reported so a human can see it did nothing.
"""

from __future__ import annotations

from dataclasses import fields, replace
from pathlib import Path
from typing import Any

from finharness.rule_change_ledger import is_traceable, load_rule_changes
from finharness.trading_guard import GuardThresholds

GUARD_TARGET_PREFIX = "guard."

_INT_FIELDS = {
    "hard_stop_consecutive_losses",
    "caution_consecutive_losses",
    "min_minutes_between_trades_after_loss",
}


def _coerce(field_name: str, value: Any) -> float | int | None:
    try:
        return int(value) if field_name in _INT_FIELDS else float(value)
    except (TypeError, ValueError):
        return None


def resolve_guard_thresholds(
    *,
    base: GuardThresholds | None = None,
    ledger_root: Path | None = None,
) -> tuple[GuardThresholds, dict[str, str], list[str]]:
    """Return (effective thresholds, provenance, ignored).

    provenance maps each overridden field to the rule_change_id that set it.
    ignored lists rule_change_ids that targeted the guard but could not be
    applied (unknown field, bad value, or untraceable) — they had no effect.
    """
    base = base or GuardThresholds()
    valid_fields = {f.name for f in fields(GuardThresholds)}
    overrides: dict[str, Any] = {}
    provenance: dict[str, str] = {}
    ignored: list[str] = []

    for change in load_rule_changes(ledger_root):
        if change.change_kind != "threshold" or change.status != "active":
            continue
        if not change.rule_target.startswith(GUARD_TARGET_PREFIX):
            continue
        field_name = change.rule_target[len(GUARD_TARGET_PREFIX) :]
        coerced = _coerce(field_name, change.new_value)
        if field_name not in valid_fields or coerced is None or not is_traceable(change):
            ignored.append(change.rule_change_id)
            continue
        # latest change per field wins (load_rule_changes is sorted by id/time)
        overrides[field_name] = coerced
        provenance[field_name] = change.rule_change_id

    effective = replace(base, **overrides) if overrides else base
    return effective, provenance, ignored
