# finharness-test-runner: pytest
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from finharness.capital_truth import (
    CapitalTruthAdmissionStatus,
    CapitalTruthInput,
    CapitalTruthResult,
    CapitalUseCase,
    EvidenceIntegrityStatus,
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

    assert result.capital_truth_admission is CapitalTruthAdmissionStatus.BLOCKED, name
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

    assert result.capital_truth_admission is CapitalTruthAdmissionStatus.BLOCKED
    assert any(code.startswith("time_bound_fx_") for code in result.blockers)


def test_intact_evidence_does_not_admit_unverified_provenance() -> None:
    result = evaluate_capital_truth(valid_input(provenance_verified=False))

    assert result.evidence_integrity is EvidenceIntegrityStatus.INTACT
    assert result.capital_truth_admission is CapitalTruthAdmissionStatus.BLOCKED
    assert result.reconciled is False


def test_missing_optional_valuation_is_partial_and_not_admitted() -> None:
    result = evaluate_capital_truth(valid_input(valued_at=None, market_price_observed_at=None))

    assert result.evidence_integrity is EvidenceIntegrityStatus.INTACT
    assert result.capital_truth_admission is CapitalTruthAdmissionStatus.PARTIAL


def test_complete_current_evidence_is_admitted_and_reconciled() -> None:
    result = evaluate_capital_truth(valid_input())

    assert result.evidence_integrity is EvidenceIntegrityStatus.INTACT
    assert result.capital_truth_admission is CapitalTruthAdmissionStatus.ADMITTED
    assert result.current is True
    assert result.reconciled is True


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"receipt_present": False}, EvidenceIntegrityStatus.MISSING),
        ({"db_mirror_present": False}, EvidenceIntegrityStatus.MISSING),
        ({"receipt_hash_valid": False}, EvidenceIntegrityStatus.CORRUPT),
        ({"db_mirror_matches_receipt": False}, EvidenceIntegrityStatus.CORRUPT),
    ],
)
def test_evidence_integrity_has_exact_non_admission_meaning(
    changes: dict[str, object],
    expected: EvidenceIntegrityStatus,
) -> None:
    result = evaluate_capital_truth(valid_input(**changes))

    assert result.evidence_integrity is expected
    assert result.capital_truth_admission is CapitalTruthAdmissionStatus.BLOCKED


def test_result_contract_rejects_verified_alias_and_unknown_fields() -> None:
    payload = evaluate_capital_truth(valid_input()).model_dump(mode="json")

    for field in ("verified", "admitted", "readiness", "truth_ok"):
        with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
            CapitalTruthResult.model_validate({**payload, field: True})


def test_result_contract_has_only_named_truth_dimensions() -> None:
    assert set(CapitalTruthResult.model_fields) == {
        "evidence_integrity",
        "capital_truth_admission",
        "current",
        "reconciled",
        "blockers",
        "warnings",
    }


def test_named_truth_dimension_values_are_exact() -> None:
    assert {item.value for item in EvidenceIntegrityStatus} == {
        "intact",
        "missing",
        "corrupt",
        "unavailable",
    }
    assert {item.value for item in CapitalTruthAdmissionStatus} == {
        "admitted",
        "partial",
        "blocked",
        "unavailable",
    }


def test_naive_time_is_rejected() -> None:
    with pytest.raises(ValidationError, match="evaluated_at must be timezone-aware"):
        valid_input(evaluated_at=datetime(2026, 7, 12, 12))
