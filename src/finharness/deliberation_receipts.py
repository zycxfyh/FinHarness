"""DeliberationReceipts v0 — OptionSet and PlanDraft receipt-only artifacts.

Agentic-space dimension: Deliberation Space.

Structured thinking artifacts for agent deliberation. Receipt-only —
no StateCore tables, no order generation, no execution connection.
These are first-class reasoning artifacts, not disguised business objects.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

NON_CLAIMS: tuple[str, ...] = (
    "OptionSet and PlanDraft are deliberation artifacts, not execution decisions.",
    "Human review is required before any option is acted upon.",
    "Not execution authorization.",
    "Not investment advice.",
)


class OptionDraft(BaseModel):
    """One option within an OptionSet — a claim with assumptions and gaps."""

    model_config = ConfigDict(frozen=True)

    option_id: str
    claim: str
    assumptions: list[str] = Field(default_factory=list)
    expected_outcomes: list[str] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    evaluation_refs: list[str] = Field(default_factory=list)


class OptionSetReceipt(BaseModel):
    """Receipt-only record of a set of deliberated options."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "finharness.option_set_receipt.v1"
    receipt_id: str
    option_set_id: str
    objective: str
    options: list[OptionDraft] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    execution_allowed: bool = False
    authority_transition: bool = False


class PlanDraftReceipt(BaseModel):
    """Receipt-only record of a deliberated plan."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "finharness.plan_draft_receipt.v1"
    receipt_id: str
    plan_id: str
    objective: str
    steps: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)
    required_evaluations: list[str] = Field(default_factory=list)
    related_option_set_id: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    receipt_refs: list[str] = Field(default_factory=list)
    execution_allowed: bool = False
    authority_transition: bool = False


def _new_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid4().hex[:8]}"


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


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


def write_option_set_receipt(
    *,
    objective: str,
    options: list[OptionDraft],
    receipt_root: str | Path,
    source_refs: list[str] | None = None,
    receipt_refs: list[str] | None = None,
) -> OptionSetReceipt:
    """Write a receipt-only OptionSet to the receipt root.

    Raises ValueError if objective is blank or options is empty.
    """
    if not objective.strip():
        raise ValueError("OptionSetReceipt requires a non-blank objective")
    if not options:
        raise ValueError("OptionSetReceipt requires at least one option")

    receipt_id = _new_id("os")
    option_set_id = _new_id("os_set")

    receipt = OptionSetReceipt(
        receipt_id=receipt_id,
        option_set_id=option_set_id,
        objective=objective.strip(),
        options=list(options),
        source_refs=_dedupe_refs(source_refs or []),
        receipt_refs=_dedupe_refs(receipt_refs or []),
    )

    root = Path(receipt_root)
    root.mkdir(parents=True, exist_ok=True)
    target_dir = root / "deliberation"
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / f"{receipt_id}.json"
    file_path.write_text(
        receipt.model_dump_json(indent=2, exclude_none=True),
        encoding="utf-8",
    )

    return receipt


def write_plan_draft_receipt(
    *,
    objective: str,
    steps: list[str],
    receipt_root: str | Path,
    stop_conditions: list[str] | None = None,
    required_evaluations: list[str] | None = None,
    related_option_set_id: str | None = None,
    source_refs: list[str] | None = None,
    receipt_refs: list[str] | None = None,
) -> PlanDraftReceipt:
    """Write a receipt-only PlanDraft to the receipt root.

    Raises ValueError if objective is blank or steps is empty.
    """
    if not objective.strip():
        raise ValueError("PlanDraftReceipt requires a non-blank objective")
    if not steps:
        raise ValueError("PlanDraftReceipt requires at least one step")

    receipt_id = _new_id("pd")
    plan_id = _new_id("plan")

    receipt = PlanDraftReceipt(
        receipt_id=receipt_id,
        plan_id=plan_id,
        objective=objective.strip(),
        steps=[s.strip() for s in steps if s.strip()],
        stop_conditions=_dedupe_refs(stop_conditions or []),
        required_evaluations=_dedupe_refs(required_evaluations or []),
        related_option_set_id=related_option_set_id.strip()
        if related_option_set_id
        else None,
        source_refs=_dedupe_refs(source_refs or []),
        receipt_refs=_dedupe_refs(receipt_refs or []),
    )

    root = Path(receipt_root)
    root.mkdir(parents=True, exist_ok=True)
    target_dir = root / "deliberation"
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / f"{receipt_id}.json"
    file_path.write_text(
        receipt.model_dump_json(indent=2, exclude_none=True),
        encoding="utf-8",
    )

    return receipt
