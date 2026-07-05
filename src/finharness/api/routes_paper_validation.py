"""Paper validation routes.

These endpoints expose a paper-only validation loop. They may carry
order-shaped fields, simulated fills, and paper account state, but they do not
create live orders, broker submissions, real-cash risk, or authority changes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import desc
from sqlmodel import Session, select

from finharness.api.dependencies import EngineDependency, ReceiptRootDependency
from finharness.statecore.models import (
    PaperAccount,
    PaperExecutionReceipt,
    PaperOrderTicketCandidate,
    PaperPosition,
)
from finharness.statecore.paper_accounts import (
    PAPER_ACCOUNT_NON_CLAIMS,
    PaperAccountStaleError,
    PaperAccountValidationError,
    apply_paper_execution_to_account,
    create_paper_account,
)
from finharness.statecore.paper_executions import (
    PAPER_EXECUTION_NON_CLAIMS,
    PaperExecutionStaleError,
    PaperExecutionStatus,
    PaperExecutionValidationError,
    record_paper_execution_receipt,
)
from finharness.statecore.paper_order_tickets import (
    PAPER_ORDER_TICKET_NON_CLAIMS,
    PaperOrderTicketStaleError,
    PaperOrderTicketValidationError,
    create_paper_order_ticket_candidate,
)

router = APIRouter(tags=["paper-validation"])


class PaperOrderTicketCandidateCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_gate_id: str
    expected_trade_plan_candidate_receipt_ref: str
    expected_review_gate_receipt_ref: str
    expected_action_intent_receipt_ref: str
    expected_action_preflight_report_hash: str
    expected_simulation_report_receipt_ref: str
    ticket: dict[str, Any]
    source_refs: list[str] = Field(default_factory=list)

    @field_validator(
        "review_gate_id",
        "expected_trade_plan_candidate_receipt_ref",
        "expected_review_gate_receipt_ref",
        "expected_action_intent_receipt_ref",
        "expected_action_preflight_report_hash",
        "expected_simulation_report_receipt_ref",
    )
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("paper order ticket candidate requires current reviewed evidence")
        return value


class PaperOrderTicketCandidateCreateResponse(BaseModel):
    paper_order_ticket: PaperOrderTicketCandidate
    receipt_ref: str
    non_claims: tuple[str, ...] = PAPER_ORDER_TICKET_NON_CLAIMS
    environment: str = "paper"
    live_execution_allowed: bool = False
    real_cash_at_risk: bool = False
    submitted_to_broker: bool = False


class PaperOrderTicketCandidateResponse(BaseModel):
    paper_order_ticket: PaperOrderTicketCandidate
    non_claims: tuple[str, ...] = PAPER_ORDER_TICKET_NON_CLAIMS
    environment: str = "paper"
    live_execution_allowed: bool = False
    real_cash_at_risk: bool = False
    submitted_to_broker: bool = False


class PaperOrderTicketCandidateListResponse(BaseModel):
    paper_order_tickets: list[PaperOrderTicketCandidate]
    non_claims: tuple[str, ...] = PAPER_ORDER_TICKET_NON_CLAIMS
    environment: str = "paper"
    live_execution_allowed: bool = False
    real_cash_at_risk: bool = False
    submitted_to_broker: bool = False


class PaperExecutionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_paper_order_ticket_receipt_ref: str
    execution_status: PaperExecutionStatus = "simulated_filled"
    fill_price: str | None = None
    simulator_ref: str = "paper-simulator://local/v0"
    executed_at_utc: str | None = None
    fees: str = "0"
    rejection_reason: str | None = None
    execution_notes: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)

    @field_validator("expected_paper_order_ticket_receipt_ref", "simulator_ref")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("paper execution requires ticket receipt and simulator")
        return value


class PaperExecutionCreateResponse(BaseModel):
    paper_execution: PaperExecutionReceipt
    receipt_ref: str
    non_claims: tuple[str, ...] = PAPER_EXECUTION_NON_CLAIMS
    environment: str = "paper"
    live_execution_allowed: bool = False
    real_cash_at_risk: bool = False
    submitted_to_broker: bool = False


class PaperExecutionResponse(BaseModel):
    paper_execution: PaperExecutionReceipt
    non_claims: tuple[str, ...] = PAPER_EXECUTION_NON_CLAIMS
    environment: str = "paper"
    live_execution_allowed: bool = False
    real_cash_at_risk: bool = False
    submitted_to_broker: bool = False


class PaperExecutionListResponse(BaseModel):
    paper_executions: list[PaperExecutionReceipt]
    non_claims: tuple[str, ...] = PAPER_EXECUTION_NON_CLAIMS
    environment: str = "paper"
    live_execution_allowed: bool = False
    real_cash_at_risk: bool = False
    submitted_to_broker: bool = False


class PaperAccountCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str
    starting_cash: str
    currency: str = "USD"
    source_refs: list[str] = Field(default_factory=list)

    @field_validator("display_name", "starting_cash", "currency")
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("paper account requires name, starting cash, and currency")
        return value


class PaperAccountCreateResponse(BaseModel):
    paper_account: PaperAccount
    receipt_ref: str
    non_claims: tuple[str, ...] = PAPER_ACCOUNT_NON_CLAIMS
    environment: str = "paper"
    live_execution_allowed: bool = False
    real_cash_at_risk: bool = False
    submitted_to_broker: bool = False


class PaperAccountResponse(BaseModel):
    paper_account: PaperAccount
    non_claims: tuple[str, ...] = PAPER_ACCOUNT_NON_CLAIMS
    environment: str = "paper"
    live_execution_allowed: bool = False
    real_cash_at_risk: bool = False
    submitted_to_broker: bool = False


class PaperAccountListResponse(BaseModel):
    paper_accounts: list[PaperAccount]
    non_claims: tuple[str, ...] = PAPER_ACCOUNT_NON_CLAIMS
    environment: str = "paper"
    live_execution_allowed: bool = False
    real_cash_at_risk: bool = False
    submitted_to_broker: bool = False


class PaperPositionListResponse(BaseModel):
    paper_positions: list[PaperPosition]
    non_claims: tuple[str, ...] = PAPER_ACCOUNT_NON_CLAIMS
    environment: str = "paper"
    live_execution_allowed: bool = False
    real_cash_at_risk: bool = False
    submitted_to_broker: bool = False


class PaperAccountExecutionApplicationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_execution_id: str
    expected_paper_account_receipt_ref: str
    expected_paper_execution_receipt_ref: str
    source_refs: list[str] = Field(default_factory=list)

    @field_validator(
        "paper_execution_id",
        "expected_paper_account_receipt_ref",
        "expected_paper_execution_receipt_ref",
    )
    @classmethod
    def require_non_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("paper account application requires current account and execution")
        return value


class PaperAccountExecutionApplicationCreateResponse(BaseModel):
    paper_account: PaperAccount
    paper_position: PaperPosition
    receipt_ref: str
    non_claims: tuple[str, ...] = PAPER_ACCOUNT_NON_CLAIMS
    environment: str = "paper"
    live_execution_allowed: bool = False
    real_cash_at_risk: bool = False
    submitted_to_broker: bool = False


@router.post(
    "/trade-plan-candidates/{trade_plan_candidate_id}/paper-order-ticket-candidates",
    response_model=PaperOrderTicketCandidateCreateResponse,
)
async def create_paper_order_ticket_candidate_endpoint(
    trade_plan_candidate_id: str,
    request: PaperOrderTicketCandidateCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> PaperOrderTicketCandidateCreateResponse:
    try:
        write = create_paper_order_ticket_candidate(
            trade_plan_candidate_id=trade_plan_candidate_id,
            review_gate_id=request.review_gate_id,
            expected_trade_plan_candidate_receipt_ref=(
                request.expected_trade_plan_candidate_receipt_ref
            ),
            expected_review_gate_receipt_ref=request.expected_review_gate_receipt_ref,
            expected_action_intent_receipt_ref=request.expected_action_intent_receipt_ref,
            expected_action_preflight_report_hash=(
                request.expected_action_preflight_report_hash
            ),
            expected_simulation_report_receipt_ref=(
                request.expected_simulation_report_receipt_ref
            ),
            ticket=request.ticket,
            source_refs=request.source_refs,
            engine=engine,
            receipt_root=receipt_root,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"paper order ticket candidate source not found: {exc}",
        ) from exc
    except PaperOrderTicketStaleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PaperOrderTicketValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PaperOrderTicketCandidateCreateResponse(
        paper_order_ticket=write.paper_order_ticket,
        receipt_ref=write.receipt_ref,
        environment="paper",
        live_execution_allowed=False,
        real_cash_at_risk=False,
        submitted_to_broker=False,
    )


@router.get(
    "/paper-order-ticket-candidates",
    response_model=PaperOrderTicketCandidateListResponse,
)
async def list_paper_order_ticket_candidates(
    engine: EngineDependency,
    paper_account_id: str | None = None,
    symbol: str | None = None,
) -> PaperOrderTicketCandidateListResponse:
    statement = select(PaperOrderTicketCandidate).order_by(
        desc(PaperOrderTicketCandidate.created_at_utc)
    )
    if paper_account_id is not None:
        statement = statement.where(
            PaperOrderTicketCandidate.paper_account_ref == paper_account_id
        )
    if symbol is not None:
        statement = statement.where(PaperOrderTicketCandidate.symbol == symbol)
    with Session(engine) as session:
        paper_tickets = list(session.exec(statement).all())
    return PaperOrderTicketCandidateListResponse(paper_order_tickets=paper_tickets)


@router.get(
    "/paper-order-ticket-candidates/{paper_order_ticket_id}",
    response_model=PaperOrderTicketCandidateResponse,
)
async def get_paper_order_ticket_candidate(
    paper_order_ticket_id: str,
    engine: EngineDependency,
) -> PaperOrderTicketCandidateResponse:
    with Session(engine) as session:
        paper_ticket = session.get(PaperOrderTicketCandidate, paper_order_ticket_id)
    if paper_ticket is None:
        raise HTTPException(
            status_code=404,
            detail=f"paper order ticket candidate not found: {paper_order_ticket_id}",
        )
    return PaperOrderTicketCandidateResponse(
        paper_order_ticket=paper_ticket,
        environment="paper",
        live_execution_allowed=False,
        real_cash_at_risk=False,
        submitted_to_broker=False,
    )


@router.post(
    "/paper-order-ticket-candidates/{paper_order_ticket_id}/simulated-executions",
    response_model=PaperExecutionCreateResponse,
)
async def create_paper_execution_receipt_endpoint(
    paper_order_ticket_id: str,
    request: PaperExecutionCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> PaperExecutionCreateResponse:
    try:
        write = record_paper_execution_receipt(
            paper_order_ticket_id=paper_order_ticket_id,
            expected_paper_order_ticket_receipt_ref=(
                request.expected_paper_order_ticket_receipt_ref
            ),
            execution_status=request.execution_status,
            fill_price=request.fill_price,
            simulator_ref=request.simulator_ref,
            executed_at_utc=request.executed_at_utc,
            fees=request.fees,
            rejection_reason=request.rejection_reason,
            execution_notes=request.execution_notes,
            source_refs=request.source_refs,
            engine=engine,
            receipt_root=receipt_root,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"paper order ticket candidate not found: {exc}",
        ) from exc
    except PaperExecutionStaleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PaperExecutionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PaperExecutionCreateResponse(
        paper_execution=write.paper_execution,
        receipt_ref=write.receipt_ref,
        environment="paper",
        live_execution_allowed=False,
        real_cash_at_risk=False,
        submitted_to_broker=False,
    )


@router.get(
    "/paper-execution-receipts",
    response_model=PaperExecutionListResponse,
)
async def list_paper_execution_receipts(
    engine: EngineDependency,
    paper_account_id: str | None = None,
    symbol: str | None = None,
) -> PaperExecutionListResponse:
    statement = select(PaperExecutionReceipt).order_by(
        desc(PaperExecutionReceipt.created_at_utc)
    )
    if paper_account_id is not None:
        statement = statement.where(PaperExecutionReceipt.paper_account_ref == paper_account_id)
    if symbol is not None:
        statement = statement.where(PaperExecutionReceipt.symbol == symbol)
    with Session(engine) as session:
        paper_executions = list(session.exec(statement).all())
    return PaperExecutionListResponse(paper_executions=paper_executions)


@router.get(
    "/paper-execution-receipts/{paper_execution_id}",
    response_model=PaperExecutionResponse,
)
async def get_paper_execution_receipt(
    paper_execution_id: str,
    engine: EngineDependency,
) -> PaperExecutionResponse:
    with Session(engine) as session:
        paper_execution = session.get(PaperExecutionReceipt, paper_execution_id)
    if paper_execution is None:
        raise HTTPException(
            status_code=404,
            detail=f"paper execution receipt not found: {paper_execution_id}",
        )
    return PaperExecutionResponse(
        paper_execution=paper_execution,
        environment="paper",
        live_execution_allowed=False,
        real_cash_at_risk=False,
        submitted_to_broker=False,
    )


@router.post("/paper-accounts", response_model=PaperAccountCreateResponse)
async def create_paper_account_endpoint(
    request: PaperAccountCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> PaperAccountCreateResponse:
    try:
        write = create_paper_account(
            display_name=request.display_name,
            starting_cash=request.starting_cash,
            currency=request.currency,
            source_refs=request.source_refs,
            engine=engine,
            receipt_root=receipt_root,
        )
    except PaperAccountValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PaperAccountCreateResponse(
        paper_account=write.paper_account,
        receipt_ref=write.receipt_ref,
        environment="paper",
        live_execution_allowed=False,
        real_cash_at_risk=False,
        submitted_to_broker=False,
    )


@router.get("/paper-accounts", response_model=PaperAccountListResponse)
async def list_paper_accounts(
    engine: EngineDependency,
    status: str | None = None,
) -> PaperAccountListResponse:
    statement = select(PaperAccount).order_by(desc(PaperAccount.updated_at_utc))
    if status is not None:
        statement = statement.where(PaperAccount.status == status)
    with Session(engine) as session:
        paper_accounts = list(session.exec(statement).all())
    return PaperAccountListResponse(paper_accounts=paper_accounts)


@router.get("/paper-accounts/{paper_account_id}", response_model=PaperAccountResponse)
async def get_paper_account(
    paper_account_id: str,
    engine: EngineDependency,
) -> PaperAccountResponse:
    with Session(engine) as session:
        paper_account = session.get(PaperAccount, paper_account_id)
    if paper_account is None:
        raise HTTPException(
            status_code=404,
            detail=f"paper account not found: {paper_account_id}",
        )
    return PaperAccountResponse(
        paper_account=paper_account,
        environment="paper",
        live_execution_allowed=False,
        real_cash_at_risk=False,
        submitted_to_broker=False,
    )


@router.get(
    "/paper-accounts/{paper_account_id}/positions",
    response_model=PaperPositionListResponse,
)
async def list_paper_account_positions(
    paper_account_id: str,
    engine: EngineDependency,
) -> PaperPositionListResponse:
    with Session(engine) as session:
        paper_account = session.get(PaperAccount, paper_account_id)
        if paper_account is None:
            raise HTTPException(
                status_code=404,
                detail=f"paper account not found: {paper_account_id}",
            )
        statement = (
            select(PaperPosition)
            .where(PaperPosition.paper_account_id == paper_account_id)
            .order_by(PaperPosition.symbol)
        )
        paper_positions = list(session.exec(statement).all())
    return PaperPositionListResponse(paper_positions=paper_positions)


@router.post(
    "/paper-accounts/{paper_account_id}/execution-applications",
    response_model=PaperAccountExecutionApplicationCreateResponse,
)
async def apply_paper_execution_to_account_endpoint(
    paper_account_id: str,
    request: PaperAccountExecutionApplicationCreateRequest,
    engine: EngineDependency,
    receipt_root: ReceiptRootDependency,
) -> PaperAccountExecutionApplicationCreateResponse:
    try:
        write = apply_paper_execution_to_account(
            paper_account_id=paper_account_id,
            paper_execution_id=request.paper_execution_id,
            expected_paper_account_receipt_ref=request.expected_paper_account_receipt_ref,
            expected_paper_execution_receipt_ref=(
                request.expected_paper_execution_receipt_ref
            ),
            source_refs=request.source_refs,
            engine=engine,
            receipt_root=receipt_root,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"paper account application source not found: {exc}",
        ) from exc
    except PaperAccountStaleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PaperAccountValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PaperAccountExecutionApplicationCreateResponse(
        paper_account=write.paper_account,
        paper_position=write.paper_position,
        receipt_ref=write.receipt_ref,
        environment="paper",
        live_execution_allowed=False,
        real_cash_at_risk=False,
        submitted_to_broker=False,
    )
