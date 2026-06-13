"""Receipt usage audit for FinHarness.

This audit answers a narrow question: which tracked receipts are referenced by
human-facing reviews, lessons, reports, or other project knowledge artifacts?
It does not decide whether a receipt proves quality or closes work.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_VERSION = "finharness_receipt_usage_audit_v1"
RECEIPT_ROOT = Path("data/receipts")
AUDIT_RECEIPT_PREFIX = "data/receipts/receipt-usage-audit/"

REFERENCE_ROOTS = (
    "README.md",
    "AGENTS.md",
    "CONTEXT.md",
    "docs",
    "ideas",
    "data/research",
    "data/reports",
    "data/security",
    "data/watchlists",
)
TEXT_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml", ".toml"}
RECEIPT_REF_RE = re.compile(r"(?:/[A-Za-z0-9_.-]+)*data/receipts/[A-Za-z0-9_.\/-]+\.json")

CONSUMING_KINDS = {"lesson", "review", "report", "governance_doc"}
DRAFT_KINDS = {"lesson_draft"}


def _repo_path(path: Path, *, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _normalize_receipt_ref(value: str) -> str:
    index = value.find("data/receipts/")
    if index == -1:
        return value
    return value[index:]


def _receipt_created_at(payload: dict[str, Any]) -> str:
    return str(
        payload.get("created_at_utc")
        or payload.get("timestamp_utc")
        or payload.get("as_of_utc")
        or payload.get("generated_at")
        or ""
    )


def _receipt_kind(path: str, payload: dict[str, Any]) -> str:
    return str(payload.get("kind") or payload.get("workflow") or Path(path).parent.name)


def _receipt_status(payload: dict[str, Any]) -> str:
    return str(payload.get("status") or payload.get("decision") or "unknown")


def _consumer_kind(path: str) -> str:
    if path.startswith("docs/lessons/drafts/"):
        return "lesson_draft"
    if path.startswith("docs/lessons/"):
        return "lesson"
    if path.startswith("docs/reviews/"):
        return "review"
    if path.startswith("docs/reports/") or path.startswith("data/reports/"):
        return "report"
    if path.startswith("docs/operations/") or path.startswith("docs/architecture/"):
        return "governance_doc"
    if path.startswith("docs/proposals/"):
        return "proposal_doc"
    if path.startswith("docs/notes/"):
        return "note_doc"
    if path.startswith("docs/think/"):
        return "think_doc"
    if path.startswith("ideas/"):
        return "idea"
    if path.startswith("data/research/"):
        return "research_asset"
    if path.startswith("data/security/"):
        return "security_asset"
    if path.startswith("data/watchlists/"):
        return "watchlist"
    return "project_doc"


def _usage_status(references: list[dict[str, str]]) -> str:
    kinds = {item["consumer_kind"] for item in references}
    if kinds & CONSUMING_KINDS:
        return "consumed"
    if kinds & DRAFT_KINDS:
        return "draft_consumed"
    if references:
        return "referenced"
    return "unreferenced"


def iter_receipts(root: Path = ROOT) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    base = root / RECEIPT_ROOT
    if not base.exists():
        return receipts
    for path in sorted(base.rglob("*.json")):
        rel = _repo_path(path, root=root)
        if rel.startswith(AUDIT_RECEIPT_PREFIX):
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            payload = {}
        receipts.append(
            {
                "path": rel,
                "kind": _receipt_kind(rel, payload),
                "status": _receipt_status(payload),
                "created_at_utc": _receipt_created_at(payload),
            }
        )
    return receipts


def _iter_reference_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for entry in REFERENCE_ROOTS:
        target = root / entry
        if target.is_file():
            paths.append(target)
        elif target.is_dir():
            paths.extend(
                path
                for path in target.rglob("*")
                if path.is_file() and path.suffix in TEXT_SUFFIXES
            )
    return sorted(set(paths))


def collect_references(root: Path = ROOT) -> dict[str, list[dict[str, str]]]:
    references: dict[str, list[dict[str, str]]] = defaultdict(list)
    for path in _iter_reference_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        referrer = _repo_path(path, root=root)
        consumer_kind = _consumer_kind(referrer)
        for match in sorted(set(RECEIPT_REF_RE.findall(text))):
            receipt_ref = _normalize_receipt_ref(match)
            references[receipt_ref].append(
                {"referrer": referrer, "consumer_kind": consumer_kind}
            )
    return dict(sorted(references.items()))


def build_receipt_usage_audit(root: Path | str = ROOT) -> dict[str, Any]:
    resolved_root = Path(root)
    receipts = iter_receipts(resolved_root)
    receipt_paths = {item["path"] for item in receipts}
    references = collect_references(resolved_root)

    audited: list[dict[str, Any]] = []
    by_consumer_kind: Counter[str] = Counter()
    for receipt in receipts:
        refs = references.get(receipt["path"], [])
        by_consumer_kind.update(item["consumer_kind"] for item in refs)
        audited.append(
            {
                **receipt,
                "usage_status": _usage_status(refs),
                "reference_count": len(refs),
                "consumer_kinds": sorted({item["consumer_kind"] for item in refs}),
                "references": refs,
            }
        )

    missing_references = [
        {
            "receipt_ref": receipt_ref,
            "referrers": refs,
        }
        for receipt_ref, refs in references.items()
        if receipt_ref not in receipt_paths
    ]
    missing_consumer_kinds = Counter(
        item["consumer_kind"]
        for missing in missing_references
        for item in missing["referrers"]
    )

    status_counts = Counter(item["usage_status"] for item in audited)
    kind_counts = Counter(item["kind"] for item in audited)

    return {
        "workflow": WORKFLOW_VERSION,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(resolved_root),
        "source": {
            "workflow": WORKFLOW_VERSION,
            "execution_allowed": False,
            "authority_boundary": (
                "This audit observes receipt references in project knowledge "
                "artifacts. It does not validate receipts, close lessons, or "
                "authorize trading, release, or rule changes."
            ),
        },
        "summary": {
            "receipt_count": len(audited),
            "consumed_count": status_counts.get("consumed", 0),
            "draft_consumed_count": status_counts.get("draft_consumed", 0),
            "referenced_count": status_counts.get("referenced", 0),
            "unreferenced_count": status_counts.get("unreferenced", 0),
            "missing_reference_count": len(missing_references),
            "usage_status_counts": dict(sorted(status_counts.items())),
            "receipt_kind_counts": dict(sorted(kind_counts.items())),
            "consumer_kind_counts": dict(sorted(by_consumer_kind.items())),
            "missing_reference_consumer_kind_counts": dict(
                sorted(missing_consumer_kinds.items())
            ),
        },
        "receipts": sorted(audited, key=lambda item: item["path"]),
        "unreferenced_receipts": [
            item["path"] for item in audited if item["usage_status"] == "unreferenced"
        ],
        "draft_consumed_receipts": [
            item["path"] for item in audited if item["usage_status"] == "draft_consumed"
        ],
        "consumed_receipts": [
            item["path"] for item in audited if item["usage_status"] == "consumed"
        ],
        "missing_references": missing_references,
        "limitations": [
            "Directory-level references do not mark every receipt in that directory consumed.",
            (
                "A reference in a review, lesson, report, or governance document "
                "is evidence of use, not proof of correctness."
            ),
            "Lesson drafts are counted separately from promoted lessons.",
        ],
    }


def write_receipt_usage_audit(
    audit: dict[str, Any],
    *,
    root: Path | str = ROOT,
) -> dict[str, str]:
    resolved_root = Path(root)
    path = resolved_root / "data" / "receipts" / "receipt-usage-audit" / "latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {"receipt": str(path)}
