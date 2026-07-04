"""Governed CapitalObjectiveFit writes.

CapitalObjectiveFit records whether a TradePlanCandidate appears aligned,
unclear, or conflicted against user capital objectives, risk budget,
liquidity, concentration, reversibility, opportunity cost, alternatives, and
next safe paths. It is explanatory review evidence only: not investment
advice, suitability certification, trade-plan approval, an order ticket,
broker submission, or execution authorization.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import Engine
from sqlmodel import Session

from finharness.action_intent_preflight import preflight_action_intent
from finharness.statecore.action_intents import _dedupe_text, forbidden_action_intent_marker
from finharness.statecore.models import (
    CAPITAL_OBJECTIVE_FIT_ALIGNMENTS,
    ActionIntent,
    ActionIntentSimulationReport,
    CapitalObjectiveFit,
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
from finharness.statecore.trade_plan_review_gates import ORDER_READY_REVIEW_KEYS

CapitalObjectiveAlignment = Literal["aligned", "unclear", "conflicted"]

CAPITAL_OBJECTIVE_FIT_NON_CLAIMS: tuple[str, ...] = (
    "CapitalObjectiveFit is not investment advice.",
    "CapitalObjectiveFit is not suitability certification.",
    "CapitalObjectiveFit is not trade-plan approval.",
    "CapitalObjectiveFit is not an order ticket.",
    "CapitalObjectiveFit is not a broker instruction or broker submission.",
    "CapitalObjectiveFit does not authorize paper or live execution.",
)

OBJECTIVE_FIT_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        *ORDER_READY_REVIEW_KEYS,
        "advice",
        "approval",
        "approval_granted",
        "approved",
        "best_interest_certified",
        "broker",
        "brokerage",
        "execute",
        "execution",
        "investment_advice",
        "order",
        "recommendation",
        "recommended_trade",
        "suitability",
        "suitability_certified",
        "suitable",
        "trade_approved",
    }
)


class CapitalObjectiveFitValidationError(ValueError):
    """Raised when objective-fit input crosses its explanatory boundary."""


class CapitalObjectiveFitStaleError(ValueError):
    """Raised when caller freshness evidence no longer matches current state."""


@dataclass(frozen=True)
class GovernedCapitalObjectiveFitWrite:
    objective_fit: CapitalObjectiveFit
    receipt_ref: str
    execution_allowed: bool = False
    authority_transition: bool = False
    submitted_to_broker: bool = False
    creates_order_ticket: bool = False
    suitability_certified: bool = False
    approval_granted: bool = False


def create_governed_capital_objective_fit(
    *,
    trade_plan_candidate_id: str,
    expected_trade_plan_candidate_receipt_ref: str,
    expected_action_intent_receipt_ref: str,
    expected_action_preflight_report_hash: str,
    expected_simulation_report_receipt_ref: str,
    objective_alignment: CapitalObjectiveAlignment,
    benefit_thesis: str,
    recommended_next_safe_path: str,
    objective_basis: dict[str, Any] | None = None,
    risk_budget_impact: dict[str, Any] | None = None,
    liquidity_impact: dict[str, Any] | None = None,
    concentration_impact: dict[str, Any] | None = None,
    reversibility: dict[str, Any] | None = None,
    opportunity_cost: dict[str, Any] | None = None,
    alternatives_considered: list[dict[str, Any]] | None = None,
    major_uncertainties: list[str] | None = None,
    user_questions: list[str] | None = None,
    source_refs: list[str] | None = None,
    engine: Engine,
    receipt_root: str | Path,
) -> GovernedCapitalObjectiveFitWrite:
    """Persist objective-fit evidence bound to current trade-plan evidence."""

    clean_alignment = str(objective_alignment).strip()
    clean_thesis = benefit_thesis.strip()
    clean_next_path = recommended_next_safe_path.strip()
    clean_objective_basis = dict(objective_basis or {})
    clean_risk_budget_impact = dict(risk_budget_impact or {})
    clean_liquidity_impact = dict(liquidity_impact or {})
    clean_concentration_impact = dict(concentration_impact or {})
    clean_reversibility = dict(reversibility or {})
    clean_opportunity_cost = dict(opportunity_cost or {})
    clean_alternatives = [dict(item) for item in alternatives_considered or []]
    clean_uncertainties = _dedupe_text(list(major_uncertainties or []))
    clean_questions = _dedupe_text(list(user_questions or []))
    clean_source_refs = _dedupe_text(list(source_refs or []))

    _require_objective_fit_fields(
        objective_alignment=clean_alignment,
        benefit_thesis=clean_thesis,
        recommended_next_safe_path=clean_next_path,
        objective_basis=clean_objective_basis,
        risk_budget_impact=clean_risk_budget_impact,
        liquidity_impact=clean_liquidity_impact,
        concentration_impact=clean_concentration_impact,
        reversibility=clean_reversibility,
        opportunity_cost=clean_opportunity_cost,
        alternatives_considered=clean_alternatives,
        major_uncertainties=clean_uncertainties,
        user_questions=clean_questions,
        source_refs=clean_source_refs,
    )

    with Session(engine) as session:
        trade_plan_candidate = session.get(TradePlanCandidate, trade_plan_candidate_id)
        if trade_plan_candidate is None:
            raise KeyError(trade_plan_candidate_id)
        action_intent = session.get(ActionIntent, trade_plan_candidate.action_intent_id)
        simulation_report = session.get(
            ActionIntentSimulationReport,
            trade_plan_candidate.simulation_report_id,
        )
    if action_intent is None:
        raise KeyError(trade_plan_candidate.action_intent_id)
    if simulation_report is None:
        raise KeyError(trade_plan_candidate.simulation_report_id)

    _require_current_evidence(
        trade_plan_candidate=trade_plan_candidate,
        action_intent=action_intent,
        simulation_report=simulation_report,
        expected_trade_plan_candidate_receipt_ref=(expected_trade_plan_candidate_receipt_ref),
        expected_action_intent_receipt_ref=expected_action_intent_receipt_ref,
        expected_action_preflight_report_hash=expected_action_preflight_report_hash,
        expected_simulation_report_receipt_ref=expected_simulation_report_receipt_ref,
        engine=engine,
    )

    created_at = _now_utc()
    objective_fit_id = _safe_id(f"capital_objective_fit_{_revision_stamp()}_{uuid4().hex[:8]}")
    receipt_id = f"receipt_{objective_fit_id}"
    receipt_path = resolve_under(
        receipt_root,
        "capital-objective-fits",
        f"{receipt_id}.json",
    )
    receipt_ref = _display_path(receipt_path)
    receipt_refs = _dedupe_text(
        [
            *_receipt_refs_without_hashes(trade_plan_candidate.receipt_refs),
            trade_plan_candidate.receipt_ref or "",
            trade_plan_candidate.source_simulation_report_receipt_ref,
            trade_plan_candidate.source_action_intent_receipt_ref,
            receipt_ref,
        ]
    )
    objective_fit = CapitalObjectiveFit(
        capital_objective_fit_id=objective_fit_id,
        trade_plan_candidate_id=trade_plan_candidate.trade_plan_candidate_id,
        action_intent_id=trade_plan_candidate.action_intent_id,
        simulation_report_id=trade_plan_candidate.simulation_report_id,
        proposal_id=trade_plan_candidate.proposal_id,
        source_trade_plan_candidate_receipt_ref=trade_plan_candidate.receipt_ref or "",
        source_action_intent_receipt_ref=trade_plan_candidate.source_action_intent_receipt_ref,
        source_action_preflight_report_hash=(
            trade_plan_candidate.source_action_preflight_report_hash
        ),
        source_simulation_report_receipt_ref=(
            trade_plan_candidate.source_simulation_report_receipt_ref
        ),
        objective_alignment=clean_alignment,
        objective_basis=clean_objective_basis,
        benefit_thesis=clean_thesis,
        risk_budget_impact=clean_risk_budget_impact,
        liquidity_impact=clean_liquidity_impact,
        concentration_impact=clean_concentration_impact,
        reversibility=clean_reversibility,
        opportunity_cost=clean_opportunity_cost,
        alternatives_considered=clean_alternatives,
        major_uncertainties=clean_uncertainties,
        user_questions=clean_questions,
        recommended_next_safe_path=clean_next_path,
        source_refs=_dedupe_text([*trade_plan_candidate.source_refs, *clean_source_refs]),
        receipt_refs=receipt_refs,
        preflight_refs=[trade_plan_candidate.source_action_preflight_report_hash],
        non_claims=list(CAPITAL_OBJECTIVE_FIT_NON_CLAIMS),
        receipt_ref=receipt_ref,
        execution_allowed=False,
        authority_transition=False,
        submitted_to_broker=False,
        creates_order_ticket=False,
        suitability_certified=False,
        approval_granted=False,
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    atomic_write_json(
        receipt_path,
        _receipt_payload(
            objective_fit=objective_fit,
            trade_plan_candidate=trade_plan_candidate,
            action_intent=action_intent,
            simulation_report=simulation_report,
        ),
    )
    receipt_index: ReceiptIndex = _receipt_index(
        receipt_id=receipt_id,
        kind="state_core_capital_objective_fit",
        path=receipt_path,
        created_at_utc=created_at,
        refs=_dedupe_text(
            [
                objective_fit.capital_objective_fit_id,
                trade_plan_candidate.trade_plan_candidate_id,
                trade_plan_candidate.action_intent_id,
                trade_plan_candidate.simulation_report_id,
                trade_plan_candidate.proposal_id,
                trade_plan_candidate.receipt_ref or "",
                trade_plan_candidate.source_action_preflight_report_hash,
                *objective_fit.source_refs,
            ]
        ),
    )
    try:
        write_records([objective_fit, receipt_index], engine=engine)
    except StateCoreStoreError:
        remove_file_best_effort(receipt_path)
        raise
    return GovernedCapitalObjectiveFitWrite(
        objective_fit=objective_fit,
        receipt_ref=receipt_ref,
        execution_allowed=False,
        authority_transition=False,
        submitted_to_broker=False,
        creates_order_ticket=False,
        suitability_certified=False,
        approval_granted=False,
    )


def _require_objective_fit_fields(
    *,
    objective_alignment: str,
    benefit_thesis: str,
    recommended_next_safe_path: str,
    objective_basis: dict[str, Any],
    risk_budget_impact: dict[str, Any],
    liquidity_impact: dict[str, Any],
    concentration_impact: dict[str, Any],
    reversibility: dict[str, Any],
    opportunity_cost: dict[str, Any],
    alternatives_considered: list[dict[str, Any]],
    major_uncertainties: list[str],
    user_questions: list[str],
    source_refs: list[str],
) -> None:
    if objective_alignment not in CAPITAL_OBJECTIVE_FIT_ALIGNMENTS:
        raise CapitalObjectiveFitValidationError(
            f"unknown objective alignment: {objective_alignment}"
        )
    if not benefit_thesis or not recommended_next_safe_path:
        raise CapitalObjectiveFitValidationError(
            "capital objective fit requires benefit_thesis and recommended_next_safe_path"
        )
    if objective_alignment in {"unclear", "conflicted"} and not (
        major_uncertainties or user_questions
    ):
        raise CapitalObjectiveFitValidationError(
            "unclear or conflicted objective fits require uncertainties or user questions"
        )
    for label, value in (
        ("benefit_thesis", benefit_thesis),
        ("recommended_next_safe_path", recommended_next_safe_path),
        ("major_uncertainties", major_uncertainties),
        ("user_questions", user_questions),
        ("source_refs", source_refs),
        ("objective_basis", objective_basis),
        ("risk_budget_impact", risk_budget_impact),
        ("liquidity_impact", liquidity_impact),
        ("concentration_impact", concentration_impact),
        ("reversibility", reversibility),
        ("opportunity_cost", opportunity_cost),
        ("alternatives_considered", alternatives_considered),
    ):
        _forbid_objective_fit_markers(label, value)


def _require_current_evidence(
    *,
    trade_plan_candidate: TradePlanCandidate,
    action_intent: ActionIntent,
    simulation_report: ActionIntentSimulationReport,
    expected_trade_plan_candidate_receipt_ref: str,
    expected_action_intent_receipt_ref: str,
    expected_action_preflight_report_hash: str,
    expected_simulation_report_receipt_ref: str,
    engine: Engine,
) -> None:
    if trade_plan_candidate.receipt_ref != expected_trade_plan_candidate_receipt_ref.strip():
        raise CapitalObjectiveFitStaleError(
            "trade plan candidate receipt ref does not match expected receipt"
        )
    if action_intent.receipt_ref != expected_action_intent_receipt_ref.strip():
        raise CapitalObjectiveFitStaleError(
            "action intent receipt ref does not match expected receipt"
        )
    if simulation_report.receipt_ref != expected_simulation_report_receipt_ref.strip():
        raise CapitalObjectiveFitStaleError(
            "simulation report receipt ref does not match expected receipt"
        )
    preflight = preflight_action_intent(action_intent.action_intent_id, engine=engine)
    if preflight is None:
        raise KeyError(action_intent.action_intent_id)
    if preflight.report_hash != expected_action_preflight_report_hash.strip():
        raise CapitalObjectiveFitStaleError(
            "action preflight report hash does not match current preflight"
        )
    if trade_plan_candidate.source_action_preflight_report_hash != preflight.report_hash:
        raise CapitalObjectiveFitStaleError(
            "trade plan candidate is not bound to the current action preflight hash"
        )
    if trade_plan_candidate.source_action_intent_receipt_ref != (action_intent.receipt_ref or ""):
        raise CapitalObjectiveFitStaleError(
            "trade plan candidate is not bound to the current action intent receipt"
        )
    if trade_plan_candidate.source_simulation_report_receipt_ref != (
        simulation_report.receipt_ref or ""
    ):
        raise CapitalObjectiveFitStaleError(
            "trade plan candidate is not bound to the current simulation report receipt"
        )
    if simulation_report.source_action_preflight_report_hash != preflight.report_hash:
        raise CapitalObjectiveFitStaleError(
            "simulation report is not bound to the current action preflight hash"
        )


def _receipt_refs_without_hashes(values: list[str]) -> list[str]:
    return [value for value in values if not str(value).startswith("sha256:")]


def _forbid_objective_fit_markers(label: str, value: Any) -> None:
    marker = _objective_fit_forbidden_marker(value)
    if marker is not None:
        raise CapitalObjectiveFitValidationError(
            f"{label} cannot carry advice/order/approval field {marker!r}"
        )


def _objective_fit_forbidden_marker(value: Any) -> str | None:
    marker = forbidden_action_intent_marker(value)
    if marker is not None:
        return marker
    if isinstance(value, str):
        return _objective_fit_forbidden_text_marker(value)
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key).strip()
            normalized = key_text.lower().replace("-", "_").replace(" ", "_")
            if normalized in OBJECTIVE_FIT_FORBIDDEN_KEYS:
                return key_text
            found = _objective_fit_forbidden_marker(child)
            if found is not None:
                return found
    if isinstance(value, list):
        for child in value:
            found = _objective_fit_forbidden_marker(child)
            if found is not None:
                return found
    return None


def _objective_fit_forbidden_text_marker(value: str) -> str | None:
    tokens = re.findall(r"[a-z0-9]+", value.lower())
    token_set = set(tokens)
    normalized = f"_{'_'.join(tokens)}_"
    for forbidden in OBJECTIVE_FIT_FORBIDDEN_KEYS:
        if "_" not in forbidden and forbidden in token_set:
            return forbidden
        if "_" in forbidden and f"_{forbidden}_" in normalized:
            return forbidden
    return None


def _receipt_payload(
    *,
    objective_fit: CapitalObjectiveFit,
    trade_plan_candidate: TradePlanCandidate,
    action_intent: ActionIntent,
    simulation_report: ActionIntentSimulationReport,
) -> dict[str, Any]:
    return {
        "receipt_id": f"receipt_{objective_fit.capital_objective_fit_id}",
        "kind": "state_core_capital_objective_fit",
        "created_at_utc": objective_fit.created_at_utc,
        "capital_objective_fit_id": objective_fit.capital_objective_fit_id,
        "trade_plan_candidate_id": objective_fit.trade_plan_candidate_id,
        "action_intent_id": objective_fit.action_intent_id,
        "simulation_report_id": objective_fit.simulation_report_id,
        "proposal_id": objective_fit.proposal_id,
        "source_trade_plan_candidate_receipt_ref": (
            objective_fit.source_trade_plan_candidate_receipt_ref
        ),
        "source_action_intent_receipt_ref": (objective_fit.source_action_intent_receipt_ref),
        "source_action_preflight_report_hash": (objective_fit.source_action_preflight_report_hash),
        "source_simulation_report_receipt_ref": (
            objective_fit.source_simulation_report_receipt_ref
        ),
        "objective_alignment": objective_fit.objective_alignment,
        "objective_basis": objective_fit.objective_basis,
        "benefit_thesis": objective_fit.benefit_thesis,
        "risk_budget_impact": objective_fit.risk_budget_impact,
        "liquidity_impact": objective_fit.liquidity_impact,
        "concentration_impact": objective_fit.concentration_impact,
        "reversibility": objective_fit.reversibility,
        "opportunity_cost": objective_fit.opportunity_cost,
        "alternatives_considered": objective_fit.alternatives_considered,
        "major_uncertainties": objective_fit.major_uncertainties,
        "user_questions": objective_fit.user_questions,
        "recommended_next_safe_path": objective_fit.recommended_next_safe_path,
        "capital_objective_fit": objective_fit.model_dump(mode="json"),
        "evidence_snapshot": {
            "trade_plan_candidate_status": trade_plan_candidate.candidate_status,
            "action_intent_receipt_ref": action_intent.receipt_ref,
            "simulation_report_receipt_ref": simulation_report.receipt_ref,
            "preflight_hash": objective_fit.source_action_preflight_report_hash,
            "simulation_status": simulation_report.simulation_status,
        },
        "governance": {
            "execution_allowed": False,
            "authority_transition": False,
            "submitted_to_broker": False,
            "creates_order_ticket": False,
            "suitability_certified": False,
            "approval_granted": False,
            "objective_fit_only": True,
            "not_investment_advice": True,
            "not_trade_plan_approval": True,
            "not_order_ticket": True,
            "not_broker_instruction": True,
            "not_broker_submission": True,
            "not_execution_authorization": True,
            "not_suitability_certification": True,
            "non_claims": list(CAPITAL_OBJECTIVE_FIT_NON_CLAIMS),
        },
    }
