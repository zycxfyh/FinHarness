"""AuthorityTransitionRecord v0 — eligibility-only transition recording.

Agentic-space dimension: Authority Space.

Records the transition of a subject from one state to another based on
evaluation evidence. This is eligibility-only (eligible / not_eligible /
deferred), NOT execution authorization. Every record requires a human
attester, human reason, and at least one EvaluationReport reference.

Receipt-only. No StateCore table. No order/execution creation.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

NON_CLAIMS: tuple[str, ...] = (
    "AuthorityTransitionRecord records eligibility only, not execution authority.",
    "Human attester and explicit confirmation are required.",
    "Not execution authorization.",
    "Not investment advice.",
)


class AuthorityTransitionRecord(BaseModel):
    """Receipt-only record of an authority eligibility transition.

    authority_transition=True is the core semantic here — this IS an
    authority transition record. It does NOT grant execution authority;
    it records the structured eligibility decision that feeds into
    downstream governance.
    """

    model_config = ConfigDict(frozen=True)

    schema_version: str = "finharness.authority_transition.v1"
    transition_id: str
    subject_type: str
    subject_id: str
    from_state: str
    to_state: str
    eligibility: Literal["eligible", "not_eligible", "deferred"]
    evaluation_report_refs: list[str]
    human_attester: str
    human_reason: str
    explicit_confirmation: bool
    capital_mandate_id: str | None = None
    agent_authority_grant_id: str | None = None
    receipt_refs: list[str] = Field(default_factory=list)
    execution_allowed: bool = False
    authority_transition: bool = True


def _new_id(prefix: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}_{stamp}_{uuid4().hex[:8]}"


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _dedupe_refs(values: Sequence[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def record_authority_transition(
    *,
    subject_type: str,
    subject_id: str,
    from_state: str,
    to_state: str,
    eligibility: str,
    evaluation_report_refs: Sequence[str],
    human_attester: str,
    human_reason: str,
    explicit_confirmation: bool,
    receipt_root: str | Path,
    capital_mandate_id: str | None = None,
    agent_authority_grant_id: str | None = None,
) -> AuthorityTransitionRecord:
    """Record an eligibility-only authority transition.

    Requirements (enforced at call time):
    - human_attester must be non-blank
    - human_reason must be non-blank
    - explicit_confirmation must be True
    - evaluation_report_refs must contain at least one ref

    The record is written as a JSON file under receipt_root/authority-transitions/
    and returned as a frozen model.

    Raises ValueError if any requirement is violated.
    """
    if not human_attester.strip():
        raise ValueError("AuthorityTransitionRecord requires a non-blank human_attester")
    if not human_reason.strip():
        raise ValueError("AuthorityTransitionRecord requires a non-blank human_reason")
    if not explicit_confirmation:
        raise ValueError(
            "AuthorityTransitionRecord requires explicit_confirmation=True"
        )

    report_refs = _dedupe_refs(evaluation_report_refs)
    if not report_refs:
        raise ValueError(
            "AuthorityTransitionRecord requires at least one evaluation_report_ref"
        )

    valid_eligibility = {"eligible", "not_eligible", "deferred"}
    eligibility_value = str(eligibility).strip().lower()
    if eligibility_value not in valid_eligibility:
        raise ValueError(
            f"eligibility must be one of {sorted(valid_eligibility)}, "
            f"got {eligibility!r}"
        )

    transition_id = _new_id("at")

    record = AuthorityTransitionRecord(
        transition_id=transition_id,
        subject_type=subject_type.strip(),
        subject_id=subject_id.strip(),
        from_state=from_state.strip(),
        to_state=to_state.strip(),
        eligibility=cast(Literal["eligible", "not_eligible", "deferred"], eligibility_value),
        evaluation_report_refs=report_refs,
        human_attester=human_attester.strip(),
        human_reason=human_reason.strip(),
        explicit_confirmation=True,
        capital_mandate_id=capital_mandate_id.strip()
        if capital_mandate_id
        else None,
        agent_authority_grant_id=agent_authority_grant_id.strip()
        if agent_authority_grant_id
        else None,
        receipt_refs=[transition_id],
    )

    root = Path(receipt_root)
    root.mkdir(parents=True, exist_ok=True)
    target_dir = root / "authority-transitions"
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / f"{transition_id}.json"
    file_path.write_text(
        record.model_dump_json(indent=2, exclude_none=True),
        encoding="utf-8",
    )

    return record
