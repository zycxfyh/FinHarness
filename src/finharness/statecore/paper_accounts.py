"""Paper account state and simulated-execution application."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import Engine
from sqlmodel import Session, select

from finharness.statecore.action_intents import _dedupe_text
from finharness.statecore.models import (
    PAPER_ACCOUNT_STATUSES,
    PaperAccount,
    PaperExecutionReceipt,
    PaperPosition,
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
from finharness.statecore.store import StateCoreStoreError, upsert_records, write_records

PAPER_ACCOUNT_NON_CLAIMS: tuple[str, ...] = (
    "PaperAccount is paper-only state.",
    "PaperAccount is not a live brokerage account.",
    "PaperAccount does not submit to a broker.",
    "PaperAccount puts no real cash at risk.",
    "PaperAccount state is validation evidence, not investment advice.",
)


class PaperAccountValidationError(ValueError):
    """Raised when a paper account operation crosses the paper-only boundary."""


class PaperAccountStaleError(ValueError):
    """Raised when caller freshness evidence no longer matches current state."""


@dataclass(frozen=True)
class PaperAccountWrite:
    paper_account: PaperAccount
    receipt_ref: str
    environment: str = "paper"
    live_execution_allowed: bool = False
    real_cash_at_risk: bool = False
    submitted_to_broker: bool = False


@dataclass(frozen=True)
class PaperAccountApplicationWrite:
    paper_account: PaperAccount
    paper_position: PaperPosition
    receipt_ref: str
    environment: str = "paper"
    live_execution_allowed: bool = False
    real_cash_at_risk: bool = False
    submitted_to_broker: bool = False


def create_paper_account(
    *,
    display_name: str,
    starting_cash: Any,
    currency: str = "USD",
    source_refs: list[str] | None = None,
    engine: Engine,
    receipt_root: str | Path,
) -> PaperAccountWrite:
    """Create an isolated paper account with starting cash."""

    clean_display_name = display_name.strip()
    clean_currency = currency.strip().upper()
    clean_source_refs = _dedupe_text(list(source_refs or []))
    if not clean_display_name:
        raise PaperAccountValidationError("paper account requires display_name")
    if not clean_currency:
        raise PaperAccountValidationError("paper account requires currency")
    marker = _live_or_submit_marker(
        {
            "display_name": clean_display_name,
            "currency": clean_currency,
            "source_refs": clean_source_refs,
        }
    )
    if marker is not None:
        raise PaperAccountValidationError(
            f"paper account cannot carry live/broker-submit marker {marker!r}"
        )
    cash = _decimal(starting_cash, "starting_cash")
    if cash < 0:
        raise PaperAccountValidationError("paper account starting_cash must be non-negative")

    created_at = _now_utc()
    paper_account_id = _safe_id(f"paper_account_{_revision_stamp()}_{uuid4().hex[:8]}")
    receipt_id = f"receipt_{paper_account_id}"
    receipt_path = resolve_under(receipt_root, "paper-accounts", f"{receipt_id}.json")
    receipt_ref = _display_path(receipt_path)
    paper_account = PaperAccount(
        paper_account_id=paper_account_id,
        display_name=clean_display_name,
        status="active",
        currency=clean_currency,
        cash_balance=cash,
        realized_pnl=Decimal("0"),
        applied_paper_execution_ids=[],
        source_refs=clean_source_refs,
        receipt_refs=[receipt_ref],
        non_claims=list(PAPER_ACCOUNT_NON_CLAIMS),
        receipt_ref=receipt_ref,
        live_execution_allowed=False,
        real_cash_at_risk=False,
        submitted_to_broker=False,
        authority_transition=False,
        created_at_utc=created_at,
        updated_at_utc=created_at,
        as_of_utc=created_at,
    )
    atomic_write_json(receipt_path, _create_receipt_payload(paper_account))
    receipt_index = _receipt_index(
        receipt_id=receipt_id,
        kind="state_core_paper_account",
        path=receipt_path,
        created_at_utc=created_at,
        refs=_dedupe_text([paper_account.paper_account_id, *clean_source_refs]),
    )
    try:
        write_records([paper_account, receipt_index], engine=engine)
    except StateCoreStoreError:
        remove_file_best_effort(receipt_path)
        raise
    return PaperAccountWrite(paper_account=paper_account, receipt_ref=receipt_ref)


def apply_paper_execution_to_account(
    *,
    paper_account_id: str,
    paper_execution_id: str,
    expected_paper_account_receipt_ref: str,
    expected_paper_execution_receipt_ref: str,
    source_refs: list[str] | None = None,
    engine: Engine,
    receipt_root: str | Path,
) -> PaperAccountApplicationWrite:
    """Apply a filled simulated execution to a paper account and position."""

    clean_source_refs = _dedupe_text(list(source_refs or []))
    marker = _live_or_submit_marker({"source_refs": clean_source_refs})
    if marker is not None:
        raise PaperAccountValidationError(
            f"paper account application cannot carry live/broker-submit marker {marker!r}"
        )

    with Session(engine) as session:
        account = session.get(PaperAccount, paper_account_id)
        execution = session.get(PaperExecutionReceipt, paper_execution_id)
        position = session.exec(
            select(PaperPosition).where(
                PaperPosition.paper_account_id == paper_account_id,
                PaperPosition.symbol == (execution.symbol if execution else ""),
            )
        ).one_or_none()
    if account is None:
        raise KeyError(paper_account_id)
    if execution is None:
        raise KeyError(paper_execution_id)
    _require_current_application_evidence(
        account=account,
        execution=execution,
        expected_paper_account_receipt_ref=expected_paper_account_receipt_ref,
        expected_paper_execution_receipt_ref=expected_paper_execution_receipt_ref,
    )
    _require_applicable_execution(account, execution)

    before = _account_position_snapshot(account, position)
    updated_at = _now_utc()
    if position is None:
        position = PaperPosition(
            paper_position_id=_safe_id(f"paper_position_{paper_account_id}_{execution.symbol}"),
            paper_account_id=account.paper_account_id,
            symbol=execution.symbol,
            quantity=Decimal("0"),
            average_cost=Decimal("0"),
            last_price=Decimal("0"),
            market_value=Decimal("0"),
            currency=account.currency,
            source_refs=[],
            receipt_refs=[],
            live_execution_allowed=False,
            real_cash_at_risk=False,
            submitted_to_broker=False,
            authority_transition=False,
            updated_at_utc=updated_at,
            as_of_utc=updated_at,
        )

    if execution.side == "buy":
        _apply_buy(account, position, execution)
    elif execution.side == "sell":
        _apply_sell(account, position, execution)
    else:
        raise PaperAccountValidationError(f"unsupported paper execution side: {execution.side}")

    receipt_id = f"receipt_paper_account_application_{_revision_stamp()}_{uuid4().hex[:8]}"
    receipt_path = resolve_under(receipt_root, "paper-accounts", f"{receipt_id}.json")
    receipt_ref = _display_path(receipt_path)
    account.applied_paper_execution_ids = _dedupe_text(
        [*account.applied_paper_execution_ids, execution.paper_execution_id]
    )
    account.last_paper_execution_id = execution.paper_execution_id
    account.last_paper_execution_receipt_ref = execution.receipt_ref
    account.source_refs = _dedupe_text([*account.source_refs, *clean_source_refs])
    account.receipt_refs = _dedupe_text(
        [*account.receipt_refs, execution.receipt_ref or "", receipt_ref]
    )
    account.receipt_ref = receipt_ref
    account.updated_at_utc = updated_at
    account.as_of_utc = updated_at
    position.last_paper_execution_id = execution.paper_execution_id
    position.last_paper_execution_receipt_ref = execution.receipt_ref
    position.source_refs = _dedupe_text([*position.source_refs, *clean_source_refs])
    position.receipt_refs = _dedupe_text(
        [*position.receipt_refs, execution.receipt_ref or "", receipt_ref]
    )
    position.receipt_ref = receipt_ref
    position.updated_at_utc = updated_at
    position.as_of_utc = updated_at

    after = _account_position_snapshot(account, position)
    atomic_write_json(
        receipt_path,
        _application_receipt_payload(
            paper_account=account,
            paper_position=position,
            paper_execution=execution,
            before=before,
            after=after,
            receipt_id=receipt_id,
            created_at_utc=updated_at,
        ),
    )
    receipt_index = _receipt_index(
        receipt_id=receipt_id,
        kind="state_core_paper_account_execution_application",
        path=receipt_path,
        created_at_utc=updated_at,
        refs=_dedupe_text(
            [
                account.paper_account_id,
                position.paper_position_id,
                execution.paper_execution_id,
                execution.paper_order_ticket_id,
                execution.receipt_ref or "",
                *clean_source_refs,
            ]
        ),
    )
    try:
        upsert_records([account, position, receipt_index], engine=engine)
    except StateCoreStoreError:
        remove_file_best_effort(receipt_path)
        raise
    return PaperAccountApplicationWrite(
        paper_account=account,
        paper_position=position,
        receipt_ref=receipt_ref,
    )


def _require_current_application_evidence(
    *,
    account: PaperAccount,
    execution: PaperExecutionReceipt,
    expected_paper_account_receipt_ref: str,
    expected_paper_execution_receipt_ref: str,
) -> None:
    if account.receipt_ref != expected_paper_account_receipt_ref.strip():
        raise PaperAccountStaleError("paper account receipt ref does not match")
    if execution.receipt_ref != expected_paper_execution_receipt_ref.strip():
        raise PaperAccountStaleError("paper execution receipt ref does not match")


def _require_applicable_execution(
    account: PaperAccount,
    execution: PaperExecutionReceipt,
) -> None:
    if execution.execution_status != "simulated_filled":
        raise PaperAccountValidationError("only simulated_filled executions can be applied")
    if account.status not in PAPER_ACCOUNT_STATUSES or account.status != "active":
        raise PaperAccountValidationError("paper account must be active")
    if execution.paper_account_ref != account.paper_account_id:
        raise PaperAccountValidationError("paper execution is for a different paper account")
    if execution.currency != account.currency:
        raise PaperAccountValidationError("paper execution currency does not match account")
    if execution.paper_execution_id in account.applied_paper_execution_ids:
        raise PaperAccountStaleError("paper execution has already been applied")


def _apply_buy(
    account: PaperAccount,
    position: PaperPosition,
    execution: PaperExecutionReceipt,
) -> None:
    debit = execution.gross_notional + execution.fees
    if debit > account.cash_balance:
        raise PaperAccountValidationError("paper account has insufficient cash")
    old_quantity = position.quantity
    old_cost = position.average_cost
    new_quantity = old_quantity + execution.quantity
    total_cost = (old_quantity * old_cost) + execution.gross_notional + execution.fees
    position.quantity = new_quantity
    position.average_cost = total_cost / new_quantity
    position.last_price = execution.fill_price
    position.market_value = new_quantity * execution.fill_price
    account.cash_balance -= debit


def _apply_sell(
    account: PaperAccount,
    position: PaperPosition,
    execution: PaperExecutionReceipt,
) -> None:
    if execution.quantity > position.quantity:
        raise PaperAccountValidationError("paper account has insufficient position quantity")
    credit = execution.gross_notional - execution.fees
    realized = ((execution.fill_price - position.average_cost) * execution.quantity) - (
        execution.fees
    )
    new_quantity = position.quantity - execution.quantity
    account.cash_balance += credit
    account.realized_pnl += realized
    position.quantity = new_quantity
    if new_quantity == 0:
        position.average_cost = Decimal("0")
    position.last_price = execution.fill_price
    position.market_value = new_quantity * execution.fill_price


def _decimal(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise PaperAccountValidationError(f"paper account {field_name} must be decimal") from exc


def _account_position_snapshot(
    account: PaperAccount,
    position: PaperPosition | None,
) -> dict[str, Any]:
    return {
        "account": {
            "paper_account_id": account.paper_account_id,
            "cash_balance": str(account.cash_balance),
            "realized_pnl": str(account.realized_pnl),
            "receipt_ref": account.receipt_ref,
        },
        "position": None
        if position is None
        else {
            "paper_position_id": position.paper_position_id,
            "symbol": position.symbol,
            "quantity": str(position.quantity),
            "average_cost": str(position.average_cost),
            "last_price": str(position.last_price),
            "market_value": str(position.market_value),
            "receipt_ref": position.receipt_ref,
        },
    }


def _create_receipt_payload(paper_account: PaperAccount) -> dict[str, Any]:
    return {
        "receipt_id": f"receipt_{paper_account.paper_account_id}",
        "kind": "state_core_paper_account",
        "created_at_utc": paper_account.created_at_utc,
        "paper_account_id": paper_account.paper_account_id,
        "paper_account": paper_account.model_dump(mode="json"),
        "governance": _paper_governance(),
        "non_claims": list(PAPER_ACCOUNT_NON_CLAIMS),
    }


def _application_receipt_payload(
    *,
    paper_account: PaperAccount,
    paper_position: PaperPosition,
    paper_execution: PaperExecutionReceipt,
    before: dict[str, Any],
    after: dict[str, Any],
    receipt_id: str,
    created_at_utc: str,
) -> dict[str, Any]:
    return {
        "receipt_id": receipt_id,
        "kind": "state_core_paper_account_execution_application",
        "created_at_utc": created_at_utc,
        "paper_account_id": paper_account.paper_account_id,
        "paper_position_id": paper_position.paper_position_id,
        "paper_execution_id": paper_execution.paper_execution_id,
        "source_paper_execution_receipt_ref": paper_execution.receipt_ref,
        "before": before,
        "after": after,
        "paper_account": paper_account.model_dump(mode="json"),
        "paper_position": paper_position.model_dump(mode="json"),
        "paper_execution": paper_execution.model_dump(mode="json"),
        "governance": _paper_governance(),
        "non_claims": list(PAPER_ACCOUNT_NON_CLAIMS),
    }


def _paper_governance() -> dict[str, Any]:
    return {
        "environment": "paper",
        "paper_state_update": True,
        "live_execution_allowed": False,
        "real_cash_at_risk": False,
        "submitted_to_broker": False,
        "authority_transition": False,
    }
