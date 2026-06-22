"""Centralized governance/boundary probes — the machine guardrail for EOS v0 (G4).

This is the home for cross-cutting, enumerable risks we have already hit (or are at
high risk of repeating), so a reviewer never has to remember them. New slices add a
probe here rather than re-litigating the same boundary in review. Run via
``task governance:check`` (frontend no-action-affordance lives in the jsdom suite).

First batch covers: import boundaries (research surfaces don't reach the optimizer /
proposal / route), research redline-policy coverage, the attachment's own redline, and
no-Pydantic-object leakage into proposal evidence.
"""

from __future__ import annotations

import ast
import json
import unittest
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


def _reachable_tasks(name: str, tasks: dict, seen: set[str] | None = None) -> set[str]:
    """Recursive task-dependency closure following `- task: <name>` references."""
    seen = seen if seen is not None else set()
    if name in seen or name not in tasks:
        return seen
    seen.add(name)
    for cmd in (tasks.get(name) or {}).get("cmds") or []:
        if isinstance(cmd, dict) and "task" in cmd:
            _reachable_tasks(cmd["task"], tasks, seen)
    return seen

# Research surfaces are read-only evidence; they must not reach advice/optimizer or the
# proposal/route writing surfaces, whether by import or by name reference.
_FORBIDDEN_IDENTIFIERS = (
    "optimize_riskfolio_allocation",
    "Proposal",
    "APIRouter",
    "FastAPI",
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


def _evidence_item(*, source_refs: tuple[str, ...] = ()) -> ResearchEvidence:
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
        source_refs=source_refs,
        non_claims=REQUIRED_NON_CLAIMS["historical_market_data"],
    )


class ImportBoundaryProbe(unittest.TestCase):
    def test_research_surfaces_do_not_reference_advice_or_write_surfaces(self) -> None:
        for module in ("research_enrichment.py", "research_history_provider.py"):
            identifiers = _identifiers(_SRC / module)
            for banned in _FORBIDDEN_IDENTIFIERS:
                self.assertNotIn(
                    banned, identifiers, f"{module} must not reference {banned}"
                )


class ReviewReadOnlyProbe(unittest.TestCase):
    def test_review_routes_never_call_write_or_compute_entrypoints(self) -> None:
        # The Retrospective cockpit must stay read-only: no annual-review compute/record,
        # no lesson/rule promotion or persistence.
        identifiers = _identifiers(_SRC / "api" / "routes_review.py")
        for banned in (
            "compute_annual_review",
            "record_annual_review",
            "promote_lesson_to_rule_change",
            "persist_lesson_draft",
        ):
            self.assertNotIn(banned, identifiers, f"/review/* must not call {banned}")


class RedlinePolicyCoverageProbe(unittest.TestCase):
    def test_every_research_output_field_has_a_policy(self) -> None:
        # A new provider-output field cannot be added without assigning a redline policy.
        self.assertEqual(
            set(ResearchEvidence.model_fields), set(RESEARCH_EVIDENCE_FIELD_POLICIES)
        )
        self.assertEqual(
            set(ResearchEvidenceResult.model_fields),
            set(RESEARCH_EVIDENCE_RESULT_FIELD_POLICIES),
        )


class AttachmentRedlineProbe(unittest.TestCase):
    def test_advice_gap_cannot_be_constructed(self) -> None:
        with self.assertRaises((ValueError, ValidationError)):
            ResearchEvidenceAttachment(data_gaps=("buy SPY now",))

    def test_free_form_source_refs_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ResearchEvidenceAttachment(source_refs=("buy SPY now",))

    def test_disclosure_gap_is_allowed(self) -> None:
        attachment = ResearchEvidenceAttachment(
            data_gaps=("market history unavailable for SPY.",)
        )
        self.assertTrue(attachment.data_gaps)


class NetworkSmokeExclusionProbe(unittest.TestCase):
    def test_research_smoke_is_not_in_the_default_check_chain(self) -> None:
        # The --with-research live smoke hits the network; it must never be reachable
        # from `task check` (which transitively includes governance:check and test:*).
        tasks = (yaml.safe_load((_ROOT / "Taskfile.yml").read_text(encoding="utf-8")) or {}).get(
            "tasks", {}
        )
        reachable = _reachable_tasks("check", tasks)
        self.assertIn("check", reachable)
        self.assertNotIn(
            "decisions:research-smoke", reachable, "network smoke must not be in task check"
        )
        # No task reachable from check may shell out to the smoke script either.
        for name in reachable:
            for cmd in (tasks.get(name) or {}).get("cmds") or []:
                if isinstance(cmd, str):
                    self.assertNotIn(
                        "run_research_smoke", cmd, f"task {name} must not run the smoke script"
                    )
        # Sanity: the manual smoke task exists.
        self.assertIn("decisions:research-smoke", tasks)


class NoPydanticLeakProbe(unittest.TestCase):
    def test_attachment_payload_is_json_serializable(self) -> None:
        attachment = ResearchEvidenceAttachment.from_result(
            ResearchEvidenceResult(items=(_evidence_item(),))
        )
        payload = attachment.to_evidence_payload()
        self.assertTrue(all(isinstance(entry, dict) for entry in payload))
        json.dumps(payload)  # must not raise on a Pydantic object


if __name__ == "__main__":
    unittest.main()
