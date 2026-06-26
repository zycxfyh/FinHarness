"""Unified personal daily brief — the B0 "what should I look at today" view.

Assembles one plain-language brief from existing, mature building blocks:
- the exposure map (`finharness.exposure.compute_exposure`),
- change-since-last (`statecore.diff` + `statecore.observations`),
- upcoming obligations (from the exposure map),
- open proposals awaiting human attestation.

``compute_daily_brief`` is a pure, read-only computation (used by the GET
endpoint and the cockpit). ``record_daily_brief`` additionally writes a receipt,
so a day's brief can be archived as evidence. Nothing here executes.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from sqlalchemy import Engine, desc
from sqlmodel import Session, select

from finharness.exposure import ExposureReport, compute_exposure
from finharness.market_data import ROOT
from finharness.statecore.diff import diff_snapshots
from finharness.statecore.models import (
    Attestation,
    Position,
    Proposal,
    ReceiptIndex,
    Snapshot,
    utc_now_iso,
)
from finharness.statecore.observations import ObservationThresholds, build_observations
from finharness.statecore.receipt_io import atomic_write_json
from finharness.statecore.store import upsert_records

DEFAULT_DAILY_BRIEF_RECEIPT_ROOT = ROOT / "data" / "receipts" / "daily-brief"
BRIEF_KIND = "daily_brief"
NON_CLAIMS = (
    "Descriptive daily brief over mirrored state.",
    "Not investment, tax, or accounting advice.",
    "Not execution authorization.",
)

# P3 Daily Financial Brief v1: ten fixed slots, fixed order. ``compute_daily_brief``
# always emits exactly these ten sections, in this order. A slot with no data emits an
# explicit placeholder line rather than disappearing (see RFC
# docs/proposals/2026-06-24-p3-daily-financial-brief-v1.md, gate conditions 1, 2, 7).
SLOT_TITLES: tuple[str, ...] = (
    "Net worth snapshot",
    "Cash & liquidity status",
    "Exposure map",
    "Concentration risks",
    "Leverage & liquidation warnings",
    "Market context",
    "Candidate decisions",
    "Do-nothing option",
    "Behavioral warnings",
    "Review prompts",
)

# Slot 6 is offline-only in v1. Live / networked market context is a separate gated
# capability (C3), explicitly excluded here — this slot never makes a network call.
MARKET_CONTEXT_OFFLINE_PLACEHOLDER = (
    "No offline market context on record. v1 market context is offline / historical / "
    "source-graded only; live context is a separate gated capability, not part of this brief."
)

# Slot 8 is a fixed, always-present line: not acting is itself a reviewable option.
# It must not imply inaction is risk-free — existing exposures and costs remain.
DO_NOTHING_LINE = (
    "Doing nothing is a valid option: it creates no new transaction or execution risk, "
    "but existing exposures, opportunity costs, and unresolved data gaps remain."
)


def _behavioral_warnings(exposure: ExposureReport) -> list[str]:
    """Deterministic, offline behavioral flags derived from existing exposure signals.

    v1 is simple rules over signals the exposure map already computes — no model, no
    network, no prediction. Surfaces patterns worth a second look (over-concentration,
    thin liquidity, leverage, ignored tax/insurance), not advice on what to do.
    """
    warnings: list[str] = []
    if exposure.concentration_flagged:
        warnings.append(
            f"Concentration: top holding is {exposure.top_holding_weight * 100:.1f}% "
            f"(over the {exposure.concentration_threshold * 100:.0f}% threshold). Watch for "
            "adding to an already-crowded position."
        )
    if exposure.cash_runway_months is not None and exposure.cash_runway_months < 3:
        warnings.append(
            f"Liquidity: cash runway is {exposure.cash_runway_months:.1f} months. Thin "
            "buffers make forced selling more likely under stress."
        )
    if exposure.interest_bearing_debt_total > 0:
        warnings.append(
            "Leverage: interest-bearing debt is on the books. Confirm new risk is not "
            "being taken on borrowed money without a written rationale."
        )
    if exposure.tax_review_gaps:
        warnings.append(
            f"Tax: {len(exposure.tax_review_gaps)} tax review gap(s) outstanding — easy to "
            "ignore until a deadline forces a worse decision."
        )
    if exposure.insurance_review_gaps:
        warnings.append(
            f"Insurance: {len(exposure.insurance_review_gaps)} coverage gap(s) outstanding."
        )
    return warnings


class BriefSection(BaseModel):
    title: str
    lines: tuple[str, ...]


class DailyBrief(BaseModel):
    as_of_date: str
    headline: str
    net_worth: float
    total_assets: float
    total_liabilities: float
    holdings_change: float | None
    open_review_count: int
    sections: tuple[BriefSection, ...]
    data_gaps: tuple[str, ...]
    source_refs: tuple[str, ...]
    non_claims: tuple[str, ...] = NON_CLAIMS
    execution_allowed: bool = False


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _money(value: float, currency: str | None) -> str:
    return f"{value:,.2f} {currency or ''}".rstrip()


def _change_section(
    engine: Engine,
    snapshots: list[Snapshot],
    thresholds: ObservationThresholds,
) -> tuple[BriefSection, float | None]:
    title = "Change since last"
    if len(snapshots) < 2:
        return BriefSection(title=title, lines=("No prior snapshot to compare.",)), None
    after, before = snapshots[0], snapshots[1]
    diff = diff_snapshots(before.snapshot_id, after.snapshot_id, engine=engine)
    with Session(engine) as session:
        current_positions = list(
            session.exec(
                select(Position).where(Position.snapshot_id == after.snapshot_id)
            ).all()
        )
    observations = build_observations(diff, current_positions, thresholds=thresholds)
    lines = [observation.detail for observation in observations]
    if not lines:
        lines = [
            f"Holdings value moved by {diff.total_market_value_delta:,.2f}; "
            "no threshold crossings."
        ]
    return BriefSection(title=title, lines=tuple(lines)), diff.total_market_value_delta


def _open_reviews(engine: Engine) -> list[Proposal]:
    with Session(engine) as session:
        proposals = list(session.exec(select(Proposal)).all())
        attestations = list(session.exec(select(Attestation)).all())
    attested = {attestation.proposal_id for attestation in attestations}
    return [proposal for proposal in proposals if proposal.proposal_id not in attested]


def compute_daily_brief(
    engine: Engine,
    *,
    as_of_date: date | None = None,
    thresholds: ObservationThresholds | None = None,
) -> DailyBrief:
    """Assemble a read-only unified daily brief from the state core."""
    active_thresholds = thresholds or ObservationThresholds()
    exposure = compute_exposure(engine, as_of_date=as_of_date, thresholds=active_thresholds)
    with Session(engine) as session:
        portfolio_snapshots = list(
            session.exec(
                select(Snapshot)
                .where(Snapshot.kind == "portfolio")
                .order_by(desc(Snapshot.as_of_utc), desc(Snapshot.snapshot_id))
                .limit(2)
            ).all()
        )
    change_section, holdings_change = _change_section(
        engine, portfolio_snapshots, active_thresholds
    )
    open_reviews = _open_reviews(engine)

    # --- Ten fixed slots, fixed order. Every slot is always emitted; an empty slot
    # gets an explicit placeholder line. Data from the prior four sections is preserved,
    # mapped into slots 1-5/7/10; slots 6/8/9 are additive. ---

    # Slot 1: Net worth snapshot (+ change-since-last, folded in here).
    net_worth_lines = [
        f"Net worth {_money(exposure.net_worth, exposure.base_currency)}",
        f"Assets {_money(exposure.total_assets, exposure.base_currency)}; "
        f"liabilities {_money(exposure.total_liabilities, exposure.base_currency)}",
    ]
    net_worth_lines += list(change_section.lines)

    # Slot 2: Cash & liquidity status (+ upcoming obligations).
    cash_lines: list[str] = []
    if exposure.cash_runway_months is not None:
        cash_lines.append(f"Cash runway {exposure.cash_runway_months:.1f} months")
    # Only render an amount when the cash total is verified; an unverified 0.00 would
    # read as "you have no cash" rather than "no snapshot to read cash from".
    if exposure.cash_total_verified:
        cash_lines.append(
            f"Cash on record {_money(exposure.cash_total, exposure.base_currency)}"
        )
    else:
        cash_lines.append("Cash total not verified; no portfolio snapshot on record.")
    cash_lines += [
        f"Upcoming: {item.due_date} · {item.label}"
        + (f" · {_money(item.amount, item.currency)}" if item.amount is not None else "")
        for item in exposure.upcoming_obligations
    ] or ["Nothing due in the horizon."]

    # Slot 3: Exposure map (holdings-level in v1; factor-level is deferred debt).
    exposure_map_lines = [
        f"{exposure.holding_count} holding(s); "
        f"top holding {exposure.top_holding_weight * 100:.1f}% "
        f"(HHI {exposure.concentration_hhi:.3f})"
    ]

    # Slot 4: Concentration risks. No holdings means "cannot assess", not "low risk" —
    # do not render absence of data as reassurance.
    if exposure.holding_count == 0:
        concentration_lines = ["Concentration not assessed: no holdings on record."]
    elif exposure.concentration_flagged:
        concentration_lines = [
            f"Concentration flag: top holding over "
            f"{exposure.concentration_threshold * 100:.0f}%"
        ]
    else:
        concentration_lines = [
            f"Top holding within the {exposure.concentration_threshold * 100:.0f}% threshold."
        ]

    # Slot 5: Leverage & liquidation warnings (qualitative in v1; no liquidation price).
    if exposure.interest_bearing_debt_total > 0:
        leverage_lines = [
            f"Interest-bearing debt {exposure.interest_bearing_debt_total:,.2f}; "
            f"annual interest ~{exposure.annual_interest_estimate:,.2f}",
            "No liquidation-price estimate in v1 (leverage/liquidation math is deferred).",
        ]
    else:
        leverage_lines = ["No interest-bearing debt on record."]

    # Slot 6: Market context (offline-only in v1; never a network call).
    market_context_lines = [MARKET_CONTEXT_OFFLINE_PLACEHOLDER]

    # Slot 7: Candidate decisions — read only from governed proposals (decisions:scan).
    candidate_lines = [
        f"- {proposal.claim} ({proposal.kind})" for proposal in open_reviews[:5]
    ] or ["No open candidate decisions on record."]

    # Slot 8: Do-nothing option — always present.
    do_nothing_lines = [DO_NOTHING_LINE]

    # Slot 9: Behavioral warnings — deterministic rules over existing signals.
    behavioral_lines = _behavioral_warnings(exposure) or [
        "No behavioral flags from the current state."
    ]

    # Slot 10: Review prompts.
    review_lines = [
        f"{len(open_reviews)} open proposal(s) awaiting human attestation.",
        "Which candidates did you act on, and is the rationale recorded?",
    ]

    slot_lines = (
        net_worth_lines,
        cash_lines,
        exposure_map_lines,
        concentration_lines,
        leverage_lines,
        market_context_lines,
        candidate_lines,
        do_nothing_lines,
        behavioral_lines,
        review_lines,
    )
    sections = tuple(
        BriefSection(title=title, lines=tuple(lines))
        for title, lines in zip(SLOT_TITLES, slot_lines, strict=True)
    )

    headline = (
        f"Net worth {exposure.net_worth:,.0f} {exposure.base_currency or ''}".rstrip()
        + f"; {1 if exposure.concentration_flagged else 0} concentration flag"
        + f"; {len(exposure.upcoming_obligations)} upcoming"
        + f"; {len(open_reviews)} open review(s)"
    )

    return DailyBrief(
        as_of_date=exposure.as_of_date,
        headline=headline,
        net_worth=exposure.net_worth,
        total_assets=exposure.total_assets,
        total_liabilities=exposure.total_liabilities,
        holdings_change=holdings_change,
        open_review_count=len(open_reviews),
        sections=sections,
        data_gaps=exposure.data_gaps,
        source_refs=exposure.source_refs,
    )


def record_daily_brief(
    engine: Engine,
    *,
    receipt_root: str | Path = DEFAULT_DAILY_BRIEF_RECEIPT_ROOT,
    as_of_date: date | None = None,
) -> tuple[DailyBrief, str]:
    """Compute the daily brief and write it as a dated receipt (one per day)."""
    brief = compute_daily_brief(engine, as_of_date=as_of_date)
    receipt_id = f"receipt_daily_brief_{brief.as_of_date}"
    receipt_path = Path(receipt_root) / f"{receipt_id}.json"
    receipt_ref = display_path(receipt_path)
    payload: dict[str, Any] = {
        "receipt_id": receipt_id,
        "kind": BRIEF_KIND,
        "created_at_utc": datetime.now(UTC).isoformat(),
        **brief.model_dump(),
    }
    atomic_write_json(receipt_path, payload)
    receipt_index = ReceiptIndex(
        receipt_id=receipt_id,
        kind=BRIEF_KIND,
        path=receipt_ref,
        created_at_utc=utc_now_iso(),
        source_refs=list(brief.source_refs),
        refs=[],
    )
    upsert_records([receipt_index], engine=engine)
    return brief, receipt_ref
