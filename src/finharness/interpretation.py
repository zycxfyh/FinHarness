"""Fourth-layer source-backed interpretation governance.

Interpretation turns EventSnapshot evidence into meaning candidates, impact
paths, scenarios, counterevidence, and watch questions. It does not authorize
execution and does not create trading recommendations.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from finharness.events import EventRecord, EventSnapshot
from finharness.market_data import ROOT, display_path, sha256_text

INTERPRETATION_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "interpretations"
INTERPRETATION_RECEIPT_ROOT = ROOT / "data" / "receipts" / "interpretations"

Horizon = Literal["intraday", "days", "weeks", "quarters", "long_term", "unknown"]
Confidence = Literal["low", "medium", "high", "unknown"]
Stance = Literal["positive", "negative", "mixed", "neutral", "unknown"]
Materiality = Literal["low", "medium", "high", "unknown"]

NO_EXECUTION_PATTERNS = [
    r"\bbuy\b",
    r"\bsell\b",
    r"\bhold\b",
    r"\bshort\b",
    r"\bincrease position\b",
    r"\breduce position\b",
    r"\bposition sizing\b",
    r"\bexecute\b",
    r"\bplace order\b",
    r"\btarget price\b",
    r"\bstop loss\b",
    r"\btake profit\b",
    "买入",
    "卖出",
    "做多",
    "做空",
    "加仓",
    "减仓",
    "开仓",
    "平仓",
    "止损",
    "止盈",
    "目标价",
    "仓位",
    "下单",
    "执行",
]

SECTOR_BY_SYMBOL = {
    "AAPL": "consumer hardware / services",
    "MSFT": "software / cloud / AI infrastructure",
    "GOOGL": "digital ads / cloud / AI",
    "AMZN": "e-commerce / cloud / logistics",
    "NVDA": "semiconductors / AI data center",
    "META": "digital ads / social platforms / AI capex",
    "TSLA": "electric vehicles / energy / autonomy",
}

BASKET_BY_SYMBOL = {
    "AAPL": ["mega-cap tech", "consumer hardware", "QQQ"],
    "MSFT": ["mega-cap tech", "cloud", "AI infrastructure", "QQQ"],
    "GOOGL": ["mega-cap tech", "digital advertising", "AI", "QQQ"],
    "AMZN": ["mega-cap tech", "cloud", "consumer discretionary", "QQQ"],
    "NVDA": ["semiconductors", "AI capex", "data center", "QQQ"],
    "META": ["mega-cap tech", "digital advertising", "AI capex", "QQQ"],
    "TSLA": ["electric vehicles", "high beta growth", "consumer discretionary", "QQQ"],
}


class InterpretationSourceSpec(BaseModel):
    """Source/input layer for interpretation."""

    model_config = ConfigDict(frozen=True)

    provider: str = "FinHarness rule-guided interpretation"
    method: str = "rule_guided_template"
    input_layer: str = "events"
    template_version: str = "finharness.interpretation.template.v1"
    model_provider: str | None = None
    prompt_version: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class InterpretationRecord(BaseModel):
    """A source-backed interpretation claim with scenarios and counterevidence."""

    model_config = ConfigDict(frozen=True)

    interpretation_id: str
    event_ids: list[str]
    symbol: str
    source_facts: list[str]
    claim: str
    evidence_refs: list[str]
    inference: str
    impact_paths: list[str]
    affected_exposures: list[str]
    horizon: Horizon
    sentiment_label: Stance
    confidence: Confidence
    materiality: Materiality
    expectation_status: Literal[
        "unknown",
        "previously_known",
        "potentially_new",
        "needs_human_review",
    ]
    counterevidence: list[str]
    watch_questions: list[str]
    scenario_base: str
    scenario_bull: str
    scenario_bear: str
    created_at_utc: str


class InterpretationQuality(BaseModel):
    """Quality gates for the interpretation layer."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    record_count: int
    source_backed_claims: bool
    counterevidence_present: bool
    no_execution_language: bool
    horizon_present: bool
    confidence_bounded: bool
    claim_evidence_separation: bool
    missing_required_fields: dict[str, list[str]] = Field(default_factory=dict)
    execution_language_hits: dict[str, list[str]] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class InterpretationLineage(BaseModel):
    """Lineage from EventSnapshot into interpretation output."""

    model_config = ConfigDict(frozen=True)

    source: InterpretationSourceSpec
    input_event_snapshot_id: str
    input_event_receipt_ref: str
    event_record_ids: list[str]
    market_snapshot_refs: list[str] = Field(default_factory=list)
    indicator_snapshot_refs: list[str] = Field(default_factory=list)
    computed_at_utc: str
    transform_version: str = "finharness.interpretation.v1"
    output_hash: str
    output_ref: str


