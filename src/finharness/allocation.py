"""Capital allocation candidates over the exposure map (north star 阶段 3 中台).

Pure, read-only generation of governed *candidates* from the 阶段 2 exposure map.
A candidate is descriptive evidence-organization, never execution: it carries a
claim, the trigger evidence, assumptions, limitations, explicit options
(do-nothing always included), key risks, and a reversibility note. It then flows
through the existing governed-proposal path (``statecore/proposals.py``) so it
shows up in ``/proposals`` and can be human-attested - no new endpoint or view.

Precision discipline: ``ExposureReport`` is float at its boundary, so the money
figures and trigger metrics in evidence are **display rollups**, labelled
descriptive and carried with ``source_refs`` (snapshot + as-of) for exact
reconstruction from the state core. They are not presented as exact, reconcilable
amounts; exact money lives in the state core, not in these candidates.

Reversibility ordering (north star 可逆 line): directing future cashflow (flow) is
cheaper and more reversible than selling existing holdings (stock, taxable, less
reversible), so flow options are listed before stock options and stock options are
flagged for human review.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import Engine

from finharness.exposure import ExposureReport, compute_exposure
from finharness.market_data import ROOT
from finharness.research_enrichment import NoopResearchEnricher, ResearchEnricher
from finharness.statecore.observations import ObservationThresholds
from finharness.statecore.proposals import GovernedProposalWrite, create_governed_proposal

DEFAULT_ALLOCATION_RECEIPT_ROOT = ROOT / "data" / "receipts" / "state-core"

CANDIDATE_NON_CLAIMS = (
    "Capital allocation candidate: descriptive evidence, not advice.",
    "Not investment, tax, or accounting advice; not a recommendation to trade.",
    "Do-nothing is always a valid option with its stated cost.",
    "Trigger metrics are descriptive (float); reconstruct exact figures from source_refs.",
    "Not execution authorization.",
)

def _refs(*groups: tuple[str, ...]) -> list[str]:
    """Merge per-domain provenance into a minimal, deduped, sorted ref list."""
    merged: set[str] = set()
    for group in groups:
        merged.update(group)
    return sorted(merged)


OptionKind = Literal["do_nothing", "flow", "stock"]


class CandidateOption(BaseModel):
    kind: OptionKind
    label: str
    cost: str
    reversibility: str


class AllocationCandidate(BaseModel):
    detector_kind: str
    dimension: Literal["stock", "flow"]
    claim: str
    evidence: dict[str, Any]
    assumptions: tuple[str, ...]
    limitations: tuple[str, ...]
    options: tuple[CandidateOption, ...]
    key_risks: tuple[str, ...]
    reversibility: str
    research_evidence: tuple[Any, ...] = ()
    execution_allowed: bool = False


def _cash_buffer_candidate(
    report: ExposureReport,
    thresholds: ObservationThresholds,
) -> AllocationCandidate | None:
    # Without a portfolio snapshot, cash_total is an unverified 0; do not assert a
    # runway claim that the candidate's own source_refs cannot reconstruct.
    if not report.cash_total_verified:
        return None
    runway = report.cash_runway_months
    target = thresholds.cash_runway_target_months
    if runway is None or runway >= target:
        return None
    options = (
        CandidateOption(
            kind="do_nothing",
            label="Do nothing",
            cost=f"Liquidity stays thin: about {runway:.1f} months of cover if income stops.",
            reversibility="Fully reversible (no action taken).",
        ),
        CandidateOption(
            kind="flow",
            label="Pause new investing; direct surplus cashflow to the cash buffer",
            cost="Slower investment contributions until the buffer is rebuilt.",
            reversibility="Reversible: resume investing once the buffer is restored.",
        ),
        CandidateOption(
            kind="stock",
            label="Trim a high-concentration holding to rebuild cash (human review)",
            cost="May realize gains/taxes and lock in market timing.",
            reversibility="Less reversible: selling is taxable and re-entry is uncertain.",
        ),
    )
    evidence = {
        "cash_runway_months": runway,
        "target_months": target,
        "cash_total": report.cash_total,
        "monthly_net_cashflow": report.monthly_net_cashflow,
        "as_of_date": report.as_of_date,
        "metric_precision": "float_descriptive; reconstruct exact via source_refs",
        "source_refs": _refs(report.provenance.cash, report.provenance.cashflow),
    }
    return AllocationCandidate(
        detector_kind="cash_buffer_low",
        dimension="flow",
        claim=(
            f"Cash covers {runway:.1f} months of expenses, below the "
            f"{target:.0f}-month emergency-fund target."
        ),
        evidence=evidence,
        assumptions=(
            "Recurring monthly cashflows represent ongoing burn.",
            "Cash holdings are liquid and available for the buffer.",
        ),
        limitations=(
            "Runway uses recurring monthly cashflows only; one-off events excluded.",
            "Figures are display floats; exact money lives in the state core (source_refs).",
        ),
        options=options,
        key_risks=("A near-term income or expense shock could exhaust the buffer.",),
        reversibility=(
            "Flow options are reversible; the stock option (selling) is taxable and "
            "less reversible, so it is flagged for human review."
        ),
    )


def _concentration_candidate(
    report: ExposureReport,
    thresholds: ObservationThresholds,
) -> AllocationCandidate | None:
    if report.holding_count == 0 or not report.holdings:
        return None
    weight = report.top_holding_weight
    threshold = thresholds.concentration_pct
    if weight < threshold:
        return None
    top = report.holdings[0]
    options = (
        CandidateOption(
            kind="do_nothing",
            label="Do nothing",
            cost=f"Single-name risk persists at about {weight:.0%} of the invested book.",
            reversibility="Fully reversible (no action taken).",
        ),
        CandidateOption(
            kind="flow",
            label="Direct new cashflow to other assets to dilute concentration over time",
            cost="Concentration falls slowly; depends on the size of future inflows.",
            reversibility="Reversible: only future contributions are redirected.",
        ),
        CandidateOption(
            kind="stock",
            label=f"Trim {top.symbol} in tranches (human review)",
            cost="May realize gains/taxes and lock in market timing.",
            reversibility="Less reversible: selling is taxable and re-entry is uncertain.",
        ),
    )
    evidence = {
        "top_symbol": top.symbol,
        "top_holding_weight": weight,
        "concentration_threshold": report.concentration_threshold,
        "concentration_hhi": report.concentration_hhi,
        "holding_count": report.holding_count,
        "as_of_date": report.as_of_date,
        "metric_precision": "float_descriptive; reconstruct exact via source_refs",
        "source_refs": _refs(report.provenance.portfolio, report.provenance.cash),
    }
    return AllocationCandidate(
        detector_kind="concentration_high",
        dimension="stock",
        claim=(
            f"{top.symbol} is {weight:.0%} of the invested (non-cash) book, above the "
            f"{threshold:.0%} concentration flag."
        ),
        evidence=evidence,
        assumptions=(
            "The latest portfolio snapshot reflects current holdings.",
            "Concentration is measured over the invested (non-cash) long book.",
        ),
        limitations=(
            "Single-asset concentration only; sector/factor overlap not measured.",
            "Figures are display floats; exact values live in the state core (source_refs).",
        ),
        options=options,
        key_risks=(
            "A single-name drawdown drives an outsized share of total loss.",
            "Selling to de-concentrate may trigger taxes and timing risk.",
        ),
        reversibility=(
            "Flow options are reversible; the stock option (selling) is taxable and "
            "less reversible, so it is flagged for human review."
        ),
    )


def _cash_overweight_candidate(
    report: ExposureReport,
    thresholds: ObservationThresholds,
) -> AllocationCandidate | None:
    if report.total_assets <= 0 or report.cash_total <= 0:
        return None
    runway = report.cash_runway_months
    if runway is None or runway < thresholds.cash_runway_target_months:
        return None
    cash_weight = report.cash_total / report.total_assets
    threshold = thresholds.cash_overweight_pct
    if cash_weight < threshold:
        return None
    options = (
        CandidateOption(
            kind="do_nothing",
            label="Do nothing",
            cost=(
                f"Keep about {cash_weight:.0%} of assets in cash; liquidity stays high, "
                "but inflation/opportunity-cost drag may persist."
            ),
            reversibility="Fully reversible (no action taken).",
        ),
        CandidateOption(
            kind="flow",
            label="Route future surplus by a written target before adding more idle cash",
            cost="Requires maintaining a target policy and revisiting it as goals change.",
            reversibility="Reversible: only future contributions are redirected.",
        ),
        CandidateOption(
            kind="stock",
            label="Move excess cash in tranches toward goals, debt, or investments (human review)",
            cost=(
                "Reduces optionality and may create market, liquidity, tax, or debt-prepayment "
                "trade-offs."
            ),
            reversibility=(
                "Less reversible: once cash is invested, spent, or paid into debt, returning "
                "to cash can have costs or timing risk."
            ),
        ),
    )
    evidence = {
        "cash_weight": cash_weight,
        "cash_overweight_threshold": threshold,
        "cash_total": report.cash_total,
        "total_assets": report.total_assets,
        "cash_runway_months": runway,
        "target_months": thresholds.cash_runway_target_months,
        "as_of_date": report.as_of_date,
        "metric_precision": "float_descriptive; reconstruct exact via source_refs",
        "source_refs": _refs(
            report.provenance.portfolio,
            report.provenance.cash,
            report.provenance.cashflow,
        ),
    }
    return AllocationCandidate(
        detector_kind="cash_overweight",
        dimension="stock",
        claim=(
            f"Cash is {cash_weight:.0%} of assets and covers {runway:.1f} months of "
            f"expenses, above the {threshold:.0%} cash-overweight review flag."
        ),
        evidence=evidence,
        assumptions=(
            "The emergency cash buffer is already at or above target.",
            "No known near-term obligation requires the excess cash.",
        ),
        limitations=(
            "No personal risk tolerance, goal priority, or spending volatility model is applied.",
            "Figures are display floats; exact values live in the state core (source_refs).",
        ),
        options=options,
        key_risks=(
            "Holding excess cash can create inflation and opportunity-cost drag.",
            "Deploying cash too aggressively can weaken liquidity for unknown obligations.",
        ),
        reversibility=(
            "Flow options are most reversible; moving existing cash into goals, debt, or "
            "investments is less reversible and requires human review."
        ),
    )


def _rate_exposure_candidate(
    report: ExposureReport,
    thresholds: ObservationThresholds,
) -> AllocationCandidate | None:
    rate = report.weighted_avg_interest_rate
    if rate is None or report.interest_bearing_debt_total <= 0:
        return None
    threshold = thresholds.high_interest_rate_pct
    if rate < threshold:
        return None
    debt = report.interest_bearing_debt_total
    annual = report.annual_interest_estimate
    options = (
        CandidateOption(
            kind="do_nothing",
            label="Do nothing",
            cost=f"Keep paying about {annual:,.0f}/yr at {rate:.1%} on {debt:,.0f} of debt.",
            reversibility="Fully reversible (no action taken).",
        ),
        CandidateOption(
            kind="flow",
            label="Direct surplus cashflow to extra principal on the highest-rate debt",
            cost="Funds become illiquid in the loan; reduces the cash available to invest/save.",
            reversibility=(
                "Low-risk: cuts a near-guaranteed interest cost; principal is not refundable."
            ),
        ),
        CandidateOption(
            kind="stock",
            label="Refinance or consolidate to a lower rate (human review)",
            cost="May carry closing costs/fees; depends on credit and prevailing rates.",
            reversibility="Less reversible: refinancing is a new contract with its own terms.",
        ),
    )
    evidence = {
        "interest_bearing_debt_total": debt,
        "weighted_avg_interest_rate": rate,
        "annual_interest_estimate": annual,
        "threshold": threshold,
        "as_of_date": report.as_of_date,
        "metric_precision": "float_descriptive; reconstruct exact via source_refs",
        "source_refs": _refs(report.provenance.liability),
    }
    return AllocationCandidate(
        detector_kind="rate_exposure_high",
        dimension="stock",
        claim=(
            f"Interest-bearing debt averages {rate:.1%}, above the {threshold:.0%} "
            f"high-rate flag (about {annual:,.0f}/yr in interest)."
        ),
        evidence=evidence,
        assumptions=(
            "Reported balances and rates reflect current debt terms.",
            "Weighted-average rate represents the blended cost of interest-bearing debt.",
        ),
        limitations=(
            "Rates/fees not modeled per-instrument; no amortization schedule.",
            "Figures are display floats; exact values live in the state core (source_refs).",
        ),
        options=options,
        key_risks=(
            "High-rate debt compounds against net worth faster than typical returns.",
            "Refinancing costs or rate moves can erode the benefit.",
        ),
        reversibility=(
            "Flow (extra principal) is low-risk and reversible only in opportunity-cost "
            "terms; the stock option (refinance) is a new contract and is flagged for "
            "human review."
        ),
    )


def _insurance_gap_candidate(
    report: ExposureReport,
    thresholds: ObservationThresholds,
) -> AllocationCandidate | None:
    gaps = report.insurance_review_gaps
    if not gaps:
        return None
    options = (
        CandidateOption(
            kind="do_nothing",
            label="Do nothing",
            cost="Coverage stays unverifiable; a real protection gap could go unnoticed.",
            reversibility="Fully reversible (no action taken).",
        ),
        CandidateOption(
            kind="flow",
            label="Collect policy declaration pages, fill missing renewal/coverage data, "
            "and schedule an annual review",
            cost="Time to gather records and set up a recurring review; small premium reserve.",
            reversibility="Reversible: this only organizes records and schedules a review.",
        ),
        CandidateOption(
            kind="stock",
            label="Review potential policy changes (human review)",
            cost="Any change means new premiums or contract terms; depends on actual needs "
            "and underwriting.",
            reversibility="Less reversible: a policy change is a new contract with its own terms.",
        ),
    )
    evidence = {
        "insurance_active_count": report.insurance_active_count,
        "review_gaps": list(gaps),
        "as_of_date": report.as_of_date,
        "metric_precision": "descriptive review gaps; reconstruct exact via source_refs",
        "source_refs": _refs(report.provenance.insurance),
    }
    plural = "gap" if len(gaps) == 1 else "gaps"
    return AllocationCandidate(
        detector_kind="insurance_gap",
        dimension="flow",
        claim=(
            f"{len(gaps)} insurance coverage review {plural} found; coverage cannot be "
            "verified from current records."
        ),
        evidence=evidence,
        assumptions=(
            "Insurance records in the state core reflect the user's actual policies.",
        ),
        limitations=(
            "This is a records / coverage-evidence review, not an actuarial or needs analysis.",
            "No household structure, income-replacement need, or risk profile is modeled.",
            "Does not assert whether coverage is sufficient, only that it is unverifiable.",
        ),
        options=options,
        key_risks=(
            "Unverifiable, lapsed, or expired coverage could leave a real exposure undetected.",
        ),
        reversibility=(
            "Flow (collecting records / scheduling a review) is fully reversible; a policy "
            "change (stock) is a new contract and is flagged for human review."
        ),
    )


def _tax_window_candidate(
    report: ExposureReport,
    thresholds: ObservationThresholds,
) -> AllocationCandidate | None:
    gaps = report.tax_review_gaps
    if not gaps:
        return None
    options = (
        CandidateOption(
            kind="do_nothing",
            label="Do nothing",
            cost="Tax deadlines/amounts stay unconfirmed; a missed filing or payment could "
            "create penalties or interest.",
            reversibility="Fully reversible (no action taken).",
        ),
        CandidateOption(
            kind="flow",
            label="Confirm each deadline's status, record estimated amounts, set a reminder, "
            "and reserve funds for what is due",
            cost="Time to gather documents and confirm status; small cash reserve for amounts due.",
            reversibility="Reversible: this only confirms status, records data, and reserves cash.",
        ),
        CandidateOption(
            kind="stock",
            label="Free up funds to cover a confirmed tax liability (human review)",
            cost="May require moving cash or selling assets; depends on the confirmed amount.",
            reversibility="Less reversible: liquidating to pay can carry market/tax/timing costs.",
        ),
    )
    evidence = {
        "review_gaps": list(gaps),
        "as_of_date": report.as_of_date,
        "metric_precision": "descriptive review gaps; reconstruct exact via source_refs",
        "source_refs": _refs(report.provenance.tax),
    }
    plural = "item" if len(gaps) == 1 else "items"
    return AllocationCandidate(
        detector_kind="tax_window",
        dimension="flow",
        claim=(
            f"{len(gaps)} tax review {plural} found; tax deadlines/amounts cannot be "
            "confirmed from current records."
        ),
        evidence=evidence,
        assumptions=(
            "Tax events in the state core reflect the user's actual obligations.",
            "Status marks (paid/filed/planned) are kept current by the user.",
        ),
        limitations=(
            "This is a deadline / records review, not tax advice or a filing recommendation.",
            "Does not compute tax owed, optimize tax, or recommend filing/payment timing.",
            "No jurisdiction-specific tax rules are applied.",
        ),
        options=options,
        key_risks=(
            "An unconfirmed or missed tax deadline could create penalties or interest.",
        ),
        reversibility=(
            "Flow (confirming status / recording amounts / reserving cash) is reversible; "
            "freeing up funds to pay (stock) is flagged for human review."
        ),
    )


_DETECTORS = (
    _cash_buffer_candidate,
    _concentration_candidate,
    _cash_overweight_candidate,
    _rate_exposure_candidate,
    _insurance_gap_candidate,
    _tax_window_candidate,
)


def compute_allocation_candidates(
    report: ExposureReport,
    thresholds: ObservationThresholds | None = None,
) -> tuple[AllocationCandidate, ...]:
    """Pure: turn an exposure report into governed capital-allocation candidates."""
    active = thresholds or ObservationThresholds()
    candidates: list[AllocationCandidate] = []
    for detector in _DETECTORS:
        candidate = detector(report, active)
        if candidate is not None:
            candidates.append(candidate)
    return tuple(candidates)


def _stable_proposal_id(detector_kind: str, as_of_date: str) -> str:
    return f"alloc_{detector_kind}_{as_of_date}"


def record_allocation_candidates(
    engine: Engine,
    *,
    receipt_root: str | Path | None = None,
    as_of_date: date | None = None,
    thresholds: ObservationThresholds | None = None,
    enricher: ResearchEnricher | None = None,
) -> tuple[ExposureReport, tuple[GovernedProposalWrite, ...]]:
    """Scan the exposure map and record candidates as governed proposals (idempotent).

    Research enrichment is off by default: ``enricher`` defaults to a no-op so the
    proposal evidence shape is byte-for-byte what it was before RE3 (``research_evidence``
    stays ``[]``, no ``research_evidence_gaps`` key, no extra source_refs). An opt-in
    ``ProviderResearchEnricher`` attaches descriptive historical evidence; enrichment
    never decides whether a candidate is recorded.
    """
    root = receipt_root if receipt_root is not None else DEFAULT_ALLOCATION_RECEIPT_ROOT
    active_enricher = enricher if enricher is not None else NoopResearchEnricher()
    report = compute_exposure(engine, as_of_date=as_of_date, thresholds=thresholds)
    candidates = compute_allocation_candidates(report, thresholds)
    writes: list[GovernedProposalWrite] = []
    for candidate in candidates:
        attachment = active_enricher.enrich(candidate)
        evidence = {
            **candidate.evidence,
            "dimension": candidate.dimension,
            "options": [option.model_dump() for option in candidate.options],
            "key_risks": list(candidate.key_risks),
            "reversibility": candidate.reversibility,
            # research_evidence key is always present (empty -> []), matching the
            # pre-RE3 shape so the default no-op path does not change content hashes.
            "research_evidence": attachment.to_evidence_payload(),
        }
        # Gaps and research source_refs only appear when there is something to disclose,
        # so the default no-op path adds neither key nor refs.
        if attachment.data_gaps:
            evidence["research_evidence_gaps"] = list(attachment.data_gaps)
        source_refs = list(candidate.evidence.get("source_refs", []))
        for ref in attachment.source_refs:
            if ref not in source_refs:
                source_refs.append(ref)
        write = create_governed_proposal(
            kind=candidate.detector_kind,
            claim=candidate.claim,
            evidence=evidence,
            assumptions={"items": list(candidate.assumptions)},
            limitations={"items": list(candidate.limitations)},
            non_claims=list(CANDIDATE_NON_CLAIMS),
            source_refs=source_refs,
            engine=engine,
            receipt_root=root,
            proposal_id=_stable_proposal_id(candidate.detector_kind, report.as_of_date),
            idempotent=True,
        )
        writes.append(write)
    return report, tuple(writes)
