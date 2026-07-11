#!/usr/bin/env python3
"""Verify attestation consumer inventory for structure, coverage, and consistency."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INV = ROOT / "docs" / "governance" / "attestation-consumers.json"

ALLOWED_ROLES = {
    "schema_model", "write_surface", "receipt_writer", "read_projection",
    "state_gate", "api_contract", "documentation_claim", "test_contract",
    "frontend_surface", "compatibility_link",
}
ALLOWED_SEMANTICS = {
    "historical_evidence", "legacy_unbound_decision", "review_completion_proxy",
    "canonical_decision_claim", "compatibility_reference", "not_decision_related",
    "unknown",
}
ALLOWED_VERSION = {
    "none", "proposal_id_only", "proposal_receipt_ref_only",
    "proposal_version_bound", "not_applicable", "unknown",
}
ALLOWED_DISP = {
    "preserve", "migrate_to_decision_record", "migrate_to_decision_validity",
    "dual_read_transition", "deprecate_after_replacement",
    "remove_canonical_claim", "investigate",
}
ALLOWED_RISK = {"low", "medium", "high", "critical"}
REQ_FIELDS = {
    "consumer_id", "path", "symbol", "line_start", "role", "current_behavior",
    "decision_semantics", "version_binding", "authority_effect", "risk",
    "disposition", "target_owner", "prerequisites", "recommended_change",
    "test_implications", "evidence",
}
REQ_TEXT = {"current_behavior", "recommended_change"}
SCAN_TERMS = [
    "Attestation", "attestation_id", "attestation_ref", "attestations",
    "create_governed_attestation", "attest_proposal", "attested_ids",
    "human_attestation_recorded", "decision of record",
]
SKIP_PARTS = {
    ".git", ".venv", "node_modules", "dist", "build", "coverage",
    "__pycache__", ".mypy_cache", ".ruff_cache",
}
SKIP_PATHS = {
    "docs/governance/attestation-consumers.json",
    "docs/audits/attestation-consumer-inventory.md",
    "scripts/verify_attestation_consumer_inventory.py",
    "tests/test_attestation_consumer_inventory.py",
}
SCAN_ROOTS = ["src", "tests", "docs", "frontend"]


def _should_scan(path: Path) -> bool:
    if any(p in SKIP_PARTS for p in path.parts):
        return False
    rel = str(path.relative_to(ROOT))
    return rel not in SKIP_PATHS


def _scan_hits() -> set[str]:
    hits: set[str] = set()
    for root_name in SCAN_ROOTS:
        root_dir = ROOT / root_name
        if not root_dir.is_dir():
            continue
        for path in sorted(root_dir.rglob("*")):
            if not path.is_file() or not _should_scan(path):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except (OSError, UnicodeDecodeError):
                continue
            if any(term in text for term in SCAN_TERMS):
                hits.add(str(path.relative_to(ROOT)))
    return hits


def _check_one(consumer: dict) -> list[str]:
    f: list[str] = []
    cid = consumer.get("consumer_id", "?")
    p = f"{cid}:"
    missing = REQ_FIELDS - set(consumer)
    if missing:
        f.append(f"{p} missing fields: {sorted(missing)}")
    if consumer.get("role") not in ALLOWED_ROLES:
        f.append(f"{p} unknown role: {consumer.get('role')}")
    if consumer.get("decision_semantics") not in ALLOWED_SEMANTICS:
        f.append(f"{p} unknown semantics: {consumer.get('decision_semantics')}")
    if consumer.get("version_binding") not in ALLOWED_VERSION:
        f.append(f"{p} unknown version_binding: {consumer.get('version_binding')}")
    if consumer.get("disposition") not in ALLOWED_DISP:
        f.append(f"{p} unknown disposition: {consumer.get('disposition')}")
    if consumer.get("risk") not in ALLOWED_RISK:
        f.append(f"{p} unknown risk: {consumer.get('risk')}")
    path_str = consumer.get("path", "")
    if path_str and not (ROOT / path_str).is_file():
        f.append(f"{p} path does not exist: {path_str}")
    ls = consumer.get("line_start", 0)
    if not isinstance(ls, int) or ls <= 0:
        f.append(f"{p} invalid line_start: {ls}")
    for field in REQ_TEXT:
        if not str(consumer.get(field, "")).strip():
            f.append(f"{p} {field} is empty")
    return f


def validate_inventory(inv_path: Path = INV) -> list[str]:
    failures: list[str] = []
    if not inv_path.is_file():
        return [f"inventory not found: {inv_path}"]
    try:
        data = json.loads(inv_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid JSON: {exc}"]
    failures.extend(_check_top(data))
    consumers = data.get("consumers")
    if not isinstance(consumers, list):
        return [*failures, "consumers must be a list"]
    failures.extend(_check_consumers(consumers))
    failures.extend(_check_summary(consumers, data.get("summary", {})))
    failures.extend(_check_coverage(consumers, data.get("exclusions", [])))
    return failures


def _check_top(data: dict) -> list[str]:
    f: list[str] = []
    if data.get("schema") != "finharness.attestation_consumer_inventory.v1":
        f.append(f"unknown schema: {data.get('schema')}")
    unclass = data.get("unclassified_hits", [])
    if unclass:
        f.append(f"{len(unclass)} unclassified_hits must be empty")
    return f


def _check_consumers(consumers: list[dict]) -> list[str]:
    f: list[str] = []
    seen: set[str] = set()
    for c in consumers:
        cid = c.get("consumer_id", "")
        if cid in seen:
            f.append(f"duplicate consumer_id: {cid}")
        seen.add(cid)
        f.extend(_check_one(c))
    return f


def _check_summary(consumers: list[dict], summary: dict) -> list[str]:
    actual = len(consumers)
    claimed = summary.get("total_consumers")
    if claimed != actual:
        return [f"summary.total_consumers={claimed} != {actual}"]
    return []


def _check_coverage(consumers: list[dict], exclusions: list[dict]) -> list[str]:
    f: list[str] = []
    consumer_paths = {c["path"] for c in consumers if c.get("path")}
    hits = _scan_hits()
    excl_paths = {e["path"] for e in exclusions}
    registered = consumer_paths | excl_paths | SKIP_PATHS
    for hit in sorted(hits):
        if hit not in registered:
            f.append(f"unregistered hit: {hit}")
    for exc in exclusions:
        if not str(exc.get("reason", "")).strip():
            f.append(f"exclusion has empty reason: {exc.get('path', '?')}")
    return f


def main() -> int:
    failures = validate_inventory()
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  {f}")
        return 1
    data = json.loads(INV.read_text(encoding="utf-8"))
    s = data["summary"]
    disp = s.get("by_disposition", {})
    print(f"OK: {len(data['consumers'])} consumers")
    for d in sorted(disp):
        print(f"  {d}: {disp[d]}")
    print(f"  high/critical: {s.get('high_or_critical_count', '?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
