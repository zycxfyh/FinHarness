"""Governed TradePlanCandidate writes.

TradePlanCandidate is a pre-trade planning artifact. It is downstream of a
preflight-bound qualitative simulation report, but it is not an order ticket,
broker instruction, approval, authority contract, or execution authorization.
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
    TRADE_PLAN_CANDIDATE_DIRECTIONS,
    ActionIntent,
    ActionIntentSimulationReport,
    ReceiptIndex,
    TradePlanCandidate,
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

TradePlanCandidateDirection = Literal[
    "reduce",
    "increase",
    "rebalance",
    "hedge_review",
    "raise_cash",
    "defer",
    "watchlist",
    "request_more_evidence",
]

TRADE_PLAN_CANDIDATE_NON_CLAIMS: tuple[str, ...] = (
    "TradePlanCandidate is not an order ticket.",
    "TradePlanCandidate is not submitted to a broker.",
    "TradePlanCandidate is not approval, attestation, or an authority contract.",
    "TradePlanCandidate does not authorize paper or live execution.",
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
ORDER_READY_KEYS: frozenset[str] = frozenset(
    {
        "broker_order_id",
        "execution_status",
        "fix_tags",
        "limit_price",
        "market_order",
        "order_submit_payload",
        "order_type",
        "route",
        "side",
        "stop_price",
        "submitted_to_broker",
        "time_in_force",
        "tif",
        "venue",
    }
)
FORBIDDEN_TEXT_MARKERS: tuple[str, ...] = (
    "broker",
    "brokerage",
    "execute",
    "execution",
    "order",
    "route",
    "submitted",
    "transfer",
    "venue",
)


class TradePlanCandidateValidationError(ValueError):
    """Raised when a trade plan candidate crosses its candidate-only boundary."""


class TradePlanCandidateStaleError(ValueError):
    """Raised when caller freshness evidence no longer matches current state."""


class TradePlanCandidatePreflightBlockedError(ValueError):
    """Raised when current action preflight blocks trade plan candidate creation."""

    def __init__(self, message: str, *, codes: list[str]) -> None:
        super().__init__(message)
        self.codes = codes


@dataclass(frozen=True)
class GovernedTradePlanCandidateWrite:
    trade_plan_candidate: TradePlanCandidate
    receipt_ref: str
    execution_allowed: bool = False
    authority_transition: bool = False
    submitted_to_broker: bool = False


def create_governed_trade_plan_candidate(
    *,
    simulation_report_id: str,
    expected_action_intent_receipt_ref: str,
    expected_action_preflight_report_hash: str,
    expected_simulation_report_receipt_ref: str,
    plan_reason: str,
    explicit_preflight_acknowledgement: bool = False,
    acknowledged_preflight_warning_codes: list[str] | None = None,
    plan_scope: dict[str, Any] | None = None,
    source_refs: list[str] | None = None,
    engine: Engine,
    receipt_root: str | Path,
) -> GovernedTradePlanCandidateWrite:
    """Persist a pre-trade plan bound to current preflight and simulation evidence."""

    if not plan_reason.strip():
        raise TradePlanCandidateValidationError("trade plan candidate requires a reason")
    scope = dict(plan_scope or {})
    _require_plan_scope_boundary(scope=scope, source_refs=source_refs or [])

    with Session(engine) as session:
        simulation_report = session.get(ActionIntentSimulationReport, simulation_report_id)
        if simulation_report is None:
            raise KeyError(simulation_report_id)
        action_intent = session.get(ActionIntent, simulation_report.action_intent_id)
    if action_intent is None:
        raise KeyError(simulation_report.action_intent_id)

    parsed_scope = _parse_plan_scope(scope, fallback_target_scope=action_intent.target_scope)

    if simulation_report.receipt_ref != expected_simulation_report_receipt_ref.strip():
        raise TradePlanCandidateStaleError(
            "simulation report receipt ref does not match expected_simulation_report_receipt_ref"
        )
    if action_intent.receipt_ref != expected_action_intent_receipt_ref.strip():
        raise TradePlanCandidateStaleError(
            "action intent receipt ref does not match expected_action_intent_receipt_ref"
        )

    preflight = preflight_action_intent(action_intent.action_intent_id, engine=engine)
    if preflight is None:
        raise KeyError(action_intent.action_intent_id)
    expected_hash = expected_action_preflight_report_hash.strip()
    if preflight.report_hash != expected_hash:
        raise TradePlanCandidateStaleError(
            "action preflight report hash does not match current preflight"
        )
    if simulation_report.source_action_preflight_report_hash != preflight.report_hash:
        raise TradePlanCandidateStaleError(
            "simulation report is not bound to the current action preflight hash"
        )
    if simulation_report.source_action_intent_receipt_ref != (action_intent.receipt_ref or ""):
        raise TradePlanCandidateStaleError(
            "simulation report is not bound to the current action intent receipt"
        )
    _require_preflight_allows_candidate(
        preflight=preflight,
        explicit_preflight_acknowledgement=explicit_preflight_acknowledgement,
        acknowledged_warning_codes=acknowledged_preflight_warning_codes or [],
    )

    created_at = _now_utc()
    trade_plan_candidate_id = _safe_id(
        f"trade_plan_candidate_{_revision_stamp()}_{uuid4().hex[:8]}"
    )
    receipt_id = f"receipt_{trade_plan_candidate_id}"
    receipt_path = resolve_under(
        receipt_root,
        "trade-plan-candidates",
        f"{receipt_id}.json",
    )
    receipt_ref = _display_path(receipt_path)
    warning_codes = _warning_codes(preflight)
    validation_findings = _validation_findings(preflight=preflight, scope=parsed_scope)
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
    trade_plan_candidate = TradePlanCandidate(
        trade_plan_candidate_id=trade_plan_candidate_id,
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
        plan_reason=plan_reason.strip(),
        plan_direction=parsed_scope["plan_direction"],
        target_scope=parsed_scope["target_scope"],
        instrument_scope=parsed_scope["instrument_scope"],
        account_scope=parsed_scope["account_scope"],
        risk_constraints=parsed_scope["risk_constraints"],
        notional_cap=parsed_scope["notional_cap"],
        percent_cap=parsed_scope["percent_cap"],
        time_window=parsed_scope["time_window"],
        required_authority_level=parsed_scope["required_authority_level"],
        candidate_status="needs_authority_contract",
        validation_findings=validation_findings,
        source_refs=final_source_refs,
        receipt_refs=final_receipt_refs,
        preflight_refs=[preflight.report_hash],
        non_claims=list(TRADE_PLAN_CANDIDATE_NON_CLAIMS),
        receipt_ref=receipt_ref,
        execution_allowed=False,
        authority_transition=False,
        submitted_to_broker=False,
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    atomic_write_json(
        receipt_path,
        _receipt_payload(
            trade_plan_candidate=trade_plan_candidate,
            preflight=preflight,
            warning_codes=warning_codes,
        ),
    )
    receipt_index: ReceiptIndex = _receipt_index(
        receipt_id=receipt_id,
        kind="state_core_trade_plan_candidate",
        path=receipt_path,
        created_at_utc=created_at,
        refs=_dedupe_text(
            [
                trade_plan_candidate.trade_plan_candidate_id,
                simulation_report.simulation_report_id,
                action_intent.action_intent_id,
                simulation_report.proposal_id,
                simulation_report.receipt_ref or "",
                action_intent.receipt_ref or "",
                preflight.report_hash,
                *trade_plan_candidate.source_refs,
            ]
        ),
    )
    try:
        write_records([trade_plan_candidate, receipt_index], engine=engine)
    except StateCoreStoreError:
        remove_file_best_effort(receipt_path)
        raise
    return GovernedTradePlanCandidateWrite(
        trade_plan_candidate=trade_plan_candidate,
        receipt_ref=receipt_ref,
        execution_allowed=False,
        authority_transition=False,
        submitted_to_broker=False,
    )


def _parse_plan_scope(
    scope: dict[str, Any],
    *,
    fallback_target_scope: dict[str, Any],
) -> dict[str, Any]:
    plan_direction = _string_field(scope, "plan_direction", required=True)
    if plan_direction not in TRADE_PLAN_CANDIDATE_DIRECTIONS:
        raise TradePlanCandidateValidationError(
            f"unknown plan_direction: {plan_direction}"
        )
    target_scope = _dict_field(scope, "target_scope", default=fallback_target_scope)
    return {
        "plan_direction": plan_direction,
        "target_scope": target_scope,
        "instrument_scope": _dict_field(scope, "instrument_scope"),
        "account_scope": _dict_field(scope, "account_scope"),
        "risk_constraints": _dict_field(scope, "risk_constraints"),
        "notional_cap": _dict_field(scope, "notional_cap"),
        "percent_cap": _dict_field(scope, "percent_cap"),
        "time_window": _dict_field(scope, "time_window"),
        "required_authority_level": _string_field(
            scope,
            "required_authority_level",
            default="authority_contract_required",
        ),
    }


def _require_plan_scope_boundary(*, scope: dict[str, Any], source_refs: list[str]) -> None:
    exact_key = _exact_quantity_key(scope)
    if exact_key is not None:
        raise TradePlanCandidateValidationError(
            f"plan_scope cannot carry exact quantity field {exact_key!r} in v0"
        )
    order_key = _order_ready_key(scope)
    if order_key is not None:
        raise TradePlanCandidateValidationError(
            f"plan_scope cannot carry order-ready field {order_key!r} in v0"
        )
    for name, value in (
        ("plan_scope", scope),
        ("account_scope", scope.get("account_scope", {})),
        ("risk_constraints", scope.get("risk_constraints", {})),
        ("notional_cap", scope.get("notional_cap", {})),
        ("percent_cap", scope.get("percent_cap", {})),
        ("time_window", scope.get("time_window", {})),
    ):
        marker = forbidden_action_intent_marker(value)
        if marker is not None:
            raise TradePlanCandidateValidationError(
                f"{name} cannot carry broker/execution/authority field {marker!r}"
            )
    for source_ref in source_refs:
        marker = _forbidden_source_ref_marker(source_ref)
        if marker is not None:
            raise TradePlanCandidateValidationError(
                f"source_refs cannot carry broker/execution/order marker {marker!r}"
            )


def _exact_quantity_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).strip()
            normalized = _normalized_key(key_text)
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


def _order_ready_key(value: Any) -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).strip()
            normalized = _normalized_key(key_text)
            if normalized in ORDER_READY_KEYS:
                return key_text
            found = _order_ready_key(child)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = _order_ready_key(child)
            if found is not None:
                return found
    return None


def _normalized_key(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


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
        raise TradePlanCandidatePreflightBlockedError(
            "action preflight blocks trade plan candidate creation",
            codes=[finding.code for finding in preflight.findings if finding.blocks_progression],
        )
    warning_codes = set(_warning_codes(preflight))
    if not warning_codes:
        return
    acknowledged = set(_dedupe_text(acknowledged_warning_codes))
    if not explicit_preflight_acknowledgement:
        raise TradePlanCandidateValidationError(
            "preflight warnings require explicit_preflight_acknowledgement=true"
        )
    missing = sorted(warning_codes - acknowledged)
    if missing:
        raise TradePlanCandidateValidationError(
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
    scope: dict[str, Any],
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
    instrument_scope = scope["instrument_scope"]
    if not instrument_scope:
        findings.append(
            {
                "code": "instrument_scope_unresolved",
                "severity": "warning",
                "source": "plan_scope",
            }
        )
    return findings


def _string_field(
    scope: dict[str, Any],
    key: str,
    *,
    required: bool = False,
    default: str = "",
) -> str:
    value = scope.get(key, default)
    clean = str(value).strip()
    if required and not clean:
        raise TradePlanCandidateValidationError(f"plan_scope requires {key}")
    return clean


def _dict_field(
    scope: dict[str, Any],
    key: str,
    *,
    default: dict[str, Any] | None = None,
) -> dict[str, Any]:
    value = scope.get(key, default or {})
    if not isinstance(value, dict):
        raise TradePlanCandidateValidationError(f"plan_scope.{key} must be an object")
    return dict(value)


def _receipt_payload(
    *,
    trade_plan_candidate: TradePlanCandidate,
    preflight: ActionIntentPreflightReport,
    warning_codes: list[str],
) -> dict[str, Any]:
    return {
        "receipt_id": f"receipt_{trade_plan_candidate.trade_plan_candidate_id}",
        "kind": "state_core_trade_plan_candidate",
        "created_at_utc": trade_plan_candidate.created_at_utc,
        "trade_plan_candidate_id": trade_plan_candidate.trade_plan_candidate_id,
        "action_intent_id": trade_plan_candidate.action_intent_id,
        "simulation_report_id": trade_plan_candidate.simulation_report_id,
        "proposal_id": trade_plan_candidate.proposal_id,
        "source_action_intent_receipt_ref": (
            trade_plan_candidate.source_action_intent_receipt_ref
        ),
        "source_action_preflight_report_hash": (
            trade_plan_candidate.source_action_preflight_report_hash
        ),
        "source_simulation_report_receipt_ref": (
            trade_plan_candidate.source_simulation_report_receipt_ref
        ),
        "source_action_preflight_status": (
            trade_plan_candidate.source_action_preflight_status
        ),
        "source_action_preflight_finding_codes": (
            trade_plan_candidate.source_action_preflight_finding_codes
        ),
        "acknowledged_preflight_warning_codes": (
            trade_plan_candidate.acknowledged_preflight_warning_codes
        ),
        "plan_scope_snapshot": {
            "plan_direction": trade_plan_candidate.plan_direction,
            "target_scope": trade_plan_candidate.target_scope,
            "instrument_scope": trade_plan_candidate.instrument_scope,
            "account_scope": trade_plan_candidate.account_scope,
            "risk_constraints": trade_plan_candidate.risk_constraints,
            "notional_cap": trade_plan_candidate.notional_cap,
            "percent_cap": trade_plan_candidate.percent_cap,
            "time_window": trade_plan_candidate.time_window,
            "required_authority_level": trade_plan_candidate.required_authority_level,
        },
        "candidate_status": trade_plan_candidate.candidate_status,
        "validation_findings": trade_plan_candidate.validation_findings,
        "trade_plan_candidate": trade_plan_candidate.model_dump(mode="json"),
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
            "candidate_only": True,
            "not_order_ticket": True,
            "not_broker_instruction": True,
            "not_execution_authorization": True,
            "requires_authority_contract": True,
            "non_claims": list(TRADE_PLAN_CANDIDATE_NON_CLAIMS),
        },
    }
