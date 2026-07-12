"""Executable vocabulary for claims made from capital-state observations.

This module admits a capital observation for a named use case. It does not
perform accounting, FX conversion, pricing, or reconciliation mechanics.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CapitalUseCase(StrEnum):
    CAPITAL_STATE = "capital_state"
    SCENARIO = "scenario"
    DECISION = "decision"
    DAILY_BRIEF = "daily_brief"
    AGENT = "agent"


class CapitalReadiness(StrEnum):
    USABLE = "usable"
    PARTIAL = "partial"
    BLOCKED = "blocked"


class CapitalTruthInput(BaseModel):
    """Evidence needed to make bounded current/verified/reconciled claims."""

    model_config = ConfigDict(frozen=True)

    use_case: CapitalUseCase
    evaluated_at: datetime
    effective_at: datetime
    observed_at: datetime
    valued_at: datetime | None
    ingested_at: datetime
    currencies: frozenset[str] = Field(min_length=1)
    fx_observed_at: datetime | None = None
    market_price_observed_at: datetime | None = None
    receipt_present: bool
    receipt_hash_valid: bool
    db_mirror_present: bool
    db_mirror_matches_receipt: bool
    provenance_verified: bool
    instrument_identity_unambiguous: bool
    cross_account_assets_deduplicated: bool

    @model_validator(mode="after")
    def require_timezone_aware_times(self) -> CapitalTruthInput:
        fields = (
            "evaluated_at",
            "effective_at",
            "observed_at",
            "valued_at",
            "ingested_at",
            "fx_observed_at",
            "market_price_observed_at",
        )
        for field in fields:
            value = getattr(self, field)
            if value is not None and value.utcoffset() is None:
                raise ValueError(f"{field} must be timezone-aware")
        return self


class CapitalTruthResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    readiness: CapitalReadiness
    admitted: bool
    current: bool
    verified: bool
    reconciled: bool
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


_MAX_AGE = {
    CapitalUseCase.CAPITAL_STATE: timedelta(hours=24),
    CapitalUseCase.DAILY_BRIEF: timedelta(hours=24),
    CapitalUseCase.SCENARIO: timedelta(hours=4),
    CapitalUseCase.DECISION: timedelta(hours=4),
    CapitalUseCase.AGENT: timedelta(hours=1),
}


def _evidence_blockers(value: CapitalTruthInput) -> list[str]:
    checks = (
        (not value.receipt_present, "receipt_or_index_missing"),
        (value.receipt_present and not value.receipt_hash_valid, "receipt_integrity_failed"),
        (not value.db_mirror_present, "db_mirror_missing"),
        (
            value.db_mirror_present and not value.db_mirror_matches_receipt,
            "db_receipt_divergence",
        ),
        (not value.provenance_verified, "provenance_unverified"),
        (not value.instrument_identity_unambiguous, "instrument_identity_ambiguous"),
        (not value.cross_account_assets_deduplicated, "cross_account_asset_duplicate"),
    )
    return [code for failed, code in checks if failed]


def _valuation_findings(
    value: CapitalTruthInput, max_age: timedelta
) -> tuple[list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    if len(value.currencies) > 1:
        if value.fx_observed_at is None:
            blockers.append("time_bound_fx_missing")
        elif value.evaluated_at - value.fx_observed_at > max_age:
            blockers.append("time_bound_fx_stale")
    if value.valued_at is None or value.market_price_observed_at is None:
        warnings.append("market_valuation_incomplete")
    elif value.evaluated_at - value.market_price_observed_at > max_age:
        blockers.append("market_price_stale")
    return blockers, warnings


def evaluate_capital_truth(value: CapitalTruthInput) -> CapitalTruthResult:
    """Fail closed on defects that can change a capital decision."""

    blockers: list[str] = []
    warnings: list[str] = []
    max_age = _MAX_AGE[value.use_case]
    current = value.evaluated_at - value.observed_at <= max_age

    if not current:
        blockers.append("snapshot_stale")
    if value.effective_at > value.evaluated_at:
        blockers.append("effective_time_in_future")
    if value.observed_at > value.ingested_at:
        blockers.append("observation_after_ingestion")
    blockers.extend(_evidence_blockers(value))
    valuation_blockers, warnings = _valuation_findings(value, max_age)
    blockers.extend(valuation_blockers)

    verified = value.receipt_present and value.receipt_hash_valid and value.provenance_verified
    reconciled = (
        verified
        and value.db_mirror_present
        and value.db_mirror_matches_receipt
        and value.cross_account_assets_deduplicated
    )
    readiness = (
        CapitalReadiness.BLOCKED
        if blockers
        else CapitalReadiness.PARTIAL
        if warnings
        else CapitalReadiness.USABLE
    )
    return CapitalTruthResult(
        readiness=readiness,
        admitted=readiness is CapitalReadiness.USABLE,
        current=current,
        verified=verified,
        reconciled=reconciled,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )
