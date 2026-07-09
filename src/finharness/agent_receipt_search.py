"""Agent receipt search v0 — deterministic local receipt search.

Agentic-space dimension: Trace Space.
Operating surface: Track C — Memory / Search.

Lets an agent (or operator) search past AgentRunReceipt and related
receipt files by keyword, code, status, or ref. Deterministic JSON
scan — no database, no FTS, no LLM summarization.
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
    "all",
]

NON_CLAIMS: tuple[str, ...] = (
    "Receipt search returns metadata, not business state.",
    "Search results are projections, not execution authorization.",
    "Not investment advice.",
)


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


_KIND_DIR_MAP: dict[str, str] = {
    "agent_run": "agent-runs",
    "evaluation_report": "evaluation-reports",
    "authority_transition": "authority-transitions",
    "option_set": "deliberation",
    "plan_draft": "deliberation",
}


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

    # Search receipt_id
    receipt_id = str(payload.get("receipt_id", ""))
    if query_lower in receipt_id.lower():
        matched_on.append("receipt_id")

    # Search goal / subject
    goal = payload.get("goal") or payload.get("objective") or ""
    goal_str = str(goal)
    if query_lower in goal_str.lower():
        matched_on.append("goal")
        if not snippet and goal_str:
            snippet = goal_str[:200]

    # Search stop_reason
    stop = str(payload.get("stop_reason", ""))
    if query_lower in stop.lower():
        matched_on.append("stop_reason")

    # Search refs
    for ref_key in ("source_refs", "evidence_refs", "context_refs", "artifact_refs"):
        refs = payload.get(ref_key, [])
        if isinstance(refs, list) and any(
            query_lower in str(r).lower() for r in refs
        ):
            matched_on.append(ref_key)

    # Search error codes
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

    # Search evaluation status / outcome
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

    # Derive receipt kind from directory
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
