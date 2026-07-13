"""Agent receipt search v0.1 — deterministic local receipt search.

Agentic-space dimension: Trace Space.
Operating surface: Track C — Memory / Search.

v0.1 (PR #211): Adds JSONL receipt search index for faster querying
and makes text-search deterministic via indexed metadata rather than
per-query file scanning.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReceiptKind = Literal[
    "agent_run",
    "evaluation_report",
    "authority_transition",
    "option_set",
    "plan_draft",
    "domain_memory",
    "agent_work_result",
    "review_workspace",
    "agent_tool_result",
    "autonomy_admission",
    "all",
]

NON_CLAIMS: tuple[str, ...] = (
    "Receipt search returns metadata, not business state.",
    "Search results are projections, not execution authorization.",
    "Not investment advice.",
)


class ReceiptSearchIndexEntry(BaseModel):
    """One entry in the receipt search index."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    receipt_kind: str
    file_path: str
    subject_id: str | None = None
    status: str | None = None
    refs: list[str] = Field(default_factory=list)
    text: str = ""
    created_at_utc: str | None = None


class AgentReceiptSearchResult(BaseModel):
    """One receipt search hit."""

    model_config = ConfigDict(frozen=True)

    receipt_id: str
    receipt_kind: str
    file_path: str
    goal_or_subject: str | None = None
    outcome_or_status: str | None = None
    created_at: str | None = None
    matched_on: list[str] = Field(default_factory=list)
    snippet: str | None = None


class ReceiptSearchIndexManifest(BaseModel):
    """Atomic commit point for checkpoint and incremental index generations."""

    model_config = ConfigDict(frozen=True)

    schema_version: Literal["finharness.receipt_search_index.v2"] = (
        "finharness.receipt_search_index.v2"
    )
    generation: int = Field(ge=1)
    checkpoint_generation: int = Field(ge=1)
    checkpoint_ref: str
    indexed_entry_count: int = Field(ge=0)
    complete: bool
    source_high_water: str | None = None
    unreadable_source_count: int = Field(ge=0)
    unreadable_sources: list[str] = Field(default_factory=list)
    updated_at_utc: str


class ReceiptSearchIndexStatus(BaseModel):
    """Freshness/completeness diagnostics returned with every bounded search."""

    model_config = ConfigDict(frozen=True)

    freshness: Literal["current", "missing", "incomplete", "corrupt"]
    generation: int | None = None
    checkpoint_generation: int | None = None
    indexed_entry_count: int = 0
    source_high_water: str | None = None
    unreadable_source_count: int = 0
    unreadable_sources: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)

    @property
    def complete(self) -> bool:
        return self.freshness == "current"


class ReceiptSearchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    results: list[AgentReceiptSearchResult] = Field(default_factory=list)
    index_status: ReceiptSearchIndexStatus


class ReceiptSearchIndexUnavailableError(RuntimeError):
    """Raised by the legacy list API rather than returning a false-complete empty list."""


_KIND_DIR_MAP: dict[str, str] = {
    "agent_run": "agent-runs",
    "evaluation_report": "evaluation-reports",
    "authority_transition": "authority-transitions",
    "option_set": "deliberation",
    "plan_draft": "deliberation",
    "domain_memory": "domain-memory",
    "agent_work_result": "agent-work-results",
    "review_workspace": "review-workspaces",
    "agent_tool_result": "agent-tool-results",
    "autonomy_admission": "autonomy-admissions",
}


# ── index building and atomic generation commits ────────────────────


_INDEX_DIR = ".receipt-index"
_MAX_REPORTED_SOURCE_FAILURES = 20


def _kind_for_payload(directory: str, payload: dict[str, object]) -> str:
    if directory != "deliberation":
        reverse = {value: key for key, value in _KIND_DIR_MAP.items()}
        return reverse.get(directory, directory)
    schema = str(payload.get("schema_version", ""))
    return "plan_draft" if "plan_draft" in schema or payload.get("plan_id") else "option_set"


def _entry_from_path(file_path: Path) -> ReceiptSearchIndexEntry:
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("receipt payload must be a JSON object")
    kind = _kind_for_payload(file_path.parent.name, payload)
    receipt_id = str(payload.get("receipt_id", file_path.stem))
    subject_id = str(
        payload.get("work_id") or payload.get("plan_id") or payload.get("subject_id") or ""
    )
    status = str(payload.get("status") or payload.get("outcome") or "")
    refs: list[str] = []
    for ref_key in (
        "source_refs",
        "evidence_refs",
        "context_refs",
        "receipt_refs",
        "artifact_refs",
    ):
        value = payload.get(ref_key, [])
        if isinstance(value, list):
            refs.extend(str(ref) for ref in value)
    text_parts = [
        value
        for key in ("work_id", "goal", "objective", "stop_reason", "content")
        if isinstance((value := payload.get(key)), str) and value.strip()
    ]
    return ReceiptSearchIndexEntry(
        receipt_id=receipt_id,
        receipt_kind=kind,
        file_path=str(file_path),
        subject_id=subject_id or None,
        status=status or None,
        refs=refs,
        text=" ".join(text_parts),
        created_at_utc=str(payload.get("created_at_utc", "")) or None,
    )


