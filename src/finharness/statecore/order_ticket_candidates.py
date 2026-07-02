"""Governed OrderTicketCandidate writes.

OrderTicketCandidate is the first order-shaped artifact in FinHarness, but it
is still only a candidate. It cannot submit, approve, or authorize execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Engine
from sqlmodel import Session

from finharness.action_intent_preflight import (
    ActionIntentPreflightReport,
    preflight_action_intent,
)
from finharness.statecore.action_intents import _dedupe_text, forbidden_action_intent_marker
from finharness.statecore.models import (
    ORDER_TICKET_CANDIDATE_ORDER_TYPES,
    ORDER_TICKET_CANDIDATE_QUANTITY_MODES,
    ORDER_TICKET_CANDIDATE_SIDES,
    ORDER_TICKET_CANDIDATE_TIME_IN_FORCE,
    ActionIntent,
    ActionIntentSimulationReport,
    OrderTicketCandidate,
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

OrderTicketCandidateSide = Literal[
    "buy_candidate",
    "sell_candidate",
    "hold_candidate",
    "reduce_candidate",
    "increase_candidate",
    "rebalance_candidate",
    "hedge_candidate",
]
OrderTicketCandidateQuantityMode = Literal[
    "no_quantity_v0",
    "notional_cap_only",
    "percent_cap_only",
]
OrderTicketCandidateOrderType = Literal[
    "market_candidate",
    "limit_candidate",
    "not_specified_v0",
]
OrderTicketCandidateTimeInForce = Literal[
    "day_candidate",
    "gtc_candidate",
    "not_specified_v0",
]

ORDER_TICKET_CANDIDATE_NON_CLAIMS: tuple[str, ...] = (
    "OrderTicketCandidate is not an order.",
    "OrderTicketCandidate is not submitted to a broker.",
    "OrderTicketCandidate is not approval, attestation, or an authority contract.",
    "OrderTicketCandidate does not authorize paper or live execution.",
    "Only a future AuthorityContract can authorize any execution path.",
)

EXACT_QUANTITY_KEYS: frozenset[str] = frozenset(
    {
        "quantity",
        "qty",
        "shares",
        "share_count",
        "contracts",
        "units",
        "exact_quantity",
    }
)
FORBIDDEN_TEXT_MARKERS: tuple[str, ...] = (
    "broker",
    "brokerage",
    "execute",
    "execution",
    "submitted",
    "transfer",
)


class OrderTicketCandidateValidationError(ValueError):
    """Raised when an order-shaped candidate crosses its candidate-only boundary."""


class OrderTicketCandidateStaleError(ValueError):
    """Raised when caller freshness evidence no longer matches current state."""


class OrderTicketCandidatePreflightBlockedError(ValueError):
    """Raised when current action preflight blocks order-shaped candidate creation."""

    def __init__(self, message: str, *, codes: list[str]) -> None:
        super().__init__(message)
        self.codes = codes


@dataclass(frozen=True)
class GovernedOrderTicketCandidateWrite:
    order_ticket_candidate: OrderTicketCandidate
    receipt_ref: str
    execution_allowed: bool = False
    authority_transition: bool = False
    submitted_to_broker: bool = False


def create_governed_order_ticket_candidate(
    *,
    simulation_report_id: str,
    expected_action_intent_receipt_ref: str,
    expected_action_preflight_report_hash: str,
    expected_simulation_report_receipt_ref: str,
    candidate_reason: str,
    explicit_preflight_acknowledgement: bool = False,
    acknowledged_preflight_warning_codes: list[str] | None = None,
    order_shape: dict[str, Any] | None = None,
    source_refs: list[str] | None = None,
    engine: Engine,
    receipt_root: str | Path,
) -> GovernedOrderTicketCandidateWrite:
    """Persist an order-shaped candidate bound to current preflight and simulation evidence."""

    if not candidate_reason.strip():
        raise OrderTicketCandidateValidationError("order ticket candidate requires a reason")
    shape = dict(order_shape or {})
    _require_order_shape_boundary(shape=shape, source_refs=source_refs or [])
    parsed_shape = _parse_order_shape(shape)

    with Session(engine) as session:
        simulation_report = session.get(ActionIntentSimulationReport, simulation_report_id)
        if simulation_report is None:
            raise KeyError(simulation_report_id)
        action_intent = session.get(ActionIntent, simulation_report.action_intent_id)
    if action_intent is None:
        raise KeyError(simulation_report.action_intent_id)

    if simulation_report.receipt_ref != expected_simulation_report_receipt_ref.strip():
        raise OrderTicketCandidateStaleError(
            "simulation report receipt ref does not match expected_simulation_report_receipt_ref"
        )
    if action_intent.receipt_ref != expected_action_intent_receipt_ref.strip():
        raise OrderTicketCandidateStaleError(
            "action intent receipt ref does not match expected_action_intent_receipt_ref"
        )

    preflight = preflight_action_intent(action_intent.action_intent_id, engine=engine)
    if preflight is None:
        raise KeyError(action_intent.action_intent_id)
    expected_hash = expected_action_preflight_report_hash.strip()
    if preflight.report_hash != expected_hash:
        raise OrderTicketCandidateStaleError(
            "action preflight report hash does not match current preflight"
        )
    if simulation_report.source_action_preflight_report_hash != preflight.report_hash:
        raise OrderTicketCandidateStaleError(
            "simulation report is not bound to the current action preflight hash"
        )
    if simulation_report.source_action_intent_receipt_ref != (action_intent.receipt_ref or ""):
        raise OrderTicketCandidateStaleError(
            "simulation report is not bound to the current action intent receipt"
        )
    _require_preflight_allows_candidate(
        preflight=preflight,
        explicit_preflight_acknowledgement=explicit_preflight_acknowledgement,
        acknowledged_warning_codes=acknowledged_preflight_warning_codes or [],
    )

    created_at = _now_utc()
    order_ticket_candidate_id = _safe_id(
        f"order_ticket_candidate_{_revision_stamp()}_{uuid4().hex[:8]}"
    )
    receipt_id = f"receipt_{order_ticket_candidate_id}"
    receipt_path = resolve_under(
        receipt_root,
        "order-ticket-candidates",
        f"{receipt_id}.json",
    )
    receipt_ref = _display_path(receipt_path)
    warning_codes = _warning_codes(preflight)
    validation_findings = _validation_findings(preflight=preflight, shape=parsed_shape)
    final_source_refs = _dedupe_text(
        [
            *simulation_report.source_refs,
            *(source_refs or []),
        ]
    )
    final_receipt_refs = _dedupe_text(
        [
            *_receipt_refs_without_hashes(simulation_report.receipt_refs),
            simulation_report.receipt_ref or "",
            action_intent.receipt_ref or "",
            preflight.current_proposal_receipt_ref or "",
            receipt_ref,
        ]
    )
    order_ticket_candidate = OrderTicketCandidate(
        order_ticket_candidate_id=order_ticket_candidate_id,
        action_intent_id=action_intent.action_intent_id,
        simulation_report_id=simulation_report.simulation_report_id,
        proposal_id=simulation_report.proposal_id,
        source_action_intent_receipt_ref=action_intent.receipt_ref or "",
        source_action_preflight_report_hash=preflight.report_hash,
        source_simulation_report_receipt_ref=simulation_report.receipt_ref or "",
        source_action_preflight_status=preflight.status,
        source_action_preflight_finding_codes=[
            finding.code for finding in preflight.findings
        ],
        acknowledged_preflight_warning_codes=_dedupe_text(
            acknowledged_preflight_warning_codes or []
        ),
        candidate_reason=candidate_reason.strip(),
        instrument_ref=parsed_shape["instrument_ref"],
        symbol_candidate=parsed_shape["symbol_candidate"],
        side_candidate=parsed_shape["side_candidate"],
        quantity_mode=parsed_shape["quantity_mode"],
        notional_cap=parsed_shape["notional_cap"],
        order_type_candidate=parsed_shape["order_type_candidate"],
        time_in_force_candidate=parsed_shape["time_in_force_candidate"],
        account_scope=parsed_shape["account_scope"],
        risk_budget_ref=parsed_shape["risk_budget_ref"],
        candidate_status="needs_authority_contract",
        validation_findings=validation_findings,
        source_refs=final_source_refs,
        receipt_refs=final_receipt_refs,
        preflight_refs=[preflight.report_hash],
        non_claims=list(ORDER_TICKET_CANDIDATE_NON_CLAIMS),
        receipt_ref=receipt_ref,
        execution_allowed=False,
        authority_transition=False,
        submitted_to_broker=False,
        broker_order_id=None,
        execution_status="not_submitted",
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    atomic_write_json(
        receipt_path,
        _receipt_payload(
            order_ticket_candidate=order_ticket_candidate,
            preflight=preflight,
            warning_codes=warning_codes,
        ),
    )
    receipt_index: ReceiptIndex = _receipt_index(
        receipt_id=receipt_id,
        kind="state_core_order_ticket_candidate",
        path=receipt_path,
        created_at_utc=created_at,
        refs=_dedupe_text(
            [
                order_ticket_candidate.order_ticket_candidate_id,
                simulation_report.simulation_report_id,
                action_intent.action_intent_id,
                simulation_report.proposal_id,
                simulation_report.receipt_ref or "",
                action_intent.receipt_ref or "",
                preflight.report_hash,
                *order_ticket_candidate.source_refs,
            ]
        ),
    )
    try:
        write_records([order_ticket_candidate, receipt_index], engine=engine)
    except StateCoreStoreError:
        remove_file_best_effort(receipt_path)
        raise
    return GovernedOrderTicketCandidateWrite(
        order_ticket_candidate=order_ticket_candidate,
        receipt_ref=receipt_ref,
        execution_allowed=False,
        authority_transition=False,
        submitted_to_broker=False,
    )


def _parse_order_shape(shape: dict[str, Any]) -> dict[str, Any]:
    side_candidate = _string_field(shape, "side_candidate", required=True)
    quantity_mode = _string_field(shape, "quantity_mode", default="no_quantity_v0")
    order_type_candidate = _string_field(
        shape,
        "order_type_candidate",
        default="not_specified_v0",
    )
    time_in_force_candidate = _string_field(
        shape,
        "time_in_force_candidate",
        default="not_specified_v0",
    )
    if side_candidate not in ORDER_TICKET_CANDIDATE_SIDES:
        raise OrderTicketCandidateValidationError(
            f"unknown side_candidate: {side_candidate}"
        )
    if quantity_mode not in ORDER_TICKET_CANDIDATE_QUANTITY_MODES:
        raise OrderTicketCandidateValidationError(f"unknown quantity_mode: {quantity_mode}")
    if order_type_candidate not in ORDER_TICKET_CANDIDATE_ORDER_TYPES:
        raise OrderTicketCandidateValidationError(
            f"unknown order_type_candidate: {order_type_candidate}"
        )
    if time_in_force_candidate not in ORDER_TICKET_CANDIDATE_TIME_IN_FORCE:
        raise OrderTicketCandidateValidationError(
            f"unknown time_in_force_candidate: {time_in_force_candidate}"
        )
    return {
        "instrument_ref": _optional_string(shape.get("instrument_ref")),
        "symbol_candidate": _optional_string(shape.get("symbol_candidate")),
        "side_candidate": side_candidate,
        "quantity_mode": quantity_mode,
        "notional_cap": _dict_field(shape, "notional_cap"),
        "order_type_candidate": order_type_candidate,
        "time_in_force_candidate": time_in_force_candidate,
        "account_scope": _dict_field(shape, "account_scope"),
        "risk_budget_ref": _optional_string(shape.get("risk_budget_ref")),
    }


def _require_order_shape_boundary(*, shape: dict[str, Any], source_refs: list[str]) -> None:
    exact_key = _exact_quantity_key(shape)
    if exact_key is not None:
        raise OrderTicketCandidateValidationError(
            f"order_shape cannot carry exact quantity field {exact_key!r} in v0"
        )
    for name, value in (
        ("order_shape", shape),
        ("account_scope", shape.get("account_scope", {})),
        ("notional_cap", shape.get("notional_cap", {})),
    ):
        marker = forbidden_action_intent_marker(value)
        if marker is not None:
            raise OrderTicketCandidateValidationError(
                f"{name} cannot carry broker/execution/authority field {marker!r}"
            )
    for source_ref in source_refs:
        marker = _forbidden_source_ref_marker(source_ref)
        if marker is not None:
            raise OrderTicketCandidateValidationError(
                f"source_refs cannot carry broker/execution marker {marker!r}"
            )


def _exact_quantity_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).strip()
            normalized = key_text.lower().replace("-", "_").replace(" ", "_")
            if normalized in EXACT_QUANTITY_KEYS:
                return key_text
            found = _exact_quantity_key(child)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = _exact_quantity_key(child)
            if found is not None:
                return found
    return None


def _forbidden_source_ref_marker(value: object) -> str | None:
    normalized = str(value).strip().lower().replace("-", "_")
    for marker in FORBIDDEN_TEXT_MARKERS:
        if marker in normalized:
            return marker
    return None


def _require_preflight_allows_candidate(
    *,
    preflight: ActionIntentPreflightReport,
    explicit_preflight_acknowledgement: bool,
    acknowledged_warning_codes: list[str],
) -> None:
    if preflight.status == "block":
        raise OrderTicketCandidatePreflightBlockedError(
            "action preflight blocks order ticket candidate creation",
            codes=[finding.code for finding in preflight.findings if finding.blocks_progression],
        )
    warning_codes = set(_warning_codes(preflight))
    if not warning_codes:
        return
    acknowledged = set(_dedupe_text(acknowledged_warning_codes))
    if not explicit_preflight_acknowledgement:
        raise OrderTicketCandidateValidationError(
            "preflight warnings require explicit_preflight_acknowledgement=true"
        )
    missing = sorted(warning_codes - acknowledged)
    if missing:
        raise OrderTicketCandidateValidationError(
            "preflight warnings are not fully acknowledged: " + ", ".join(missing)
        )


def _warning_codes(preflight: ActionIntentPreflightReport) -> list[str]:
    return _dedupe_text(
        [finding.code for finding in preflight.findings if finding.severity == "warning"]
    )


def _receipt_refs_without_hashes(values: list[str]) -> list[str]:
    return [value for value in values if not str(value).startswith("sha256:")]


def _validation_findings(
    *,
    preflight: ActionIntentPreflightReport,
    shape: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for code in _warning_codes(preflight):
        findings.append(
            {
                "code": code,
                "severity": "warning",
                "source": "action_preflight",
            }
        )
    if not shape["symbol_candidate"] and not shape["instrument_ref"]:
        findings.append(
            {
                "code": "instrument_unresolved",
                "severity": "warning",
                "source": "order_shape",
            }
        )
    return findings


def _string_field(
    shape: dict[str, Any],
    key: str,
    *,
    required: bool = False,
    default: str = "",
) -> str:
    value = shape.get(key, default)
    clean = str(value).strip()
    if required and not clean:
        raise OrderTicketCandidateValidationError(f"order_shape requires {key}")
    return clean


def _optional_string(value: object) -> str | None:
    clean = str(value).strip() if value is not None else ""
    return clean or None


def _dict_field(shape: dict[str, Any], key: str) -> dict[str, Any]:
    value = shape.get(key, {})
    if not isinstance(value, dict):
        raise OrderTicketCandidateValidationError(f"order_shape.{key} must be an object")
    return dict(value)


def _receipt_payload(
    *,
    order_ticket_candidate: OrderTicketCandidate,
    preflight: ActionIntentPreflightReport,
    warning_codes: list[str],
) -> dict[str, Any]:
    return {
        "receipt_id": f"receipt_{order_ticket_candidate.order_ticket_candidate_id}",
        "kind": "state_core_order_ticket_candidate",
        "created_at_utc": order_ticket_candidate.created_at_utc,
        "order_ticket_candidate_id": order_ticket_candidate.order_ticket_candidate_id,
        "action_intent_id": order_ticket_candidate.action_intent_id,
        "simulation_report_id": order_ticket_candidate.simulation_report_id,
        "proposal_id": order_ticket_candidate.proposal_id,
        "source_action_intent_receipt_ref": (
            order_ticket_candidate.source_action_intent_receipt_ref
        ),
        "source_action_preflight_report_hash": (
            order_ticket_candidate.source_action_preflight_report_hash
        ),
        "source_simulation_report_receipt_ref": (
            order_ticket_candidate.source_simulation_report_receipt_ref
        ),
        "source_action_preflight_status": (
            order_ticket_candidate.source_action_preflight_status
        ),
        "source_action_preflight_finding_codes": (
            order_ticket_candidate.source_action_preflight_finding_codes
        ),
        "acknowledged_preflight_warning_codes": (
            order_ticket_candidate.acknowledged_preflight_warning_codes
        ),
        "order_shape_snapshot": {
            "instrument_ref": order_ticket_candidate.instrument_ref,
            "symbol_candidate": order_ticket_candidate.symbol_candidate,
            "side_candidate": order_ticket_candidate.side_candidate,
            "quantity_mode": order_ticket_candidate.quantity_mode,
            "notional_cap": order_ticket_candidate.notional_cap,
            "order_type_candidate": order_ticket_candidate.order_type_candidate,
            "time_in_force_candidate": order_ticket_candidate.time_in_force_candidate,
            "account_scope": order_ticket_candidate.account_scope,
            "risk_budget_ref": order_ticket_candidate.risk_budget_ref,
        },
        "candidate_status": order_ticket_candidate.candidate_status,
        "validation_findings": order_ticket_candidate.validation_findings,
        "order_ticket_candidate": order_ticket_candidate.model_dump(mode="json"),
        "preflight_snapshot": {
            "status": preflight.status,
            "report_hash": preflight.report_hash,
            "warning_codes": warning_codes,
            "finding_codes": [finding.code for finding in preflight.findings],
        },
        "governance": {
            "execution_allowed": False,
            "authority_transition": False,
            "submitted_to_broker": False,
            "broker_order_id": None,
            "execution_status": "not_submitted",
            "candidate_only": True,
            "not_order": True,
            "not_broker_instruction": True,
            "not_execution_authorization": True,
            "requires_authority_contract": True,
            "non_claims": list(ORDER_TICKET_CANDIDATE_NON_CLAIMS),
        },
    }
