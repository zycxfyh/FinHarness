"""Governance policy registry (EOS).

Each enumerable governance rule is a declarative ``PolicyRule`` with ``id / owner / scope /
source / description / check`` — so a rule is discoverable (who owns it, what it governs,
what motivated it) instead of being an anonymous test method. ``check`` returns a list of
violation messages (empty == pass), so the driver reports failures by policy id.

This is a Python registry, deliberately *not* OPA/Conftest yet — adopt those only when the
rule set outgrows Python (see scaffolding-inventory.md).
"""

from __future__ import annotations

import ast
import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from finharness.research_enrichment import ResearchEvidenceAttachment
from finharness.research_evidence import (
    REQUIRED_NON_CLAIMS,
    RESEARCH_EVIDENCE_FIELD_POLICIES,
    RESEARCH_EVIDENCE_RESULT_FIELD_POLICIES,
    ResearchEvidence,
    ResearchEvidenceResult,
)

_ROOT = Path(__file__).resolve().parents[1]
_SRC = _ROOT / "src" / "finharness"


@dataclass(frozen=True)
class PolicyRule:
    id: str
    owner: str  # the system/area that owns the boundary
    scope: str  # the files/surface it governs
    source: str  # the slice / gate / postmortem that motivated it
    description: str
    check: Callable[[], list[str]]  # returns violation messages; empty == pass


# --- shared helpers ---------------------------------------------------------------------

_FORBIDDEN_RESEARCH_IDENTIFIERS = (
    "optimize_riskfolio_allocation",
    "Proposal",
    "APIRouter",
    "FastAPI",
)

_REVIEW_WRITE_ENTRYPOINTS = (
    "compute_annual_review",
    "record_annual_review",
    "promote_lesson_to_rule_change",
    "persist_lesson_draft",
    "create_governed_proposal",
    "create_governed_attestation",
    "create_governed_review_event",
)


def _identifiers(module_path: Path) -> set[str]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names.update(alias.name for alias in node.names)
    return names


def _reachable_tasks(name: str, tasks: dict, seen: set[str] | None = None) -> set[str]:
    seen = seen if seen is not None else set()
    if name in seen or name not in tasks:
        return seen
    seen.add(name)
    for cmd in (tasks.get(name) or {}).get("cmds") or []:
        if isinstance(cmd, dict) and "task" in cmd:
            _reachable_tasks(cmd["task"], tasks, seen)
    return seen


def _evidence_item() -> ResearchEvidence:
    return ResearchEvidence(
        kind="historical_risk_profile",
        claim="Over the trailing 3 years, SPY's observed realized volatility was 18%.",
        evidence_grade="historical_market_data",
        value={
            "realized_volatility": 0.18,
            "max_drawdown": -0.34,
            "conditional_var": -0.03,
            "average_volume": 1_000_000.0,
        },
        time_window="trailing_3y",
        non_claims=REQUIRED_NON_CLAIMS["historical_market_data"],
    )


# --- checks (return violation messages; empty == pass) ----------------------------------

def _check_research_import_boundary() -> list[str]:
    out: list[str] = []
    for module in ("research_enrichment.py", "research_history_provider.py"):
        identifiers = _identifiers(_SRC / module)
        out += [
            f"{module} references {banned}"
            for banned in _FORBIDDEN_RESEARCH_IDENTIFIERS
            if banned in identifiers
        ]
    return out


def _check_review_read_only() -> list[str]:
    out: list[str] = []
    for module in (_SRC / "api" / "routes_review.py", _SRC / "review_read.py"):
        identifiers = _identifiers(module)
        out += [
            f"{module.name} calls {banned}"
            for banned in _REVIEW_WRITE_ENTRYPOINTS
            if banned in identifiers
        ]
    return out


def _check_system_directory_reference() -> list[str]:
    roles = {
        "domain": _SRC / "statecore" / "models.py",
        "commands": _SRC / "statecore" / "proposals.py",
        "read_model": _SRC / "review_read.py",
        "adapters": _SRC / "api" / "routes_review.py",
        "fixtures": _ROOT / "tests" / "_review_fixtures.py",
        "governance": _ROOT / "tests" / "_policy_registry.py",
    }
    return [
        f"Review System {role} reference missing: {path}"
        for role, path in roles.items()
        if not path.exists()
    ]


def _check_redline_policy_coverage() -> list[str]:
    out: list[str] = []
    if set(ResearchEvidence.model_fields) != set(RESEARCH_EVIDENCE_FIELD_POLICIES):
        out.append("ResearchEvidence fields not covered by field policies")
    if set(ResearchEvidenceResult.model_fields) != set(RESEARCH_EVIDENCE_RESULT_FIELD_POLICIES):
        out.append("ResearchEvidenceResult fields not covered by field policies")
    return out


