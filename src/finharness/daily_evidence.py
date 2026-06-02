"""Daily evidence bundle governance for virtual training workflows."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from finharness.market_data import ROOT, display_path, sha256_text, write_json

DAILY_EVIDENCE_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "daily-evidence"
DAILY_EVIDENCE_RECEIPT_ROOT = ROOT / "data" / "receipts" / "daily-evidence"
DAILY_EVIDENCE_REVIEW_ROOT = ROOT / "docs" / "reviews"


class DailyEvidenceQuality(BaseModel):
    """Quality summary for the cross-layer daily evidence graph."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    layer_quality: dict[str, bool]
    failed_layers: list[str] = Field(default_factory=list)
    execution_allowed: bool = False
    notes: list[str] = Field(default_factory=list)


class DailyEvidenceLineage(BaseModel):
    """Lineage over the first four evidence layers."""

    model_config = ConfigDict(frozen=True)

    market_snapshot_refs: list[str]
    indicator_snapshot_refs: list[str]
    event_snapshot_ref: str | None = None
    interpretation_snapshot_ref: str | None = None
    computed_at_utc: str
    transform_version: str = "finharness.daily_evidence.v1"
    output_hash: str
    output_ref: str


class DailyEvidenceSnapshot(BaseModel):
    """Snapshot consumed by daily virtual training and review."""

    model_config = ConfigDict(frozen=True)

    daily_evidence_snapshot_id: str
    as_of_utc: str
    universe: list[str]
    market_symbols: list[str]
    layer_summaries: dict[str, Any]
    quality: DailyEvidenceQuality
    lineage: DailyEvidenceLineage
    payload_ref: str
    receipt_ref: str
    execution_allowed: bool = False
    review_questions: list[str] = Field(default_factory=list)