def _scan_receipts(
    receipt_root: Path,
) -> tuple[list[ReceiptSearchIndexEntry], list[str], str | None]:
    entries: list[ReceiptSearchIndexEntry] = []
    failures: list[str] = []
    high_water: str | None = None
    for directory in sorted(set(_KIND_DIR_MAP.values())):
        search_dir = receipt_root / directory
        if not search_dir.is_dir():
            continue
        for file_path in sorted(search_dir.glob("*.json")):
            relative = file_path.relative_to(receipt_root).as_posix()
            try:
                entries.append(_entry_from_path(file_path))
                marker = f"{file_path.stat().st_mtime_ns}:{relative}"
                high_water = max(high_water or marker, marker)
            except (json.JSONDecodeError, OSError, ValueError):
                failures.append(relative)
    return entries, failures, high_water


def build_receipt_search_index(receipt_root: Path) -> list[ReceiptSearchIndexEntry]:
    """Recovery/audit scan. Fail explicitly when any source cannot be represented."""
    entries, failures, _ = _scan_receipts(receipt_root)
    if failures:
        raise ReceiptSearchIndexUnavailableError(
            f"unreadable receipt sources: {', '.join(failures[:_MAX_REPORTED_SOURCE_FAILURES])}"
        )
    return entries


def _atomic_write_jsonl(path: Path, entries: list[ReceiptSearchIndexEntry]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            temp_path = Path(handle.name)
            for entry in entries:
                handle.write(entry.model_dump_json() + "\n")
            handle.flush()
        temp_path.replace(path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def _read_manifest(index_path: Path) -> ReceiptSearchIndexManifest:
    return ReceiptSearchIndexManifest.model_validate_json(index_path.read_text(encoding="utf-8"))


def write_receipt_search_index(receipt_root: Path) -> Path:
    """Atomically rebuild a deterministic checkpoint; intended for recovery/audit."""
    from finharness.statecore.receipt_io import atomic_write_json

    entries, failures, high_water = _scan_receipts(receipt_root)
    index_path = receipt_root / "receipt-index.jsonl"
    try:
        generation = _read_manifest(index_path).generation + 1
    except (OSError, ValueError):
        generation = 1
    checkpoint_ref = f"{_INDEX_DIR}/checkpoint-{generation:020d}.jsonl"
    _atomic_write_jsonl(receipt_root / checkpoint_ref, entries)
    manifest = ReceiptSearchIndexManifest(
        generation=generation,
        checkpoint_generation=generation,
        checkpoint_ref=checkpoint_ref,
        indexed_entry_count=len(entries),
        complete=not failures,
        source_high_water=high_water,
        unreadable_source_count=len(failures),
        unreadable_sources=failures[:_MAX_REPORTED_SOURCE_FAILURES],
        updated_at_utc=datetime.now(UTC).isoformat(),
    )
    atomic_write_json(index_path, manifest.model_dump(mode="json"))
    return index_path


def update_receipt_search_index(receipt_root: Path, receipt_refs: list[str]) -> Path:
    """Commit one bounded incremental segment without scanning historical receipts."""
    from finharness.statecore.receipt_io import atomic_write_json, resolve_under

    index_path = receipt_root / "receipt-index.jsonl"
    if not index_path.exists():
        return write_receipt_search_index(receipt_root)
    try:
        manifest = _read_manifest(index_path)
    except (OSError, ValueError):
        return write_receipt_search_index(receipt_root)
    generation = manifest.generation + 1
    entries: list[ReceiptSearchIndexEntry] = []
    failures: list[str] = []
    high_water = manifest.source_high_water
    for raw_ref in dict.fromkeys(receipt_refs):
        clean_ref = raw_ref.split("#", maxsplit=1)[0]
        try:
            file_path = resolve_under(receipt_root, clean_ref)
            entries.append(_entry_from_path(file_path))
            marker = f"{file_path.stat().st_mtime_ns}:{clean_ref}"
            high_water = max(high_water or marker, marker)
        except (json.JSONDecodeError, OSError, ValueError):
            failures.append(clean_ref)
    segment_ref = f"{_INDEX_DIR}/update-{generation:020d}.json"
    segment_payload = {
        "schema": "finharness.receipt_search_index_update.v1",
        "generation": generation,
        "entries": [entry.model_dump(mode="json") for entry in entries],
    }
    atomic_write_json(receipt_root / segment_ref, segment_payload)
    all_failures = [*manifest.unreadable_sources, *failures]
    updated = manifest.model_copy(
        update={
            "generation": generation,
            "indexed_entry_count": manifest.indexed_entry_count + len(entries),
            "complete": manifest.complete and not failures,
            "source_high_water": high_water,
            "unreadable_source_count": manifest.unreadable_source_count + len(failures),
            "unreadable_sources": all_failures[:_MAX_REPORTED_SOURCE_FAILURES],
            "updated_at_utc": datetime.now(UTC).isoformat(),
        }
    )
    atomic_write_json(index_path, updated.model_dump(mode="json"))
    return index_path


def _match_entry(
    entry: ReceiptSearchIndexEntry,
    query_lower: str,
) -> tuple[list[str], str | None]:
    """Match a query against an index entry. Returns (matched_on, snippet)."""
    matched_on: list[str] = []
    snippet: str | None = None
    if query_lower in entry.receipt_id.lower():
        matched_on.append("receipt_id")
    if entry.status and query_lower in entry.status.lower():
        matched_on.append("status")
    if query_lower in entry.receipt_kind.lower():
        matched_on.append("kind")
    if any(query_lower in r.lower() for r in entry.refs):
        matched_on.append("refs")
    if query_lower in entry.text.lower():
        matched_on.append("text")
        snippet = entry.text[:200]
    return matched_on, snippet


def search_receipt_index(
    index_path: Path,
    query: str,
    *,
    kinds: list[str] | None = None,
    limit: int = 20,
) -> list[AgentReceiptSearchResult]:
    """Backward-compatible list API that fails closed on incomplete index truth."""
    response = search_receipt_index_with_status(index_path, query, kinds=kinds, limit=limit)
    if not response.index_status.complete:
        raise ReceiptSearchIndexUnavailableError(
            "; ".join(response.index_status.findings)
            or f"receipt search index is {response.index_status.freshness}"
        )
    return response.results


def _load_committed_entries(
    index_path: Path,
) -> tuple[dict[str, ReceiptSearchIndexEntry], ReceiptSearchIndexStatus]:
    if not index_path.exists():
        return {}, ReceiptSearchIndexStatus(
            freshness="missing", findings=["receipt search index manifest is missing"]
        )
    try:
        manifest = _read_manifest(index_path)
        root = index_path.parent
        entries: dict[str, ReceiptSearchIndexEntry] = {}
        with (root / manifest.checkpoint_ref).open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                entry = ReceiptSearchIndexEntry.model_validate_json(line)
                entries[entry.file_path] = entry
        for generation in range(manifest.checkpoint_generation + 1, manifest.generation + 1):
            segment_path = root / _INDEX_DIR / f"update-{generation:020d}.json"
            payload = json.loads(segment_path.read_text(encoding="utf-8"))
            if payload.get("generation") != generation:
                raise ValueError(f"segment generation mismatch: {segment_path}")
            for raw_entry in payload.get("entries", []):
                entry = ReceiptSearchIndexEntry.model_validate(raw_entry)
                entries[entry.file_path] = entry
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        return {}, ReceiptSearchIndexStatus(
            freshness="corrupt", findings=[f"receipt search index is corrupt: {exc}"]
        )
    freshness: Literal["current", "incomplete"] = (
        "current" if manifest.complete else "incomplete"
    )
    findings = []
    if not manifest.complete:
        findings.append(
            f"{manifest.unreadable_source_count} receipt source(s) were unreadable"
        )
    return entries, ReceiptSearchIndexStatus(
        freshness=freshness,
        generation=manifest.generation,
        checkpoint_generation=manifest.checkpoint_generation,
        indexed_entry_count=manifest.indexed_entry_count,
        source_high_water=manifest.source_high_water,
        unreadable_source_count=manifest.unreadable_source_count,
        unreadable_sources=manifest.unreadable_sources,
        findings=findings,
    )


def search_receipt_index_with_status(
    index_path: Path,
    query: str,
    *,
    kinds: list[str] | None = None,
    limit: int = 20,
) -> ReceiptSearchResponse:
    """Search committed generations and always return freshness/completeness diagnostics."""
    entries, status = _load_committed_entries(index_path)
    if not query.strip():
        return ReceiptSearchResponse(results=[], index_status=status)
    query_lower = query.lower()
    results: list[AgentReceiptSearchResult] = []
    for entry in sorted(entries.values(), key=lambda item: item.file_path):
        if len(results) >= limit:
            break
        if kinds is not None and entry.receipt_kind not in kinds:
            continue
        matched_on, snippet = _match_entry(entry, query_lower)
        if not matched_on:
            continue
        results.append(
            AgentReceiptSearchResult(
                receipt_id=entry.receipt_id,
                receipt_kind=entry.receipt_kind,
                file_path=entry.file_path,
                goal_or_subject=entry.subject_id,
                outcome_or_status=entry.status,
                created_at=entry.created_at_utc,
                matched_on=matched_on,
                snippet=snippet,
            )
        )
    return ReceiptSearchResponse(results=results, index_status=status)


# ── existing scan-based search (backward compat) ──────────────────────


def search_agent_receipts(
    *,
    receipt_root: str | Path,
    query: str,
    kinds: list[ReceiptKind] | None = None,
    limit: int = 20,
) -> list[AgentReceiptSearchResult]:
    """Search agent receipts under receipt_root by keyword.

    Scans JSON files in receipt subdirectories, matching the query
    against receipt_id, goal, outcome, error codes, and refs.
    Returns up to `limit` results and fails closed if the source set is missing
    or unreadable; callers must not interpret an incomplete scan as no evidence.

    Prefer build_receipt_search_index() + search_receipt_index() for
    repeated queries — this scan-based approach re-reads every file.
    """
    if not query.strip():
        return []

    root = Path(receipt_root)
    if not root.is_dir():
        raise ReceiptSearchIndexUnavailableError(f"receipt root is missing: {root}")

    search_kinds = _resolve_kinds(kinds)
    results: list[AgentReceiptSearchResult] = []
    query_lower = query.lower()

    search_dirs = _search_directories(root, search_kinds)
    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for file_path in sorted(search_dir.glob("*.json")):
            if len(results) >= limit:
                break
            result = _scan_file(file_path, query_lower, search_dir.name)
            if result is not None:
                results.append(result)

    return results[:limit]


def _resolve_kinds(kinds: list[ReceiptKind] | None) -> set[str]:
    if kinds is None or "all" in kinds:
        return set(_KIND_DIR_MAP.values())
    return {_KIND_DIR_MAP[k] for k in kinds if k in _KIND_DIR_MAP}


def _search_directories(root: Path, dir_names: set[str]) -> list[Path]:
    return [root / d for d in sorted(dir_names)]


def _scan_file(  # noqa: C901 — deterministic scan, well-bounded branches
    file_path: Path,
    query_lower: str,
    dir_name: str,
) -> AgentReceiptSearchResult | None:
    """Scan one receipt JSON file for a query match."""
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise ReceiptSearchIndexUnavailableError(
            f"receipt source is unreadable: {file_path}: {exc}"
        ) from exc

    matched_on: list[str] = []
    snippet: str | None = None

    receipt_id = str(payload.get("receipt_id", ""))
    if query_lower in receipt_id.lower():
        matched_on.append("receipt_id")

    goal = payload.get("goal") or payload.get("objective") or ""
    goal_str = str(goal)
    if query_lower in goal_str.lower():
        matched_on.append("goal")
        if not snippet and goal_str:
            snippet = goal_str[:200]

    stop = str(payload.get("stop_reason", ""))
    if query_lower in stop.lower():
        matched_on.append("stop_reason")

    for ref_key in ("source_refs", "evidence_refs", "context_refs", "artifact_refs"):
        refs = payload.get(ref_key, [])
        if isinstance(refs, list) and any(
            query_lower in str(r).lower() for r in refs
        ):
            matched_on.append(ref_key)

    tool_calls = payload.get("tool_calls", [])
    if isinstance(tool_calls, list):
        for tc in tool_calls:
            if (
                isinstance(tc, dict)
                and tc.get("error_code")
                and query_lower in str(tc["error_code"]).lower()
            ):
                matched_on.append("error_code")
                break

    for key in ("status", "outcome"):
        val = str(payload.get(key, ""))
        if query_lower in val.lower():
            matched_on.append(key if key == "status" else "outcome")

    if not matched_on:
        return None

    created_at = str(payload.get("created_at_utc", "")) or None
    outcome_or_status = (
        payload.get("outcome")
        or payload.get("status")
    )

    kind = _kind_from_dir(dir_name)

    return AgentReceiptSearchResult(
        receipt_id=receipt_id,
        receipt_kind=kind,
        file_path=str(file_path),
        goal_or_subject=goal_str if goal_str else None,
        outcome_or_status=str(outcome_or_status) if outcome_or_status else None,
        created_at=created_at,
        matched_on=matched_on,
        snippet=snippet,
    )


def _kind_from_dir(dir_name: str) -> str:
    reverse: dict[str, str] = {v: k for k, v in _KIND_DIR_MAP.items()}
    return reverse.get(dir_name, dir_name)
