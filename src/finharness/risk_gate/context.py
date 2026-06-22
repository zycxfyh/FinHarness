"""Risk-gate context shaping and portfolio-risk evidence helpers."""

from __future__ import annotations

from typing import Any

from finharness.portfolio_risk import (
    RiskfolioAllocationSummary,
    concentration_request_from_allocation,
)
from finharness.proposal import ProposalCandidate, ProposalSnapshot
from finharness.risk_gate.models import RiskGateContext


def normalize_allocation_summary(
    allocation_summary: RiskfolioAllocationSummary | dict[str, Any] | None,
) -> RiskfolioAllocationSummary | None:
    if allocation_summary is None:
        return None
    if isinstance(allocation_summary, RiskfolioAllocationSummary):
        return allocation_summary
    return RiskfolioAllocationSummary(**allocation_summary)


def risk_context_for_candidate(
    *,
    context: RiskGateContext,
    candidate: ProposalCandidate,
    allocation_summary: RiskfolioAllocationSummary | None = None,
) -> RiskGateContext:
    """Apply portfolio-risk evidence to the requested side of the gate only."""

    if allocation_summary is None:
        return context
    requested = concentration_request_from_allocation(allocation_summary, candidate.symbol)
    return context.model_copy(
        update={"requested_symbol_concentration_pct": requested}
    )


def representative_risk_context(
    *,
    context: RiskGateContext,
    proposal_snapshot: ProposalSnapshot,
    allocation_summary: RiskfolioAllocationSummary | None = None,
) -> RiskGateContext:
    """Expose the Riskfolio request in snapshot context for single-symbol runs."""

    if allocation_summary is None:
        return context
    symbols = {candidate.symbol for candidate in proposal_snapshot.candidates}
    if len(symbols) != 1:
        return context
    symbol = next(iter(symbols))
    requested = concentration_request_from_allocation(allocation_summary, symbol)
    return context.model_copy(
        update={"requested_symbol_concentration_pct": requested}
    )


def riskfolio_concentration_evidence_refs(
    *,
    allocation_summary: RiskfolioAllocationSummary | None,
    symbol: str,
    requested_concentration_pct: float,
    max_symbol_concentration_pct: float,
) -> list[str]:
    if allocation_summary is None:
        return []
    return [
        f"portfolio_risk_backend:{allocation_summary.backend}",
        f"riskfolio_symbol:{symbol.upper()}",
        f"riskfolio_requested_symbol_concentration_pct:{requested_concentration_pct:.6f}",
        f"mandate_max_symbol_concentration_pct:{max_symbol_concentration_pct:.6f}",
        (
            "riskfolio_limitation:research suggestion only; mandate cap unchanged; "
            "historical optimizer assumptions"
        ),
    ]
