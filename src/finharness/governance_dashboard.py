"""Governance dashboard aggregation for FinHarness RC hardening.

The dashboard reads local governance receipts and graph outputs, then writes a
single human-facing release posture report. It is evidence aggregation only: it
does not run trading code, authorize releases, or replace release preflight.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from finharness.release_preflight_graph import run_release_preflight_graph
from finharness.repo_intelligence import ROOT
from finharness.repo_intelligence_graph import run_repo_intelligence_graph

WORKFLOW_VERSION = "finharness_governance_dashboard_v1"


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"present": False, "path": str(path)}
    return {
        "present": True,
        "path": str(path),
        "payload": json.loads(path.read_text(encoding="utf-8")),
    }


def _check_status(check_results: list[dict[str, Any]], name: str) -> dict[str, Any]:
    match = next((item for item in check_results if item.get("name") == name), None)
    if not match:
        return {"name": name, "status": "missing", "ok": False}
    return {
        "name": name,
        "status": match.get("status", "unknown"),
        "ok": match.get("status") == "passed",
        "duration_seconds": match.get("duration_seconds"),
        "budget_seconds": match.get("budget_seconds"),
    }


def _hardening_summary(hardening: dict[str, Any]) -> dict[str, Any]:
    if not hardening.get("present"):
        return {
            "present": False,
            "release_blocked": True,
            "status": "missing",
            "execution_allowed": False,
        }
    payload = hardening["payload"]
    return {
        "present": True,
        "generated_at": payload.get("generated_at"),
        "release_blocked": bool(payload.get("release_blocked", True)),
        "status": "blocked" if payload.get("release_blocked", True) else "passed",
        "checks": [
            {
                "tool": item.get("tool"),
                "returncode": item.get("returncode"),
                "release_blocked": bool(item.get("release_blocked")),
            }
            for item in payload.get("checks", [])
        ],
        "execution_allowed": bool(payload.get("execution_allowed", False)),
    }


def _render_mermaid() -> str:
    return "\n".join(
        [
            "flowchart TD",
            '  repo["repo_intelligence"]',
            '  quality["quality_governance"]',
            '  hardening["hardening_gate"]',
            '  redteam["redteam_boundary"]',
            '  preflight["release_preflight"]',
            '  dashboard["governance_dashboard"]',
            '  human["human_review_gate"]',
            "  repo --> quality",
            "  quality --> preflight",
            "  hardening --> dashboard",
            "  redteam --> dashboard",
            "  preflight --> dashboard",
            "  dashboard --> human",
        ]
    )


def _render_markdown(dashboard: dict[str, Any]) -> str:
    repo = dashboard["repo_intelligence"]
    quality = dashboard["quality_governance"]
    release = dashboard["release_preflight"]
    hardening = dashboard["hardening_gate"]
    redteam = dashboard["redteam_boundary"]
    lines = [
        "# Governance Dashboard",
        "",
        f"Generated at: `{dashboard['generated_at']}`",
        "",
        "## RC0.1 Posture",
        "",
        f"- Release ready: `{str(release['release_ready']).lower()}`",
        f"- Release blocked: `{str(release['release_blocked']).lower()}`",
        f"- Requires human review: `{str(dashboard['requires_human_review']).lower()}`",
        f"- Execution allowed: `{str(dashboard['execution_allowed']).lower()}`",
        f"- Dashboard status: `{dashboard['dashboard_status']}`",
        "",
        "## Repo Intelligence",
        "",
        f"- Files: `{repo['inventory_summary'].get('file_count')}`",
        f"- Total lines: `{repo['inventory_summary'].get('total_lines')}`",
        f"- Changed files: `{len(repo['changed_surface'])}`",
        "",
        "## Required Checks",
        "",
    ]
    lines.extend(f"- `{check}`" for check in repo["required_checks"])
    lines.extend(
        [
            "",
            "## Quality Governance",
            "",
            f"- Decision: `{quality['decision']}`",
            f"- Release blocked: `{str(quality['release_blocked']).lower()}`",
            f"- Performance status: `{quality['performance_status']}`",
            "",
            "## Hardening And Red Team",
            "",
            f"- Hardening gate: `{hardening['status']}`",
            f"- Red-team boundary: `{redteam['status']}`",
            "",
            "## Mermaid",
            "",
            "```mermaid",
            dashboard["mermaid"],
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def build_governance_dashboard(
    *,
    root: Path = ROOT,
    run_checks: bool = False,
) -> dict[str, Any]:
    repo = run_repo_intelligence_graph(root=str(root))["final"]
    preflight_receipt_ref = root / "data" / "receipts" / "release-preflight" / "latest.json"
    preflight_receipt = load_json(preflight_receipt_ref)
    if run_checks or not preflight_receipt.get("present"):
        preflight = run_release_preflight_graph(root=str(root), run_checks=run_checks)["final"]
    else:
        preflight = preflight_receipt["payload"]
        preflight.setdefault("receipt_ref", str(preflight_receipt_ref))
    quality_receipt_ref = Path(preflight["quality"]["receipt_ref"])
    quality_receipt = load_json(quality_receipt_ref)
    hardening_receipt = load_json(
        root / "data" / "receipts" / "hardening" / "latest-hardening-gate.json"
    )

    quality_payload = quality_receipt.get("payload", {})
    check_results = quality_payload.get("check_results", [])
    quality_decision = preflight["quality"]["release_decision"]
    hardening_summary = _hardening_summary(hardening_receipt)
    redteam_status = _check_status(check_results, "task eval:redteam-boundary")
    release_gate = preflight["release_gate"]
    dashboard_status = (
        "blocked"
        if release_gate["release_blocked"] or hardening_summary["release_blocked"]
        else "human_review"
        if release_gate["requires_human_review"]
        else "ready"
    )

    dashboard = {
        "workflow": WORKFLOW_VERSION,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {
            "workflow": WORKFLOW_VERSION,
            "graph": "governance_dashboard_graph",
            "execution_allowed": False,
            "authority_boundary": (
                "This dashboard aggregates governance evidence; it does not "
                "authorize live trading or replace release preflight."
            ),
        },
        "repo_intelligence": {
            "inventory_summary": repo["inventory_summary"],
            "changed_surface": repo["blast_radius"]["changed_files"],
            "required_checks": repo["blast_radius"]["required_checks"],
            "security_surface": repo["security_surface"],
            "receipt_ref": repo["outputs"]["receipt"],
        },
        "quality_governance": {
            "decision": quality_decision["decision"],
            "release_blocked": quality_decision["release_blocked"],
            "failed_required_checks": quality_decision["failed_required_checks"],
            "requires_human_review": quality_decision["requires_human_review"],
            "performance_status": quality_decision["performance_status"],
            "checks": [
                _check_status(check_results, "task check"),
                _check_status(check_results, "task hardening:gate"),
                _check_status(check_results, "task eval:redteam-boundary"),
            ],
            "receipt_ref": str(quality_receipt_ref),
        },
        "hardening_gate": hardening_summary,
        "redteam_boundary": redteam_status,
        "performance_baseline": quality_payload.get("performance_baseline", {}),
        "release_preflight": {
            "release_ready": release_gate["release_ready"],
            "release_blocked": release_gate["release_blocked"],
            "missing": release_gate["missing"],
            "requires_human_review": release_gate["requires_human_review"],
            "receipt_ref": preflight["receipt_ref"],
        },
        "receipt_refs": {
            "repo_intelligence": repo["outputs"]["receipt"],
            "quality_governance": str(quality_receipt_ref),
            "hardening_gate": hardening_receipt["path"],
            "release_preflight": preflight["receipt_ref"],
        },
        "requires_human_review": release_gate["requires_human_review"],
        "execution_allowed": False,
        "dashboard_status": dashboard_status,
        "mermaid": _render_mermaid(),
    }
    return dashboard


def write_governance_dashboard_outputs(
    dashboard: dict[str, Any],
    *,
    root: Path = ROOT,
) -> dict[str, str]:
    receipt_path = root / "data" / "receipts" / "governance-dashboard" / "latest.json"
    report_path = root / "docs" / "operations" / "governance-dashboard-latest.md"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(dashboard, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    report_path.write_text(_render_markdown(dashboard), encoding="utf-8")
    return {"receipt": str(receipt_path), "report": str(report_path)}
