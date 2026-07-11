"""Canonical, version-bound planning decisions.

DecisionRecord is immutable.  Its current validity is derived from the latest
ProposalVersion rather than maintained by a second mutable status flag.  This
makes a material proposal revision invalidate an old decision immediately and
deterministically.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from finharness.delegated_review import (
    DecisionCase,
    Scenario,
    load_delegated_review_result,
)
from finharness.project_paths import display_path
from finharness.statecore.models import DecisionRecord, ReceiptIndex
from finharness.statecore.receipt_io import (
    atomic_write_json,
    remove_file_best_effort,
    resolve_under,
)
from finharness.statecore.store import StateCoreStoreError, write_records

DecisionRecordDecision = Literal["accepted_for_planning", "rejected", "deferred"]
ActorIdentityClass = Literal["human", "agent"]
DecisionValidityStatus = Literal["effective", "superseded", "missing"]


class DecisionValidity(BaseModel):
    model_config = ConfigDict(frozen=True)

    proposal_id: str
    current_proposal_version_id: str
    status: DecisionValidityStatus
    effective_decision_record_id: str | None = None
    superseded_decision_record_ids: tuple[str, ...] = ()
    reason: str
    execution_allowed: bool = False
    authority_transition: bool = False

    @model_validator(mode="after")
    def remain_read_only(self) -> DecisionValidity:
        if self.execution_allowed or self.authority_transition:
            raise ValueError("DecisionValidity is a read model, not effect authority")
        return self


@dataclass(frozen=True)
class DecisionRecordWrite:
    decision_record: DecisionRecord
    receipt_ref: str
    validity: DecisionValidity
    execution_allowed: bool = False


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _safe_id(value: str) -> str:
    return "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value)


def _record_payload(record: DecisionRecord) -> dict[str, object]:
    return {
        "schema": "finharness.decision_record.v1",
        "kind": "state_core_decision_record",
        "decision_record": record.model_dump(mode="json"),
        "governance": {
            "planning_decision_only": True,
            "execution_allowed": False,
            "authority_transition": False,
            "proposal_revision_invalidates": True,
        },
    }


def _validate_binding(
    *,
    decision_case: DecisionCase,
    scenario: Scenario | None,
    decision: DecisionRecordDecision,
) -> None:
    if decision_case.readiness != "ready_for_scenario":
        raise ValueError("decision case is not ready for a planning decision")
    if decision == "accepted_for_planning" and scenario is None:
        raise ValueError("accepted_for_planning requires a selected Scenario")
    if scenario is None:
        return
    if scenario.decision_case_id != decision_case.decision_case_id:
        raise ValueError("Scenario is bound to another DecisionCase")
    if scenario.decision_case_version_id != decision_case.case_version_id:
        raise ValueError("Scenario is stale for the current DecisionCase version")
    if scenario.proposal_version_id != decision_case.proposal_version.proposal_version_id:
        raise ValueError("Scenario is stale for the current ProposalVersion")
    if scenario.data_gaps:
        raise ValueError("Scenario with data gaps cannot support a decision of record")


def _validate_agent_review(
    *,
    actor_identity_class: ActorIdentityClass,
    delegated_review_ref: str | None,
    decision_case: DecisionCase,
    scenario: Scenario | None,
    decision: DecisionRecordDecision,
    receipt_root: str | Path,
) -> None:
    if actor_identity_class == "human":
        return
    if not delegated_review_ref:
        raise ValueError("agent DecisionRecord requires persisted delegated-review evidence")
    review_id = Path(delegated_review_ref).stem
    result = load_delegated_review_result(review_id, receipt_root=receipt_root)
    if not result.effective_planning_decision or result.disposition != "effective":
        raise ValueError("agent DecisionRecord requires an effective delegated review")
    expected = {
        "accepted_for_planning": "accept_for_planning",
        "rejected": "reject",
        "deferred": "defer",
    }[decision]
    if result.proposed_decision != expected:
        raise ValueError("delegated review decision does not match DecisionRecord")
    if result.decision_case_version_id != decision_case.case_version_id:
        raise ValueError("delegated review is stale for the DecisionCase version")
    if result.proposal_version_id != decision_case.proposal_version.proposal_version_id:
        raise ValueError("delegated review is stale for the ProposalVersion")
    if scenario is not None and result.selected_scenario_id != scenario.scenario_id:
        raise ValueError("delegated review selected a different Scenario")


def record_planning_decision(
    *,
    decision_case: DecisionCase,
    scenario: Scenario | None,
    decision: DecisionRecordDecision,
    reason: str,
    actor_id: str,
    actor_identity_class: ActorIdentityClass,
    engine: Engine,
    receipt_root: str | Path,
    delegated_review_ref: str | None = None,
    next_review_condition: str | None = None,
    source_refs: tuple[str, ...] = (),
    created_at_utc: str | None = None,
) -> DecisionRecordWrite:
    """Append one immutable decision for the exact current proposal version."""
    if not reason.strip() or not actor_id.strip():
        raise ValueError("DecisionRecord requires actor identity and written reason")
    if decision == "deferred" and not (next_review_condition or "").strip():
        raise ValueError("deferred DecisionRecord requires a next review condition")
    _validate_binding(decision_case=decision_case, scenario=scenario, decision=decision)
    _validate_agent_review(
        actor_identity_class=actor_identity_class,
        delegated_review_ref=delegated_review_ref,
        decision_case=decision_case,
        scenario=scenario,
        decision=decision,
        receipt_root=receipt_root,
    )

    version = decision_case.proposal_version
    with Session(engine) as session:
        existing = session.exec(
            select(DecisionRecord).where(
                DecisionRecord.proposal_id == version.proposal_id,
                DecisionRecord.proposal_version_id == version.proposal_version_id,
            )
        ).first()
    if existing is not None:
        raise ValueError(
            f"proposal version already has DecisionRecord {existing.decision_record_id}"
        )

    created_at = created_at_utc or _now_utc()
    fingerprint = hashlib.sha256(
        f"{version.proposal_id}:{version.proposal_version_id}:{decision}:{actor_id}".encode()
    ).hexdigest()[:16]
    record_id = _safe_id(f"decision_{fingerprint}_{uuid4().hex[:8]}")
    receipt_id = f"receipt_{record_id}"
    receipt_path = resolve_under(receipt_root, "decision-records", f"{receipt_id}.json")
    receipt_ref = display_path(receipt_path)
    refs = list(
        dict.fromkeys(
            (
                version.proposal_receipt_ref,
                decision_case.case_version_id,
                *([scenario.scenario_version_id] if scenario else []),
                *([delegated_review_ref] if delegated_review_ref else []),
                *source_refs,
            )
        )
    )
    record = DecisionRecord(
        decision_record_id=record_id,
        proposal_id=version.proposal_id,
        proposal_version_id=version.proposal_version_id,
        proposal_receipt_ref=version.proposal_receipt_ref,
        proposal_content_hash=version.proposal_content_hash,
        decision_case_version_id=decision_case.case_version_id,
        scenario_version_id=scenario.scenario_version_id if scenario else None,
        decision=decision,
        reason=reason.strip(),
        actor_id=actor_id.strip(),
        actor_identity_class=actor_identity_class,
        delegated_review_ref=delegated_review_ref,
        next_review_condition=(next_review_condition or "").strip() or None,
        source_refs=refs,
        execution_allowed=False,
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    atomic_write_json(receipt_path, _record_payload(record))
    index = ReceiptIndex(
        receipt_id=receipt_id,
        kind="state_core_decision_record",
        path=receipt_ref,
        created_at_utc=created_at,
        source_refs=[receipt_ref],
        refs=[record_id, version.proposal_id, version.proposal_version_id, *refs],
    )
    try:
        write_records([record, index], engine=engine)
    except (StateCoreStoreError, IntegrityError):
        remove_file_best_effort(receipt_path)
        raise
    validity = resolve_decision_validity(decision_case=decision_case, engine=engine)
    return DecisionRecordWrite(
        decision_record=record,
        receipt_ref=receipt_ref,
        validity=validity,
    )


def resolve_decision_validity(*, decision_case: DecisionCase, engine: Engine) -> DecisionValidity:
    """Resolve current decision validity from immutable version bindings."""
    version = decision_case.proposal_version
    with Session(engine) as session:
        records = tuple(
            session.exec(
                select(DecisionRecord).where(DecisionRecord.proposal_id == version.proposal_id)
            ).all()
        )
    effective = tuple(
        record for record in records if record.proposal_version_id == version.proposal_version_id
    )
    superseded = tuple(
        sorted(
            record.decision_record_id
            for record in records
            if record.proposal_version_id != version.proposal_version_id
        )
    )
    if len(effective) > 1:
        raise StateCoreStoreError("conflicting DecisionRecords bind the current ProposalVersion")
    if effective:
        return DecisionValidity(
            proposal_id=version.proposal_id,
            current_proposal_version_id=version.proposal_version_id,
            status="effective",
            effective_decision_record_id=effective[0].decision_record_id,
            superseded_decision_record_ids=superseded,
            reason="DecisionRecord binds the current ProposalVersion.",
        )
    if superseded:
        return DecisionValidity(
            proposal_id=version.proposal_id,
            current_proposal_version_id=version.proposal_version_id,
            status="superseded",
            superseded_decision_record_ids=superseded,
            reason="Material proposal revision invalidated prior DecisionRecord bindings.",
        )
    return DecisionValidity(
        proposal_id=version.proposal_id,
        current_proposal_version_id=version.proposal_version_id,
        status="missing",
        reason="Current ProposalVersion has no DecisionRecord.",
    )
