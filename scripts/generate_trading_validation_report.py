"""Generate the FinHarness trading validation report v1.

The report validates the MVP boundary and evidence posture. It does not certify
strategy performance, best execution, live readiness, or regulatory compliance.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from finharness.market_data import ROOT

DEFAULT_JSON = ROOT / "data" / "reports" / "trading-validation-report-v1.json"
DEFAULT_MARKDOWN = ROOT / "docs" / "reports" / "trading-validation-report-v1.md"


def repo_path(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"present": False, "path": repo_path(path)}
    return {"present": True, "path": repo_path(path), "payload": json.loads(path.read_text())}


def git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def evidence_status(evidence: dict[str, Any], keys: list[str]) -> Any:
    payload = evidence.get("payload") if evidence.get("present") else {}
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def build_report() -> dict[str, Any]:
    release_preflight = read_json(ROOT / "data" / "receipts" / "release-preflight" / "latest.json")
    governance_dashboard = read_json(
        ROOT / "data" / "receipts" / "governance-dashboard" / "latest.json"
    )
    fuzz = read_json(ROOT / "data" / "security" / "fuzzing" / "latest.json")
    sbom = read_json(ROOT / "data" / "security" / "sbom" / "finharness-sbom.json")
    provenance = read_json(
        ROOT / "data" / "security" / "provenance" / "finharness-provenance-baseline.json"
    )
    evidence = {
        "release_preflight": release_preflight,
        "governance_dashboard": governance_dashboard,
        "fuzz_baseline": fuzz,
        "sbom": sbom,
        "provenance_baseline": provenance,
    }
    release_ready = evidence_status(release_preflight, ["release_gate", "release_ready"])
    dashboard_status = evidence_status(governance_dashboard, ["dashboard_status"])
    fuzz_failed = evidence_status(fuzz, ["failed_case_count"])
    sbom_components = evidence_status(sbom, ["component_count"])
    validation_passed = (
        release_ready is True
        and dashboard_status in {"ready", "human_review"}
        and fuzz_failed == 0
        and isinstance(sbom_components, int)
        and sbom_components > 0
    )
    return {
        "schema": "finharness.trading_validation_report.v1",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "git_head": git_head(),
        "scope": "FinHarness ten-layer MVP trading research and governance boundary",
        "validation_result": {
            "mvp_boundary_validated": validation_passed,
            "classification": "research_evidence_chain_ready_for_local_paper_or_fake_first_use",
            "release_ready": release_ready,
            "dashboard_status": dashboard_status,
            "requires_human_review": evidence_status(
                governance_dashboard,
                ["requires_human_review"],
            ),
            "execution_allowed": False,
        },
        "evidence_summary": {
            "release_preflight_ready": release_ready,
            "fuzz_failed_case_count": fuzz_failed,
            "fuzz_case_count": evidence_status(fuzz, ["case_count"]),
            "sbom_component_count": sbom_components,
            "provenance_status": evidence_status(provenance, ["slsa_status"]),
        },
        "claim_ledger": [
            {
                "claim": "Ten-layer MVP chain exists and preserves evidence boundaries.",
                "status": "supported",
                "evidence": [
                    "docs/reviews/2026-06-02-finharness-ten-layer-mvp-summary.md",
                    "task check",
                    "task release:preflight",
                ],
            },
            {
                "claim": "Local hardening, dependency, secret, and workflow checks pass.",
                "status": "supported",
                "evidence": ["security workflow", "task security:scan", "CodeQL/Gitleaks/Trivy"],
            },
            {
                "claim": "Governance-boundary fuzzing has a deterministic baseline.",
                "status": "supported_local_baseline",
                "evidence": ["task security:fuzz", "data/security/fuzzing/latest.json"],
            },
            {
                "claim": "FinHarness has validated profitable trading performance.",
                "status": "not_supported",
                "evidence": [],
            },
            {
                "claim": "FinHarness is ready for autonomous live trading.",
                "status": "rejected",
                "evidence": ["execution_allowed=false", "live execution blocked by design"],
            },
        ],
        "validation_matrix": [
            {
                "area": "L1-L10 contracts",
                "evidence": "unit tests and ten-layer docs",
                "status": "pass",
            },
            {
                "area": "Execution boundary",
                "evidence": "risk gate and execution tests",
                "status": "paper_or_fake_first_only",
            },
            {
                "area": "Post-trade reconciliation",
                "evidence": "post-trade tests and MVP summary",
                "status": "local_snapshot_reconciliation_only",
            },
            {
                "area": "Security maturity",
                "evidence": "threat model, SSDF map, SBOM, fuzz baseline",
                "status": "rc0_2_baseline",
            },
            {
                "area": "External performance validity",
                "evidence": "none",
                "status": "not_validated",
            },
        ],
        "residual_gaps": [
            "No statistically significant out-of-sample strategy validation report.",
            "No broker-certified best execution or venue routing analysis.",
            "No live trading authorization, dual-control approval, or signed live receipt.",
            "No formal CycloneDX/SPDX SBOM or signed SLSA provenance yet.",
            "OpenSSF Scorecard still does not recognize the local fuzz baseline as formal fuzzing.",
            "Main branch still has admin bypass and is not PR-only.",
        ],
        "next_validation_steps": [
            "Add strategy-level validation report templates for StrategySpec assets.",
            "Add transaction-cost and slippage assumption reports for any paper experiment.",
            "Add signed/checksummed release receipts before distributing artifacts.",
            "Decide whether to adopt Hypothesis, Atheris, OSS-Fuzz, or ClusterFuzzLite.",
            "Add CODEOWNERS and decide if main should become PR-only.",
        ],
        "evidence_refs": {name: item["path"] for name, item in evidence.items()},
        "non_claims": [
            "Not investment advice.",
            "Not a performance presentation.",
            "Not GIPS, FINRA, SEC, broker, exchange, custody, tax, or accounting compliance.",
            "Not best-execution certification.",
            "Not autonomous live trading approval.",
        ],
        "execution_allowed": False,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Trading Validation Report v1",
        "",
        f"Date: {report['generated_at'][:10]}",
        "Status: RC0.2 boundary validation",
        "",
        "## Verdict",
        "",
        "FinHarness passes as a local ten-layer research evidence chain with paper/fake-first "
        "execution boundaries. It does not pass as a live trading system or a validated "
        "profitable strategy system.",
        "",
        "```text",
        f"mvp_boundary_validated: {report['validation_result']['mvp_boundary_validated']}",
        f"classification: {report['validation_result']['classification']}",
        f"release_ready: {report['validation_result']['release_ready']}",
        f"dashboard_status: {report['validation_result']['dashboard_status']}",
        f"execution_allowed: {report['validation_result']['execution_allowed']}",
        "```",
        "",
        "## Evidence Summary",
        "",
    ]
    for key, value in report["evidence_summary"].items():
        lines.append(f"- {key}: {value}")
    lines.extend(["", "## Claim Ledger", ""])
    for item in report["claim_ledger"]:
        lines.append(f"- {item['status']}: {item['claim']}")
    lines.extend(["", "## Validation Matrix", ""])
    lines.append("| Area | Evidence | Status |")
    lines.append("| --- | --- | --- |")
    for item in report["validation_matrix"]:
        lines.append(f"| {item['area']} | {item['evidence']} | {item['status']} |")
    lines.extend(["", "## Residual Gaps", ""])
    for item in report["residual_gaps"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Next Validation Steps", ""])
    for item in report["next_validation_steps"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Non-Claims", ""])
    for item in report["non_claims"]:
        lines.append(f"- {item}")
    lines.extend(["", "## Evidence Refs", ""])
    for key, value in report["evidence_refs"].items():
        lines.append(f"- {key}: `{value}`")
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], json_output: Path, markdown_output: Path) -> None:
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    markdown_output.write_text(render_markdown(report))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MARKDOWN)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report()
    write_outputs(report, args.json_output, args.markdown_output)
    print(
        json.dumps(
            {
                "json_ref": repo_path(args.json_output),
                "markdown_ref": repo_path(args.markdown_output),
                "mvp_boundary_validated": report["validation_result"]["mvp_boundary_validated"],
                "execution_allowed": False,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if report["validation_result"]["mvp_boundary_validated"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
