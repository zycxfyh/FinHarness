"""Fail-closed scalar and time semantics for production capital imports."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

FindingSeverity = Literal["partial", "blocking"]


@dataclass(frozen=True)
class ImportFinding:
    code: str
    severity: FindingSeverity
    message: str
    record_type: str | None = None
    record_number: int | None = None
    field: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class CapitalImportContractError(ValueError):
    """Raised with machine-readable findings when source input is unsafe."""

    def __init__(self, finding: ImportFinding) -> None:
        self.findings = (finding,)
        super().__init__(finding.message)


@dataclass(frozen=True)
class ImportTimeSemantics:
    effective_at_utc: str
    observed_at_utc: str
    valued_at_utc: str | None
    ingested_at_utc: str
    recorded_at_utc: str

    def as_dict(self) -> dict[str, str | None]:
        return asdict(self)


def _blocking(
    code: str,
    message: str,
    *,
    record_type: str | None = None,
    record_number: int | None = None,
    field: str | None = None,
) -> CapitalImportContractError:
    return CapitalImportContractError(
        ImportFinding(code, "blocking", message, record_type, record_number, field)
    )


def exact_decimal(
    value: Any,
    *,
    field: str,
    record_type: str | None = None,
    record_number: int | None = None,
) -> Decimal:
    """Parse exact decimal input while rejecting binary floating-point values."""
    if isinstance(value, (float, bool)):
        raise _blocking(
            "monetary_float_forbidden",
            f"{field} must be an exact decimal string or Decimal, not float",
            record_type=record_type,
            record_number=record_number,
            field=field,
        )
    try:
        parsed = value if isinstance(value, Decimal) else Decimal(str(value).strip())
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise _blocking(
            "invalid_decimal",
            f"{field} is not a valid decimal amount: {value!r}",
            record_type=record_type,
            record_number=record_number,
            field=field,
        ) from exc
    if not parsed.is_finite():
        raise _blocking(
            "non_finite_decimal",
            f"{field} must be finite",
            record_type=record_type,
            record_number=record_number,
            field=field,
        )
    return parsed


def currency_code(
    value: Any,
    *,
    field: str = "currency",
    record_type: str | None = None,
    record_number: int | None = None,
) -> str:
    """Validate an explicit ISO-style three-letter currency code."""
    clean = str(value or "").strip().upper()
    if len(clean) != 3 or not clean.isascii() or not clean.isalpha():
        raise _blocking(
            "invalid_or_missing_currency",
            f"{field} must be an explicit three-letter currency code",
            record_type=record_type,
            record_number=record_number,
            field=field,
        )
    return clean


def canonical_utc(
    value: str | datetime,
    *,
    field: str,
    record_type: str | None = None,
    record_number: int | None = None,
) -> str:
    """Parse a timezone-aware timestamp and normalize it to canonical UTC."""
    try:
        parsed = (
            value
            if isinstance(value, datetime)
            else datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
        )
    except (TypeError, ValueError) as exc:
        raise _blocking(
            "invalid_timestamp",
            f"{field} is not a valid ISO-8601 timestamp: {value!r}",
            record_type=record_type,
            record_number=record_number,
            field=field,
        ) from exc
    if parsed.utcoffset() is None:
        raise _blocking(
            "timezone_ambiguous",
            f"{field} must include a UTC offset",
            record_type=record_type,
            record_number=record_number,
            field=field,
        )
    return parsed.astimezone(UTC).isoformat()


def build_time_semantics(
    *,
    effective_at: str | datetime,
    observed_at: str | datetime,
    valued_at: str | datetime | None,
    ingested_at: str | datetime,
    recorded_at: str | datetime | None = None,
    valuation_max_age: timedelta = timedelta(hours=24),
) -> tuple[ImportTimeSemantics, tuple[ImportFinding, ...]]:
    """Build ordered clocks and surface stale valuation as a blocking finding."""
    effective = canonical_utc(effective_at, field="effective_at_utc")
    observed = canonical_utc(observed_at, field="observed_at_utc")
    valued = canonical_utc(valued_at, field="valued_at_utc") if valued_at else None
    ingested = canonical_utc(ingested_at, field="ingested_at_utc")
    recorded = canonical_utc(recorded_at or ingested, field="recorded_at_utc")
    parsed = {
        key: datetime.fromisoformat(value)
        for key, value in {
            "effective": effective,
            "observed": observed,
            "ingested": ingested,
            "recorded": recorded,
        }.items()
    }
    if parsed["effective"] > parsed["observed"]:
        raise _blocking("invalid_time_order", "effective_at_utc cannot follow observed_at_utc")
    if parsed["observed"] > parsed["ingested"]:
        raise _blocking("invalid_time_order", "observed_at_utc cannot follow ingested_at_utc")
    if parsed["ingested"] > parsed["recorded"]:
        raise _blocking("invalid_time_order", "ingested_at_utc cannot follow recorded_at_utc")
    findings: list[ImportFinding] = []
    if valued is not None:
        valued_dt = datetime.fromisoformat(valued)
        if valued_dt > parsed["observed"]:
            raise _blocking("invalid_time_order", "valued_at_utc cannot follow observed_at_utc")
        if parsed["observed"] - valued_dt > valuation_max_age:
            findings.append(
                ImportFinding(
                    "stale_valuation",
                    "blocking",
                    "valuation is older than the admitted 24-hour import window",
                    field="valued_at_utc",
                )
            )
    return (
        ImportTimeSemantics(effective, observed, valued, ingested, recorded),
        tuple(findings),
    )


def completeness_status(findings: list[ImportFinding] | tuple[ImportFinding, ...]) -> str:
    if any(finding.severity == "blocking" for finding in findings):
        return "blocked"
    if findings:
        return "partial"
    return "complete"
