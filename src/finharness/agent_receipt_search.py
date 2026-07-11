"""Agent receipt search v0.1 — deterministic local receipt search.

Agentic-space dimension: Trace Space.
Operating surface: Track C — Memory / Search.

v0.1 (PR #211): Adds JSONL receipt search index for faster querying
and makes text-search deterministic via indexed metadata rather than
per-query file scanning.
"""

from __future__ import annotations

import json
from pathlib import Path
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


# ── index building ───────────────────────────────────────────────────


def build_receipt_search_index(receipt_root: Path) -> list[ReceiptSearchIndexEntry]:
    """Build a search index from all receipt files under receipt_root.

    Scans known receipt directories and extracts metadata into
    ReceiptSearchIndexEntry objects. Stale or unreadable files are
    skipped (not reported as errors).
    """
    entries: list[ReceiptSearchIndexEntry] = []
    for kind, dir_name in sorted(_KIND_DIR_MAP.items()):
        search_dir = receipt_root / dir_name
        if not search_dir.is_dir():
            continue
        for file_path in sorted(search_dir.glob("*.json")):
            try:
                payload = json.loads(file_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            receipt_id = str(payload.get("receipt_id", file_path.stem))
            subject_id = str(
                payload.get("work_id")
                or payload.get("plan_id")
                or payload.get("subject_id")
                or ""
            )
            status = str(payload.get("status") or payload.get("outcome") or "")

            # Collect refs
            refs: list[str] = []
            _ref_keys = ("source_refs", "evidence_refs", "context_refs",
                         "receipt_refs", "artifact_refs")
            for ref_key in _ref_keys:
                val = payload.get(ref_key, [])
                if isinstance(val, list):
                    refs.extend(str(r) for r in val)

            # Collect text for search
            text_parts: list[str] = []
            for key in ("work_id", "goal", "objective", "stop_reason", "content"):
                val = payload.get(key)
                if isinstance(val, str) and val.strip():
                    text_parts.append(val)

            entries.append(ReceiptSearchIndexEntry(
                receipt_id=receipt_id,
                receipt_kind=kind,
                file_path=str(file_path),
                subject_id=subject_id or None,
                status=status or None,
                refs=refs,
                text=" ".join(text_parts),
                created_at_utc=str(payload.get("created_at_utc", "")) or None,
            ))

    return entries


def write_receipt_search_index(receipt_root: Path) -> Path:
    """Build the index and write it as JSONL next to the receipt root.

    Returns the path to the written index file.
    """
    entries = build_receipt_search_index(receipt_root)
    index_path = receipt_root / "receipt-index.jsonl"
    with index_path.open("w", encoding="utf-8") as f:
        for entry in entries:
            f.write(entry.model_dump_json() + "\n")
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
    """Search the receipt index by keyword.

    Matches query against receipt_id, receipt_kind, status, refs, and
    text fields. When no index file exists, falls back to an empty result.
    """
    if not index_path.exists():
        return []
    if not query.strip():
        return []

    query_lower = query.lower()
    results: list[AgentReceiptSearchResult] = []

    with index_path.open("r", encoding="utf-8") as f:
        for line in f:
            if len(results) >= limit:
                break
            line = line.strip()
            if not line:
                continue
            try:
                entry = ReceiptSearchIndexEntry.model_validate_json(line)
            except ValueError:
                continue

            if kinds is not None and entry.receipt_kind not in kinds:
                continue

            matched_on, snippet = _match_entry(entry, query_lower)
            if not matched_on:
                continue

            results.append(AgentReceiptSearchResult(
                receipt_id=entry.receipt_id,
                receipt_kind=entry.receipt_kind,
                file_path=entry.file_path,
                goal_or_subject=entry.subject_id,
                outcome_or_status=entry.status,
                created_at=entry.created_at_utc,
                matched_on=matched_on,
                snippet=snippet,
            ))

    return results[:limit]


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
    Returns up to `limit` results.

    Prefer build_receipt_search_index() + search_receipt_index() for
    repeated queries — this scan-based approach re-reads every file.
    """
    if not query.strip():
        return []

    root = Path(receipt_root)
    if not root.is_dir():
        return []

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
    except (json.JSONDecodeError, OSError):
        return None

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
