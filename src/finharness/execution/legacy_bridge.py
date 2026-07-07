"""Legacy Action Chain Separation Bridge.

Separates the old ActionIntent chain into:
- execution-relevant facts   → canonical Execution Spine projection
- agentic artifacts          → skill output, evaluator finding, trace, context
- deletion candidates        → old shadow objects ready for removal
- unresolved semantics       → concepts that don't cleanly map

Principle: do NOT migrate the whole legacy chain into execution.
Only execution-relevant facts enter ExecutionOrder / OrderDraft /
ApprovalRecord / PreTradeCheck / ExecutionReport.
Agentic artifacts stay in agentic layers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import Engine
from sqlmodel import Session, select

from finharness.statecore.models import (
    ActionIntent,
    ActionIntentAuthorityBinding,
    ActionIntentSimulationReport,
    CapitalObjectiveFit,
    PaperExecutionReceipt,
    PaperOrderTicketCandidate,
    TradePlanCandidate,
    TradePlanReviewGate,
)


# ── Bridge result types ─────────────────────────────────────────────────────


@dataclass
class ExecutionProjection:
    """Facts that belong in the canonical Execution Spine.

    These are execution facts — not agent reasoning, review memos,
    or permission traces.
    """

    # From PaperOrderTicketCandidate → OrderDraft / ExecutionOrder
    order_draft_projections: list[dict[str, Any]] = field(default_factory=list)
    execution_order_projections: list[dict[str, Any]] = field(default_factory=list)

    # From TradePlanReviewGate → ApprovalRecord
    approval_projections: list[dict[str, Any]] = field(default_factory=list)

    # From ActionIntentSimulationReport → PreTradeCheck findings
    pretrade_findings: list[dict[str, Any]] = field(default_factory=list)

    # From PaperExecutionReceipt → ExecutionReport
    execution_report_projections: list[dict[str, Any]] = field(default_factory=list)

    # From PaperPosition → PositionDelta (via paper execution)
    position_delta_projections: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AgenticArtifact:
    """Artifacts that belong in agentic layers — NOT execution objects."""

    kind: str  # skill_output, evaluator_finding, permission_trace, context, workflow_output, review_memo
    source_object: str  # which legacy model produced this
    source_id: str
    summary: str


@dataclass
class DeletionCandidate:
    """A legacy object or surface ready for deletion once bridged."""

    legacy_id: str
    object_type: str
    reason: str
    superseded_by: str  # what replaces it, or "none"


@dataclass
class UnresolvedSemantic:
    """A concept that doesn't cleanly map to either execution or agentic."""

    source: str
    field_or_concept: str
    issue: str
    recommendation: str


@dataclass
class LegacyExecutionBridgeResult:
    """Full separation result for a proposal's legacy chain."""

    proposal_id: str

    # ── Classical execution facts ──
    execution_projection: ExecutionProjection = field(
        default_factory=ExecutionProjection
    )

    # ── Agentic artifacts (NOT execution objects) ──
    agentic_artifacts: list[AgenticArtifact] = field(default_factory=list)

    # ── Deletion candidates ──
    deletion_candidates: list[DeletionCandidate] = field(default_factory=list)

    # ── Unresolved ──
    unresolved_semantics: list[UnresolvedSemantic] = field(
        default_factory=list
    )


# ── Bridge function ─────────────────────────────────────────────────────────