class DailyEvidenceReceipt(BaseModel):
    """Durable evidence root for the first-four-layer daily graph."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    created_at_utc: str
    kind: str = "daily_evidence_bundle"
    stage_flow: dict[str, str]
    snapshot: DailyEvidenceSnapshot
    status: Literal["ok", "warning", "failed"] = "ok"


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def build_daily_evidence_quality(
    layer_quality: dict[str, bool],
    *,
    notes: list[str] | None = None,
) -> DailyEvidenceQuality:
    failed_layers = [layer for layer, ok in layer_quality.items() if not ok]
    return DailyEvidenceQuality(
        ok=not failed_layers,
        layer_quality=layer_quality,
        failed_layers=failed_layers,
        execution_allowed=False,
        notes=notes or [],
    )


def daily_review_questions(quality: DailyEvidenceQuality) -> list[str]:
    if not quality.ok:
        return [
            "Which layer failed its quality gate?",
            "Is the failure caused by missing data, stale data, parsing, or model logic?",
            "Should this run be excluded from hypothesis generation?",
        ]
    if any("no candidate" in note or "interpretation skipped" in note for note in quality.notes):
        return [
            "No matching event records were available; is the absence useful context?",
            "Do market data and indicator evidence show anything worth monitoring anyway?",
            "Should the event source scope, forms, or per-symbol limit be adjusted?",
            "Should this run produce hypotheses, or remain a market-only review?",
        ]
    return [
        "Do market data and indicator evidence agree with event interpretation?",
        "Which interpretation should be promoted into a falsifiable hypothesis?",
        "Which evidence item has the weakest lineage or quality support?",
        "Did any output drift toward execution language?",
    ]


def persist_daily_evidence_receipt(
    *,
    universe: list[str],
    market_symbols: list[str],
    layer_summaries: dict[str, Any],
    layer_quality: dict[str, bool],
    market_snapshot_refs: list[str],
    indicator_snapshot_refs: list[str],
    event_snapshot_ref: str | None = None,
    interpretation_snapshot_ref: str | None = None,
    status: Literal["ok", "warning", "failed"] | None = None,
    notes: list[str] | None = None,
) -> DailyEvidenceReceipt:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid4().hex[:8]
    snapshot_id = f"devs_{stamp}_{suffix}"
    receipt_id = f"receipt_{snapshot_id}"
    output_ref = DAILY_EVIDENCE_NORMALIZED_ROOT / f"{snapshot_id}.json"
    receipt_ref = DAILY_EVIDENCE_RECEIPT_ROOT / f"{receipt_id}.json"
    quality = build_daily_evidence_quality(layer_quality, notes=notes)
    output_payload = {
        "daily_evidence_snapshot_id": snapshot_id,
        "universe": universe,
        "market_symbols": market_symbols,
        "layer_summaries": layer_summaries,
        "market_snapshot_refs": market_snapshot_refs,
        "indicator_snapshot_refs": indicator_snapshot_refs,
        "event_snapshot_ref": event_snapshot_ref,
        "interpretation_snapshot_ref": interpretation_snapshot_ref,
    }
    output_hash = sha256_text(
        json.dumps(output_payload, ensure_ascii=False, sort_keys=True, default=str)
    )
    lineage = DailyEvidenceLineage(
        market_snapshot_refs=market_snapshot_refs,
        indicator_snapshot_refs=indicator_snapshot_refs,
        event_snapshot_ref=event_snapshot_ref,
        interpretation_snapshot_ref=interpretation_snapshot_ref,
        computed_at_utc=now_utc(),
        output_hash=output_hash,
        output_ref=display_path(output_ref),
    )
    snapshot = DailyEvidenceSnapshot(
        daily_evidence_snapshot_id=snapshot_id,
        as_of_utc=now_utc(),
        universe=universe,
        market_symbols=market_symbols,
        layer_summaries=layer_summaries,
        quality=quality,
        lineage=lineage,
        payload_ref=display_path(output_ref),
        receipt_ref=display_path(receipt_ref),
        execution_allowed=False,
        review_questions=daily_review_questions(quality),
    )
    resolved_status = status or ("ok" if quality.ok else "failed")
    receipt = DailyEvidenceReceipt(
        receipt_id=receipt_id,
        created_at_utc=now_utc(),
        stage_flow={
            "source_input": "configured universe, market symbols, and date range",
            "market_data": "Layer 1 MarketDataSnapshot evidence",
            "indicators": "Layer 2 IndicatorSnapshot evidence",
            "events": "Layer 3 EventSnapshot evidence linked to market/indicator refs",
            "interpretation": "Layer 4 InterpretationSnapshot evidence linked to refs",
            "quality": "conditional quality gates after each layer",
            "lineage": "cross-layer snapshot refs",
            "snapshot": "DailyEvidenceSnapshot",
            "receipt": "DailyEvidenceReceipt",
            "review_hook": "daily virtual training review questions",
        },
        snapshot=snapshot,
        status=resolved_status,
    )
    write_json(output_ref, output_payload)
    write_json(receipt_ref, receipt.model_dump(mode="json"))
    return receipt


def write_daily_evidence_review(receipt: DailyEvidenceReceipt) -> str:
    """Write a human review draft for a daily evidence run."""
    snapshot = receipt.snapshot
    date = datetime.now(UTC).strftime("%Y-%m-%d")
    path = (
        DAILY_EVIDENCE_REVIEW_ROOT
        / f"{date}-daily-evidence-{snapshot.daily_evidence_snapshot_id}.md"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        f"# Daily Evidence Review: {snapshot.daily_evidence_snapshot_id}",
        "",
        f"Date: {date}",
        f"Status: {receipt.status}",
        f"Execution allowed: {str(snapshot.execution_allowed).lower()}",
        "",
        "## Quality",
        "",
        f"- OK: {str(snapshot.quality.ok).lower()}",
        f"- Failed layers: {', '.join(snapshot.quality.failed_layers) or 'none'}",
        f"- Notes: {'; '.join(snapshot.quality.notes) or 'none'}",
        "",
        "## Evidence Refs",
        "",
        f"- Daily evidence payload: {snapshot.payload_ref}",
        f"- Daily evidence receipt: {snapshot.receipt_ref}",
        f"- Market snapshots: {', '.join(snapshot.lineage.market_snapshot_refs) or 'none'}",
        f"- Indicator snapshots: {', '.join(snapshot.lineage.indicator_snapshot_refs) or 'none'}",
        f"- Event snapshot: {snapshot.lineage.event_snapshot_ref or 'none'}",
        f"- Interpretation snapshot: {snapshot.lineage.interpretation_snapshot_ref or 'none'}",
        "",
        "## Review Questions",
        "",
        *[f"- {question}" for question in snapshot.review_questions],
        "",
        "## Human Notes",
        "",
        "- ",
        "",
        "## Decision",
        "",
        "```text",
        "review_only",
        "```",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return display_path(path)
