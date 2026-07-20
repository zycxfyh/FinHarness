"""Deterministic personal exposure map over the state core.

This is the B0 "situational awareness" foundation: a pure, read-only computation
that turns mirrored state (holdings, liabilities, cashflows, tax/insurance dates)
into net worth, concentration, cash runway, rate exposure, and upcoming
obligations. It is descriptive aggregation, not advice, and it never executes.

Money is aggregated in exact ``Decimal`` and exposed as ``float`` display rollups
at the report boundary (the raw exact values live in the state core). Standard
metrics are adopted rather than invented: concentration uses the Herfindahl-
Hirschman Index (HHI) plus top-N share; cash runway is months of expenses covered.
Cases we cannot value (unpriced holdings, mixed currency, missing cashflows) are
disclosed as data gaps, not silently guessed.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import Engine, desc
from sqlmodel import Session, select

from finharness.position_valuation import (
    PositionValuationError,
    parse_valuation_evaluation_clock,
    reconcile_position_totals,
    valuation_blockers,
)
from finharness.statecore.models import (
    CashflowEvent,
    InsurancePolicy,
    Liability,
    Position,
    Snapshot,
    TaxEvent,
)
from finharness.statecore.observations import ObservationThresholds

DEFAULT_OBLIGATION_HORIZON_DAYS = 90
NON_CLAIMS = (
    "Descriptive exposure map over mirrored state.",
    "Not investment, tax, or accounting advice.",
    "Not a net-worth guarantee; disclosed data gaps may apply.",
    "Not execution authorization.",
)
_FIAT_CURRENCIES = frozenset(
    {
        "USD",
        "EUR",
        "GBP",
        "JPY",
        "CNY",
        "CAD",
        "AUD",
        "CHF",
        "HKD",
        "SGD",
        "NZD",
        "SEK",
        "NOK",
    }
)


def _is_cash_symbol(symbol: str) -> bool:
    upper = symbol.upper()
    return upper in _FIAT_CURRENCIES or upper.startswith("CASH")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


class HoldingExposure(BaseModel):
    symbol: str
    market_value: float
    weight: float | None


class UpcomingObligation(BaseModel):
    kind: str
    label: str
    due_date: str
    amount: float | None
    currency: str | None


class ExposureProvenance(BaseModel):
    """Per-domain source refs so each candidate carries only its own provenance.

    The report-level ``source_refs`` stays a global union (API invariant); detectors
    read the specific domain(s) they actually use, avoiding cross-domain ref leakage.
    """

    portfolio: tuple[str, ...] = ()
    cash: tuple[str, ...] = ()
    cashflow: tuple[str, ...] = ()
    liability: tuple[str, ...] = ()
    tax: tuple[str, ...] = ()
    insurance: tuple[str, ...] = ()


class ExposureReport(BaseModel):
    as_of_date: str
    base_currency: str | None
    asset_valuation_admitted: bool
    net_worth_admitted: bool
    total_assets: float | None
    total_liabilities: float | None
    net_worth: float | None
    per_currency_totals: dict[str, float]
    liability_per_currency_totals: dict[str, float]
    asset_valuation_blockers: tuple[str, ...]
    net_worth_blockers: tuple[str, ...]
    holding_count: int
    holdings: tuple[HoldingExposure, ...]
    concentration_hhi: float | None
    top_holding_weight: float | None
    top5_weight: float | None
    concentration_flagged: bool | None
    concentration_threshold: float
    cash_total: float | None
    cash_total_verified: bool
    monthly_net_cashflow: float | None
    cash_runway_months: float | None
    interest_bearing_debt_total: float | None
    weighted_avg_interest_rate: float | None
    annual_interest_estimate: float | None
    insurance_active_count: int
    insurance_review_gaps: tuple[str, ...]
    tax_review_gaps: tuple[str, ...]
    upcoming_obligations: tuple[UpcomingObligation, ...]
    data_gaps: tuple[str, ...]
    source_refs: tuple[str, ...]
    provenance: ExposureProvenance = ExposureProvenance()
    non_claims: tuple[str, ...] = NON_CLAIMS
    execution_allowed: bool = False


def _latest_portfolio_snapshot(session: Session) -> Snapshot | None:
    return session.exec(
        select(Snapshot)
        .where(Snapshot.kind == "portfolio")
        .order_by(desc(Snapshot.as_of_utc), desc(Snapshot.snapshot_id))
        .limit(1)
    ).first()


def _parse_snapshot_clock(snapshot: Snapshot) -> datetime | None:
    """Validate and normalize snapshot.as_of_utc.

    Raises PositionValuationError on empty, invalid, or timezone-naive values
    so the consumer fails closed rather than silently disabling freshness checks.
    Returns None only when the snapshot itself is None (caller-side guard).
    """
    raw = snapshot.as_of_utc
    return parse_valuation_evaluation_clock(raw)



def _holdings(
    positions: list[Position],
    data_gaps: list[str],
    *,
    denominator_admitted: bool,
) -> tuple[list[HoldingExposure], Decimal | None, Decimal | None, Decimal | None]:
    by_symbol: dict[str, Decimal] = {}
    for position in positions:
        if position.market_value is None:
            data_gaps.append(f"unvalued holding: {position.symbol} ({position.valuation_status})")
            continue
        if position.quantity != 0 and position.market_value == 0:
            data_gaps.append(f"unpriced holding: {position.symbol}")
        # Cash/fiat is liquidity, not a single-name concentration risk; it is
        # reported separately via cash_total and excluded from the holdings book
        # so it is never surfaced as a holding to "trim".
        if _is_cash_symbol(position.symbol):
            continue
        by_symbol[position.symbol] = by_symbol.get(position.symbol, Decimal("0")) + (
            position.market_value
        )
    ordered = sorted(by_symbol.items(), key=lambda item: (item[1], item[0]), reverse=True)
    # Concentration is measured over the long securities book (positive holdings,
    # excluding cash) so weights stay in [0, 1] and reflect single-name risk; a
    # negative position (e.g. margin/short) is not a share of exposure.
    gross_long = sum((value for value in by_symbol.values() if value > 0), Decimal("0"))
    holdings: list[HoldingExposure] = []
    hhi = Decimal("0")
    positive_weights: list[Decimal] = []
    for symbol, value in ordered:
        weight = (
            value / gross_long
            if denominator_admitted and gross_long > 0 and value > 0
            else None
        )
        holdings.append(
            HoldingExposure(
                symbol=symbol,
                market_value=float(value),
                weight=float(weight) if weight is not None else None,
            )
        )
        if weight is not None:
            positive_weights.append(weight)
            hhi += weight * weight
    if not denominator_admitted:
        return holdings, None, None, None
    top_weight = positive_weights[0] if positive_weights else Decimal("0")
    top5_weight = sum(positive_weights[:5], Decimal("0"))
    return holdings, hhi, top_weight, top5_weight


def _currency_totals(
    values: list[tuple[str, Decimal]],
) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for raw_currency, value in values:
        currency = raw_currency.strip().upper()
        if not currency:
            continue
        totals[currency] = totals.get(currency, Decimal("0")) + value
    return totals


def _rate_exposure(liabilities: list[Liability]) -> tuple[Decimal, Decimal, Decimal | None]:
    interest_bearing = Decimal("0")
    annual_interest = Decimal("0")
    for liability in liabilities:
        if liability.interest_rate is None:
            continue
        interest_bearing += liability.balance
        annual_interest += liability.balance * liability.interest_rate
    weighted_avg = annual_interest / interest_bearing if interest_bearing > 0 else None
    return interest_bearing, annual_interest, weighted_avg


def _cash_runway(
    cash_total: Decimal,
    cashflows: list[CashflowEvent],
    data_gaps: list[str],
) -> tuple[Decimal | None, Decimal | None]:
    monthly = [flow for flow in cashflows if (flow.frequency or "").lower() == "monthly"]
    if not monthly:
        data_gaps.append("no recurring monthly cashflow; cash runway not computed")
        return None, None
    income = sum((flow.amount for flow in monthly if flow.amount > 0), Decimal("0"))
    expenses = sum((-flow.amount for flow in monthly if flow.amount < 0), Decimal("0"))
    net = income - expenses
    if expenses <= 0:
        data_gaps.append("no recurring monthly expenses; cash runway not computed")
        return net, None
    # Emergency-fund standard: months of expenses covered by liquid cash (CFP-style),
    # independent of whether the month nets to saving or burning.
    return net, cash_total / expenses


def _upcoming_obligations(
    *,
    tax_events: list[TaxEvent],
    insurance: list[InsurancePolicy],
    cashflows: list[CashflowEvent],
    as_of_date: date,
    horizon_days: int,
) -> list[UpcomingObligation]:
    horizon_end = date.fromordinal(as_of_date.toordinal() + horizon_days)
    obligations: list[UpcomingObligation] = []

    def _within(due: date | None) -> bool:
        return due is not None and as_of_date <= due <= horizon_end

    for event in tax_events:
        due = _parse_date(event.due_date)
        if _within(due) and due is not None:
            obligations.append(
                UpcomingObligation(
                    kind="tax_event",
                    label=f"{event.event_type} ({event.jurisdiction})",
                    due_date=due.isoformat(),
                    amount=float(event.estimated_amount)
                    if event.estimated_amount is not None
                    else None,
                    currency=event.currency,
                )
            )
    for policy in insurance:
        due = _parse_date(policy.renewal_date)
        if _within(due) and due is not None:
            obligations.append(
                UpcomingObligation(
                    kind="insurance_renewal",
                    label=f"{policy.policy_type} ({policy.provider})",
                    due_date=due.isoformat(),
                    amount=float(policy.premium_amount)
                    if policy.premium_amount is not None
                    else None,
                    currency=policy.currency,
                )
            )
    for flow in cashflows:
        due = _parse_date(flow.event_date)
        if _within(due) and due is not None:
            obligations.append(
                UpcomingObligation(
                    kind="cashflow",
                    label=flow.description,
                    due_date=due.isoformat(),
                    amount=float(flow.amount),
                    currency=flow.currency,
                )
            )
    obligations.sort(key=lambda item: (item.due_date, item.kind, item.label))
    return obligations


def _insurance_review(
    policies: list[InsurancePolicy],
    as_of_date: date,
    data_gaps: list[str],
) -> tuple[int, list[str]]:
    """Coverage-evidence review (not a needs/actuarial analysis).

    Returns the active policy count and concrete review gaps: policies on record
    but none active, unrecorded coverage, or missing/unverifiable/expired renewal
    dates. Zero policies on record is disclosed as a data gap, not a review gap,
    so a brand-new state core does not nag about absent data.
    """
    if not policies:
        data_gaps.append("no insurance policy on record")
        return 0, []
    active = [policy for policy in policies if (policy.status or "").strip().lower() == "active"]
    review_gaps: list[str] = []
    if not active:
        review_gaps.append("insurance policies on record but none active")
        return 0, review_gaps
    for policy in active:
        label = f"{policy.policy_type} ({policy.provider})"
        if policy.coverage_amount <= 0:
            review_gaps.append(f"coverage amount not recorded for {label}")
        if not policy.renewal_date:
            review_gaps.append(f"missing renewal date for {label}")
        else:
            due = _parse_date(policy.renewal_date)
            if due is None:
                review_gaps.append(f"unverifiable renewal date for {label}")
            elif due < as_of_date:
                review_gaps.append(
                    f"renewal date {due.isoformat()} is past but {label} is still active"
                )
    return len(active), review_gaps


_TAX_HANDLED_STATUSES = frozenset({"paid", "filed", "settled", "done", "complete", "closed"})


def _tax_review(
    tax_events: list[TaxEvent],
    as_of_date: date,
    horizon_days: int,
    data_gaps: list[str],
) -> list[str]:
    """Deadline / estimated-payment / document review (not tax advice).

    Surfaces tax obligations that need human confirmation: missing or unverifiable
    due dates, estimated payments with no recorded amount, upcoming or past-due
    deadlines not yet marked handled. It never computes tax owed, optimizes tax, or
    recommends filing/payment. Zero tax events on record is a data gap, not a
    review gap, so an empty state core does not nag.
    """
    if not tax_events:
        data_gaps.append("no tax event on record")
        return []
    horizon_end = date.fromordinal(as_of_date.toordinal() + horizon_days)
    review_gaps: list[str] = []
    for event in tax_events:
        label = f"{event.event_type} ({event.jurisdiction})"
        handled = (event.status or "").strip().lower() in _TAX_HANDLED_STATUSES
        if not event.due_date.strip():
            review_gaps.append(f"missing due date for {label}")
        else:
            due = _parse_date(event.due_date)
            if due is None:
                review_gaps.append(f"unverifiable due date for {label}")
            elif not handled and due < as_of_date:
                review_gaps.append(
                    f"tax deadline {due.isoformat()} for {label} is past but not marked "
                    "handled; confirm status"
                )
            elif not handled and due <= horizon_end:
                review_gaps.append(
                    f"tax deadline {due.isoformat()} for {label} is within {horizon_days} "
                    "days; confirm it is handled"
                )
        if event.event_type.strip().lower().replace(" ", "_") == "estimated_payment" and (
            event.estimated_amount is None or event.estimated_amount <= 0
        ):
            review_gaps.append(f"estimated payment amount not recorded for {label}")
    return review_gaps


def compute_exposure(  # noqa: C901 -- one auditable capital-admission orchestration
    engine: Engine,
    *,
    as_of_date: date | None = None,
    horizon_days: int = DEFAULT_OBLIGATION_HORIZON_DAYS,
    thresholds: ObservationThresholds | None = None,
) -> ExposureReport:
    """Compute a read-only personal exposure map from the state core."""
    active_thresholds = thresholds or ObservationThresholds()
    reference_date = as_of_date or datetime.now(UTC).date()
    with Session(engine) as session:
        snapshot = _latest_portfolio_snapshot(session)
        positions: list[Position] = []
        if snapshot is not None:
            positions = list(
                session.exec(
                    select(Position).where(Position.snapshot_id == snapshot.snapshot_id)
                ).all()
            )
        liabilities = list(session.exec(select(Liability)).all())
        cashflows = list(session.exec(select(CashflowEvent)).all())
        tax_events = list(session.exec(select(TaxEvent)).all())
        insurance = list(session.exec(select(InsurancePolicy)).all())

    data_gaps: list[str] = []
    # Cash total is only verifiable when a portfolio snapshot exists (the snapshot
    # is what proves how much cash is held, including a real zero). Without one, a
    # 0 cash total is unverified and must not back a candidate.
    cash_total_verified = snapshot is not None
    if not cash_total_verified:
        data_gaps.append("no portfolio snapshot on record; cash total not verified")
    # Propagate exact snapshot clock to valuation checks.
    snapshot_evaluated_at: datetime | None = None
    if snapshot is not None:
        try:
            snapshot_evaluated_at = _parse_snapshot_clock(snapshot)
        except PositionValuationError:
            data_gaps.append("snapshot_time_invalid: snapshot as_of_utc is empty or malformed")
            snapshot_evaluated_at = None
    position_totals = reconcile_position_totals(
        positions,
        evaluated_at=snapshot_evaluated_at,
    )
    asset_blockers = list(position_totals.blockers)
    if snapshot is None:
        asset_blockers.append("portfolio_snapshot_missing")
    elif not positions:
        asset_blockers.append("portfolio_valuation_unavailable")
    asset_blockers = list(dict.fromkeys(asset_blockers))
    asset_admitted = (
        snapshot is not None
        and bool(positions)
        and position_totals.admitted
        and not asset_blockers
    )
    base_currency = position_totals.base_currency if asset_admitted else None
    total_assets = position_totals.unified_total if asset_admitted else None

    liability_currency_totals = _currency_totals(
        [(liability.currency, liability.balance) for liability in liabilities]
    )
    net_worth_blockers = list(asset_blockers)
    if any(not liability.currency.strip() for liability in liabilities):
        net_worth_blockers.append("liability_currency_missing")
    if len(liability_currency_totals) > 1:
        net_worth_blockers.append("mixed_liability_currencies")
    elif liability_currency_totals and base_currency is not None:
        liability_currency = next(iter(liability_currency_totals))
        if liability_currency != base_currency:
            net_worth_blockers.append(
                f"liability_currency_mismatch:{liability_currency}:{base_currency}"
            )
    net_worth_blockers = list(dict.fromkeys(net_worth_blockers))
    net_worth_admitted = (
        asset_admitted
        and not net_worth_blockers
        and (
            not liability_currency_totals
            or next(iter(liability_currency_totals)) == base_currency
        )
    )
    total_liabilities = (
        sum(liability_currency_totals.values(), Decimal("0"))
        if net_worth_admitted
        else None
    )
    net_worth = (
        total_assets - total_liabilities
        if total_assets is not None and total_liabilities is not None
        else None
    )

    admitted_positions = [
        position for position in positions
        if not valuation_blockers(position, evaluated_at=snapshot_evaluated_at)
    ]
    cash_total = (
        sum(
            (
                position.market_value
                for position in admitted_positions
                if _is_cash_symbol(position.symbol) and position.market_value is not None
            ),
            Decimal("0"),
        )
        if asset_admitted
        else None
    )

    holdings, hhi, top_weight, top5_weight = _holdings(
        admitted_positions,
        data_gaps,
        denominator_admitted=asset_admitted,
    )
    interest_bearing, annual_interest, weighted_avg = _rate_exposure(liabilities)
    if cash_total is None:
        monthly_net, runway = None, None
        data_gaps.append("cash runway not computed because capital valuation is blocked")
    else:
        monthly_net, runway = _cash_runway(cash_total, cashflows, data_gaps)
    obligations = _upcoming_obligations(
        tax_events=tax_events,
        insurance=insurance,
        cashflows=cashflows,
        as_of_date=reference_date,
        horizon_days=horizon_days,
    )
    insurance_active_count, insurance_review_gaps = _insurance_review(
        insurance, reference_date, data_gaps
    )
    tax_review_gaps = _tax_review(tax_events, reference_date, horizon_days, data_gaps)
    data_gaps.extend(
        f"capital valuation blocked: {blocker}" for blocker in asset_blockers
    )
    data_gaps.extend(
        f"net worth blocked: {blocker}"
        for blocker in net_worth_blockers
        if blocker not in asset_blockers
    )
    # Aggregate provenance from every state input that participated in this report,
    # not just the portfolio snapshot. Otherwise candidates derived from non-position
    # state (insurance, liabilities, cashflows) lose their source_refs and break the
    # "evidence carries source_refs, reconstructible" line.
    # Domain-grouped provenance: each detector reads only the domain(s) it uses, so
    # candidate evidence carries minimal source refs (no cross-domain leakage). The
    # report-level source_refs stays a global union for the API. Per-type loops keep
    # each element's concrete type (source_refs lives on the subclasses).
    portfolio_refs: set[str] = set()
    cash_refs: set[str] = set()
    if snapshot is not None:
        # The snapshot is the provenance of the whole position set, so it backs both
        # the securities (portfolio) and the cash total (including cash_total == 0,
        # when no cash position exists).
        portfolio_refs.update(snapshot.source_refs)
        cash_refs.update(snapshot.source_refs)
    for position in positions:
        if _is_cash_symbol(position.symbol):
            cash_refs.update(position.source_refs)
        else:
            portfolio_refs.update(position.source_refs)
    cashflow_refs: set[str] = set()
    for flow in cashflows:
        cashflow_refs.update(flow.source_refs)
    liability_refs: set[str] = set()
    for liability in liabilities:
        liability_refs.update(liability.source_refs)
    tax_refs: set[str] = set()
    for event in tax_events:
        tax_refs.update(event.source_refs)
    insurance_refs: set[str] = set()
    for policy in insurance:
        insurance_refs.update(policy.source_refs)
    provenance = ExposureProvenance(
        portfolio=tuple(sorted(portfolio_refs)),
        cash=tuple(sorted(cash_refs)),
        cashflow=tuple(sorted(cashflow_refs)),
        liability=tuple(sorted(liability_refs)),
        tax=tuple(sorted(tax_refs)),
        insurance=tuple(sorted(insurance_refs)),
    )
    source_refs = tuple(
        sorted(
            portfolio_refs | cash_refs | cashflow_refs | liability_refs | tax_refs | insurance_refs
        )
    )

    return ExposureReport(
        as_of_date=reference_date.isoformat(),
        base_currency=base_currency,
        asset_valuation_admitted=asset_admitted,
        net_worth_admitted=net_worth_admitted,
        total_assets=float(total_assets) if total_assets is not None else None,
        total_liabilities=(
            float(total_liabilities) if total_liabilities is not None else None
        ),
        net_worth=float(net_worth) if net_worth is not None else None,
        per_currency_totals={
            key: float(value)
            for key, value in position_totals.per_currency_totals.items()
        },
        liability_per_currency_totals={
            key: float(value) for key, value in liability_currency_totals.items()
        },
        asset_valuation_blockers=tuple(asset_blockers),
        net_worth_blockers=tuple(net_worth_blockers),
        holding_count=len(holdings),
        holdings=tuple(holdings),
        concentration_hhi=float(hhi) if hhi is not None else None,
        top_holding_weight=float(top_weight) if top_weight is not None else None,
        top5_weight=float(top5_weight) if top5_weight is not None else None,
        concentration_flagged=(
            float(top_weight) >= active_thresholds.concentration_pct
            if top_weight is not None
            else None
        ),
        concentration_threshold=active_thresholds.concentration_pct,
        cash_total=float(cash_total) if cash_total is not None else None,
        cash_total_verified=cash_total_verified and asset_admitted,
        monthly_net_cashflow=float(monthly_net) if monthly_net is not None else None,
        cash_runway_months=float(runway) if runway is not None else None,
        interest_bearing_debt_total=(
            float(interest_bearing) if net_worth_admitted else None
        ),
        weighted_avg_interest_rate=(
            float(weighted_avg)
            if weighted_avg is not None and net_worth_admitted
            else None
        ),
        annual_interest_estimate=(
            float(annual_interest) if net_worth_admitted else None
        ),
        insurance_active_count=insurance_active_count,
        insurance_review_gaps=tuple(insurance_review_gaps),
        tax_review_gaps=tuple(tax_review_gaps),
        upcoming_obligations=tuple(obligations),
        data_gaps=tuple(data_gaps),
        source_refs=source_refs,
        provenance=provenance,
    )
