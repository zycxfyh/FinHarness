"""Small proposal utility helpers."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from finharness.proposal._constants import BLOCKED_PROPOSAL_LANGUAGE
from finharness.proposal.models import ProposalCandidate


def now_utc() -> str:
    return datetime.now(UTC).isoformat()


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def find_blocked_language(value: str) -> list[str]:
    lower = value.lower()
    hits: list[str] = []
    for pattern in BLOCKED_PROPOSAL_LANGUAGE:
        if re.search(pattern, lower):
            hits.append(pattern)
    return hits


def candidate_text_for_guard(candidate: ProposalCandidate) -> str:
    return "\n".join(
        [
            candidate.portfolio_role,
            candidate.rationale,
            candidate.evidence_summary,
            candidate.validation_summary,
            candidate.expected_benefit,
            candidate.time_horizon,
            candidate.benchmark_context,
            candidate.do_nothing_case,
            candidate.risk_gate_request.risk_budget_request,
            candidate.risk_gate_request.sizing_intent,
            candidate.risk_gate_request.execution_intent,
            *candidate.key_risks,
            *candidate.invalidation_triggers,
            *candidate.scenario_notes,
            *candidate.constraint_notes,
            *candidate.alternatives_considered,
        ]
    )
