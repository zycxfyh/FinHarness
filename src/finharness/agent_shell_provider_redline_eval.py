"""Deterministic multilingual evaluation for the Agent Shell provider redline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from finharness.project_paths import ROOT
from finharness.redlines import NARROW_RESEARCH_REDLINE, find_nested_redlines

DEFAULT_FIXTURE = ROOT / "tests/fixtures/agent_shell/provider_redline_cases.json"


def evaluate_provider_redline(
    fixture: Path = DEFAULT_FIXTURE,
) -> dict[str, Any]:
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    cases = payload.get("cases")
    if not isinstance(cases, list):
        raise RuntimeError("provider redline corpus has no cases")
    results: list[dict[str, Any]] = []
    failures: list[str] = []
    for raw_case in cases:
        if not isinstance(raw_case, dict):
            raise RuntimeError("provider redline case is not an object")
        case_id = str(raw_case["id"])
        expected = str(raw_case["expected"])
        hits = find_nested_redlines(raw_case["payload"], NARROW_RESEARCH_REDLINE)
        actual = "blocked" if hits else "allowed"
        results.append(
            {
                "id": case_id,
                "language": raw_case["language"],
                "expected": expected,
                "actual": actual,
                "hits": [
                    {
                        "path": finding.path,
                        "matched": finding.matched,
                        "surface": finding.surface,
                    }
                    for finding in hits
                ],
            }
        )
        if actual != expected:
            failures.append(case_id)
    return {
        "schema_version": "finharness.agent_shell_provider_redline_eval.v1",
        "case_count": len(results),
        "blocked_count": sum(item["actual"] == "blocked" for item in results),
        "allowed_count": sum(item["actual"] == "allowed" for item in results),
        "failures": failures,
        "ok": not failures,
        "results": results,
    }
