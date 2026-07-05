"""Paper-only order ticket candidates.

This module is the first deliberately order-shaped mainline artifact. It turns
an allowed TradePlanReviewGate into a paper order ticket candidate so FinHarness
can validate a plan without jumping to live execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Engine
from sqlmodel import Session

from finharness.action_intent_preflight import preflight_action_intent
from finharness.statecore.action_intents import _dedupe_text
from finharness.statecore.models import (
    PAPER_ORDER_TICKET_ORDER_TYPES,
    PAPER_ORDER_TICKET_SIDES,
    PAPER_ORDER_TICKET_TIFS,
    ActionIntent,
    ActionIntentSimulationReport,
    PaperAccount,
    PaperOrderTicketCandidate,
    ReceiptIndex,
    TradePlanCandidate,
    TradePlanReviewGate,
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

PaperOrderSide = Literal["buy", "sell"]
PaperOrderType = Literal["market", "limit", "stop", "stop_limit"]
PaperOrderTimeInForce = Literal["day", "gtc"]

PAPER_ORDER_TICKET_NON_CLAIMS: tuple[str, ...] = (
    "PaperOrderTicketCandidate is paper-only.",
    "PaperOrderTicketCandidate is not a live order.",
    "PaperOrderTicketCandidate does not submit to a broker.",
    "PaperOrderTicketCandidate puts no real cash at risk.",
    "PaperOrderTicketCandidate is validation evidence, not investment advice.",
)

LIVE_OR_BROKER_SUBMIT_KEYS: frozenset[str] = frozenset(
    {
        "broker_order_id",
        "cash_at_risk",
        "execution_allowed",
        "execution_status",
        "fix_tags",
        "live",
        "live_execution_allowed",
        "real_cash_at_risk",
        "route",
        "submitted_to_broker",
        "submitted_to_paper_broker",
        "venue",
    }
)


class PaperOrderTicketValidationError(ValueError):
    """Raised when a paper order ticket crosses the paper-only boundary."""


class PaperOrderTicketStaleError(ValueError):
    """Raised when caller freshness evidence no longer matches current state."""


@dataclass(frozen=True)
class PaperOrderTicketCandidateWrite:
    paper_order_ticket: PaperOrderTicketCandidate
    receipt_ref: str
    environment: str = "paper"
    live_execution_allowed: bool = False
    real_cash_at_risk: bool = False
    submitted_to_broker: bool = False


def create_paper_order_ticket_candidate(
    *,
    trade_plan_candidate_id: str,
    review_gate_id: str,
    expected_trade_plan_candidate_receipt_ref: str,
    expected_review_gate_receipt_ref: str,
    expected_action_intent_receipt_ref: str,
    expected_action_preflight_report_hash: str,
    expected_simulation_report_receipt_ref: str,
    ticket: dict[str, Any],
    source_refs: list[str] | None = None,
    engine: Engine,
    receipt_root: str | Path,
) -> PaperOrderTicketCandidateWrite:
    """Persist a paper order ticket candidate bound to current reviewed evidence."""

    parsed = _parse_ticket(ticket)
    clean_source_refs = _dedupe_text(list(source_refs or []))
    _reject_live_or_submit_markers({"ticket": ticket, "source_refs": clean_source_refs})

    with Session(engine) as session:
        trade_plan_candidate = session.get(TradePlanCandidate, trade_plan_candidate_id)
        if trade_plan_candidate is None:
            raise KeyError(trade_plan_candidate_id)
        review_gate = session.get(TradePlanReviewGate, review_gate_id)
        if review_gate is None:
            raise KeyError(review_gate_id)
        action_intent = session.get(ActionIntent, trade_plan_candidate.action_intent_id)
        simulation_report = session.get(
            ActionIntentSimulationReport,
            trade_plan_candidate.simulation_report_id,
        )
        paper_account = session.get(PaperAccount, parsed["paper_account_ref"])
    if action_intent is None:
        raise KeyError(trade_plan_candidate.action_intent_id)
    if simulation_report is None:
        raise KeyError(trade_plan_candidate.simulation_report_id)
    if paper_account is None:
        raise KeyError(parsed["paper_account_ref"])

    _require_current_reviewed_evidence(
        trade_plan_candidate=trade_plan_candidate,
        review_gate=review_gate,
        action_intent=action_intent,
        simulation_report=simulation_report,
        expected_trade_plan_candidate_receipt_ref=expected_trade_plan_candidate_receipt_ref,
        expected_review_gate_receipt_ref=expected_review_gate_receipt_ref,
        expected_action_intent_receipt_ref=expected_action_intent_receipt_ref,
        expected_action_preflight_report_hash=expected_action_preflight_report_hash,
        expected_simulation_report_receipt_ref=expected_simulation_report_receipt_ref,
        engine=engine,
    )
    _require_ticket_consistent_with_plan(parsed, trade_plan_candidate)
    _require_ticket_consistent_with_paper_account(parsed, paper_account)

    created_at = _now_utc()
    paper_order_ticket_id = _safe_id(
        f"paper_order_ticket_{_revision_stamp()}_{uuid4().hex[:8]}"
    )
    receipt_id = f"receipt_{paper_order_ticket_id}"
    receipt_path = resolve_under(
        receipt_root,
        "paper-order-ticket-candidates",
        f"{receipt_id}.json",
    )
    receipt_ref = _display_path(receipt_path)
    receipt_refs = _dedupe_text(
        [
            *_receipt_refs_without_hashes(trade_plan_candidate.receipt_refs),
            trade_plan_candidate.receipt_ref or "",
            review_gate.receipt_ref or "",
            trade_plan_candidate.source_simulation_report_receipt_ref,
            trade_plan_candidate.source_action_intent_receipt_ref,
            receipt_ref,
        ]
    )
    final_source_refs = _dedupe_text(
        [
            *trade_plan_candidate.source_refs,
            *review_gate.source_refs,
            *clean_source_refs,
        ]
    )
    paper_ticket = PaperOrderTicketCandidate(
        paper_order_ticket_id=paper_order_ticket_id,
        trade_plan_candidate_id=trade_plan_candidate.trade_plan_candidate_id,
        review_gate_id=review_gate.review_gate_id,
        action_intent_id=trade_plan_candidate.action_intent_id,
        simulation_report_id=trade_plan_candidate.simulation_report_id,
        proposal_id=trade_plan_candidate.proposal_id,
        source_trade_plan_candidate_receipt_ref=trade_plan_candidate.receipt_ref or "",
        source_review_gate_receipt_ref=review_gate.receipt_ref or "",
        source_action_intent_receipt_ref=trade_plan_candidate.source_action_intent_receipt_ref,
        source_action_preflight_report_hash=(
            trade_plan_candidate.source_action_preflight_report_hash
        ),
        source_simulation_report_receipt_ref=(
            trade_plan_candidate.source_simulation_report_receipt_ref
        ),
        paper_account_ref=parsed["paper_account_ref"],
        instrument_ref=parsed["instrument_ref"],
        symbol=parsed["symbol"],
        side=parsed["side"],
        order_type=parsed["order_type"],
        time_in_force=parsed["time_in_force"],
        quantity=parsed["quantity"],
        limit_price=parsed["limit_price"],
        stop_price=parsed["stop_price"],
        notional_estimate=parsed["notional_estimate"],
        currency=parsed["currency"],
        ticket_rationale=parsed["ticket_rationale"],
        validation_findings=_validation_findings(parsed, trade_plan_candidate),
        source_refs=final_source_refs,
        receipt_refs=receipt_refs,
        preflight_refs=[trade_plan_candidate.source_action_preflight_report_hash],
        non_claims=list(PAPER_ORDER_TICKET_NON_CLAIMS),
        receipt_ref=receipt_ref,
        live_execution_allowed=False,
        real_cash_at_risk=False,
        submitted_to_broker=False,
        authority_transition=False,
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    atomic_write_json(
        receipt_path,
        _receipt_payload(
            paper_ticket=paper_ticket,
            trade_plan_candidate=trade_plan_candidate,
            review_gate=review_gate,
            action_intent=action_intent,
            simulation_report=simulation_report,
        ),
    )
    receipt_index: ReceiptIndex = _receipt_index(
        receipt_id=receipt_id,
        kind="state_core_paper_order_ticket_candidate",
        path=receipt_path,
        created_at_utc=created_at,
        refs=_dedupe_text(
            [
                paper_ticket.paper_order_ticket_id,
                trade_plan_candidate.trade_plan_candidate_id,
                review_gate.review_gate_id,
                trade_plan_candidate.action_intent_id,
                trade_plan_candidate.simulation_report_id,
                trade_plan_candidate.proposal_id,
                trade_plan_candidate.receipt_ref or "",
                review_gate.receipt_ref or "",
                trade_plan_candidate.source_action_preflight_report_hash,
                *paper_ticket.source_refs,
            ]
        ),
    )
    try:
        write_records([paper_ticket, receipt_index], engine=engine)
    except StateCoreStoreError:
        remove_file_best_effort(receipt_path)
        raise
    return PaperOrderTicketCandidateWrite(
        paper_order_ticket=paper_ticket,
        receipt_ref=receipt_ref,
        environment="paper",
        live_execution_allowed=False,
        real_cash_at_risk=False,
        submitted_to_broker=False,
    )


def _parse_ticket(ticket: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(ticket, dict):
        raise PaperOrderTicketValidationError("ticket must be an object")
    environment = str(ticket.get("environment", "paper")).strip()
    if environment != "paper":
        raise PaperOrderTicketValidationError("paper order tickets require environment='paper'")
    side = _string(ticket, "side", required=True).lower()
    if side not in PAPER_ORDER_TICKET_SIDES:
        raise PaperOrderTicketValidationError(f"unknown paper order side: {side}")
    order_type = _string(ticket, "order_type", required=True).lower()
    if order_type not in PAPER_ORDER_TICKET_ORDER_TYPES:
        raise PaperOrderTicketValidationError(f"unknown paper order_type: {order_type}")
    time_in_force = _string(ticket, "time_in_force", default="day").lower()
    if time_in_force not in PAPER_ORDER_TICKET_TIFS:
        raise PaperOrderTicketValidationError(f"unknown paper order time_in_force: {time_in_force}")
    quantity = _decimal(ticket.get("quantity"), "quantity")
    if quantity <= 0:
        raise PaperOrderTicketValidationError("paper order quantity must be positive")
    limit_price = _optional_decimal(ticket.get("limit_price"), "limit_price")
    stop_price = _optional_decimal(ticket.get("stop_price"), "stop_price")
    notional_estimate = _optional_decimal(
        ticket.get("notional_estimate"),
        "notional_estimate",
    )
    if limit_price is not None and limit_price <= 0:
        raise PaperOrderTicketValidationError("ticket.limit_price must be positive")
    if stop_price is not None and stop_price <= 0:
        raise PaperOrderTicketValidationError("ticket.stop_price must be positive")
    if notional_estimate is not None and notional_estimate < 0:
        raise PaperOrderTicketValidationError("ticket.notional_estimate must be non-negative")
    if order_type in {"limit", "stop_limit"} and limit_price is None:
        raise PaperOrderTicketValidationError(f"{order_type} paper orders require limit_price")
    if order_type in {"stop", "stop_limit"} and stop_price is None:
        raise PaperOrderTicketValidationError(f"{order_type} paper orders require stop_price")
    return {
        "paper_account_ref": _string(ticket, "paper_account_ref", required=True),
        "instrument_ref": _string(ticket, "instrument_ref", required=True),
        "symbol": _string(ticket, "symbol", required=True).upper(),
        "side": side,
        "order_type": order_type,
        "time_in_force": time_in_force,
        "quantity": quantity,
        "limit_price": limit_price,
        "stop_price": stop_price,
        "notional_estimate": notional_estimate,
        "currency": _string(ticket, "currency", default="USD").upper(),
        "ticket_rationale": _string(ticket, "ticket_rationale", required=True),
    }


def _require_current_reviewed_evidence(
    *,
    trade_plan_candidate: TradePlanCandidate,
    review_gate: TradePlanReviewGate,
    action_intent: ActionIntent,
    simulation_report: ActionIntentSimulationReport,
    expected_trade_plan_candidate_receipt_ref: str,
    expected_review_gate_receipt_ref: str,
    expected_action_intent_receipt_ref: str,
    expected_action_preflight_report_hash: str,
    expected_simulation_report_receipt_ref: str,
    engine: Engine,
) -> None:
    if review_gate.trade_plan_candidate_id != trade_plan_candidate.trade_plan_candidate_id:
        raise PaperOrderTicketValidationError("review gate does not belong to trade plan candidate")
    if not review_gate.may_enter_order_ticket_candidate_staging:
        raise PaperOrderTicketValidationError(
            "paper order ticket candidate requires an allowed trade plan review gate"
        )
    if trade_plan_candidate.receipt_ref != expected_trade_plan_candidate_receipt_ref.strip():
        raise PaperOrderTicketStaleError("trade plan candidate receipt ref does not match")
    if review_gate.receipt_ref != expected_review_gate_receipt_ref.strip():
        raise PaperOrderTicketStaleError("review gate receipt ref does not match")
    if action_intent.receipt_ref != expected_action_intent_receipt_ref.strip():
        raise PaperOrderTicketStaleError("action intent receipt ref does not match")
    if simulation_report.receipt_ref != expected_simulation_report_receipt_ref.strip():
        raise PaperOrderTicketStaleError("simulation report receipt ref does not match")
    preflight = preflight_action_intent(action_intent.action_intent_id, engine=engine)
    if preflight is None:
        raise KeyError(action_intent.action_intent_id)
    if preflight.report_hash != expected_action_preflight_report_hash.strip():
        raise PaperOrderTicketStaleError(
            "action preflight report hash does not match current preflight"
        )
    if trade_plan_candidate.source_action_preflight_report_hash != preflight.report_hash:
        raise PaperOrderTicketStaleError(
            "trade plan candidate is not bound to current preflight"
        )
    if review_gate.source_action_preflight_report_hash != preflight.report_hash:
        raise PaperOrderTicketStaleError("review gate is not bound to current preflight")


def _require_ticket_consistent_with_plan(
    parsed: dict[str, Any],
    trade_plan_candidate: TradePlanCandidate,
) -> None:
    plan_symbol = str(trade_plan_candidate.instrument_scope.get("symbol", "")).upper()
    if plan_symbol and parsed["symbol"] != plan_symbol:
        raise PaperOrderTicketValidationError(
            "paper order symbol must match trade plan instrument scope"
        )
    if trade_plan_candidate.plan_direction in {"reduce", "raise_cash"} and parsed["side"] != "sell":
        raise PaperOrderTicketValidationError(
            "reduce/raise_cash plans require a sell-side paper ticket"
        )
    if trade_plan_candidate.plan_direction == "increase" and parsed["side"] != "buy":
        raise PaperOrderTicketValidationError(
            "increase plans require a buy-side paper ticket"
        )


def _require_ticket_consistent_with_paper_account(
    parsed: dict[str, Any],
    paper_account: PaperAccount,
) -> None:
    if paper_account.environment != "paper":
        raise PaperOrderTicketValidationError("paper ticket account must be paper environment")
    if paper_account.status != "active":
        raise PaperOrderTicketValidationError("paper ticket account must be active")
    if paper_account.currency != parsed["currency"]:
        raise PaperOrderTicketValidationError(
            "paper ticket currency must match paper account currency"
        )


def _reject_live_or_submit_markers(value: Any) -> None:
    marker = _live_or_submit_marker(value)
    if marker is not None:
        raise PaperOrderTicketValidationError(
            f"paper order ticket cannot carry live/broker-submit field {marker!r}"
        )


def _live_or_submit_marker(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).strip()
            normalized = key_text.lower().replace("-", "_").replace(" ", "_")
            if normalized in LIVE_OR_BROKER_SUBMIT_KEYS:
                return key_text
            found = _live_or_submit_marker(child)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = _live_or_submit_marker(child)
            if found is not None:
                return found
    if isinstance(value, str) and "live://" in value.lower():
        return value
    return None


def _validation_findings(
    parsed: dict[str, Any],
    trade_plan_candidate: TradePlanCandidate,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if trade_plan_candidate.plan_direction == "rebalance":
        findings.append(
            {
                "code": "rebalance_side_requires_human_review",
                "severity": "info",
                "source": "paper_order_ticket_candidate",
            }
        )
    if parsed["order_type"] == "market":
        findings.append(
            {
                "code": "paper_market_order_has_no_price_limit",
                "severity": "warning",
                "source": "paper_order_ticket_candidate",
            }
        )
    return findings


def _receipt_refs_without_hashes(values: list[str]) -> list[str]:
    return [value for value in values if not str(value).startswith("sha256:")]


def _string(
    ticket: dict[str, Any],
    key: str,
    *,
    required: bool = False,
    default: str = "",
) -> str:
    clean = str(ticket.get(key, default)).strip()
    if required and not clean:
        raise PaperOrderTicketValidationError(f"ticket requires {key}")
    return clean


def _decimal(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError) as exc:
        raise PaperOrderTicketValidationError(f"ticket.{field_name} must be decimal") from exc


def _optional_decimal(value: Any, field_name: str) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    return _decimal(value, field_name)


def _receipt_payload(
    *,
    paper_ticket: PaperOrderTicketCandidate,
    trade_plan_candidate: TradePlanCandidate,
    review_gate: TradePlanReviewGate,
    action_intent: ActionIntent,
    simulation_report: ActionIntentSimulationReport,
) -> dict[str, Any]:
    return {
        "receipt_id": f"receipt_{paper_ticket.paper_order_ticket_id}",
        "kind": "state_core_paper_order_ticket_candidate",
        "created_at_utc": paper_ticket.created_at_utc,
        "paper_order_ticket_id": paper_ticket.paper_order_ticket_id,
        "trade_plan_candidate_id": paper_ticket.trade_plan_candidate_id,
        "review_gate_id": paper_ticket.review_gate_id,
        "action_intent_id": paper_ticket.action_intent_id,
        "simulation_report_id": paper_ticket.simulation_report_id,
        "proposal_id": paper_ticket.proposal_id,
        "source_trade_plan_candidate_receipt_ref": (
            paper_ticket.source_trade_plan_candidate_receipt_ref
        ),
        "source_review_gate_receipt_ref": paper_ticket.source_review_gate_receipt_ref,
        "source_action_intent_receipt_ref": paper_ticket.source_action_intent_receipt_ref,
        "source_action_preflight_report_hash": paper_ticket.source_action_preflight_report_hash,
        "source_simulation_report_receipt_ref": paper_ticket.source_simulation_report_receipt_ref,
        "ticket": {
            "environment": paper_ticket.environment,
            "paper_account_ref": paper_ticket.paper_account_ref,
            "instrument_ref": paper_ticket.instrument_ref,
            "symbol": paper_ticket.symbol,
            "side": paper_ticket.side,
            "order_type": paper_ticket.order_type,
            "time_in_force": paper_ticket.time_in_force,
            "quantity": str(paper_ticket.quantity),
            "limit_price": str(paper_ticket.limit_price)
            if paper_ticket.limit_price is not None
            else None,
            "stop_price": str(paper_ticket.stop_price)
            if paper_ticket.stop_price is not None
            else None,
            "notional_estimate": str(paper_ticket.notional_estimate)
            if paper_ticket.notional_estimate is not None
            else None,
            "currency": paper_ticket.currency,
        },
        "paper_order_ticket_candidate": paper_ticket.model_dump(mode="json"),
        "evidence_snapshot": {
            "trade_plan_candidate_status": trade_plan_candidate.candidate_status,
            "review_gate_decision": review_gate.review_decision,
            "action_intent_receipt_ref": action_intent.receipt_ref,
            "simulation_report_receipt_ref": simulation_report.receipt_ref,
        },
        "governance": {
            "environment": "paper",
            "paper_order_ticket_candidate": True,
            "order_fields_allowed_in_this_artifact": True,
            "live_execution_allowed": False,
            "real_cash_at_risk": False,
            "submitted_to_broker": False,
            "not_live_order": True,
            "not_broker_submission": True,
            "non_claims": list(PAPER_ORDER_TICKET_NON_CLAIMS),
        },
    }
