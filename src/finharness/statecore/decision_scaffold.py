"""Decision scaffold — the minimal forcing gate for governed proposals.

A governed proposal awaiting human confirmation must state, in writing, the four
things that make up a minimal rational brake:

- ``decision_intent`` — what I want to do;
- ``thesis`` — why I think it is worth doing;
- ``do_nothing_case`` — what happens if I do nothing (so action is never the default);
- ``risk_if_wrong`` — what it costs if I am wrong.

If those four cannot be stated, the proposal must not become confirm-ready
(fail-closed). The remaining fields are optional context and are not gated. This is
deliberately the *minimal* set: not all-optional (decoration nobody fills), not
all-required (form fatigue that pollutes data with rushed entries).
"""

from __future__ import annotations

from typing import Any

REQUIRED_FIELDS: tuple[str, ...] = (
    "decision_intent",
    "thesis",
    "do_nothing_case",
    "risk_if_wrong",
)
OPTIONAL_FIELDS: tuple[str, ...] = (
    "counter_evidence",
    "alternatives",
    "position_impact",
    "tax_consideration",
    "review_date",
    "emotion",
)
ALL_FIELDS: tuple[str, ...] = REQUIRED_FIELDS + OPTIONAL_FIELDS


class DecisionScaffoldError(ValueError):
    """A governed proposal is missing a required decision-scaffold field."""


def normalize(scaffold: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only known fields, drop blanks, in a deterministic key order."""
    data = scaffold or {}
    cleaned: dict[str, Any] = {}
    for field in ALL_FIELDS:
        value = data.get(field)
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        cleaned[field] = value
    return cleaned


def missing_required(scaffold: dict[str, Any] | None) -> list[str]:
    """Required fields that are absent or blank, in canonical order."""
    cleaned = normalize(scaffold)
    return [field for field in REQUIRED_FIELDS if field not in cleaned]


def is_complete(scaffold: dict[str, Any] | None) -> bool:
    """True when all four required fields are present and non-blank."""
    return not missing_required(scaffold)


def ensure_forcing(scaffold: dict[str, Any] | None) -> dict[str, Any]:
    """Validate a governed proposal's scaffold and return it normalized; fail-closed.

    Raises ``DecisionScaffoldError`` listing the missing required field(s) if any of
    the four are absent or blank. A confirm-ready governed proposal cannot exist
    without them.
    """
    cleaned = normalize(scaffold)
    missing = [field for field in REQUIRED_FIELDS if field not in cleaned]
    if missing:
        raise DecisionScaffoldError(
            "governed proposal missing required decision-scaffold field(s): "
            + ", ".join(missing)
            + ". A confirm-ready proposal must state decision_intent, thesis, "
            "do_nothing_case, and risk_if_wrong."
        )
    return cleaned
