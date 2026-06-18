"""Third-layer event governance for official market-moving information.

The event source owns the original filing data. FinHarness owns the evidence
boundary: normalization, quality, lineage, snapshots, receipts, and execution
permission boundaries.
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from finharness.market_data import ROOT, display_path

EVENT_RAW_ROOT = ROOT / "data" / "raw" / "events" / "sec-edgar"
EVENT_NORMALIZED_ROOT = ROOT / "data" / "normalized" / "events" / "sec-edgar"
EVENT_RECEIPT_ROOT = ROOT / "data" / "receipts" / "events"

EDGAR_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"
EDGAR_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"

FILING_SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]
CONTEXT_SYMBOLS = ["SPY", "QQQ"]
DEFAULT_UNIVERSE = [*FILING_SYMBOLS, *CONTEXT_SYMBOLS]
DEFAULT_FORMS = ["8-K", "10-Q", "10-K"]

CIK_BY_SYMBOL = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "NVDA": "0001045810",
    "META": "0001326801",
    "TSLA": "0001318605",
}

COMPANY_NAME_BY_SYMBOL = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Corporation",
    "GOOGL": "Alphabet Inc.",
    "AMZN": "Amazon.com, Inc.",
    "NVDA": "NVIDIA Corporation",
    "META": "Meta Platforms, Inc.",
    "TSLA": "Tesla, Inc.",
}


class EventSourceSpec(BaseModel):
    """Source/input layer: which official source owns the upstream event call."""

    model_config = ConfigDict(frozen=True)

    provider: str = "SEC EDGAR"
    endpoint: str = EDGAR_SUBMISSIONS_BASE
    access_method: Literal["api_pull", "websocket", "batch", "manual"] = "api_pull"
    license: str = "SEC public data"
    fetch_config: dict[str, Any] = Field(default_factory=dict)


class EventEntity(BaseModel):
    """Entity/instrument mapping for an event record."""

    model_config = ConfigDict(frozen=True)

    entity_id: str
    entity_type: Literal["company", "etf", "index_context"]
    name: str
    ticker: str
    cik: str | None = None
    mapping_confidence: float


class EventRecord(BaseModel):
    """Normalized event record consumed by review and hypothesis workflows."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    event_type: str
    source: str
    provider: str
    raw_id: str
    title: str
    summary: str
    published_at: str
    received_at: str
    entities: list[EventEntity]
    instruments: list[str]
    source_url: str
    raw_ref: str
    parsed_ref: str | None = None


class EventQuality(BaseModel):
    """Quality layer: explicit checks and flags for event records."""

    model_config = ConfigDict(frozen=True)

    ok: bool
    record_count: int
    missing_fields: dict[str, list[str]] = Field(default_factory=dict)
    parse_errors: list[str] = Field(default_factory=list)
    duplicate_count: int = 0
    stale_count: int = 0
    mapping_confidence_min: float | None = None
    license_boundary: str = "official_public_sec_data"
    execution_allowed: bool = False
    notes: list[str] = Field(default_factory=list)


class EventLineage(BaseModel):
    """Lineage layer: evidence for event fetches and transformations."""

    model_config = ConfigDict(frozen=True)

    source: EventSourceSpec
    fetched_at_utc: str
    fetch_config: dict[str, Any]
    raw_hash: str
    parsed_hash: str
    transform_version: str = "finharness.events.sec_edgar.v1"
    raw_refs: list[str]
    parsed_ref: str
    linked_market_snapshot_refs: list[str] = Field(default_factory=list)
    linked_indicator_snapshot_refs: list[str] = Field(default_factory=list)


class EventSnapshot(BaseModel):
    """Snapshot layer: stable event evidence consumed by review workflows."""

    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    as_of_utc: str
    universe: list[str]
    filing_symbols: list[str]
    context_symbols: list[str]
    event_count: int
    records: list[EventRecord]
    quality: EventQuality
    lineage: EventLineage
    payload_ref: str
    receipt_ref: str
    execution_allowed: bool = False
    review_questions: list[str] = Field(default_factory=list)


