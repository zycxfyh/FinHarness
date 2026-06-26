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

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

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


def _clean(value: Any) -> Any:
    """Strip strings; treat a blank string as absent (``None``)."""
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return None
    return value


class DecisionScaffold(BaseModel):
    """Typed domain model for a governed proposal's decision scaffold.

    The four required fields make up the minimal rational brake (see module docstring);
    the six optional fields are unforced context. Unknown keys are dropped rather than
    rejected (``extra="ignore"``), matching the original dict helper. A blank/whitespace
    string is treated as absent: blank required fields fail validation (fail-closed),
    blank optional fields normalize to ``None`` and are excluded from the stored dict.
    """

    model_config = ConfigDict(extra="ignore")

    decision_intent: str
    thesis: str
    do_nothing_case: str
    risk_if_wrong: str

    counter_evidence: str | None = None
    alternatives: str | None = None
    position_impact: str | None = None
    tax_consideration: str | None = None
    review_date: str | None = None
    emotion: str | None = None

    @field_validator("*", mode="before")
    @classmethod
    def _blank_is_absent(cls, value: Any) -> Any:
        return _clean(value)

    def to_dict(self) -> dict[str, Any]:
        """Storage form: known non-blank fields only, in canonical field order."""
        return self.model_dump(exclude_none=True)


def normalize(scaffold: dict[str, Any] | None) -> dict[str, Any]:
    """Keep only known fields, drop blanks, in a deterministic key order.

    Lenient (partial-friendly) view used by the ``missing_required``/``is_complete``
    predicates: it does not require the four fields, so it can describe an
    incomplete scaffold. The strict, validated form is :class:`DecisionScaffold`.
    """
    data = scaffold or {}
    cleaned: dict[str, Any] = {}
    for field in ALL_FIELDS:
        value = _clean(data.get(field))
        if value is not None:
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

    Validation goes through :class:`DecisionScaffold`. Raises ``DecisionScaffoldError``
    listing the missing required field(s) if any of the four are absent or blank. A
    confirm-ready governed proposal cannot exist without them.
    """
    try:
        model = DecisionScaffold.model_validate(scaffold or {})
    except ValidationError as exc:
        missing = [
            field
            for field in REQUIRED_FIELDS
            if any(error["loc"][:1] == (field,) for error in exc.errors())
        ]
        if not missing:
            # A non-required validation error: surface it rather than mask it as
            # "missing required field(s)".
            raise
        raise DecisionScaffoldError(
            "governed proposal missing required decision-scaffold field(s): "
            + ", ".join(missing)
            + ". A confirm-ready proposal must state decision_intent, thesis, "
            "do_nothing_case, and risk_if_wrong."
        ) from exc
    return model.to_dict()
