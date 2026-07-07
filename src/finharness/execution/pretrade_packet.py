"""PreTradePacket — read-only aggregate view over the action-intent chain.

A PreTradePacket assembles a proposal's action chain into a single coherent
view without modifying any existing object, schema, receipt, or route. It is
the first step in reclassifying the action chain's complexity from
Object-heavy to Evaluator / Workflow / Permission layers.

Constraints:
    - Read-only: no StateCore writes, no receipt creation, no API routes.
    - No schema change: uses existing SQLModel tables as-is.
    - Graceful degradation: represents missing, partial, and complete chains.
    - execution_allowed is always False.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import Engine
from sqlmodel import Session, select

from finharness.statecore.models import (
    ActionIntent,
    ActionIntentAuthorityBinding,
    ActionIntentSimulationReport,
    CapitalObjectiveFit,
    PaperOrderTicketCandidate,
    TradePlanCandidate,
    TradePlanReviewGate,
)

# ── Section types ────────────────────────────────────────────────────────────


@dataclass
class ActionDraftView:
    """A shallow, non-authoritative view of an ActionIntent for the packet."""

    action_intent_id: str
    action_type: str
    intent_summary: str
    rationale: str
    status: str
    expected_next_step: str
    created_by: str
    receipt_ref: str | None = None
    created_at_utc: str = ""


@dataclass
class AuthorityFinding:
    """A single authority-binding result re-expressed as an evaluator finding."""

    binding_id: str
    author_type: str
    author_id: str
    allowed: bool
    deny_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    receipt_ref: str | None = None


PreflightStatus = Literal["pass", "warn", "block", "missing"]


@dataclass
class SimulationSection:
    """Key fields from an ActionIntentSimulationReport."""

    simulation_report_id: str
    scenario_mode: str
    simulation_status: str
    risk_posture: str
    risk_direction: str
    qualitative_impact: dict[str, Any] = field(default_factory=dict)
    missing_data: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    receipt_ref: str | None = None


@dataclass
class TradePlanSection:
    """Key fields from a TradePlanCandidate."""

    trade_plan_candidate_id: str
    plan_direction: str
    plan_reason: str
    candidate_status: str
    target_scope: dict[str, Any] = field(default_factory=dict)
    notional_cap: dict[str, Any] = field(default_factory=dict)
    required_authority_level: str = ""
    validation_findings: list[dict[str, Any]] = field(default_factory=list)
    receipt_ref: str | None = None


@dataclass
class ObjectiveFitSection:
    """Key fields from a CapitalObjectiveFit."""

    capital_objective_fit_id: str
    objective_alignment: str
    benefit_thesis: str
    recommended_next_safe_path: str
    risk_budget_impact: dict[str, Any] = field(default_factory=dict)
    liquidity_impact: dict[str, Any] = field(default_factory=dict)
    major_uncertainties: list[str] = field(default_factory=list)
    alternatives_considered: list[dict[str, Any]] = field(default_factory=list)
    receipt_ref: str | None = None


@dataclass
class ApprovalSection:
    """Key fields from a TradePlanReviewGate."""

    review_gate_id: str
    review_decision: str
    reviewer_type: str
    rationale: str = ""
    receipt_ref: str | None = None


@dataclass
class PaperStatusSection:
    """Key fields from a PaperOrderTicketCandidate."""

    paper_ticket_id: str
    side: str
    order_type: str
    status: str
    symbol: str = ""
    quantity: str = ""
    receipt_ref: str | None = None


# ── Aggregate view ───────────────────────────────────────────────────────────


@dataclass
class PreTradePacket:
    """Read-only aggregate view of a proposal's action-intent chain.

    Assembles ActionIntent, AuthorityBinding, SimulationReport,
    TradePlanCandidate, CapitalObjectiveFit, TradePlanReviewGate, and
    PaperOrderTicketCandidate into a single coherent view.

    This is a read model bridge — it does not modify any existing object,
    schema, receipt, or route.
    """

    proposal_id: str
    action_draft: ActionDraftView | None = None
    authority_findings: list[AuthorityFinding] = field(default_factory=list)
    preflight_status: PreflightStatus = "missing"
    simulation: SimulationSection | None = None
    plan: TradePlanSection | None = None
    objective_fit: ObjectiveFitSection | None = None
    approval: ApprovalSection | None = None
    paper_status: PaperStatusSection | None = None
    next_allowed_actions: list[str] = field(default_factory=list)
    execution_allowed: Literal[False] = False


# ── Builder ──────────────────────────────────────────────────────────────────


def build_pretrade_packet(
    proposal_id: str,
    engine: Engine,
) -> PreTradePacket:
    """Build a PreTradePacket by reading the existing action chain.

    Returns a valid packet even when the chain is incomplete or empty.
    All sections are optional; only proposal_id is guaranteed.

    Raises no exceptions on missing data — every query failure or missing
    row produces a ``None`` section or empty list.
    """
    packet = PreTradePacket(proposal_id=proposal_id)

    with Session(engine) as session:
        # ── ActionIntent ──
        action_intents = session.exec(
            select(ActionIntent)
            .where(ActionIntent.proposal_id == proposal_id)
            .order_by(ActionIntent.created_at_utc.desc())
        ).all()

        if action_intents:
            latest = action_intents[0]
            packet.action_draft = ActionDraftView(
                action_intent_id=latest.action_intent_id,
                action_type=latest.action_type,
                intent_summary=latest.intent_summary,
                rationale=latest.rationale,
                status=latest.status,
                expected_next_step=latest.expected_next_step,
                created_by=latest.created_by,
                receipt_ref=latest.receipt_ref,
                created_at_utc=latest.created_at_utc,
            )

            # ── Authority bindings (for the latest action intent) ──
            bindings = session.exec(
                select(ActionIntentAuthorityBinding)
                .where(
                    ActionIntentAuthorityBinding.action_intent_id
                    == latest.action_intent_id
                )
                .order_by(ActionIntentAuthorityBinding.created_at_utc.desc())
            ).all()
            for b in bindings:
                packet.authority_findings.append(
                    AuthorityFinding(
                        binding_id=b.binding_id,
                        author_type=b.author_type,
                        author_id=b.author_id,
                        allowed=b.allowed,
                        deny_reasons=list(b.deny_reasons),
                        warnings=list(b.warnings),
                        receipt_ref=b.receipt_ref,
                    )
                )

            # Derive preflight_status from authority findings
            if bindings:
                if all(b.allowed for b in bindings):
                    packet.preflight_status = "pass"
                elif any(b.allowed for b in bindings):
                    packet.preflight_status = "warn"
                else:
                    packet.preflight_status = "block"

            # ── SimulationReport (latest for this action intent) ──
            sim_reports = session.exec(
                select(ActionIntentSimulationReport)
                .where(
                    ActionIntentSimulationReport.action_intent_id
                    == latest.action_intent_id
                )
                .order_by(
                    ActionIntentSimulationReport.created_at_utc.desc()
                )
            ).all()
            latest_sim = sim_reports[0] if sim_reports else None
            if latest_sim:
                packet.simulation = SimulationSection(
                    simulation_report_id=latest_sim.simulation_report_id,
                    scenario_mode=latest_sim.scenario_mode,
                    simulation_status=latest_sim.simulation_status,
                    risk_posture=latest_sim.risk_posture,
                    risk_direction=latest_sim.risk_direction,
                    qualitative_impact=dict(latest_sim.qualitative_impact),
                    missing_data=list(latest_sim.missing_data),
                    next_actions=list(latest_sim.next_actions),
                    receipt_ref=latest_sim.receipt_ref,
                )

                # ── TradePlanCandidate (latest for this sim report) ──
                plans = session.exec(
                    select(TradePlanCandidate)
                    .where(
                        TradePlanCandidate.simulation_report_id
                        == latest_sim.simulation_report_id
                    )
                    .order_by(TradePlanCandidate.created_at_utc.desc())
                ).all()
                latest_plan = plans[0] if plans else None
                if latest_plan:
                    packet.plan = TradePlanSection(
                        trade_plan_candidate_id=latest_plan.trade_plan_candidate_id,
                        plan_direction=latest_plan.plan_direction,
                        plan_reason=latest_plan.plan_reason,
                        candidate_status=latest_plan.candidate_status,
                        target_scope=dict(latest_plan.target_scope),
                        notional_cap=dict(latest_plan.notional_cap),
                        required_authority_level=latest_plan.required_authority_level,
                        validation_findings=list(latest_plan.validation_findings),
                        receipt_ref=latest_plan.receipt_ref,
                    )

                    # ── CapitalObjectiveFit ──
                    fits = session.exec(
                        select(CapitalObjectiveFit)
                        .where(
                            CapitalObjectiveFit.trade_plan_candidate_id
                            == latest_plan.trade_plan_candidate_id
                        )
                        .order_by(CapitalObjectiveFit.created_at_utc.desc())
                    ).all()
                    latest_fit = fits[0] if fits else None
                    if latest_fit:
                        packet.objective_fit = ObjectiveFitSection(
                            capital_objective_fit_id=latest_fit.capital_objective_fit_id,
                            objective_alignment=latest_fit.objective_alignment,
                            benefit_thesis=latest_fit.benefit_thesis,
                            recommended_next_safe_path=latest_fit.recommended_next_safe_path,
                            risk_budget_impact=dict(latest_fit.risk_budget_impact),
                            liquidity_impact=dict(latest_fit.liquidity_impact),
                            major_uncertainties=list(latest_fit.major_uncertainties),
                            alternatives_considered=list(latest_fit.alternatives_considered),
                            receipt_ref=latest_fit.receipt_ref,
                        )

                    # ── TradePlanReviewGate ──
                    gates = session.exec(
                        select(TradePlanReviewGate)
                        .where(
                            TradePlanReviewGate.trade_plan_candidate_id
                            == latest_plan.trade_plan_candidate_id
                        )
                        .order_by(TradePlanReviewGate.created_at_utc.desc())
                    ).all()
                    latest_gate = gates[0] if gates else None
                    if latest_gate:
                        packet.approval = ApprovalSection(
                            review_gate_id=latest_gate.review_gate_id,
                            review_decision=latest_gate.review_decision,
                            reviewer_type=latest_gate.reviewer_type,
                            rationale=latest_gate.review_reason,
                            receipt_ref=latest_gate.receipt_ref,
                        )

                    # ── PaperOrderTicket ──
                    tickets = session.exec(
                        select(PaperOrderTicketCandidate)
                        .where(
                            PaperOrderTicketCandidate.trade_plan_candidate_id
                            == latest_plan.trade_plan_candidate_id
                        )
                        .order_by(
                            PaperOrderTicketCandidate.created_at_utc.desc()
                        )
                    ).all()
                    latest_ticket = tickets[0] if tickets else None
                    if latest_ticket:
                        packet.paper_status = PaperStatusSection(
                            paper_ticket_id=latest_ticket.paper_order_ticket_id,
                            side=latest_ticket.side,
                            order_type=latest_ticket.order_type,
                            status=latest_ticket.candidate_status,
                            symbol=latest_ticket.symbol,
                            quantity=str(latest_ticket.quantity)
                            if latest_ticket.quantity
                            else "",
                            receipt_ref=latest_ticket.receipt_ref,
                        )

    # Compute next_allowed_actions based on chain completeness
    packet.next_allowed_actions = _compute_next_actions(packet)
    return packet


def _compute_next_actions(packet: PreTradePacket) -> list[str]:
    """Determine which downstream actions are sensible given the chain state."""
    actions: list[str] = []

    if packet.action_draft is None:
        actions.append("create_action_intent")
        return actions

    if not packet.authority_findings:
        actions.append("create_authority_binding")
    if packet.preflight_status == "block":
        return actions

    if packet.simulation is None:
        actions.append("create_simulation_report")
        return actions

    if packet.plan is None:
        actions.append("create_trade_plan_candidate")
        return actions

    if packet.objective_fit is None:
        actions.append("create_capital_objective_fit")
    if packet.approval is None:
        actions.append("create_review_gate")
    if packet.paper_status is None:
        actions.append("create_paper_order_ticket")

    return actions