class EventReceipt(BaseModel):
    """Durable evidence root for third-layer event processing."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    created_at_utc: str
    kind: str = "event_ingestion"
    stage_flow: dict[str, str]
    snapshot: EventSnapshot
    status: Literal["ok", "warning", "failed"] = "ok"


class EventBundle(BaseModel):
    """Compact workflow handoff for scripts and LangGraph nodes."""

    model_config = ConfigDict(frozen=True)

    source: EventSourceSpec
    raw_payloads: dict[str, dict[str, Any]]
    records: list[EventRecord]
    quality: EventQuality
    lineage: EventLineage
    snapshot: EventSnapshot
    receipt: EventReceipt


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def sec_user_agent() -> str:
    return os.environ.get(
        "FINHARNESS_SEC_USER_AGENT",
        "FinHarness research workflow contact@example.com",
    )


def normalize_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def filing_symbols_from_universe(universe: list[str] | None = None) -> list[str]:
    symbols = [normalize_symbol(symbol) for symbol in (universe or DEFAULT_UNIVERSE)]
    return [symbol for symbol in symbols if symbol in CIK_BY_SYMBOL]


def context_symbols_from_universe(universe: list[str] | None = None) -> list[str]:
    symbols = [normalize_symbol(symbol) for symbol in (universe or DEFAULT_UNIVERSE)]
    return [symbol for symbol in symbols if symbol not in CIK_BY_SYMBOL]


def cik_without_leading_zeroes(cik: str) -> str:
    return str(int(cik))


def accession_without_dashes(accession: str) -> str:
    return accession.replace("-", "")


def sec_submission_url(cik: str) -> str:
    return f"{EDGAR_SUBMISSIONS_BASE}/CIK{cik}.json"


def sec_filing_url(cik: str, accession: str, primary_document: str) -> str:
    return (
        f"{EDGAR_ARCHIVES_BASE}/{cik_without_leading_zeroes(cik)}/"
        f"{accession_without_dashes(accession)}/{primary_document}"
    )


def fetch_sec_submission(
    cik: str,
    *,
    timeout: float = 20.0,
    retries: int = 3,
    retry_delay_seconds: float = 1.0,
) -> dict[str, Any]:
    request = urllib.request.Request(  # noqa: S310 -- SEC EDGAR HTTPS endpoint.
        sec_submission_url(cik),
        headers={
            "Accept": "application/json",
            "User-Agent": sec_user_agent(),
        },
    )
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 -- request object targets SEC EDGAR HTTPS API.
                return json.loads(response.read().decode("utf-8"))
        except (
            TimeoutError,
            http.client.IncompleteRead,
            http.client.RemoteDisconnected,
            urllib.error.HTTPError,
            urllib.error.URLError,
        ) as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(retry_delay_seconds)
    raise RuntimeError(f"failed to fetch SEC submissions for CIK {cik}") from last_error


def fetch_sec_edgar_raw_payloads(
    *,
    universe: list[str] | None = None,
    timeout: float = 20.0,
) -> dict[str, dict[str, Any]]:
    payloads: dict[str, dict[str, Any]] = {}
    for symbol in filing_symbols_from_universe(universe):
        payloads[symbol] = fetch_sec_submission(CIK_BY_SYMBOL[symbol], timeout=timeout)
    return payloads


def extract_recent_filings(
    payload: dict[str, Any],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    recent = payload.get("filings", {}).get("recent", {})
    if not isinstance(recent, dict):
        return []
    forms = recent.get("form", [])
    rows: list[dict[str, Any]] = []
    for index, form in enumerate(forms[:limit]):
        rows.append(
            {
                "accessionNumber": _recent_value(recent, "accessionNumber", index),
                "filingDate": _recent_value(recent, "filingDate", index),
                "reportDate": _recent_value(recent, "reportDate", index),
                "acceptanceDateTime": _recent_value(recent, "acceptanceDateTime", index),
                "act": _recent_value(recent, "act", index),
                "form": form,
                "fileNumber": _recent_value(recent, "fileNumber", index),
                "filmNumber": _recent_value(recent, "filmNumber", index),
                "items": _recent_value(recent, "items", index),
                "primaryDocument": _recent_value(recent, "primaryDocument", index),
                "primaryDocDescription": _recent_value(recent, "primaryDocDescription", index),
            }
        )
    return rows


def _recent_value(recent: dict[str, Any], field: str, index: int) -> Any:
    values = recent.get(field, [])
    if not isinstance(values, list) or index >= len(values):
        return None
    return values[index]


def normalize_sec_edgar_records(
    raw_payloads: dict[str, dict[str, Any]],
    *,
    forms: list[str] | None = None,
    per_symbol_limit: int = 40,
    raw_refs: dict[str, str] | None = None,
) -> list[EventRecord]:
    allowed_forms = set(forms or DEFAULT_FORMS)
    records: list[EventRecord] = []
    received_at = now_utc()
    for symbol, payload in raw_payloads.items():
        normalized_symbol = normalize_symbol(symbol)
        cik = CIK_BY_SYMBOL[normalized_symbol]
        entity = EventEntity(
            entity_id=f"cik:{cik}",
            entity_type="company",
            name=COMPANY_NAME_BY_SYMBOL[normalized_symbol],
            ticker=normalized_symbol,
            cik=cik,
            mapping_confidence=1.0,
        )
        raw_ref = raw_refs.get(normalized_symbol, "") if raw_refs else ""
        for filing in extract_recent_filings(payload, limit=per_symbol_limit):
            form = str(filing.get("form") or "")
            accession = str(filing.get("accessionNumber") or "")
            primary_document = str(filing.get("primaryDocument") or "")
            if form not in allowed_forms:
                continue
            source_url = (
                sec_filing_url(cik, accession, primary_document)
                if accession and primary_document
                else sec_submission_url(cik)
            )
            title = f"{normalized_symbol} {form}"
            if filing.get("primaryDocDescription"):
                title = f"{title}: {filing['primaryDocDescription']}"
            published_at = str(filing.get("acceptanceDateTime") or filing.get("filingDate") or "")
            event_id = (
                f"sec-edgar:{normalized_symbol}:"
                f"{accession or form}:{filing.get('filingDate')}"
            )
            records.append(
                EventRecord(
                    event_id=event_id,
                    event_type=form,
                    source="SEC EDGAR submissions API",
                    provider="SEC EDGAR",
                    raw_id=accession,
                    title=title,
                    summary=(
                        f"{normalized_symbol} filed {form}"
                        f" on {filing.get('filingDate') or 'unknown date'}."
                    ),
                    published_at=published_at,
                    received_at=received_at,
                    entities=[entity],
                    instruments=[normalized_symbol],
                    source_url=source_url,
                    raw_ref=raw_ref,
                )
            )
    return records


def build_event_quality(
    records: list[EventRecord],
    *,
    parse_errors: list[str] | None = None,
) -> EventQuality:
    required = ["event_id", "event_type", "provider", "raw_id", "published_at", "source_url"]
    missing_fields: dict[str, list[str]] = {}
    for record in records:
        missing = [field for field in required if not getattr(record, field)]
        if not record.entities:
            missing.append("entities")
        if not record.instruments:
            missing.append("instruments")
        if missing:
            missing_fields[record.event_id] = missing

    event_ids = [record.event_id for record in records]
    duplicate_count = len(event_ids) - len(set(event_ids))
    confidence_values = [
        entity.mapping_confidence for record in records for entity in record.entities
    ]
    mapping_confidence_min = min(confidence_values) if confidence_values else None
    notes: list[str] = []
    if not records:
        notes.append("no matching SEC filings found for configured forms")
    ok = not missing_fields and duplicate_count == 0 and not parse_errors
    return EventQuality(
        ok=ok,
        record_count=len(records),
        missing_fields=missing_fields,
        parse_errors=parse_errors or [],
        duplicate_count=duplicate_count,
        stale_count=0,
        mapping_confidence_min=mapping_confidence_min,
        execution_allowed=False,
        notes=notes,
    )


def review_questions(records: list[EventRecord], context_symbols: list[str]) -> list[str]:
    questions = [
        "Which filings appeared since the last review?",
        "Do any 8-K filings describe a concrete catalyst or risk?",
        "How did the related symbol trade around the filing date?",
    ]
    if context_symbols:
        questions.append(
            f"Did market context assets ({', '.join(context_symbols)}) confirm or fade the move?"
        )
    if not records:
        questions.append("No matching filings appeared; is the absence itself useful context?")
    return questions


def persist_event_bundle(
    *,
    source: EventSourceSpec,
    raw_payloads: dict[str, dict[str, Any]],
    records: list[EventRecord],
    universe: list[str],
    filing_symbols: list[str],
    context_symbols: list[str],
    linked_market_snapshot_refs: list[str] | None = None,
    linked_indicator_snapshot_refs: list[str] | None = None,
) -> EventBundle:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = uuid4().hex[:8]
    snapshot_id = f"evs_{stamp}_{suffix}"
    receipt_id = f"receipt_{snapshot_id}"

    raw_refs: dict[str, str] = {}
    for symbol, payload in raw_payloads.items():
        path = EVENT_RAW_ROOT / f"{snapshot_id}-{symbol}.json"
        write_json(path, payload)
        raw_refs[symbol] = display_path(path)

    records_with_refs = [
        record.model_copy(
            update={
                "raw_ref": raw_refs.get(record.instruments[0], record.raw_ref),
                "parsed_ref": display_path(EVENT_NORMALIZED_ROOT / f"{snapshot_id}.json"),
            }
        )
        for record in records
    ]
    quality = build_event_quality(records_with_refs)

    parsed_payload = {
        "snapshot_id": snapshot_id,
        "universe": universe,
        "filing_symbols": filing_symbols,
        "context_symbols": context_symbols,
        "records": [record.model_dump(mode="json") for record in records_with_refs],
    }
    parsed_ref = EVENT_NORMALIZED_ROOT / f"{snapshot_id}.json"
    write_json(parsed_ref, parsed_payload)

    raw_hash = sha256_text(
        json.dumps(raw_payloads, ensure_ascii=False, sort_keys=True, default=str)
    )
    parsed_hash = sha256_text(
        json.dumps(parsed_payload, ensure_ascii=False, sort_keys=True, default=str)
    )
    lineage = EventLineage(
        source=source,
        fetched_at_utc=now_utc(),
        fetch_config=source.fetch_config,
        raw_hash=raw_hash,
        parsed_hash=parsed_hash,
        raw_refs=list(raw_refs.values()),
        parsed_ref=display_path(parsed_ref),
        linked_market_snapshot_refs=linked_market_snapshot_refs or [],
        linked_indicator_snapshot_refs=linked_indicator_snapshot_refs or [],
    )
    receipt_ref = EVENT_RECEIPT_ROOT / f"{receipt_id}.json"
    snapshot = EventSnapshot(
        snapshot_id=snapshot_id,
        as_of_utc=now_utc(),
        universe=universe,
        filing_symbols=filing_symbols,
        context_symbols=context_symbols,
        event_count=len(records_with_refs),
        records=records_with_refs,
        quality=quality,
        lineage=lineage,
        payload_ref=display_path(parsed_ref),
        receipt_ref=display_path(receipt_ref),
        execution_allowed=False,
        review_questions=review_questions(records_with_refs, context_symbols),
    )
    receipt = EventReceipt(
        receipt_id=receipt_id,
        created_at_utc=now_utc(),
        stage_flow={
            "source_input": "EventSourceSpec + static Magnificent Seven CIK mapping",
            "fetch_compute": "SEC EDGAR submissions API raw payload fetch",
            "normalize": "recent filings to EventRecord",
            "quality": "missing fields, duplicate ids, mapping confidence, execution boundary",
            "lineage": "raw/parsed hashes and refs",
            "snapshot": "EventSnapshot",
            "receipt": "EventReceipt",
            "consumer_handoff": "review questions for human virtual training",
            "review_hook": "daily event review before hypotheses or proposals",
        },
        snapshot=snapshot,
        status="ok" if quality.ok else "warning",
    )
    write_json(receipt_ref, receipt.model_dump(mode="json"))
    return EventBundle(
        source=source,
        raw_payloads=raw_payloads,
        records=records_with_refs,
        quality=quality,
        lineage=lineage,
        snapshot=snapshot,
        receipt=receipt,
    )


def build_sec_edgar_event_bundle_from_raw(
    raw_payloads: dict[str, dict[str, Any]],
    *,
    universe: list[str] | None = None,
    forms: list[str] | None = None,
    per_symbol_limit: int = 40,
) -> EventBundle:
    resolved_universe = [normalize_symbol(symbol) for symbol in (universe or DEFAULT_UNIVERSE)]
    filing_symbols = filing_symbols_from_universe(resolved_universe)
    context_symbols = context_symbols_from_universe(resolved_universe)
    source = EventSourceSpec(
        fetch_config={
            "universe": resolved_universe,
            "filing_symbols": filing_symbols,
            "context_symbols": context_symbols,
            "forms": forms or DEFAULT_FORMS,
            "per_symbol_limit": per_symbol_limit,
        }
    )
    records = normalize_sec_edgar_records(
        raw_payloads,
        forms=forms or DEFAULT_FORMS,
        per_symbol_limit=per_symbol_limit,
    )
    return persist_event_bundle(
        source=source,
        raw_payloads=raw_payloads,
        records=records,
        universe=resolved_universe,
        filing_symbols=filing_symbols,
        context_symbols=context_symbols,
    )


def run_events_workflow(
    *,
    universe: list[str] | None = None,
    forms: list[str] | None = None,
    per_symbol_limit: int = 40,
    timeout: float = 20.0,
) -> EventBundle:
    resolved_universe = [normalize_symbol(symbol) for symbol in (universe or DEFAULT_UNIVERSE)]
    raw_payloads = fetch_sec_edgar_raw_payloads(universe=resolved_universe, timeout=timeout)
    return build_sec_edgar_event_bundle_from_raw(
        raw_payloads,
        universe=resolved_universe,
        forms=forms or DEFAULT_FORMS,
        per_symbol_limit=per_symbol_limit,
    )
