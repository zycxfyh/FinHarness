"""Investment Policy Statement (north star L3 / 投资政策声明).

The IPS is the bridge between the L2 capital map ("what is my state") and the
L4 proposal layer ("what is suitable for me"). It carries the user's numeric
policy thresholds and declarative constraints as a versioned, receipt-backed
object.

Two pure functions connect it to the rest of the system:

* ``thresholds_from_ips`` maps an IPS onto the existing ``ObservationThresholds``
  so the L4 detectors become personalized without any detector rewrite (default
  thresholds remain the fallback when no IPS exists).
* ``check_ips_compliance`` reads an ``ExposureReport`` against the IPS and reports
  each rule as ``pass`` / ``violation`` / ``blocked`` (blocked == the underlying
  data is not verifiable, so no claim is made).

An IPS is policy, never execution authority.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import Engine
from sqlmodel import Session, col, select

from finharness.exposure import ExposureReport
from finharness.project_paths import ROOT
from finharness.statecore.models import InvestmentPolicyStatement, ReceiptIndex
from finharness.statecore.observations import ObservationThresholds
from finharness.statecore.receipt_io import (
    atomic_write_json,
    remove_file_best_effort,
    resolve_under,
)
from finharness.statecore.store import StateCoreStoreError, upsert_records

DEFAULT_IPS_RECEIPT_ROOT = ROOT / "data" / "receipts" / "state-core"

IPS_NON_CLAIMS = (
    "Investment Policy Statement: the user's own policy, not advice.",
    "Policy boundaries are user-set; the system checks them, it does not set them.",
    "A compliance check is descriptive; it is not a recommendation to trade.",
    "Not execution authorization.",
)

RuleStatus = Literal["pass", "violation", "blocked"]


def thresholds_from_ips(ips: InvestmentPolicyStatement) -> ObservationThresholds:
    """Personalize the L4 detector thresholds from an IPS (defaults remain the fallback)."""
    base = ObservationThresholds()
    return replace(
        base,
        cash_runway_target_months=float(ips.liquidity_floor_months),
        concentration_pct=float(ips.max_single_holding_pct),
        cash_overweight_pct=(
            float(ips.cash_overweight_pct)
            if ips.cash_overweight_pct is not None
            else base.cash_overweight_pct
        ),
        high_interest_rate_pct=(
            float(ips.high_interest_rate_pct)
            if ips.high_interest_rate_pct is not None
            else base.high_interest_rate_pct
        ),
    )


class IpsRuleResult(BaseModel):
    rule: str
    boundary: str
    observed: str
    status: RuleStatus
    detail: str


class IpsCheckReport(BaseModel):
    ips_id: str
    as_of_date: str
    results: tuple[IpsRuleResult, ...]
    violations: tuple[str, ...]
    blocked: tuple[str, ...]
    source_refs: tuple[str, ...]
    non_claims: tuple[str, ...] = IPS_NON_CLAIMS
    execution_allowed: bool = False


def _liquidity_rule(report: ExposureReport, ips: InvestmentPolicyStatement) -> IpsRuleResult:
    floor = float(ips.liquidity_floor_months)
    boundary = f"cash runway >= {floor:.1f} months"
    if not report.cash_total_verified or report.cash_runway_months is None:
        return IpsRuleResult(
            rule="liquidity_floor",
            boundary=boundary,
            observed="unverified",
            status="blocked",
            detail="No verified cash runway (missing portfolio snapshot or recurring cashflows).",
        )
    runway = report.cash_runway_months
    status: RuleStatus = "violation" if runway < floor else "pass"
    return IpsRuleResult(
        rule="liquidity_floor",
        boundary=boundary,
        observed=f"{runway:.1f} months",
        status=status,
        detail=(
            f"Cash covers {runway:.1f} months vs the {floor:.1f}-month floor."
            if status == "pass"
            else f"Cash covers only {runway:.1f} months, below the {floor:.1f}-month floor."
        ),
    )


def _single_holding_rule(report: ExposureReport, ips: InvestmentPolicyStatement) -> IpsRuleResult:
    cap = float(ips.max_single_holding_pct)
    boundary = f"top holding <= {cap:.0%} of invested book"
    if report.holding_count == 0 or not report.holdings:
        return IpsRuleResult(
            rule="single_holding_cap",
            boundary=boundary,
            observed="no holdings",
            status="blocked",
            detail="No holdings on record to measure concentration against.",
        )
    weight = report.top_holding_weight
    top = report.holdings[0]
    status: RuleStatus = "violation" if weight > cap else "pass"
    return IpsRuleResult(
        rule="single_holding_cap",
        boundary=boundary,
        observed=f"{top.symbol} {weight:.0%}",
        status=status,
        detail=(
            f"{top.symbol} is {weight:.0%} of the invested book, within the {cap:.0%} cap."
            if status == "pass"
            else f"{top.symbol} is {weight:.0%} of the invested book, above the {cap:.0%} cap."
        ),
    )


def _high_interest_rule(
    report: ExposureReport, ips: InvestmentPolicyStatement
) -> IpsRuleResult | None:
    if ips.high_interest_rate_pct is None:
        return None
    threshold = float(ips.high_interest_rate_pct)
    boundary = f"weighted debt rate < {threshold:.0%}"
    if report.interest_bearing_debt_total <= 0 or report.weighted_avg_interest_rate is None:
        return IpsRuleResult(
            rule="high_interest_debt",
            boundary=boundary,
            observed="no interest-bearing debt",
            status="pass",
            detail="No interest-bearing debt on record.",
        )
    rate = report.weighted_avg_interest_rate
    status: RuleStatus = "violation" if rate >= threshold else "pass"
    return IpsRuleResult(
        rule="high_interest_debt",
        boundary=boundary,
        observed=f"{rate:.1%}",
        status=status,
        detail=(
            f"Weighted debt rate {rate:.1%} is within the {threshold:.0%} flag."
            if status == "pass"
            else f"Weighted debt rate {rate:.1%} is at/above the {threshold:.0%} high-rate flag."
        ),
    )


def check_ips_compliance(report: ExposureReport, ips: InvestmentPolicyStatement) -> IpsCheckReport:
    """Pure: check an exposure report against an IPS, rule by rule."""
    results: list[IpsRuleResult] = [
        _liquidity_rule(report, ips),
        _single_holding_rule(report, ips),
    ]
    high_interest = _high_interest_rule(report, ips)
    if high_interest is not None:
        results.append(high_interest)
    violations = tuple(r.rule for r in results if r.status == "violation")
    blocked = tuple(r.rule for r in results if r.status == "blocked")
    source_refs = tuple(
        sorted(
            {
                *report.provenance.portfolio,
                *report.provenance.cash,
                *report.provenance.cashflow,
                *report.provenance.liability,
                *ips.source_refs,
            }
        )
    )
    return IpsCheckReport(
        ips_id=ips.ips_id,
        as_of_date=report.as_of_date,
        results=tuple(results),
        violations=violations,
        blocked=blocked,
        source_refs=source_refs,
    )


def current_ips(engine: Engine) -> InvestmentPolicyStatement | None:
    """Return the latest active IPS, or ``None`` when none has been set."""
    with Session(engine) as session:
        statement = (
            select(InvestmentPolicyStatement)
            .where(InvestmentPolicyStatement.status == "active")
            .order_by(col(InvestmentPolicyStatement.created_at_utc).desc())
            .limit(1)
        )
        return session.exec(statement).first()


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _ips_receipt_payload(ips: InvestmentPolicyStatement, receipt_id: str) -> dict[str, Any]:
    return {
        "receipt_id": receipt_id,
        "kind": "state_core_ips",
        "created_at_utc": ips.created_at_utc,
        "ips": ips.model_dump(mode="json"),
        "governance": {
            "execution_allowed": False,
            "not_execution_authorization": True,
            "not_investment_advice": True,
            "user_set_policy": True,
        },
    }


def record_ips(
    *,
    liquidity_floor_months: Any,
    max_single_holding_pct: Any,
    cash_overweight_pct: Any = None,
    high_interest_rate_pct: Any = None,
    base_currency: str = "USD",
    allowed_asset_classes: list[str] | None = None,
    restricted_actions: list[str] | None = None,
    review_cadence: str = "",
    source_refs: list[str] | None = None,
    engine: Engine,
    receipt_root: str | Path = DEFAULT_IPS_RECEIPT_ROOT,
    ips_id: str | None = None,
    created_at_utc: str | None = None,
) -> InvestmentPolicyStatement:
    """Write a receipt-backed IPS and mark it the active policy.

    Any previously active IPS is superseded (status flips to ``superseded``) so
    ``current_ips`` returns exactly one active policy. The receipt file is the
    source of truth; the row is the queryable mirror.
    """
    created_at = created_at_utc or _now_utc()
    # The DB primary key may come from a caller-supplied id, so sanitize it; but the
    # receipt *filename* is server-generated (stamp + uuid) and never derived from
    # caller input, so the path can never depend on a user-controlled value.
    resolved_id = _safe_id(ips_id) if ips_id else f"ips_{_stamp()}_{uuid4().hex[:8]}"
    receipt_id = f"receipt_ips_{_stamp()}_{uuid4().hex[:8]}"
    receipt_path = resolve_under(receipt_root, "ips", f"{receipt_id}.json")
    ips = InvestmentPolicyStatement(
        ips_id=resolved_id,
        status="active",
        base_currency=base_currency,
        liquidity_floor_months=_decimal(liquidity_floor_months),
        max_single_holding_pct=_decimal(max_single_holding_pct),
        cash_overweight_pct=_optional_decimal(cash_overweight_pct),
        high_interest_rate_pct=_optional_decimal(high_interest_rate_pct),
        allowed_asset_classes=list(allowed_asset_classes or []),
        restricted_actions=list(restricted_actions or []),
        review_cadence=review_cadence,
        source_refs=list(source_refs or []),
        receipt_ref=_display_path(receipt_path),
        execution_allowed=False,
        created_at_utc=created_at,
        as_of_utc=created_at,
    )
    receipt_existed = receipt_path.exists()
    atomic_write_json(receipt_path, _ips_receipt_payload(ips, receipt_id))
    # Build the index record directly from known fields rather than re-reading the
    # path we just constructed (which would route a derived path back into the
    # receipt-reading code); the row is the queryable mirror of the receipt file.
    display = _display_path(receipt_path)
    index = ReceiptIndex(
        receipt_id=receipt_id,
        kind="state_core_ips",
        path=display,
        created_at_utc=created_at,
        source_refs=[display],
        refs=[resolved_id, *ips.source_refs],
    )
    superseded = _supersede_active(engine, keep=resolved_id)
    try:
        upsert_records([*superseded, ips, index], engine=engine)
    except StateCoreStoreError:
        if not receipt_existed:
            remove_file_best_effort(receipt_path)
        raise
    return ips


def _supersede_active(engine: Engine, *, keep: str) -> list[InvestmentPolicyStatement]:
    with Session(engine) as session:
        rows = session.exec(
            select(InvestmentPolicyStatement).where(InvestmentPolicyStatement.status == "active")
        ).all()
    superseded: list[InvestmentPolicyStatement] = []
    for row in rows:
        if row.ips_id == keep:
            continue
        row.status = "superseded"
        superseded.append(row)
    return superseded


def _safe_id(value: str) -> str:
    # Map every path-significant character (including ".") to "_", so an id can
    # never carry a ".." traversal segment even before resolve_under guards it.
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _decimal(value: Any):
    from decimal import Decimal

    return value if isinstance(value, Decimal) else Decimal(str(value))


def _optional_decimal(value: Any):
    if value is None:
        return None
    return _decimal(value)