class InterpretationSnapshot(BaseModel):
    """Snapshot layer: stable interpretation evidence for downstream workflows."""

    model_config = ConfigDict(frozen=True)

    interpretation_snapshot_id: str
    as_of_utc: str
    input_event_snapshot_id: str
    universe: list[str]
    record_count: int
    records: list[InterpretationRecord]
    quality: InterpretationQuality
    lineage: InterpretationLineage
    payload_ref: str
    receipt_ref: str
    execution_allowed: bool = False
    hypothesis_candidates: list[str] = Field(default_factory=list)
    review_questions: list[str] = Field(default_factory=list)


class InterpretationReceipt(BaseModel):
    """Durable evidence root for fourth-layer interpretation processing."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    created_at_utc: str
    kind: str = "interpretation_processing"
    stage_flow: dict[str, str]
    snapshot: InterpretationSnapshot
    status: Literal["ok", "warning", "failed"] = "ok"


class InterpretationBundle(BaseModel):
    """Compact handoff for scripts and LangGraph nodes."""

    model_config = ConfigDict(frozen=True)

    source: InterpretationSourceSpec
    input_event_snapshot: EventSnapshot
    records: list[InterpretationRecord]
    quality: InterpretationQuality
    lineage: InterpretationLineage
    snapshot: InterpretationSnapshot
    receipt: InterpretationReceipt


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def event_symbol(record: EventRecord) -> str:
    if record.instruments:
        return normalize_symbol(record.instruments[0])
    if record.entities:
        return normalize_symbol(record.entities[0].ticker)
    return "UNKNOWN"


def impact_paths_for_event(record: EventRecord) -> list[str]:
    if record.event_type == "8-K":
        return ["management", "guidance", "capital_allocation", "regulation"]
    if record.event_type == "10-Q":
        return ["revenue", "margin", "cash_flow", "balance_sheet", "risk_factors"]
    if record.event_type == "10-K":
        return [
            "revenue",
            "margin",
            "cash_flow",
            "balance_sheet",
            "risk_factors",
            "competition",
            "valuation",
        ]
    return ["unknown"]


def horizon_for_event(record: EventRecord) -> Horizon:
    if record.event_type == "8-K":
        return "days"
    if record.event_type == "10-Q":
        return "quarters"
    if record.event_type == "10-K":
        return "long_term"
    return "unknown"


def materiality_for_event(record: EventRecord) -> Materiality:
    if record.event_type == "8-K":
        return "medium"
    if record.event_type in {"10-Q", "10-K"}:
        return "medium"
    return "unknown"


def affected_exposures(symbol: str) -> list[str]:
    sector = SECTOR_BY_SYMBOL.get(symbol, "unknown sector")
    baskets = BASKET_BY_SYMBOL.get(symbol, ["single-name"])
    return [
        f"single_name:{symbol}",
        f"sector:{sector}",
        *[f"basket:{basket}" for basket in baskets],
        "index_context:SPY",
        "index_context:QQQ",
    ]


def source_facts(record: EventRecord) -> list[str]:
    return [
        f"{event_symbol(record)} filed {record.event_type}.",
        f"Published at {record.published_at}.",
        f"SEC accession number {record.raw_id}.",
    ]


def watch_questions_for_record(record: EventRecord, paths: list[str]) -> list[str]:
    symbol = event_symbol(record)
    return [
        f"Which specific filing sections changed the {', '.join(paths[:3])} interpretation?",
        f"Did {symbol} price/volume reaction confirm or fade after the filing?",
        "Did SPY and QQQ confirm or contradict the single-name reaction?",
        "What later filing, transcript, or market data would falsify this interpretation?",
    ]


def counterevidence_for_record(record: EventRecord) -> list[str]:
    return [
        "The filing may not introduce new information relative to prior disclosures.",
        "Market expectations may already reflect the disclosed information.",
        "The event may not be material relative to company scale or current market regime.",
    ]


def interpret_event_record(record: EventRecord) -> InterpretationRecord:
    symbol = event_symbol(record)
    paths = impact_paths_for_event(record)
    horizon = horizon_for_event(record)
    exposure = affected_exposures(symbol)
    path_text = ", ".join(paths[:3])
    claim = f"{symbol} {record.event_type} may be relevant to {path_text} over a {horizon} horizon."
    inference = (
        f"The interpretation is based on the filing type and source-backed event metadata. "
        f"If the filing changes investor understanding of {path_text}, it may affect "
        f"future review questions for {symbol} and related index context."
    )
    return InterpretationRecord(
        interpretation_id=f"interp_{uuid4().hex[:12]}",
        event_ids=[record.event_id],
        symbol=symbol,
        source_facts=source_facts(record),
        claim=claim,
        evidence_refs=[record.event_id, record.raw_ref, record.parsed_ref or record.source_url],
        inference=inference,
        impact_paths=paths,
        affected_exposures=exposure,
        horizon=horizon,
        sentiment_label="unknown",
        confidence="low",
        materiality=materiality_for_event(record),
        expectation_status="needs_human_review",
        counterevidence=counterevidence_for_record(record),
        watch_questions=watch_questions_for_record(record, paths),
        scenario_base=(
            f"The {record.event_type} filing is relevant enough to monitor, but materiality "
            "requires human review and later evidence."
        ),
        scenario_bull=(
            "The interpretation becomes more constructive if later filings, management "
            "commentary, and market reaction confirm the affected drivers without offsetting "
            "risk."
        ),
        scenario_bear=(
            "The interpretation becomes more concerning if later evidence shows weaker "
            "drivers, higher costs, regulatory pressure, or fading market confirmation."
        ),
        created_at_utc=now_utc(),
    )


def extract_candidate_events(
    event_snapshot: EventSnapshot,
    *,
    event_types: list[str] | None = None,
    max_records: int = 30,
) -> list[EventRecord]:
    allowed = set(event_types or ["8-K", "10-Q", "10-K"])
    candidates = [
        record
        for record in event_snapshot.records
        if record.event_type in allowed and record.event_id and record.raw_ref
    ]
    return candidates[:max_records]


def find_execution_language(value: str) -> list[str]:
    lower = value.lower()
    hits: list[str] = []
    for pattern in NO_EXECUTION_PATTERNS:
        if re.search(pattern, lower):
            hits.append(pattern)
    return hits


def record_text_for_guard(record: InterpretationRecord) -> str:
    return "\n".join(
        [
            record.claim,
            record.inference,
            record.scenario_base,
            record.scenario_bull,
            record.scenario_bear,
            *record.watch_questions,
            *record.counterevidence,
        ]
    )


def build_interpretation_quality(records: list[InterpretationRecord]) -> InterpretationQuality:
    missing_required_fields: dict[str, list[str]] = {}
    execution_language_hits: dict[str, list[str]] = {}
    for record in records:
        missing: list[str] = []
        if not record.event_ids:
            missing.append("event_ids")
        if not record.evidence_refs:
            missing.append("evidence_refs")
        if not record.source_facts:
            missing.append("source_facts")
        if not record.claim:
            missing.append("claim")
        if not record.inference:
            missing.append("inference")
        if not record.counterevidence:
            missing.append("counterevidence")
        if not record.watch_questions:
            missing.append("watch_questions")
        if record.horizon == "unknown":
            missing.append("horizon")
        if record.confidence not in {"low", "medium", "high", "unknown"}:
            missing.append("confidence")
        if missing:
            missing_required_fields[record.interpretation_id] = missing
        hits = find_execution_language(record_text_for_guard(record))
        if hits:
            execution_language_hits[record.interpretation_id] = hits

    source_backed = all(record.event_ids and record.evidence_refs for record in records)
    counterevidence_present = all(bool(record.counterevidence) for record in records)
    no_execution_language = not execution_language_hits
    horizon_present = all(record.horizon != "unknown" for record in records)
    confidence_bounded = all(
        record.confidence in {"low", "medium", "high", "unknown"} for record in records
    )
    claim_evidence_separation = all(
        bool(record.source_facts and record.claim and record.inference) for record in records
    )
    notes: list[str] = []
    if not records:
        notes.append("no candidate events were interpreted")
    ok = (
        bool(records)
        and source_backed
        and counterevidence_present
        and no_execution_language
        and horizon_present
        and confidence_bounded
        and claim_evidence_separation
        and not missing_required_fields
    )
    return InterpretationQuality(
        ok=ok,
        record_count=len(records),
        source_backed_claims=source_backed,
        counterevidence_present=counterevidence_present,
        no_execution_language=no_execution_language,
        horizon_present=horizon_present,
        confidence_bounded=confidence_bounded,
        claim_evidence_separation=claim_evidence_separation,
        missing_required_fields=missing_required_fields,
        execution_language_hits=execution_language_hits,
        notes=notes,
    )


def hypothesis_candidates(records: list[InterpretationRecord]) -> list[str]:
    return [
        (
            f"If {record.symbol} {record.event_ids[0]} matters through "
            f"{', '.join(record.impact_paths[:2])}, then later filings, market reaction, "
            "and related index context should provide confirming or disconfirming evidence."
        )
        for record in records[:10]
    ]


def snapshot_review_questions(records: list[InterpretationRecord]) -> list[str]:
    questions = [
        "Which interpretation has the weakest source support?",
        "Which claim is most sensitive to missing expectation/consensus context?",
        "Which counterevidence should be checked first?",
        "Did any interpretation language drift toward trade advice?",
    ]
    if records:
        questions.append("Which interpretation should become a formal hypothesis candidate?")
    return questions


def persist_interpretation_bundle(
    *,
    source: InterpretationSourceSpec,
    input_event_snapshot: EventSnapshot,
    records: list[InterpretationRecord],
    market_snapshot_refs: list[str] | None = None,
    indicator_snapshot_refs: list[str] | None = None,
) -> InterpretationBundle:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid4().hex[:8]
    snapshot_id = f"ints_{stamp}_{suffix}"
    receipt_id = f"receipt_{snapshot_id}"
    output_ref = INTERPRETATION_NORMALIZED_ROOT / f"{snapshot_id}.json"
    receipt_ref = INTERPRETATION_RECEIPT_ROOT / f"{receipt_id}.json"
    quality = build_interpretation_quality(records)
    output_payload = {
        "interpretation_snapshot_id": snapshot_id,
        "input_event_snapshot_id": input_event_snapshot.snapshot_id,
        "universe": input_event_snapshot.universe,
        "records": [record.model_dump(mode="json") for record in records],
    }
    output_hash = sha256_text(
        json.dumps(output_payload, ensure_ascii=False, sort_keys=True, default=str)
    )
    lineage = InterpretationLineage(
        source=source,
        input_event_snapshot_id=input_event_snapshot.snapshot_id,
        input_event_receipt_ref=input_event_snapshot.receipt_ref,
        event_record_ids=[event_id for record in records for event_id in record.event_ids],
        market_snapshot_refs=market_snapshot_refs or [],
        indicator_snapshot_refs=indicator_snapshot_refs or [],
        computed_at_utc=now_utc(),
        output_hash=output_hash,
        output_ref=display_path(output_ref),
    )
    snapshot = InterpretationSnapshot(
        interpretation_snapshot_id=snapshot_id,
        as_of_utc=now_utc(),
        input_event_snapshot_id=input_event_snapshot.snapshot_id,
        universe=input_event_snapshot.universe,
        record_count=len(records),
        records=records,
        quality=quality,
        lineage=lineage,
        payload_ref=display_path(output_ref),
        receipt_ref=display_path(receipt_ref),
        execution_allowed=False,
        hypothesis_candidates=hypothesis_candidates(records),
        review_questions=snapshot_review_questions(records),
    )
    receipt = InterpretationReceipt(
        receipt_id=receipt_id,
        created_at_utc=now_utc(),
        stage_flow={
            "source_input": "InterpretationSourceSpec + EventSnapshot",
            "fetch_compute": "rule-guided interpretation over candidate events",
            "normalize": "InterpretationRecord with claim/evidence/inference separation",
            "quality": "source-backed, counterevidence, no-execution-language gates",
            "lineage": "EventSnapshot refs, event ids, output hash/ref",
            "snapshot": "InterpretationSnapshot",
            "receipt": "InterpretationReceipt",
            "consumer_handoff": "hypothesis/review/risk-note inputs only",
            "review_hook": "human review before hypothesis promotion",
        },
        snapshot=snapshot,
        status="ok" if quality.ok else "warning",
    )
    write_json(output_ref, output_payload)
    write_json(receipt_ref, receipt.model_dump(mode="json"))
    return InterpretationBundle(
        source=source,
        input_event_snapshot=input_event_snapshot,
        records=records,
        quality=quality,
        lineage=lineage,
        snapshot=snapshot,
        receipt=receipt,
    )


def build_interpretation_bundle_from_event_snapshot(
    event_snapshot: EventSnapshot | dict[str, Any],
    *,
    event_types: list[str] | None = None,
    max_records: int = 30,
    market_snapshot_refs: list[str] | None = None,
    indicator_snapshot_refs: list[str] | None = None,
) -> InterpretationBundle:
    snapshot = (
        event_snapshot
        if isinstance(event_snapshot, EventSnapshot)
        else EventSnapshot.model_validate(event_snapshot)
    )
    source = InterpretationSourceSpec(
        config={
            "event_types": event_types or ["8-K", "10-Q", "10-K"],
            "max_records": max_records,
            "universe": snapshot.universe,
        }
    )
    candidates = extract_candidate_events(
        snapshot,
        event_types=event_types or ["8-K", "10-Q", "10-K"],
        max_records=max_records,
    )
    records = [interpret_event_record(record) for record in candidates]
    return persist_interpretation_bundle(
        source=source,
        input_event_snapshot=snapshot,
        records=records,
        market_snapshot_refs=market_snapshot_refs,
        indicator_snapshot_refs=indicator_snapshot_refs,
    )