def separate_legacy_chain(
    proposal_id: str,
    engine: Engine,
) -> LegacyExecutionBridgeResult:
    """Read a proposal's legacy chain and separate into execution / agentic / deletion.

    Returns a LegacyExecutionBridgeResult even when the chain is empty
    or partially populated. Every legacy object is classified.
    """
    result = LegacyExecutionBridgeResult(proposal_id=proposal_id)

    with Session(engine) as session:
        # ── ActionIntent ──
        intents = session.exec(
            select(ActionIntent)
            .where(ActionIntent.proposal_id == proposal_id)
            .order_by(ActionIntent.created_at_utc.desc())
        ).all()

        for intent in intents:
            # ActionIntent is primarily an agentic draft — not an execution object
            result.agentic_artifacts.append(
                AgenticArtifact(
                    kind="context",
                    source_object="ActionIntent",
                    source_id=intent.action_intent_id,
                    summary=f"action draft: {intent.action_type} — {intent.intent_summary[:80]}",
                )
            )
            # Its rationale is context, not broker order state
            result.agentic_artifacts.append(
                AgenticArtifact(
                    kind="context",
                    source_object="ActionIntent.rationale",
                    source_id=intent.action_intent_id,
                    summary=f"rationale: {intent.rationale[:80]}",
                )
            )
            result.deletion_candidates.append(
                DeletionCandidate(
                    legacy_id=intent.action_intent_id,
                    object_type="ActionIntent",
                    reason="agentic draft, not execution object; replaced by OrderDraft as canonical entry point",
                    superseded_by="OrderDraft",
                )
            )

            # ── AuthorityBinding ──
            bindings = session.exec(
                select(ActionIntentAuthorityBinding)
                .where(
                    ActionIntentAuthorityBinding.action_intent_id
                    == intent.action_intent_id
                )
            ).all()
            for b in bindings:
                result.agentic_artifacts.append(
                    AgenticArtifact(
                        kind="evaluator_finding",
                        source_object="ActionIntentAuthorityBinding",
                        source_id=b.binding_id,
                        summary=f"authority check: allowed={b.allowed} author={b.author_type}:{b.author_id}",
                    )
                )
                if b.deny_reasons:
                    result.agentic_artifacts.append(
                        AgenticArtifact(
                            kind="evaluator_finding",
                            source_object="ActionIntentAuthorityBinding.deny_reasons",
                            source_id=b.binding_id,
                            summary=f"deny: {', '.join(b.deny_reasons)}",
                        )
                    )
                result.deletion_candidates.append(
                    DeletionCandidate(
                        legacy_id=b.binding_id,
                        object_type="ActionIntentAuthorityBinding",
                        reason="evaluator finding, not execution object; replaced by PreTradeCheck + evaluator layer",
                        superseded_by="PreTradeCheck",
                    )
                )

            # ── SimulationReport ──
            sims = session.exec(
                select(ActionIntentSimulationReport)
                .where(
                    ActionIntentSimulationReport.action_intent_id
                    == intent.action_intent_id
                )
            ).all()
            for sim in sims:
                # Execution-relevant findings → pretrade findings projection
                if sim.source_action_preflight_finding_codes:
                    for code in sim.source_action_preflight_finding_codes:
                        result.execution_projection.pretrade_findings.append(
                            {
                                "source": "ActionIntentSimulationReport",
                                "source_id": sim.simulation_report_id,
                                "finding_code": code,
                                "preflight_status": sim.source_action_preflight_status,
                            }
                        )
                # The simulation narrative is a workflow output, not execution state
                result.agentic_artifacts.append(
                    AgenticArtifact(
                        kind="workflow_output",
                        source_object="ActionIntentSimulationReport",
                        source_id=sim.simulation_report_id,
                        summary=f"simulation: mode={sim.scenario_mode} status={sim.simulation_status} risk={sim.risk_posture}",
                    )
                )
                result.deletion_candidates.append(
                    DeletionCandidate(
                        legacy_id=sim.simulation_report_id,
                        object_type="ActionIntentSimulationReport",
                        reason="workflow output; execution-relevant findings projected to PreTradeCheck, narrative stays in agentic layer",
                        superseded_by="PreTradeCheck (findings) + workflow trace (narrative)",
                    )
                )

                # ── TradePlanCandidate ──
                plans = session.exec(
                    select(TradePlanCandidate)
                    .where(
                        TradePlanCandidate.simulation_report_id
                        == sim.simulation_report_id
                    )
                ).all()
                for plan in plans:
                    result.agentic_artifacts.append(
                        AgenticArtifact(
                            kind="context",
                            source_object="TradePlanCandidate",
                            source_id=plan.trade_plan_candidate_id,
                            summary=f"plan: direction={plan.plan_direction} reason={plan.plan_reason[:60]}",
                        )
                    )
                    result.deletion_candidates.append(
                        DeletionCandidate(
                            legacy_id=plan.trade_plan_candidate_id,
                            object_type="TradePlanCandidate",
                            reason="planning artifact, not execution object; direction/reason are context for OrderDraft",
                            superseded_by="OrderDraft (context fields)",
                        )
                    )

                    # ── CapitalObjectiveFit ──
                    fits = session.exec(
                        select(CapitalObjectiveFit)
                        .where(
                            CapitalObjectiveFit.trade_plan_candidate_id
                            == plan.trade_plan_candidate_id
                        )
                    ).all()
                    for fit in fits:
                        result.agentic_artifacts.append(
                            AgenticArtifact(
                                kind="skill_output",
                                source_object="CapitalObjectiveFit",
                                source_id=fit.capital_objective_fit_id,
                                summary=f"objective fit: alignment={fit.objective_alignment} thesis={fit.benefit_thesis[:60]}",
                            )
                        )
                        result.unresolved_semantics.append(
                            UnresolvedSemantic(
                                source="CapitalObjectiveFit",
                                field_or_concept="benefit_thesis / risk_budget_impact / alternatives_considered",
                                issue="valuable review context; not execution state, but useful for compliance/audit",
                                recommendation="preserve as review memo trace; do NOT project into ExecutionOrder",
                            )
                        )
                        result.deletion_candidates.append(
                            DeletionCandidate(
                                legacy_id=fit.capital_objective_fit_id,
                                object_type="CapitalObjectiveFit",
                                reason="skill output / review memo, not execution object; preserve as trace",
                                superseded_by="review memo trace (agentic layer)",
                            )
                        )

                    # ── TradePlanReviewGate ──
                    gates = session.exec(
                        select(TradePlanReviewGate)
                        .where(
                            TradePlanReviewGate.trade_plan_candidate_id
                            == plan.trade_plan_candidate_id
                        )
                    ).all()
                    for gate in gates:
                        # Human approval decision → execution projection
                        result.execution_projection.approval_projections.append({
                            "source": "TradePlanReviewGate",
                            "source_id": gate.review_gate_id,
                            "decision": gate.review_decision,
                            "reviewer_id": gate.reviewer_id,
                            "reviewer_type": gate.reviewer_type,
                            "review_reason": gate.review_reason,
                            "may_enter_staging": gate.may_enter_order_ticket_candidate_staging,
                        })
                        result.agentic_artifacts.append(
                            AgenticArtifact(
                                kind="permission_trace",
                                source_object="TradePlanReviewGate",
                                source_id=gate.review_gate_id,
                                summary=f"gate: decision={gate.review_decision} reviewer={gate.reviewer_id}",
                            )
                        )
                        result.deletion_candidates.append(
                            DeletionCandidate(
                                legacy_id=gate.review_gate_id,
                                object_type="TradePlanReviewGate",
                                reason="permission checkpoint; human decision projected to ApprovalRecord, gate itself is trace",
                                superseded_by="ApprovalRecord",
                            )
                        )

                    # ── PaperOrderTicketCandidate ──
                    tickets = session.exec(
                        select(PaperOrderTicketCandidate)
                        .where(
                            PaperOrderTicketCandidate.trade_plan_candidate_id
                            == plan.trade_plan_candidate_id
                        )
                    ).all()
                    for ticket in tickets:
                        # Order-shaped fields → ExecutionOrder projection
                        result.execution_projection.order_draft_projections.append({
                            "source": "PaperOrderTicketCandidate",
                            "source_id": ticket.paper_order_ticket_id,
                            "symbol": ticket.symbol,
                            "side": ticket.side,
                            "order_type": ticket.order_type,
                            "quantity": str(ticket.quantity),
                            "time_in_force": ticket.time_in_force,
                            "limit_price": str(ticket.limit_price)
                            if ticket.limit_price
                            else None,
                            "environment": ticket.environment,
                            "rationale": ticket.ticket_rationale,
                        })
                        result.execution_projection.execution_order_projections.append({
                            "source": "PaperOrderTicketCandidate",
                            "source_id": ticket.paper_order_ticket_id,
                            "status": ticket.candidate_status,
                            "environment": ticket.environment,
                        })
                        result.deletion_candidates.append(
                            DeletionCandidate(
                                legacy_id=ticket.paper_order_ticket_id,
                                object_type="PaperOrderTicketCandidate",
                                reason="shadow ExecutionOrder; order-shaped fields projected to OrderDraft + ExecutionOrder",
                                superseded_by="OrderDraft + ExecutionOrder",
                            )
                        )

                        # ── PaperExecutionReceipt ──
                        paper_reports = session.exec(
                            select(PaperExecutionReceipt)
                            .where(
                                PaperExecutionReceipt.paper_order_ticket_id
                                == ticket.paper_order_ticket_id
                            )
                        ).all()
                        for pr in paper_reports:
                            result.execution_projection.execution_report_projections.append({
                                "source": "PaperExecutionReceipt",
                                "source_id": pr.paper_execution_id,
                                "execution_status": pr.execution_status,
                                "filled_quantity": str(pr.quantity),
                                "fill_price": str(pr.fill_price)
                                if pr.fill_price
                                else None,
                            })
                            result.deletion_candidates.append(
                                DeletionCandidate(
                                    legacy_id=pr.paper_execution_id,
                                    object_type="PaperExecutionReceipt",
                                    reason="shadow ExecutionReport; projected to ExecutionReport",
                                    superseded_by="ExecutionReport",
                                )
                            )

    return result
