"""Small risk-gate helpers shared by implementation modules."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from finharness.risk_gate._constants import BLOCKED_RISK_GATE_LANGUAGE
from finharness.risk_gate.models import RiskGateCheck, RiskGateDecision


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
    for pattern in BLOCKED_RISK_GATE_LANGUAGE:
        if re.search(pattern, lower):
            hits.append(pattern)
    return hits


def decision_text_for_guard(decision: RiskGateDecision) -> str:
    return "\n".join(
        [
            decision.execution_intent,
            decision.sizing_intent,
            *decision.blocking_reasons,
            *decision.required_remediations,
        ]
    )


def check(
    *,
    proposal_id: str,
    check_type: str,
    passed: bool,
    reason: str,
    evidence_refs: list[str] | None = None,
    blocked_language_hits: list[str] | None = None,
    blocking: bool = True,
) -> RiskGateCheck:
    return RiskGateCheck(
        check_id=f"rgchk_{uuid4().hex[:12]}",
        proposal_id=proposal_id,
        check_type=check_type,
        status="passed" if passed else "failed",
        reason=reason,
        evidence_refs=evidence_refs or [],
        blocked_language_hits=blocked_language_hits or [],
        blocking=blocking and not passed,
        created_at_utc=now_utc(),
    )
