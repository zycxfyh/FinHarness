from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from finharness.capital_truth import (
    CapitalReadiness,
    CapitalTruthInput,
    CapitalUseCase,
    evaluate_capital_truth,
)

NOW = datetime(2026, 7, 12, 12, tzinfo=UTC)


def valid_input(**changes: object) -> CapitalTruthInput:
    values: dict[str, object] = {
        "use_case": CapitalUseCase.DECISION,
        "evaluated_at": NOW,
        "effective_at": NOW - timedelta(minutes=30),
        "observed_at": NOW - timedelta(minutes=20),
        "valued_at": NOW - timedelta(minutes=15),
        "ingested_at": NOW - timedelta(minutes=10),
        "currencies": frozenset({"USD"}),
        "market_price_observed_at": NOW - timedelta(minutes=15),
        "receipt_present": True,
        "receipt_hash_valid": True,
        "db_mirror_present": True,
        "db_mirror_matches_receipt": True,
        "provenance_verified": True,
        "instrument_identity_unambiguous": True,
        "cross_account_assets_deduplicated": True,
    }
    values.update(changes)
    return CapitalTruthInput.model_validate(values)


@pytest.mark.parametrize(
    ("name", "changes", "blocker"),
    [
        ("stale snapshot", {"observed_at": NOW - timedelta(days=2)}, "snapshot_stale"),
        ("missing receipt/index", {"receipt_present": False}, "receipt_or_index_missing"),
        ("forged provenance", {"provenance_verified": False}, "provenance_unverified"),
        (
            "symbol collision",
            {"instrument_identity_unambiguous": False},
            "instrument_identity_ambiguous",
        ),
        (
            "duplicate cross-account asset",
            {"cross_account_assets_deduplicated": False},
            "cross_account_asset_duplicate",
        ),
        (
            "stale market price",
            {"market_price_observed_at": NOW - timedelta(days=2)},
            "market_price_stale",
        ),
    ],
)
def test_adversarial_inputs_fail_closed(
    name: str, changes: dict[str, object], blocker: str
) -> None:
    result = evaluate_capital_truth(valid_input(**changes))

    assert result.readiness is CapitalReadiness.BLOCKED, name
    assert result.admitted is False
    assert blocker in result.blockers


@pytest.mark.parametrize("fx_age", [None, timedelta(days=2)])
def test_mixed_currency_without_current_time_bound_fx_is_blocked(
    fx_age: timedelta | None,
) -> None:
    result = evaluate_capital_truth(
        valid_input(
            currencies=frozenset({"USD", "EUR"}),
            fx_observed_at=None if fx_age is None else NOW - fx_age,
        )
    )

    assert result.readiness is CapitalReadiness.BLOCKED
    assert any(code.startswith("time_bound_fx_") for code in result.blockers)


def test_receipt_integrity_alone_is_not_financial_verification() -> None:
    result = evaluate_capital_truth(valid_input(provenance_verified=False))

    assert result.verified is False
    assert result.reconciled is False


def test_missing_optional_valuation_is_partial_and_not_admitted() -> None:
    result = evaluate_capital_truth(valid_input(valued_at=None, market_price_observed_at=None))

    assert result.readiness is CapitalReadiness.PARTIAL
    assert result.admitted is False


def test_complete_current_evidence_is_usable_verified_and_reconciled() -> None:
    result = evaluate_capital_truth(valid_input())

    assert result.readiness is CapitalReadiness.USABLE
    assert result.admitted is True
    assert result.current is True
    assert result.verified is True
    assert result.reconciled is True


def test_naive_time_is_rejected() -> None:
    with pytest.raises(ValidationError, match="evaluated_at must be timezone-aware"):
        valid_input(evaluated_at=datetime(2026, 7, 12, 12))
