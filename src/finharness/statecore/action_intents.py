"""Governed ActionIntentCandidate writes.

Action intents are the first typed bridge from reviewed proposals toward future
capital action workflows. They are candidate-only: no orders, broker execution,
approval, or authority transition.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Engine
from sqlmodel import Session

from finharness.statecore.models import (
    ACTION_INTENT_NEXT_STEPS,
    ACTION_INTENT_TYPES,
    ActionIntent,
    Proposal,
    ReceiptIndex,
)
from finharness.statecore.proposals import (
    _display_path,
    _now_utc,
    _receipt_index,
    _revision_stamp,
    _safe_id,
)
from finharness.statecore.receipt_io import (
    atomic_write_json,
    remove_file_best_effort,
    resolve_under,
)
from finharness.statecore.store import StateCoreStoreError, write_records

ActionIntentType = Literal[
    "reduce_exposure",
    "increase_exposure",
    "rebalance",
    "raise_cash",
    "defer_action",
    "hedge_review",
    "watchlist",
    "request_more_evidence",
]
ActionIntentCreator = Literal["agent", "human", "system"]
ActionIntentNextStep = Literal["action_preflight", "simulation", "human_review", "discard"]

ACTION_INTENT_NON_CLAIMS: tuple[str, ...] = (
    "ActionIntentCandidate is not an order.",
    "ActionIntentCandidate is not broker execution.",
    "ActionIntentCandidate is not investment advice.",
    "ActionIntentCandidate does not authorize trading.",
    "ActionIntentCandidate must pass future action preflight or simulation before any "
    "order ticket.",
)

FORBIDDEN_ACTION_INTENT_KEYS: frozenset[str] = frozenset(
    {
        "account_number",
        "approval_status",
        "authority_transition",
        "broker",
        "brokerage",
        "execute",
        "execution_allowed",
        "limit_price",
        "market_order",
        "order",
        "order_id",
        "order_ticket",
        "quantity",
        "side",
        "trade",
        "transfer",
    }
)


class ActionIntentValidationError(ValueError):
    """Raised when an action intent would cross its candidate-only boundary."""


class ActionIntentStaleProposalError(ValueError):
    """Raised when the caller's expected proposal receipt is stale."""


@dataclass(frozen=True)
class GovernedActionIntentWrite:
    action_intent: ActionIntent
    receipt_ref: str
    execution_allowed: bool = False
    authority_transition: bool = False


