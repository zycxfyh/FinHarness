"""Local observability contract for trace ids and receipt indexing.

D7 keeps the default path local-only: no exporter and no network path. The
FinHarness trace id is a bounded correlation handle; receipts remain the
authority. OpenTelemetry spans are an adapter around that handle, not a
replacement for receipts.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Span, SpanKind, Status, StatusCode, Tracer

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
_MAX_ATTRIBUTE_LENGTH = 200
_LOCAL_TRACER_NAME = "finharness.local"

_LOCAL_PROVIDER: TracerProvider | None = None


@dataclass(frozen=True)
class TraceContext:
    """Bounded local trace context.

    ``accepted_supplied`` is diagnostic only; it must not be treated as authority.
    """

    trace_id: str
    accepted_supplied: bool = False


@dataclass(frozen=True)
class LocalTracingConfig:
    """D7b local-only tracing configuration."""

    service_name: str = "finharness"
    provider: Literal["opentelemetry-sdk-local"] = "opentelemetry-sdk-local"
    exporter_configured: bool = False
    network_export_allowed: bool = False


@dataclass(frozen=True)
class TraceReceiptSummary:
    """Bounded read model for a trace-index receipt.

    This intentionally summarizes receipt refs and gaps; it does not expose raw
    domain receipt payloads. Receipts remain the authority, the trace is only a
    correlation index.
    """

    trace_id: str
    run_kind: str
    trace_receipt_ref: str | None
    receipt_refs: tuple[str, ...]
    existing_receipt_refs: tuple[str, ...]
    missing_receipt_refs: tuple[str, ...]
    data_gaps: tuple[str, ...]
    created_at_utc: str | None
    content_hash: str | None
    execution_allowed: bool = False

    def to_json(self) -> dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "run_kind": self.run_kind,
            "trace_receipt_ref": self.trace_receipt_ref,
            "receipt_ref_count": len(self.receipt_refs),
            "receipt_refs": list(self.receipt_refs),
            "existing_receipt_refs": list(self.existing_receipt_refs),
            "missing_receipt_refs": list(self.missing_receipt_refs),
            "data_gaps": list(self.data_gaps),
            "created_at_utc": self.created_at_utc,
            "content_hash": self.content_hash,
            "execution_allowed": self.execution_allowed,
            "non_claims": [
                "Trace id is a correlation handle only.",
                "This summary does not include raw receipt payloads.",
                "Not execution authorization.",
            ],
        }


def new_trace_id() -> str:
    """Create a local FinHarness trace id."""

    return f"{TRACE_ID_PREFIX}{uuid4().hex}"


def configure_local_tracer_provider(service_name: str = "finharness") -> LocalTracingConfig:
    """Initialise a local OpenTelemetry SDK provider with no exporters.

    The provider is intentionally module-local rather than a process-global OTel
    install. That keeps D7b from changing unrelated libraries' tracing behavior.
    """

    global _LOCAL_PROVIDER
    if _LOCAL_PROVIDER is None:
        _LOCAL_PROVIDER = TracerProvider()
    return LocalTracingConfig(service_name=service_name)


def local_tracing_config() -> dict[str, object]:
    """JSON-safe summary of the default local tracing posture."""

    config = configure_local_tracer_provider()
    return {
        "service_name": config.service_name,
        "provider": config.provider,
        "exporter_configured": config.exporter_configured,
        "network_export_allowed": config.network_export_allowed,
        "execution_allowed": False,
    }


def _local_tracer() -> Tracer:
    configure_local_tracer_provider()
    if _LOCAL_PROVIDER is None:
        raise RuntimeError("local tracer provider was not configured")
    return _LOCAL_PROVIDER.get_tracer(_LOCAL_TRACER_NAME)


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


def _safe_attribute_value(value: object) -> bool | int | float | str:
    if isinstance(value, bool | int | float):
        return value
    text = str(value).strip()
    if _SECRET_LIKE_RE.search(text):
        return "sensitive-looking attribute redacted"
    if len(text) > _MAX_ATTRIBUTE_LENGTH:
        return f"{text[:_MAX_ATTRIBUTE_LENGTH]}..."
    return text


def _span_attributes(
    *,
    trace_id: str,
    attributes: Mapping[str, object] | None,
) -> dict[str, bool | int | float | str]:
    context = trace_context_from_value(trace_id)
    safe: dict[str, bool | int | float | str] = {
        "finharness.trace_id": context.trace_id,
        "finharness.execution_allowed": False,
    }
    for key, value in (attributes or {}).items():
        if not key.startswith(("finharness.", "http.", "url.", "task.")):
            continue
        safe[key] = _safe_attribute_value(value)
    return safe


@contextmanager
def start_local_span(
    name: str,
    *,
    trace_id: str,
    attributes: Mapping[str, object] | None = None,
) -> Iterator[Span]:
    """Start a local-only OTel span with a FinHarness trace id attribute."""

    tracer = _local_tracer()
    with tracer.start_as_current_span(
        name,
        kind=SpanKind.INTERNAL,
        attributes=_span_attributes(trace_id=trace_id, attributes=attributes),
    ) as span:
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception:
            span.set_status(Status(StatusCode.ERROR))
            raise


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _path_from_ref(ref: str, *, receipt_root: Path) -> Path | None:
    """Resolve a path-like receipt ref for existence checks only."""

    text = ref.strip()
    if not text or text.startswith(("http://", "https://")):
        return None
    path = Path(text)
    if path.is_absolute():
        return path
    if text.startswith("data/receipts/"):
        return ROOT / text
    if "/" in text or text.endswith(".json"):
        return receipt_root / text
    return None


def _iter_trace_receipts(receipt_root: Path) -> Iterator[Path]:
    if not receipt_root.exists():
        return
    yield from sorted(receipt_root.glob("*.json"))


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _trace_receipt_matches(payload: Mapping[str, Any], trace_id: str) -> bool:
    trace = payload.get("trace")
    return (
        payload.get("kind") == OBSERVABILITY_RECEIPT_KIND
        and isinstance(trace, Mapping)
        and trace.get("trace_id") == trace_id
    )


def summarize_trace_receipt(
    trace_id: str,
    *,
    receipt_root: str | Path = DEFAULT_OBSERVABILITY_RECEIPT_ROOT,
) -> TraceReceiptSummary:
    """Read the latest trace-index receipt for ``trace_id`` as a bounded summary."""

    context = trace_context_from_value(trace_id)
    root = Path(receipt_root)
    data_gaps: list[str] = []
    matches: list[tuple[str, str, Path, dict[str, Any]]] = []
    for receipt_file in _iter_trace_receipts(root):
        payload = _load_json(receipt_file)
        if payload is None:
            data_gaps.append(f"unreadable observability receipt: {receipt_file.name}")
            continue
        if not _trace_receipt_matches(payload, context.trace_id):
            continue
        created = str(payload.get("created_at_utc") or "")
        matches.append((created, receipt_file.name, receipt_file, payload))

    if not matches:
        return TraceReceiptSummary(
            trace_id=context.trace_id,
            run_kind="unknown",
            trace_receipt_ref=None,
            receipt_refs=(),
            existing_receipt_refs=(),
            missing_receipt_refs=(),
            data_gaps=(
                *data_gaps,
                f"no trace index receipt found for {context.trace_id}",
            ),
            created_at_utc=None,
            content_hash=None,
        )

    _created, _name, receipt_path, payload = sorted(
        matches,
        key=lambda item: (item[0], item[1]),
    )[-1]
    trace_value = payload.get("trace")
    trace = trace_value if isinstance(trace_value, Mapping) else {}
    receipt_refs = tuple(
        str(ref)
        for ref in (trace.get("receipt_refs") or [])
        if str(ref).strip()
    )
    existing: list[str] = []
    missing: list[str] = []
    for ref in receipt_refs:
        ref_path = _path_from_ref(ref, receipt_root=root)
        if ref_path is None or ref_path.exists():
            existing.append(ref)
        else:
            missing.append(ref)

    gaps = [
        _bounded_note(str(gap))
        for gap in (trace.get("data_gaps") or [])
        if str(gap).strip()
    ]
    gaps.extend(data_gaps)
    gaps.extend(f"receipt ref missing: {Path(ref).name}" for ref in missing)

    return TraceReceiptSummary(
        trace_id=context.trace_id,
        run_kind=str(trace.get("run_kind") or "unknown"),
        trace_receipt_ref=_display_path(receipt_path),
        receipt_refs=receipt_refs,
        existing_receipt_refs=tuple(existing),
        missing_receipt_refs=tuple(missing),
        data_gaps=tuple(gaps),
        created_at_utc=(
            str(payload.get("created_at_utc"))
            if payload.get("created_at_utc")
            else None
        ),
        content_hash=(
            str(payload.get("content_hash"))
            if payload.get("content_hash")
            else None
        ),
    )


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
