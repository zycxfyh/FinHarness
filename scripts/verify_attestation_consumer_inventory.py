#!/usr/bin/env python3
"""Verify attestation consumer inventory for structure, hit-level coverage, and consistency."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
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
    "consumer_id", "path", "symbol", "line_start", "line_end", "match_terms",
    "role", "current_behavior", "decision_semantics", "version_binding",
    "authority_effect", "risk", "disposition", "target_owner",
    "prerequisites", "recommended_change", "test_implications", "evidence",
}
REQ_TEXT = {"current_behavior", "recommended_change"}

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
SCAN_GLOBS = [
    "src/finharness/**/*.py",
    "tests/**/*.py",
    "docs/**/*.md", "docs/**/*.json", "docs/**/*.yml", "docs/**/*.yaml",
    "frontend/**/*.js", "frontend/**/*.ts", "frontend/**/*.tsx",
    "frontend/**/*.html",
]

MAX_RANGE_LINES = 250
CID_RE = re.compile(r"^ATT-CONS-(\d{3})$")


@dataclass(frozen=True)
class ScanHit:
    path: str
    line: int
    term: str


@dataclass
class ConsumerRange:
    path: str
    line_start: int
    line_end: int
    match_terms: list[str]
    consumer_id: str = ""


@dataclass
class ExclusionEntry:
    path: str
    match_line: int
    term: str = ""
    reason: str = ""


# ── scanning ──────────────────────────────────────────────────────────────────


def _should_scan(path: Path, root: Path) -> bool:
    if any(p in SKIP_PARTS for p in path.parts):
        return False
    return str(path.relative_to(root)) not in SKIP_PATHS


def _scan_hits(scan_terms: list[str], root: Path = ROOT) -> list[ScanHit]:
    hits: list[ScanHit] = []
    for glob_pat in SCAN_GLOBS:
        for path in sorted(root.glob(glob_pat)):
            if not path.is_file() or not _should_scan(path, root):
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
            except (OSError, UnicodeDecodeError):
                continue
            for i, line_text in enumerate(lines, start=1):
                for term in scan_terms:
                    if term in line_text:
                        hits.append(ScanHit(
                            path=str(path.relative_to(root)),
                            line=i,
                            term=term,
                        ))
    return hits


# ── consumer / exclusion parsing ──────────────────────────────────────────────


def _parse_consumer_ranges(consumers: list[dict]) -> list[ConsumerRange]:
    result: list[ConsumerRange] = []
    for c in consumers:
        result.append(ConsumerRange(
            consumer_id=c.get("consumer_id", "?"),
            path=c.get("path", ""),
            line_start=c.get("line_start", 0),
            line_end=c.get("line_end", 0),
            match_terms=c.get("match_terms", []),
        ))
    return result


def _parse_exclusions(exclusions: list[dict]) -> list[ExclusionEntry]:
    result: list[ExclusionEntry] = []
    for e in exclusions:
        result.append(ExclusionEntry(
            path=e.get("path", ""),
            match_line=e.get("match_line", 0),
            term=e.get("term", ""),
            reason=e.get("reason", ""),
        ))
    return result


# ── hit matching ──────────────────────────────────────────────────────────────


def _hit_covered(hit: ScanHit, ranges: list[ConsumerRange],
                 excl: list[ExclusionEntry]) -> bool:
    for cr in ranges:
        if (hit.path == cr.path
                and cr.line_start <= hit.line <= cr.line_end
                and hit.term in cr.match_terms):
            return True
    for ex in excl:
        if (hit.path == ex.path
                and hit.line == ex.match_line
                and hit.term == ex.term):
            return True
    return False


# ── per-consumer validation ───────────────────────────────────────────────────


def _check_one(consumer: dict, root: Path = ROOT) -> list[str]:
    f: list[str] = []
    cid = consumer.get("consumer_id", "?")
    p = f"{cid}:"
    missing = REQ_FIELDS - set(consumer)
    if missing:
        f.append(f"{p} missing fields: {sorted(missing)}")
    f.extend(_check_one_enums(consumer, p))
    f.extend(_check_one_path_lines(consumer, p, root))
    return f


def _check_one_enums(consumer: dict, p: str) -> list[str]:
    f: list[str] = []
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
    cid = consumer.get("consumer_id", "")
    if not CID_RE.match(cid):
        f.append(f"{p} invalid consumer_id format, expected ATT-CONS-NNN: {cid}")
    for req_field in REQ_TEXT:
        if not str(consumer.get(req_field, "")).strip():
            f.append(f"{p} {req_field} is empty")
    return f


def _check_one_path_lines(consumer: dict, p: str, root: Path = ROOT) -> list[str]:
    f: list[str] = []
    path_str = consumer.get("path", "")
    if path_str and not (root / path_str).is_file():
        f.append(f"{p} path does not exist: {path_str}")
    ls = consumer.get("line_start", 0)
    le = consumer.get("line_end", 0)
    if not isinstance(ls, int) or ls <= 0:
        f.append(f"{p} invalid line_start: {ls}")
    if not isinstance(le, int) or le <= 0:
        f.append(f"{p} invalid line_end: {le}")
    if isinstance(ls, int) and isinstance(le, int) and ls > 0 and le > 0 and ls > le:
        f.append(f"{p} line_start > line_end: {ls} > {le}")
    # Range size check — prevent whole-file masking
    if isinstance(ls, int) and isinstance(le, int) and le - ls > MAX_RANGE_LINES:
        just = consumer.get("wide_range_justification", "")
        if not just.strip():
            f.append(f"{p} range too wide ({le - ls} lines > {MAX_RANGE_LINES}); "
                     f"provide wide_range_justification")
    mt = consumer.get("match_terms")
    if not isinstance(mt, list) or not mt:
        f.append(f"{p} match_terms is empty")
    return f


# ── consumer ID sequence check ────────────────────────────────────────────────


def _check_ids(consumers: list[dict]) -> list[str]:
    f: list[str] = []
    seen: set[str] = set()
    for c in consumers:
        cid = c.get("consumer_id", "")
        if cid in seen:
            f.append(f"duplicate consumer_id: {cid}")
        seen.add(cid)
    ids = [c.get("consumer_id", "") for c in consumers]
    for i, cid in enumerate(ids, start=1):
        expected = f"ATT-CONS-{i:03d}"
        if cid != expected:
            f.append(f"expected {expected} at position {i}, got {cid}")
    return f


# ── summary recalculation ─────────────────────────────────────────────────────


def _check_summary(consumers: list[dict], summary: dict) -> list[str]:
    f: list[str] = []
    roles = Counter(c.get("role") for c in consumers)
    disps = Counter(c.get("disposition") for c in consumers)
    hc = sum(1 for c in consumers if c.get("risk") in {"high", "critical"})
    actual_count = len(consumers)

    claimed_count = summary.get("total_consumers")
    if claimed_count != actual_count:
        f.append(f"summary.total_consumers: claimed={claimed_count}, actual={actual_count}")

    claimed_roles = summary.get("by_role", {})
    actual_roles = dict(roles)
    if claimed_roles != actual_roles:
        f.append(f"summary.by_role mismatch: claimed={claimed_roles}, actual={actual_roles}")

    claimed_disps = summary.get("by_disposition", {})
    actual_disps = dict(disps)
    if claimed_disps != actual_disps:
        f.append(f"summary.by_disposition mismatch: claimed={claimed_disps}, "
                 f"actual={actual_disps}")

    claimed_hc = summary.get("high_or_critical_count")
    if claimed_hc != hc:
        f.append(f"summary.high_or_critical_count: claimed={claimed_hc}, actual={hc}")

    return f


# ── exclusion validation ──────────────────────────────────────────────────────


def _check_exclusions(exclusions: list[dict], scan_terms: list[str],
                      scan_hits: list[ScanHit], root: Path = ROOT) -> list[str]:
    f: list[str] = []
    hit_set = {(h.path, h.line, h.term) for h in scan_hits}
    valid_terms = set(scan_terms)
    seen_excl: set[tuple] = set()
    for i, exc in enumerate(exclusions):
        f.extend(_check_one_exclusion(i, exc, valid_terms, hit_set, seen_excl, root))
    return f


def _check_one_exclusion(i, exc, valid_terms, hit_set, seen_excl, root):
    f: list[str] = []
    idx = f"exclusion[{i}]"
    p = exc.get("path", "")
    ml = exc.get("match_line", 0)
    term = exc.get("term", "")
    reason = exc.get("reason", "")

    f.extend(_check_excl_structure(idx, p, ml, term, reason, root))
    if not f or any("empty path" in x for x in f):
        return f
    f.extend(_check_excl_term_match(idx, p, ml, term, valid_terms, root))
    f.extend(_check_excl_hit_match(idx, p, ml, term, hit_set, seen_excl))
    return f


def _check_excl_structure(idx, p, ml, term, reason, root):
    f = []
    if not p:
        f.append(f"{idx}: empty path")
        return f
    if not (root / p).is_file():
        f.append(f"{idx}: path does not exist: {p}")
    if not isinstance(ml, int) or ml <= 0:
        f.append(f"{idx}: invalid match_line: {ml}")
    if not term:
        f.append(f"{idx}: empty term")
    if not reason.strip():
        f.append(f"{idx}: empty reason")
    return f


def _check_excl_term_match(idx, p, ml, term, valid_terms, root):
    f = []
    if term and term not in valid_terms:
        f.append(f"{idx}: term '{term}' not in scope.scan_terms")
    if (root / p).is_file() and term and ml > 0:
        try:
            lines = (root / p).read_text(errors="replace").split("\n")
            if ml <= len(lines):
                if term not in lines[ml - 1]:
                    f.append(f"{idx}: term '{term}' not found at line {ml} in {p}")
            else:
                f.append(f"{idx}: line {ml} out of range ({len(lines)} lines) in {p}")
        except OSError:
            pass
    return f


def _check_excl_hit_match(idx, p, ml, term, hit_set, seen_excl):
    f = []
    key = (p, ml, term)
    if key not in hit_set:
        f.append(f"{idx}: no scan hit at {p}:{ml}:{term}")
    if key in seen_excl:
        f.append(f"{idx}: duplicate exclusion: {key}")
    seen_excl.add(key)
    return f


# ── main entry ────────────────────────────────────────────────────────────────


def validate_inventory(inv_path: Path = INV, root: Path = ROOT) -> list[str]:
    failures: list[str] = []
    if not inv_path.is_file():
        return [f"inventory not found: {inv_path}"]
    try:
        data = json.loads(inv_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"invalid JSON: {exc}"]

    if data.get("schema") != "finharness.attestation_consumer_inventory.v1":
        failures.append(f"unknown schema: {data.get('schema')}")

    unclass = data.get("unclassified_hits", [])
    if unclass:
        failures.append(f"{len(unclass)} unclassified_hits must be empty")

    consumers = data.get("consumers")
    if not isinstance(consumers, list):
        return [*failures, "consumers must be a list"]

    scan_terms = data.get("scope", {}).get("scan_terms", [])
    if not scan_terms:
        failures.append("scope.scan_terms is empty")

    for c in consumers:
        failures.extend(_check_one(c, root))

    failures.extend(_check_ids(consumers))
    failures.extend(_check_summary(consumers, data.get("summary", {})))

    exclusions = data.get("exclusions", [])
    scan_hits = _scan_hits(scan_terms, root)
    failures.extend(_check_exclusions(exclusions, scan_terms, scan_hits, root))

    ranges = _parse_consumer_ranges(consumers)
    parsed_excl = _parse_exclusions(exclusions)
    for hit in scan_hits:
        if not _hit_covered(hit, ranges, parsed_excl):
            failures.append(f"unregistered hit: {hit.path}:{hit.line}:{hit.term}")

    return failures


def main() -> int:
    failures = validate_inventory()
    if failures:
        print("FAILURES:")
        for f in failures:
            print(f"  {f}")
        return 1

    data = json.loads(INV.read_text(encoding="utf-8"))
    s = data["summary"]
    print(f"OK: {len(data['consumers'])} consumers")
    for d in sorted(s.get("by_disposition", {})):
        print(f"  {d}: {s['by_disposition'][d]}")
    print(f"  high/critical: {s.get('high_or_critical_count', '?')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
