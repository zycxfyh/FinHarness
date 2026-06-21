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

from finharness.exposure import compute_exposure
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

    exposure_lines = [
        f"Net worth {_money(exposure.net_worth, exposure.base_currency)}",
        f"Top holding {exposure.top_holding_weight * 100:.1f}% "
        f"(HHI {exposure.concentration_hhi:.3f})",
    ]
    if exposure.concentration_flagged:
        exposure_lines.append(
            f"Concentration flag: top holding over "
            f"{exposure.concentration_threshold * 100:.0f}%"
        )
    if exposure.cash_runway_months is not None:
        exposure_lines.append(f"Cash runway {exposure.cash_runway_months:.1f} months")
    if exposure.interest_bearing_debt_total > 0:
        exposure_lines.append(
            f"Interest-bearing debt {exposure.interest_bearing_debt_total:,.2f}; "
            f"annual interest ~{exposure.annual_interest_estimate:,.2f}"
        )

    obligation_lines = [
        f"{item.due_date} · {item.label}"
        + (f" · {_money(item.amount, item.currency)}" if item.amount is not None else "")
        for item in exposure.upcoming_obligations
    ] or ["Nothing due in the horizon."]

    review_lines = [f"{len(open_reviews)} open proposal(s) awaiting human attestation."]
    review_lines += [f"- {proposal.claim}" for proposal in open_reviews[:5]]

    sections = (
        change_section,
        BriefSection(title="Exposure & concentration", lines=tuple(exposure_lines)),
        BriefSection(title="Upcoming obligations", lines=tuple(obligation_lines)),
        BriefSection(title="Needs review", lines=tuple(review_lines)),
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
