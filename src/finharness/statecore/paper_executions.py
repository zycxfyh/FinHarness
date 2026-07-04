"""Paper-only simulated execution receipts."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Engine
from sqlmodel import Session

from finharness.statecore.action_intents import _dedupe_text
from finharness.statecore.models import (
    PAPER_EXECUTION_STATUSES,
    PaperExecutionReceipt,
    PaperOrderTicketCandidate,
    ReceiptIndex,
)
from finharness.statecore.paper_order_tickets import _live_or_submit_marker
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

PaperExecutionStatus = Literal["simulated_filled", "simulated_rejected"]

PAPER_EXECUTION_NON_CLAIMS: tuple[str, ...] = (
    "PaperExecutionReceipt is a simulator result.",
    "PaperExecutionReceipt is not a live broker fill.",
    "PaperExecutionReceipt does not submit to a broker.",
    "PaperExecutionReceipt puts no real cash at risk.",
    "PaperExecutionReceipt is validation evidence, not investment advice.",
)


class PaperExecutionValidationError(ValueError):
    """Raised when simulated execution input crosses the paper-only boundary."""


class PaperExecutionStaleError(ValueError):
    """Raised when caller freshness evidence no longer matches current state."""


@dataclass(frozen=True)
class PaperExecutionWrite:
    paper_execution: PaperExecutionReceipt
    receipt_ref: str
    environment: str = "paper"
    live_execution_allowed: bool = False
    real_cash_at_risk: bool = False
    submitted_to_broker: bool = False


def record_paper_execution_receipt(
    *,
    paper_order_ticket_id: str,
    expected_paper_order_ticket_receipt_ref: str,
    execution_status: PaperExecutionStatus,
    fill_price: Any,
    simulator_ref: str = "paper-simulator://local/v0",
    executed_at_utc: str | None = None,
    fees: Any = "0",
    execution_notes: list[str] | None = None,
    source_refs: list[str] | None = None,
    engine: Engine,
    receipt_root: str | Path,
) -> PaperExecutionWrite:
    """Record a local paper-simulator execution result for a paper ticket."""

    clean_status = str(execution_status).strip()
    if clean_status not in PAPER_EXECUTION_STATUSES:
        raise PaperExecutionValidationError(f"unknown paper execution status: {clean_status}")
    clean_simulator_ref = simulator_ref.strip()
    if not clean_simulator_ref:
        raise PaperExecutionValidationError("paper execution requires simulator_ref")
    marker = _live_or_submit_marker(
        {
            "simulator_ref": clean_simulator_ref,
            "execution_notes": execution_notes or [],
            "source_refs": source_refs or [],
        }
    )
    if marker is not None:
        raise PaperExecutionValidationError(
            f"paper execution cannot carry live/broker-submit marker {marker!r}"
        )

    price = _decimal(fill_price, "fill_price")
    if price < 0:
        raise PaperExecutionValidationError("paper execution fill_price must be non-negative")
    fee_amount = _decimal(fees, "fees")
    if fee_amount < 0:
        raise PaperExecutionValidationError("paper execution fees must be non-negative")

    with Session(engine) as session:
        paper_ticket = session.get(PaperOrderTicketCandidate, paper_order_ticket_id)
    if paper_ticket is None:
        raise KeyError(paper_order_ticket_id)
    if paper_ticket.receipt_ref != expected_paper_order_ticket_receipt_ref.strip():
        raise PaperExecutionStaleError("paper order ticket receipt ref does not match")

    gross_notional = paper_ticket.quantity * price
    created_at = _now_utc()
    paper_execution_id = _safe_id(f"paper_execution_{_revision_stamp()}_{uuid4().hex[:8]}")
    receipt_id = f"receipt_{paper_execution_id}"
    receipt_path = resolve_under(
        receipt_root,
        "paper-executions",
        f"{receipt_id}.json",
    )
    receipt_ref = _display_path(receipt_path)
    final_source_refs = _dedupe_text([*paper_ticket.source_refs, *(source_refs or [])])
    final_receipt_refs = _dedupe_text(
        [
            *_receipt_refs_without_hashes(paper_ticket.receipt_refs),
            paper_ticket.receipt_ref or "",
            receipt_ref,
        ]
    )
    paper_execution = PaperExecutionReceipt(
        paper_execution_id=paper_execution_id,
        paper_order_ticket_id=paper_ticket.paper_order_ticket_id,
        trade_plan_candidate_id=paper_ticket.trade_plan_candidate_id,
        review_gate_id=paper_ticket.review_gate_id,
        action_intent_id=paper_ticket.action_intent_id,
        simulation_report_id=paper_ticket.simulation_report_id,
        proposal_id=paper_ticket.proposal_id,
        source_paper_order_ticket_receipt_ref=paper_ticket.receipt_ref or "",
        source_trade_plan_candidate_receipt_ref=(
            paper_ticket.source_trade_plan_candidate_receipt_ref
        ),
        source_review_gate_receipt_ref=paper_ticket.source_review_gate_receipt_ref,
        source_action_intent_receipt_ref=paper_ticket.source_action_intent_receipt_ref,
        source_action_preflight_report_hash=(
            paper_ticket.source_action_preflight_report_hash
        ),
        source_simulation_report_receipt_ref=(
            paper_ticket.source_simulation_report_receipt_ref
        ),
        paper_account_ref=paper_ticket.paper_account_ref,
        simulator_ref=clean_simulator_ref,
        execution_status=clean_status,
        symbol=paper_ticket.symbol,
        side=paper_ticket.side,
        quantity=paper_ticket.quantity,
        fill_price=price,
        gross_notional=gross_notional,
        fees=fee_amount,
        currency=paper_ticket.currency,
        executed_at_utc=executed_at_utc or created_at,
        execution_notes=_dedupe_text(list(execution_notes or [])),
        source_refs=final_source_refs,
        receipt_refs=final_receipt_refs,
        non_claims=list(PAPER_EXECUTION_NON_CLAIMS),
        receipt_ref=receipt_ref,
        live_execution_allowed=False,
        real_cash_at_risk=False,
        submitted_to_broker=False,
        authority_transition=False,
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    atomic_write_json(receipt_path, _receipt_payload(paper_execution, paper_ticket))
    receipt_index: ReceiptIndex = _receipt_index(
        receipt_id=receipt_id,
        kind="state_core_paper_execution_receipt",
        path=receipt_path,
        created_at_utc=created_at,
        refs=_dedupe_text(
            [
                paper_execution.paper_execution_id,
                paper_ticket.paper_order_ticket_id,
                paper_ticket.trade_plan_candidate_id,
                paper_ticket.review_gate_id,
                paper_ticket.action_intent_id,
                paper_ticket.simulation_report_id,
                paper_ticket.proposal_id,
                paper_ticket.receipt_ref or "",
                *paper_execution.source_refs,
            ]
        ),
    )
    try:
        write_records([paper_execution, receipt_index], engine=engine)
    except StateCoreStoreError:
        remove_file_best_effort(receipt_path)
        raise
    return PaperExecutionWrite(
        paper_execution=paper_execution,
        receipt_ref=receipt_ref,
        environment="paper",
        live_execution_allowed=False,
        real_cash_at_risk=False,
        submitted_to_broker=False,
    )


def _decimal(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise PaperExecutionValidationError(
            f"paper execution {field_name} must be decimal"
        ) from exc


def _receipt_refs_without_hashes(values: list[str]) -> list[str]:
    return [value for value in values if not str(value).startswith("sha256:")]


def _receipt_payload(
    paper_execution: PaperExecutionReceipt,
    paper_ticket: PaperOrderTicketCandidate,
) -> dict[str, Any]:
    return {
        "receipt_id": f"receipt_{paper_execution.paper_execution_id}",
        "kind": "state_core_paper_execution_receipt",
        "created_at_utc": paper_execution.created_at_utc,
        "paper_execution_id": paper_execution.paper_execution_id,
        "paper_order_ticket_id": paper_execution.paper_order_ticket_id,
        "trade_plan_candidate_id": paper_execution.trade_plan_candidate_id,
        "review_gate_id": paper_execution.review_gate_id,
        "action_intent_id": paper_execution.action_intent_id,
        "simulation_report_id": paper_execution.simulation_report_id,
        "proposal_id": paper_execution.proposal_id,
        "source_paper_order_ticket_receipt_ref": (
            paper_execution.source_paper_order_ticket_receipt_ref
        ),
        "execution": {
            "environment": "paper",
            "paper_account_ref": paper_execution.paper_account_ref,
            "simulator_ref": paper_execution.simulator_ref,
            "execution_status": paper_execution.execution_status,
            "symbol": paper_execution.symbol,
            "side": paper_execution.side,
            "quantity": str(paper_execution.quantity),
            "fill_price": str(paper_execution.fill_price),
            "gross_notional": str(paper_execution.gross_notional),
            "fees": str(paper_execution.fees),
            "currency": paper_execution.currency,
            "executed_at_utc": paper_execution.executed_at_utc,
        },
        "paper_execution_receipt": paper_execution.model_dump(mode="json"),
        "evidence_snapshot": {
            "paper_order_ticket_status": paper_ticket.candidate_status,
            "paper_order_ticket_receipt_ref": paper_ticket.receipt_ref,
        },
        "governance": {
            "environment": "paper",
            "simulator_result": True,
            "live_execution_allowed": False,
            "real_cash_at_risk": False,
            "submitted_to_broker": False,
            "not_live_broker_fill": True,
            "not_broker_submission": True,
            "non_claims": list(PAPER_EXECUTION_NON_CLAIMS),
        },
    }
