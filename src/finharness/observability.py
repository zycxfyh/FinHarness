"""Local observability contract for trace ids and receipt indexing.

D7a deliberately stays dependency-free: no OpenTelemetry SDK, no exporter, and no
network path. The trace id is only a bounded correlation handle. Receipts remain
the authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from finharness.market_data import ROOT
from finharness.statecore.receipt_io import atomic_write_json, resolve_under

TRACE_HEADER = "X-FinHarness-Trace-Id"
TRACE_ID_PREFIX = "trace_"
OBSERVABILITY_RECEIPT_KIND = "observability_trace_index"
DEFAULT_OBSERVABILITY_RECEIPT_ROOT = ROOT / "data" / "receipts" / "observability"

_TRACE_ID_RE = re.compile(r"^trace_[A-Za-z0-9_-]{1,64}$")
_RUN_KIND_RE = re.compile(r"^[a-z][a-z0-9:_-]{0,80}$")
_SECRET_LIKE_RE = re.compile(
    r"(?i)(api[_-]?key|bearer|password|secret|token|sk-[a-z0-9_-]{8,})"
)
_MAX_NOTE_LENGTH = 160


@dataclass(frozen=True)
class TraceContext:
    """Bounded local trace context.

    ``accepted_supplied`` is diagnostic only; it must not be treated as authority.
    """

    trace_id: str
    accepted_supplied: bool = False


def new_trace_id() -> str:
    """Create a local FinHarness trace id."""

    return f"{TRACE_ID_PREFIX}{uuid4().hex}"


def is_safe_trace_id(value: str) -> bool:
    """Return whether ``value`` is safe to echo into headers/logs/receipts."""

    return bool(_TRACE_ID_RE.fullmatch(value))


def trace_context_from_value(value: str | None) -> TraceContext:
    """Accept a caller trace id only if it is bounded and non-secret-looking.

    Malformed, multi-line, path-like, or secret-looking values fail soft by being
    replaced with a fresh local trace id. The raw supplied value is never returned.
    """

    supplied = (value or "").strip()
    if supplied and is_safe_trace_id(supplied) and not _SECRET_LIKE_RE.search(supplied):
        return TraceContext(trace_id=supplied, accepted_supplied=True)
    return TraceContext(trace_id=new_trace_id(), accepted_supplied=False)


def trace_context_from_headers(headers: Mapping[str, str]) -> TraceContext:
    """Build trace context from HTTP-ish headers."""

    return trace_context_from_value(headers.get(TRACE_HEADER) or headers.get(TRACE_HEADER.lower()))


def trace_metadata(trace_id: str) -> dict[str, object]:
    """Small JSON-safe metadata block for bounded logs/receipts."""

    context = trace_context_from_value(trace_id)
    return {
        "trace_id": context.trace_id,
        "schema": "finharness.trace.v1",
        "execution_allowed": False,
        "non_claims": [
            "Trace id is a correlation handle only.",
            "Receipt content_hash and source_refs remain authoritative.",
            "Not execution authorization.",
        ],
    }


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            out.append(value)
    return tuple(out)


def _bounded_note(value: str) -> str:
    note = value.strip()
    if _SECRET_LIKE_RE.search(note):
        return "sensitive-looking observability detail redacted"
    if len(note) > _MAX_NOTE_LENGTH:
        return f"{note[:_MAX_NOTE_LENGTH]}..."
    return note


def _safe_run_kind(value: str) -> str:
    run_kind = value.strip()
    if not _RUN_KIND_RE.fullmatch(run_kind):
        raise ValueError(f"invalid observability run kind: {value!r}")
    return run_kind


def build_trace_index_receipt(
    *,
    trace_id: str,
    run_kind: str,
    receipt_refs: Iterable[str],
    data_gaps: Iterable[str] = (),
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    """Build an observability receipt that indexes trace id to receipt refs.

    This is intentionally a separate receipt: it does not mutate domain receipts or
    alter their content hashes.
    """

    context = trace_context_from_value(trace_id)
    refs = _unique(str(ref) for ref in receipt_refs if str(ref).strip())
    gaps = tuple(_bounded_note(str(gap)) for gap in data_gaps if str(gap).strip())
    created = created_at_utc or datetime.now(UTC).isoformat()
    trace = {
        "trace_id": context.trace_id,
        "run_kind": _safe_run_kind(run_kind),
        "receipt_refs": list(refs),
        "data_gaps": list(gaps),
        "schema": "finharness.trace.v1",
    }
    content_hash = hashlib.sha256(
        json.dumps(trace, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    trace_suffix = context.trace_id.removeprefix(TRACE_ID_PREFIX)
    receipt_id = f"receipt_trace_{trace_suffix}_{content_hash[:8]}"
    return {
        "receipt_id": receipt_id,
        "kind": OBSERVABILITY_RECEIPT_KIND,
        "created_at_utc": created,
        "content_hash": content_hash,
        "trace": trace,
        "source_refs": list(refs),
        "governance": {
            "execution_allowed": False,
            "non_claims": [
                "Trace indexes receipts; it does not replace them.",
                "Receipt content_hash and source_refs remain authoritative.",
                "No telemetry exporter is configured by this receipt.",
            ],
        },
    }


def write_trace_index_receipt(
    *,
    trace_id: str,
    run_kind: str,
    receipt_refs: Iterable[str],
    data_gaps: Iterable[str] = (),
    receipt_root: str | Path = DEFAULT_OBSERVABILITY_RECEIPT_ROOT,
) -> str:
    """Write an observability trace-index receipt and return its display ref."""

    payload = build_trace_index_receipt(
        trace_id=trace_id,
        run_kind=run_kind,
        receipt_refs=receipt_refs,
        data_gaps=data_gaps,
    )
    filename = f"{payload['receipt_id']}.json"
    receipt_path = resolve_under(receipt_root, filename)
    atomic_write_json(receipt_path, payload)
    return _display_path(receipt_path)