def _check_attachment_redline() -> list[str]:
    out: list[str] = []
    try:
        ResearchEvidenceAttachment(data_gaps=("buy SPY now",))
        out.append("advice-bearing data_gap was constructible")
    except (ValueError, ValidationError):
        pass
    try:
        ResearchEvidenceAttachment(source_refs=("buy SPY now",))
        out.append("free-form source_ref was accepted")
    except ValueError:
        pass
    try:
        attachment = ResearchEvidenceAttachment(data_gaps=("market history unavailable for SPY.",))
        if not attachment.data_gaps:
            out.append("a plain disclosure gap was dropped")
    except Exception as exc:  # a disclosure gap must be constructible
        out.append(f"plain disclosure gap rejected: {type(exc).__name__}")
    return out


def _check_no_pydantic_leak() -> list[str]:
    attachment = ResearchEvidenceAttachment.from_result(
        ResearchEvidenceResult(items=(_evidence_item(),))
    )
    payload = attachment.to_evidence_payload()
    if not all(isinstance(entry, dict) for entry in payload):
        return ["attachment payload contains non-dict (Pydantic) entries"]
    try:
        json.dumps(payload)
    except TypeError:
        return ["attachment payload is not JSON-serializable (Pydantic leak)"]
    return []


def _check_network_smoke_excluded() -> list[str]:
    tasks = (yaml.safe_load((_ROOT / "Taskfile.yml").read_text(encoding="utf-8")) or {}).get(
        "tasks", {}
    )
    reachable = _reachable_tasks("check", tasks)
    out: list[str] = []
    if "check" not in reachable:
        return ["task 'check' not found"]
    for manual in ("decisions:research-smoke", "decisions:golden-path"):
        if manual in reachable:
            out.append(f"{manual} is reachable from task check")
        if manual not in tasks:
            out.append(f"{manual} task missing")
    for name in reachable:
        for cmd in (tasks.get(name) or {}).get("cmds") or []:
            if isinstance(cmd, str):
                out += [
                    f"task {name} runs {script}"
                    for script in ("run_research_smoke", "run_golden_path")
                    if script in cmd
                ]
    return out


POLICIES: tuple[PolicyRule, ...] = (
    PolicyRule(
        id="GOV-RESEARCH-001",
        owner="research-evidence",
        scope="research_enrichment.py, research_history_provider.py",
        source="RE2 design gate (read-only evidence, no optimizer/route)",
        description="Research surfaces never reference optimizer/proposal/route write surfaces.",
        check=_check_research_import_boundary,
    ),
    PolicyRule(
        id="GOV-REVIEW-001",
        owner="review-system",
        scope="api/routes_review.py, review_read.py",
        source="R3 design gate + R4a-0 read-model extraction",
        description="Review read surfaces never call write/compute/promote/persist entrypoints.",
        check=_check_review_read_only,
    ),
    PolicyRule(
        id="GOV-ARCH-001",
        owner="eos",
        scope="Review System reference files (6 roles)",
        source="system-directory-standard.md (#2)",
        description="Review System reference files exist (the standard can't silently rot).",
        check=_check_system_directory_reference,
    ),
    PolicyRule(
        id="GOV-RESEARCH-002",
        owner="research-evidence",
        scope="ResearchEvidence / ResearchEvidenceResult fields",
        source="RE1 redline contract",
        description="Every research output field is covered by a redline field policy.",
        check=_check_redline_policy_coverage,
    ),
    PolicyRule(
        id="GOV-RESEARCH-003",
        owner="research-evidence",
        scope="ResearchEvidenceAttachment construction",
        source="RE3 impl gate (attachment redline bypass; postmortem R2)",
        description="Attachment self-guards redline: advice gaps / free-form refs rejected.",
        check=_check_attachment_redline,
    ),
    PolicyRule(
        id="GOV-RESEARCH-004",
        owner="research-evidence",
        scope="ResearchEvidenceAttachment.to_evidence_payload",
        source="RE3 impl gate (no Pydantic leak into proposal evidence)",
        description="Attachment payload is plain JSON-serializable (no Pydantic objects).",
        check=_check_no_pydantic_leak,
    ),
    PolicyRule(
        id="GOV-EOS-001",
        owner="eos",
        scope="Taskfile.yml `check` dependency closure",
        source="research live smoke + golden path mini-RFCs",
        description="Network/manual demo tasks are unreachable from `task check`.",
        check=_check_network_smoke_excluded,
    ),
)


def list_policies() -> list[dict[str, str]]:
    """Discoverable view of the registry (id/owner/scope/source/description)."""
    return [
        {"id": p.id, "owner": p.owner, "scope": p.scope, "source": p.source,
         "description": p.description}
        for p in POLICIES
    ]


if __name__ == "__main__":
    print(json.dumps(list_policies(), indent=2))
