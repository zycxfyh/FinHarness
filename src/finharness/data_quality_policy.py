"""Data quality policy and assessment models v0.

Read-only assessment over existing market-data receipt metadata.
No network calls. No ingestion. No Agent/scenario/paper integration.

Freshness is computed from snapshot.as_of_utc. Quality, bias, and reconciliation
are derived from existing MarketDataQuality, data_bias_controls, and
reconciliation fields in the receipt.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from finharness.market_data import MarketDataQuality

# Default freshness thresholds (days since latest bar).
DEFAULT_STALE_AFTER_DAYS = 5
DEFAULT_CRITICAL_AFTER_DAYS = 30

DATA_QUALITY_NON_CLAIMS = (
    "Read-only quality assessment from receipt metadata.",
    "No network calls triggered.",
    "No execution authorization.",
    "No provider fetch or refresh.",
    "Freshness computed from snapshot.as_of_utc only.",
)

FreshnessStatus = Literal["fresh", "stale", "critically_stale", "unknown"]
QualityStatus = Literal["ok", "degraded", "unknown"]
BiasStatus = Literal["controlled", "uncontrolled"]
ReadinessStatus = Literal["usable", "usable_with_warnings", "not_ready"]
FindingSeverity = Literal["info", "warning", "critical"]


class FreshnessPolicy(BaseModel):
    """Policy for assessing data freshness from snapshot timestamp."""

    model_config = ConfigDict(frozen=True)

    policy_id: str = "default_v0"
    dataset: str = "*"
    max_age_days: int = DEFAULT_STALE_AFTER_DAYS
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS
    critical_after_days: int = DEFAULT_CRITICAL_AFTER_DAYS
    timezone: str = "UTC"
    applies_to: list[str] = Field(default_factory=lambda: ["*"])
    blocks: list[str] = Field(default_factory=list)
    non_claims: tuple[str, ...] = DATA_QUALITY_NON_CLAIMS
    execution_allowed: bool = False


class DataQualityFinding(BaseModel):
    """A single quality, freshness, bias, or reconciliation finding."""

    model_config = ConfigDict(frozen=True)

    finding_id: str
    severity: FindingSeverity
    code: str
    message: str
    source_ref: str | None = None
    blocks: list[str] = Field(default_factory=list)


class DataQualityReport(BaseModel):
    """Structured quality report for a single dataset snapshot."""

    model_config = ConfigDict(from_attributes=True)

    report_id: str
    dataset_key: str
    as_of_utc: str
    latest_receipt_ref: str
    freshness_status: FreshnessStatus = "unknown"
    quality_status: QualityStatus = "unknown"
    reconciliation_status: str = "single_source_unreconciled"
    bias_status: BiasStatus = "uncontrolled"
    readiness_status: ReadinessStatus = "not_ready"
    findings: list[DataQualityFinding] = Field(default_factory=list)
    blocks: list[str] = Field(default_factory=list)
    non_claims: tuple[str, ...] = DATA_QUALITY_NON_CLAIMS
    execution_allowed: bool = False


def _finding_id(prefix: str, index: int) -> str:
    return f"{prefix}_{index:04d}"


def _days_since(as_of_utc_str: str) -> int | None:
    """Return days since as_of_utc, or None if unparseable."""
    try:
        as_of = datetime.fromisoformat(as_of_utc_str.replace("Z", "+00:00"))
        return (datetime.now(UTC) - as_of).days
    except (ValueError, TypeError):
        return None


def assess_freshness(
    as_of_utc: str,
    *,
    policy: FreshnessPolicy | None = None,
) -> tuple[FreshnessStatus, list[DataQualityFinding], list[str]]:
    """Assess data freshness from snapshot timestamp.

    Returns (freshness_status, findings, blocks).
    """
    findings: list[DataQualityFinding] = []
    blocks: list[str] = []
    idx = 0

    days = _days_since(as_of_utc)
    if days is None:
        idx += 1
        return (
            "unknown",
            [
                DataQualityFinding(
                    finding_id=_finding_id("fresh", idx),
                    severity="warning",
                    code="freshness_unknown",
                    message="Cannot determine data age from as_of_utc.",
                    source_ref=as_of_utc,
                    blocks=["freshness_assessment"],
                )
            ],
            ["freshness_assessment"],
        )

    pol = policy or FreshnessPolicy()

    if days > pol.critical_after_days:
        idx += 1
        findings.append(
            DataQualityFinding(
                finding_id=_finding_id("fresh", idx),
                severity="critical",
                code="critically_stale",
                message=(
                    f"Data is {days} days old, exceeds critical threshold "
                    f"of {pol.critical_after_days} days."
                ),
                source_ref=as_of_utc,
                blocks=["research", "backtest", "risk", "execution"],
            )
        )
        blocks.extend(["research", "backtest", "risk", "execution"])
        return ("critically_stale", findings, blocks)

    if days > pol.stale_after_days:
        idx += 1
        findings.append(
            DataQualityFinding(
                finding_id=_finding_id("fresh", idx),
                severity="warning",
                code="stale",
                message=(
                    f"Data is {days} days old, exceeds warning threshold "
                    f"of {pol.stale_after_days} days."
                ),
                source_ref=as_of_utc,
                blocks=[],
            )
        )
        return ("stale", findings, blocks)

    return ("fresh", findings, blocks)


def assess_quality(
    quality: MarketDataQuality,
) -> tuple[QualityStatus, list[DataQualityFinding]]:
    """Assess data quality from MarketDataQuality metadata.

    Returns (quality_status, findings).
    """
    findings: list[DataQualityFinding] = []
    idx = 0

    if quality.ok and not quality.missing_required_columns and quality.duplicate_timestamps == 0:
        return ("ok", findings)

    idx += 1
    messages: list[str] = []
    if quality.missing_required_columns:
        messages.append(f"missing columns: {quality.missing_required_columns}")
    if quality.duplicate_timestamps > 0:
        messages.append(f"{quality.duplicate_timestamps} duplicate timestamps")
    if not quality.ok:
        messages.append(f"quality check not ok: {quality.notes}")

    findings.append(
        DataQualityFinding(
            finding_id=_finding_id("qual", idx),
            severity="warning",
            code="quality_degraded",
            message="; ".join(messages),
            source_ref=None,
            blocks=[],
        )
    )
    return ("degraded", findings)


def assess_reconciliation(
    reconciliation_status: str,
) -> tuple[str, list[DataQualityFinding]]:
    """Assess reconciliation status.

    Returns (reconciliation_status, findings).
    """
    findings: list[DataQualityFinding] = []
    if reconciliation_status == "single_source_unreconciled":
        findings.append(
            DataQualityFinding(
                finding_id=_finding_id("recon", 1),
                severity="warning",
                code="single_source_unreconciled",
                message="Close prices are unreconciled — single source only.",
                source_ref=None,
                blocks=[],
            )
        )
    return (reconciliation_status, findings)


def assess_bias(
    bias_controls: list[str],
) -> tuple[BiasStatus, list[DataQualityFinding]]:
    """Assess data bias controls.

    Returns (bias_status, findings).
    """
    findings: list[DataQualityFinding] = []
    uncontrolled: list[str] = []

    if "survivorship_uncontrolled" in bias_controls:
        uncontrolled.append("survivorship bias not controlled")
    if "point_in_time_uncontrolled" in bias_controls:
        uncontrolled.append("point-in-time bias not controlled")

    if not uncontrolled:
        return ("controlled", findings)

    idx = 1
    for msg in uncontrolled:
        findings.append(
            DataQualityFinding(
                finding_id=_finding_id("bias", idx),
                severity="warning",
                code="bias_uncontrolled",
                message=msg,
                source_ref=None,
                blocks=[],
            )
        )
        idx += 1
    return ("uncontrolled", findings)


def compute_readiness(
    freshness_status: FreshnessStatus,
    quality_status: QualityStatus,
    bias_status: BiasStatus,
    reconciliation_status: str,
) -> ReadinessStatus:
    """Compute composite readiness from individual statuses."""
    if freshness_status == "critically_stale":
        return "not_ready"
    if quality_status == "degraded":
        return "usable_with_warnings"
    warnings = (
        freshness_status == "stale"
        or bias_status == "uncontrolled"
        or reconciliation_status == "single_source_unreconciled"
    )
    if warnings:
        return "usable_with_warnings"
    return "usable"


def build_quality_report(
    *,
    dataset_key: str,
    as_of_utc: str,
    latest_receipt_ref: str,
    quality: MarketDataQuality,
    reconciliation_status: str,
    bias_controls: list[str],
    freshness_policy: FreshnessPolicy | None = None,
) -> DataQualityReport:
    """Build a structured DataQualityReport from receipt metadata.

    No network calls. All data comes from already-loaded receipt fields.
    """
    freshness_status, fresh_findings, fresh_blocks = assess_freshness(
        as_of_utc, policy=freshness_policy
    )
    quality_status, qual_findings = assess_quality(quality)
    recon_status, recon_findings = assess_reconciliation(reconciliation_status)
    bias_status, bias_findings = assess_bias(bias_controls)
    readiness = compute_readiness(
        freshness_status, quality_status, bias_status, reconciliation_status
    )

    all_findings = [*fresh_findings, *qual_findings, *recon_findings, *bias_findings]
    all_blocks = list(fresh_blocks)

    return DataQualityReport(
        report_id=f"qr_{dataset_key.replace('/', '_')}",
        dataset_key=dataset_key,
        as_of_utc=as_of_utc,
        latest_receipt_ref=latest_receipt_ref,
        freshness_status=freshness_status,
        quality_status=quality_status,
        reconciliation_status=recon_status,
        bias_status=bias_status,
        readiness_status=readiness,
        findings=all_findings,
        blocks=all_blocks,
    )
