"""Action intent candidate routes.

These endpoints bridge proposal review state to future capital-action workflows.
They do not create orders, broker instructions, approvals, or execution
authorization.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlmodel import Session

from finharness.api.dependencies import EngineDependency, ReceiptRootDependency
from finharness.statecore.action_intents import (
    ACTION_INTENT_NON_CLAIMS,
    ActionIntentCreator,
    ActionIntentNextStep,
    ActionIntentStaleProposalError,
    ActionIntentType,
    ActionIntentValidationError,
    create_governed_action_intent,
)
from finharness.statecore.models import ActionIntent

router = APIRouter(tags=["action-intents"])


class ActionIntentCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_type: ActionIntentType
    intent_summary: str
    rationale: str
    target_scope: dict[str, Any]
    constraints: dict[str, Any] = Field(default_factory=dict)
    trigger_context: dict[str, Any] = Field(default_factory=dict)
    required_preconditions: list[str] = Field(default_factory=list)
    expected_next_step: ActionIntentNextStep = "action_preflight"
    expected_proposal_receipt_ref: str
    source_refs: list[str]
    source_revision_receipt_ref: str | None = None
    created_by: ActionIntentCreator = "human"
    active_profile: str | None = None

    @field_validator("intent_summary", "rationale", "expected_proposal_receipt_ref")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("action intent requires summary, rationale, and receipt freshness")
        return value

    @field_validator("source_refs")
    @classmethod
    def require_source_refs(cls, value: list[str]) -> list[str]:
        clean = sorted({str(item).strip() for item in value if str(item).strip()})
        if not clean:
            raise ValueError("action intent requires at least one source_ref")
        return clean


class ActionIntentCreateResponse(BaseModel):
    action_intent: ActionIntent
    receipt_ref: str
    non_claims: tuple[str, ...] = ACTION_INTENT_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


class ActionIntentResponse(BaseModel):
    action_intent: ActionIntent
    non_claims: tuple[str, ...] = ACTION_INTENT_NON_CLAIMS
    execution_allowed: bool = False
    authority_transition: bool = False


@router.post(
    "/proposals/{proposal_id}/action-intents",
    response_model=ActionIntentCreateResponse,
)
async def create_action_intent(
    proposal_id: str,
    request: ActionIntentCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> ActionIntentCreateResponse:
    try:
        write = create_governed_action_intent(
            proposal_id=proposal_id,
            expected_proposal_receipt_ref=request.expected_proposal_receipt_ref,
            action_type=request.action_type,
            intent_summary=request.intent_summary,
            rationale=request.rationale,
            target_scope=request.target_scope,
            constraints=request.constraints,
            trigger_context=request.trigger_context,
            required_preconditions=request.required_preconditions,
            expected_next_step=request.expected_next_step,
            created_by=request.created_by,
            active_profile=request.active_profile,
            source_refs=request.source_refs,
            source_revision_receipt_ref=request.source_revision_receipt_ref,
            engine=engine,
            receipt_root=receipt_root,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"proposal not found: {proposal_id}") from exc
    except ActionIntentStaleProposalError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ActionIntentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ActionIntentCreateResponse(
        action_intent=write.action_intent,
        receipt_ref=write.receipt_ref,
        execution_allowed=False,
        authority_transition=False,
    )


@router.get("/action-intents/{action_intent_id}", response_model=ActionIntentResponse)
async def get_action_intent(
    action_intent_id: str,
    engine: EngineDependency,
) -> ActionIntentResponse:
    with Session(engine) as session:
        action_intent = session.get(ActionIntent, action_intent_id)
    if action_intent is None:
        raise HTTPException(
            status_code=404,
            detail=f"action intent not found: {action_intent_id}",
        )
    return ActionIntentResponse(
        action_intent=action_intent,
        execution_allowed=False,
        authority_transition=False,
    )
