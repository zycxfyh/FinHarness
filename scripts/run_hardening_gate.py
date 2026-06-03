"""Run FinHarness local hardening checks without printing secret material."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from finharness.hardening import (
    RED_TEAM_BOUNDARY_MATRIX,
    classify_gitleaks_findings,
    load_red_team_payloads,
    red_team_payload_summary,
    summarize_findings,
)
from finharness.market_data import ROOT


def run_command(command: list[str], *, cwd: Path) -> dict[str, Any]:
    env = os.environ.copy()
    src_path = str(cwd / "src")
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        capture_output=True,
    )
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def gitignored_files(paths: set[str], *, cwd: Path) -> set[str]:
    ignored: set[str] = set()
    for path in sorted(paths):
        result = run_command(["git", "check-ignore", "-q", path], cwd=cwd)
        if result["returncode"] == 0:
            ignored.add(path)
    return ignored


def run_gitleaks(*, cwd: Path, report_path: Path) -> dict[str, Any]:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    result = run_command(
        [
            "gitleaks",
            "detect",
            "--no-git",
            "--redact",
            "--source",
            ".",
            "--report-format",
            "json",
            "--report-path",
            str(report_path),
        ],
        cwd=cwd,
    )
    findings: list[dict[str, Any]] = []
    if report_path.exists() and report_path.stat().st_size > 0:
        findings = json.loads(report_path.read_text(encoding="utf-8"))
    files = {
        path[2:] if path.startswith("./") else path
        for path in (str(item.get("File", "")) for item in findings)
    }
    ignored = gitignored_files(files, cwd=cwd)
    classified = classify_gitleaks_findings(findings, gitignored_files=ignored)
    summary = summarize_findings(classified)
    return {
        "tool": "gitleaks",
        "returncode": result["returncode"],
        "summary": summary.as_dict(),
        "release_blocked": summary.release_blocked,
        "finding_rules": sorted({item.rule_id for item in classified}),
        "blocking_files": sorted(
            {item.file for item in classified if item.bucket == "project_blocking"}
        ),
        "warning_files_sample": sorted(
            {item.file for item in classified if item.bucket != "project_blocking"}
        )[:25],
        "raw_report_ref": str(report_path),
    }


def run_trivy(*, cwd: Path) -> dict[str, Any]:
    result = run_command(
        [
            "trivy",
            "fs",
            "--scanners",
            "vuln,misconfig",
            "--skip-dirs",
            ".venv",
            "--skip-dirs",
            "vendor",
            "--format",
            "json",
            "--exit-code",
            "0",
            ".",
        ],
        cwd=cwd,
    )
    payload: dict[str, Any] = {}
    if result["stdout"].strip().startswith("{"):
        payload = json.loads(result["stdout"])
    vulnerabilities = 0
    misconfigurations = 0
    for scan_result in payload.get("Results", []):
        vulnerabilities += len(scan_result.get("Vulnerabilities", []) or [])
        misconfigurations += len(scan_result.get("Misconfigurations", []) or [])
    return {
        "tool": "trivy",
        "returncode": result["returncode"],
        "vulnerabilities": vulnerabilities,
        "misconfigurations": misconfigurations,
        "release_blocked": vulnerabilities > 0 or misconfigurations > 0,
    }


def run_redteam_unit_checks(*, cwd: Path) -> dict[str, Any]:
    corpus_path = cwd / "data" / "redteam" / "payloads" / "asset-boundary-v0.json"
    payloads = load_red_team_payloads(corpus_path)
    result = run_command(
        [
            "uv",
            "run",
            "python",
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_hardening_gate.py",
        ],
        cwd=cwd,
    )
    return {
        "tool": "unittest-redteam-boundaries",
        "returncode": result["returncode"],
        "matrix": RED_TEAM_BOUNDARY_MATRIX,
        "payload_corpus": red_team_payload_summary(payloads),
        "release_blocked": result["returncode"] != 0,
    }


def run_dependency_check(*, cwd: Path) -> dict[str, Any]:
    result = run_command(["uv", "pip", "check"], cwd=cwd)
    return {
        "tool": "uv-pip-check",
        "returncode": result["returncode"],
        "release_blocked": result["returncode"] != 0,
    }


def run_redteam_tool_readiness(*, cwd: Path) -> dict[str, Any]:
    result = run_command(
        ["uv", "run", "python", "scripts/check_redteam_tool_readiness.py"],
        cwd=cwd,
    )
    payload: dict[str, Any] = {}
    if result["stdout"].strip().startswith("{"):
        payload = json.loads(result["stdout"])
    summary = payload.get("summary", {})
    return {
        "tool": "redteam-tool-readiness",
        "returncode": result["returncode"],
        "summary": summary,
        "report_ref": "data/redteam/exports/tool-readiness.json",
        "release_blocked": result["returncode"] != 0,
    }


def run_promptfoo_redteam_dryrun_validation(*, cwd: Path) -> dict[str, Any]:
    result = run_command(
        ["uv", "run", "python", "scripts/validate_promptfoo_redteam_dryrun.py"],
        cwd=cwd,
    )
    payload: dict[str, Any] = {}
    if result["stdout"].strip().startswith("{"):
        payload = json.loads(result["stdout"])
    return {
        "tool": "promptfoo-redteam-dryrun-contract",
        "returncode": result["returncode"],
        "quality_ok": payload.get("quality_ok", False),
        "report_ref": "data/redteam/exports/promptfoo-redteam-dryrun-validation.json",
        "release_blocked": result["returncode"] != 0,
    }


def write_report(report: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--checks",
        nargs="+",
        choices=[
            "dependency",
            "gitleaks",
            "trivy",
            "redteam",
            "tools",
            "dryrun",
            "all",
        ],
        default=["all"],
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=ROOT / "data" / "receipts" / "hardening" / "latest-hardening-gate.json",
    )
    parser.add_argument(
        "--gitleaks-report-path",
        type=Path,
        default=ROOT / "data" / "receipts" / "hardening" / "latest-gitleaks-redacted.json",
    )
    args = parser.parse_args()

    selected = set(args.checks)
    if "all" in selected:
        selected = {"dependency", "gitleaks", "trivy", "redteam", "tools", "dryrun"}

    checks: list[dict[str, Any]] = []
    if "dependency" in selected:
        checks.append(run_dependency_check(cwd=ROOT))
    if "gitleaks" in selected:
        checks.append(run_gitleaks(cwd=ROOT, report_path=args.gitleaks_report_path))
    if "trivy" in selected:
        checks.append(run_trivy(cwd=ROOT))
    if "redteam" in selected:
        checks.append(run_redteam_unit_checks(cwd=ROOT))
    if "tools" in selected:
        checks.append(run_redteam_tool_readiness(cwd=ROOT))
    if "dryrun" in selected:
        checks.append(run_promptfoo_redteam_dryrun_validation(cwd=ROOT))

    release_blocked = any(bool(item.get("release_blocked")) for item in checks)
    report = {
        "workflow": "finharness_hardening_gate_v1",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "execution_allowed": False,
        "release_blocked": release_blocked,
        "checks": checks,
    }
    write_report(report, args.report_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if release_blocked else 0


if __name__ == "__main__":
    sys.exit(main())
