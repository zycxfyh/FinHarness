"""Typed, evidence-bound valuation assessment for capital positions.

Functional core: adapters and the materializer call
``assess_position_valuation``; no adapter may invent ``valued`` independently.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from finharness.capital_import_contract import ImportFinding

if TYPE_CHECKING:
    from finharness.statecore.models import Position
else:
    Position = Any


class ValuationStatus(StrEnum):
    VALUED = "valued"
    VALUED_CONVERTED = "valued_converted"
    UNPRICED = "unpriced"
    FX_MISSING = "fx_missing"
    STALE = "stale"
    UNKNOWN_LEGACY = "unknown_legacy"


ADMITTED_VALUATION_STATUSES = frozenset(
    {ValuationStatus.VALUED.value, ValuationStatus.VALUED_CONVERTED.value}
)


@dataclass(frozen=True)
class ValuationEvidence:
    quantity: Decimal
    market_value: Decimal | None
    valuation_currency: str | None
    unit_price: Decimal | None
    price_currency: str | None
    valued_at_utc: str | None
    price_source_ref: str | None
    fx_rate: Decimal | None = None
    fx_as_of_utc: str | None = None
    fx_source_ref: str | None = None


@dataclass(frozen=True)
class ValuationPolicy:
    policy_id: str
    max_price_age: timedelta
    max_fx_age: timedelta
    reconciliation_tolerance: Decimal


BASE_VALUATION_POLICY_V1 = ValuationPolicy(
    policy_id="finharness.position_valuation.base.v1",
    max_price_age=timedelta(hours=24),
    max_fx_age=timedelta(hours=24),
    reconciliation_tolerance=Decimal("0.01"),
)


@dataclass(frozen=True)
class ValuationAssessment:
    status: ValuationStatus
    findings: tuple[ImportFinding, ...]
    policy_id: str
    evaluated_at_utc: str

    @property
    def admitted(self) -> bool:
        return self.status.value in ADMITTED_VALUATION_STATUSES and not self.findings

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(finding.code for finding in self.findings)


class PositionValuationError(ValueError):
    """Raised when a position cannot support a monetary use case."""


@dataclass(frozen=True)
class ValuationTotals:
    base_currency: str | None
    unified_total: Decimal | None
    per_currency_totals: dict[str, Decimal]
    blockers: tuple[str, ...]

    @property
    def admitted(self) -> bool:
        return not self.blockers and self.unified_total is not None


def _finding(
    code: str,
    message: str,
    *,
    record_id: str | None,
    record_number: int | None,
    field: str | None,
) -> ImportFinding:
    return ImportFinding(
        code,
        "blocking",
        message,
        record_type="position",
        record_number=record_number,
        field=field,
        record_id=record_id,
    )


def _has_typed_evidence(evidence: ValuationEvidence) -> bool:
    return any(
        value is not None and value != ""
        for value in (
            evidence.unit_price,
            evidence.valuation_currency,
            evidence.price_currency,
            evidence.valued_at_utc,
            evidence.price_source_ref,
            evidence.fx_rate,
            evidence.fx_as_of_utc,
            evidence.fx_source_ref,
        )
    )


def assess_position_valuation(  # noqa: C901 -- single ordered valuation state machine
    evidence: ValuationEvidence,
    *,
    record_id: str | None,
    record_number: int | None = None,
    evaluated_at_utc: str,
    policy: ValuationPolicy = BASE_VALUATION_POLICY_V1,
    check_freshness: bool = True,
    allow_unknown_legacy: bool = True,
) -> ValuationAssessment:
    """Derive valuation status and findings from evidence alone.

    Pure: no DB, filesystem, wall clock, or stored status input.
    """
    structural: list[ImportFinding] = []
    timestamp_findings: list[ImportFinding] = []
    fx_findings: list[ImportFinding] = []
    recon_findings: list[ImportFinding] = []
    freshness_findings: list[ImportFinding] = []

    def miss(code: str, field: str, message: str) -> None:
        structural.append(
            _finding(
                code, message, record_id=record_id, record_number=record_number, field=field
            )
        )

    if not _has_typed_evidence(evidence) and allow_unknown_legacy:
        coarse = _finding(
            "valuation_unknown_legacy",
            "position lacks typed valuation evidence",
            record_id=record_id,
            record_number=record_number,
            field="valuation_status",
        )
        return ValuationAssessment(
            status=ValuationStatus.UNKNOWN_LEGACY,
            findings=(coarse,),
            policy_id=policy.policy_id,
            evaluated_at_utc=evaluated_at_utc,
        )
    # Not legacy: production typed imports fall through to structural checks below.

    if evidence.market_value is None:
        miss("market_value_missing", "market_value", "market_value is required")
    if evidence.unit_price is None:
        miss("unit_price_missing", "unit_price", "unit_price is required")
    if not evidence.valuation_currency:
        miss(
            "valuation_currency_missing",
            "valuation_currency",
            "valuation_currency is required",
        )
    if not evidence.price_currency:
        miss("price_currency_missing", "price_currency", "price_currency is required")
    if not evidence.valued_at_utc:
        miss("valued_at_utc_missing", "valued_at_utc", "valued_at_utc is required")
    if not evidence.price_source_ref:
        miss(
            "price_source_ref_missing",
            "price_source_ref",
            "price_source_ref is required",
        )

    cross = (
        evidence.price_currency is not None
        and evidence.valuation_currency is not None
        and evidence.price_currency != evidence.valuation_currency
    )
    fx_incomplete = False
    if cross:
        if evidence.fx_rate is None:
            fx_findings.append(
                _finding(
                    "fx_rate_missing",
                    "fx_rate is required for cross-currency valuation",
                    record_id=record_id,
                    record_number=record_number,
                    field="fx_rate",
                )
            )
            fx_incomplete = True
        elif evidence.fx_rate <= 0:
            fx_findings.append(
                _finding(
                    "fx_rate_not_positive",
                    "fx_rate must be positive",
                    record_id=record_id,
                    record_number=record_number,
                    field="fx_rate",
                )
            )
            fx_incomplete = True
        if not evidence.fx_as_of_utc:
            fx_findings.append(
                _finding(
                    "fx_as_of_utc_missing",
                    "fx_as_of_utc is required for cross-currency valuation",
                    record_id=record_id,
                    record_number=record_number,
                    field="fx_as_of_utc",
                )
            )
            fx_incomplete = True
        if not evidence.fx_source_ref:
            fx_findings.append(
                _finding(
                    "fx_source_ref_missing",
                    "fx_source_ref is required for cross-currency valuation",
                    record_id=record_id,
                    record_number=record_number,
                    field="fx_source_ref",
                )
            )
            fx_incomplete = True

    try:
        evaluated_at = datetime.fromisoformat(
            evaluated_at_utc.strip().replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        raise PositionValuationError(
            f"invalid evaluated_at_utc: {evaluated_at_utc!r}"
        ) from None
    if evaluated_at.utcoffset() is None:
        raise PositionValuationError(
            f"timezone-naive evaluated_at_utc: {evaluated_at_utc!r}"
        )
    evaluated_at = evaluated_at.astimezone(UTC)

    valued_at_dt: datetime | None = None
    if evidence.valued_at_utc:
        try:
            raw = datetime.fromisoformat(
                evidence.valued_at_utc.strip().replace("Z", "+00:00")
            )
        except (TypeError, ValueError):
            timestamp_findings.append(
                _finding(
                    "valued_at_invalid",
                    "valued_at_utc is not a valid ISO-8601 timestamp",
                    record_id=record_id,
                    record_number=record_number,
                    field="valued_at_utc",
                )
            )
        else:
            if raw.utcoffset() is None:
                timestamp_findings.append(
                    _finding(
                        "valued_at_not_timezone_aware",
                        "valued_at_utc must include a UTC offset",
                        record_id=record_id,
                        record_number=record_number,
                        field="valued_at_utc",
                    )
                )
            else:
                valued_at_dt = raw.astimezone(UTC)
                if valued_at_dt > evaluated_at:
                    timestamp_findings.append(
                        _finding(
                            "valued_at_after_evaluation",
                            "valued_at_utc cannot follow evaluation time",
                            record_id=record_id,
                            record_number=record_number,
                            field="valued_at_utc",
                        )
                    )

    fx_as_of_dt: datetime | None = None
    if evidence.fx_as_of_utc:
        try:
            raw_fx = datetime.fromisoformat(
                evidence.fx_as_of_utc.strip().replace("Z", "+00:00")
            )
        except (TypeError, ValueError):
            timestamp_findings.append(
                _finding(
                    "fx_as_of_invalid",
                    "fx_as_of_utc is not a valid ISO-8601 timestamp",
                    record_id=record_id,
                    record_number=record_number,
                    field="fx_as_of_utc",
                )
            )
        else:
            if raw_fx.utcoffset() is None:
                timestamp_findings.append(
                    _finding(
                        "fx_as_of_not_timezone_aware",
                        "fx_as_of_utc must include a UTC offset",
                        record_id=record_id,
                        record_number=record_number,
                        field="fx_as_of_utc",
                    )
                )
            else:
                fx_as_of_dt = raw_fx.astimezone(UTC)
                if fx_as_of_dt > evaluated_at:
                    timestamp_findings.append(
                        _finding(
                            "fx_as_of_after_evaluation",
                            "fx_as_of_utc cannot follow evaluation time",
                            record_id=record_id,
                            record_number=record_number,
                            field="fx_as_of_utc",
                        )
                    )

    fx_valid = (
        evidence.fx_rate is not None
        and evidence.fx_rate > 0
        and evidence.fx_as_of_utc
        and evidence.fx_source_ref
    )

    if (
        evidence.market_value is not None
        and evidence.unit_price is not None
        and evidence.valuation_currency
        and evidence.price_currency
    ):
        if cross and not fx_valid:
            # Cross-currency reconciliation requires complete FX evidence.
            pass
        else:
            expected = evidence.quantity * evidence.unit_price
            if cross and fx_valid:
                expected *= evidence.fx_rate
            if abs(expected - evidence.market_value) > policy.reconciliation_tolerance:
                recon_findings.append(
                    _finding(
                        "valuation_components_do_not_reconcile",
                        "market_value does not reconcile with quantity * unit_price [* fx]",
                        record_id=record_id,
                        record_number=record_number,
                        field="market_value",
                    )
                )

    price_stale = False
    fx_stale = False
    if check_freshness:
        if valued_at_dt is not None and evaluated_at - valued_at_dt > policy.max_price_age:
            price_stale = True
            freshness_findings.append(
                _finding(
                    "market_price_stale",
                    "market price exceeds admitted freshness window",
                    record_id=record_id,
                    record_number=record_number,
                    field="valued_at_utc",
                )
            )
        if (
            cross
            and fx_as_of_dt is not None
            and evaluated_at - fx_as_of_dt > policy.max_fx_age
        ):
            fx_stale = True
            freshness_findings.append(
                _finding(
                    "fx_stale",
                    "FX evidence exceeds admitted freshness window",
                    record_id=record_id,
                    record_number=record_number,
                    field="fx_as_of_utc",
                )
            )

    structural_block = bool(structural or timestamp_findings or recon_findings)
    if structural_block:
        status = ValuationStatus.UNPRICED
    elif cross and fx_incomplete:
        status = ValuationStatus.FX_MISSING
    elif price_stale or fx_stale:
        status = ValuationStatus.STALE
    elif cross:
        status = ValuationStatus.VALUED_CONVERTED
    else:
        status = ValuationStatus.VALUED

    detail = (
        *structural,
        *timestamp_findings,
        *fx_findings,
        *recon_findings,
        *freshness_findings,
    )
    coarse_code = {
        ValuationStatus.UNPRICED: "valuation_unpriced",
        ValuationStatus.FX_MISSING: "valuation_fx_missing",
        ValuationStatus.STALE: "valuation_stale",
        ValuationStatus.UNKNOWN_LEGACY: "valuation_unknown_legacy",
    }.get(status)
    findings: list[ImportFinding] = []
    if coarse_code is not None:
        findings.append(
            _finding(
                coarse_code,
                f"position valuation status is {status.value}",
                record_id=record_id,
                record_number=record_number,
                field="valuation_status",
            )
        )
    findings.extend(detail)

    if status in (ValuationStatus.VALUED, ValuationStatus.VALUED_CONVERTED) and findings:
        status = ValuationStatus.UNPRICED
        findings = [
            _finding(
                "valuation_unpriced",
                "position valuation status is unpriced",
                record_id=record_id,
                record_number=record_number,
                field="valuation_status",
            ),
            *detail,
        ]

    return ValuationAssessment(
        status=status,
        findings=tuple(findings),
        policy_id=policy.policy_id,
        evaluated_at_utc=evaluated_at_utc,
    )


def evidence_from_position(position: Position) -> ValuationEvidence:
    return ValuationEvidence(
        quantity=position.quantity,
        market_value=position.market_value,
        valuation_currency=position.valuation_currency,
        unit_price=position.unit_price,
        price_currency=position.price_currency,
        valued_at_utc=position.valued_at_utc,
        price_source_ref=position.price_source_ref,
        fx_rate=position.fx_rate,
        fx_as_of_utc=position.fx_as_of_utc,
        fx_source_ref=position.fx_source_ref,
    )


def valuation_blockers(
    position: Position,
    *,
    evaluated_at: datetime | None = None,
    max_age: timedelta | None = None,
) -> tuple[str, ...]:
    """Return stable blocker codes via the canonical assessor.

    Does not trust stored ``valuation_status`` as business input. Optional
    ``evaluated_at`` / ``max_age`` enable freshness checks for time-sensitive uses.
    When ``evaluated_at`` is omitted, ``position.as_of_utc`` is used when present
    so import-time freshness remains re-derivable without a wall clock.
    """
    evidence = evidence_from_position(position)
    if evaluated_at is not None:
        evaluated_at_utc = evaluated_at.astimezone(UTC).isoformat()
        check_freshness = True
    elif getattr(position, "as_of_utc", None):
        evaluated_at_utc = str(position.as_of_utc)
        check_freshness = True
    else:
        evaluated_at_utc = position.valued_at_utc or "1970-01-01T00:00:00+00:00"
        check_freshness = False
    policy = (
        BASE_VALUATION_POLICY_V1
        if max_age is None
        else replace(
            BASE_VALUATION_POLICY_V1,
            max_price_age=max_age,
            max_fx_age=max_age,
        )
    )
    assessment = assess_position_valuation(
        evidence,
        record_id=getattr(position, "position_id", None),
        evaluated_at_utc=evaluated_at_utc,
        policy=policy,
        check_freshness=check_freshness,
    )
    codes = list(assessment.codes)
    stored = getattr(position, "valuation_status", None)
    if stored is not None and stored != assessment.status.value:
        codes.append("valuation_status_mismatch")
    return tuple(dict.fromkeys(codes))


def reconcile_position_totals(
    positions: Iterable[Position],
    *,
    evaluated_at: datetime | None = None,
    max_age: timedelta | None = None,
) -> ValuationTotals:
    """Aggregate admitted components; never add unlike or unverified currencies."""
    totals: dict[str, Decimal] = {}
    blockers: list[str] = []
    for position in positions:
        row_blockers = valuation_blockers(
            position, evaluated_at=evaluated_at, max_age=max_age
        )
        blockers.extend(f"{position.position_id}:{code}" for code in row_blockers)
        if row_blockers or position.market_value is None or not position.valuation_currency:
            continue
        currency = position.valuation_currency
        totals[currency] = totals.get(currency, Decimal("0")) + position.market_value
    if len(totals) > 1:
        blockers.append("mixed_valuation_currencies")
    base_currency = next(iter(totals)) if len(totals) == 1 else None
    unified = (
        totals[base_currency] if base_currency is not None and not blockers else None
    )
    return ValuationTotals(
        base_currency=base_currency,
        unified_total=unified,
        per_currency_totals=totals,
        blockers=tuple(blockers),
    )