def _dedupe_text(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        clean = str(value).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        result.append(clean)
    return result


def _normalized_marker_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def _forbidden_marker(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).strip()
            if _normalized_marker_key(key_text) in FORBIDDEN_ACTION_INTENT_KEYS:
                return key_text
            marker = _forbidden_marker(child)
            if marker is not None:
                return marker
    if isinstance(value, list):
        for child in value:
            marker = _forbidden_marker(child)
            if marker is not None:
                return marker
    return None


def forbidden_action_intent_marker(value: Any) -> str | None:
    """Return the first order/broker/authority marker found in a candidate payload."""

    return _forbidden_marker(value)


def _require_candidate_payload_boundary(
    *,
    target_scope: dict[str, Any],
    constraints: dict[str, Any],
    trigger_context: dict[str, Any],
) -> None:
    for name, value in (
        ("target_scope", target_scope),
        ("constraints", constraints),
        ("trigger_context", trigger_context),
    ):
        marker = _forbidden_marker(value)
        if marker is not None:
            raise ActionIntentValidationError(
                f"{name} cannot carry order/broker/authority field {marker!r}"
            )


def _receipt_payload(action_intent: ActionIntent, proposal: Proposal) -> dict[str, Any]:
    return {
        "receipt_id": f"receipt_{action_intent.action_intent_id}",
        "kind": "state_core_action_intent_candidate",
        "created_at_utc": action_intent.created_at_utc,
        "proposal_id": proposal.proposal_id,
        "source_proposal_receipt_ref": action_intent.source_proposal_receipt_ref,
        "source_revision_receipt_ref": action_intent.source_revision_receipt_ref,
        "action_intent": action_intent.model_dump(mode="json"),
        "governance": {
            "execution_allowed": False,
            "authority_transition": False,
            "candidate_only": True,
            "not_order": True,
            "not_broker_execution": True,
            "not_execution_authorization": True,
            "not_investment_advice": True,
            "non_claims": list(ACTION_INTENT_NON_CLAIMS),
        },
    }


def create_governed_action_intent(
    *,
    proposal_id: str,
    expected_proposal_receipt_ref: str,
    action_type: ActionIntentType,
    intent_summary: str,
    rationale: str,
    target_scope: dict[str, Any],
    constraints: dict[str, Any] | None = None,
    trigger_context: dict[str, Any] | None = None,
    required_preconditions: list[str] | None = None,
    expected_next_step: ActionIntentNextStep = "action_preflight",
    created_by: ActionIntentCreator = "human",
    active_profile: str | None = None,
    source_refs: list[str] | None = None,
    source_revision_receipt_ref: str | None = None,
    engine: Engine,
    receipt_root: str | Path,
) -> GovernedActionIntentWrite:
    """Persist a proposal-bound ActionIntentCandidate with a receipt."""
    if created_by not in {"agent", "human", "system"}:
        raise ActionIntentValidationError(
            "action intent creator must be agent, human, or system"
        )
    if action_type not in ACTION_INTENT_TYPES:
        raise ActionIntentValidationError(f"unknown action intent type: {action_type}")
    if expected_next_step not in ACTION_INTENT_NEXT_STEPS:
        raise ActionIntentValidationError(f"unknown action intent next step: {expected_next_step}")
    if not intent_summary.strip() or not rationale.strip():
        raise ActionIntentValidationError("action intent requires summary and rationale")
    final_source_refs = _dedupe_text(list(source_refs or []))
    if not final_source_refs:
        raise ActionIntentValidationError("action intent requires at least one source_ref")
    final_constraints = constraints or {}
    final_trigger_context = trigger_context or {}
    _require_candidate_payload_boundary(
        target_scope=target_scope,
        constraints=final_constraints,
        trigger_context=final_trigger_context,
    )

    with Session(engine) as session:
        proposal = session.get(Proposal, proposal_id)
    if proposal is None:
        raise KeyError(proposal_id)
    if not proposal.receipt_ref:
        raise ActionIntentValidationError("proposal has no current receipt_ref")
    expected_ref = expected_proposal_receipt_ref.strip()
    if proposal.receipt_ref != expected_ref:
        raise ActionIntentStaleProposalError(
            "proposal receipt ref does not match expected_proposal_receipt_ref"
        )

    created_at = _now_utc()
    action_intent_id = _safe_id(f"action_intent_{_revision_stamp()}_{uuid4().hex[:8]}")
    receipt_id = f"receipt_{action_intent_id}"
    receipt_path = resolve_under(receipt_root, "action-intents", f"{receipt_id}.json")
    receipt_ref = _display_path(receipt_path)
    final_receipt_refs = _dedupe_text(
        [
            proposal.receipt_ref,
            *([source_revision_receipt_ref] if source_revision_receipt_ref else []),
            *final_source_refs,
            receipt_ref,
        ]
    )
    action_intent = ActionIntent(
        action_intent_id=action_intent_id,
        proposal_id=proposal.proposal_id,
        source_proposal_receipt_ref=proposal.receipt_ref,
        source_revision_receipt_ref=source_revision_receipt_ref,
        created_by=created_by,
        active_profile=active_profile,
        action_type=action_type,
        target_scope=target_scope,
        intent_summary=intent_summary.strip(),
        rationale=rationale.strip(),
        constraints=final_constraints,
        trigger_context=final_trigger_context,
        required_preconditions=_dedupe_text(list(required_preconditions or [])),
        expected_next_step=expected_next_step,
        source_refs=final_source_refs,
        receipt_refs=final_receipt_refs,
        non_claims=list(ACTION_INTENT_NON_CLAIMS),
        receipt_ref=receipt_ref,
        execution_allowed=False,
        authority_transition=False,
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    atomic_write_json(receipt_path, _receipt_payload(action_intent, proposal))
    receipt_index: ReceiptIndex = _receipt_index(
        receipt_id=receipt_id,
        kind="state_core_action_intent_candidate",
        path=receipt_path,
        created_at_utc=created_at,
        refs=_dedupe_text(
            [
                proposal.proposal_id,
                proposal.receipt_ref,
                action_intent.action_intent_id,
                *action_intent.source_refs,
            ]
        ),
    )
    try:
        write_records([action_intent, receipt_index], engine=engine)
    except StateCoreStoreError:
        remove_file_best_effort(receipt_path)
        raise
    return GovernedActionIntentWrite(
        action_intent=action_intent,
        receipt_ref=receipt_ref,
        execution_allowed=False,
        authority_transition=False,
    )
