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
    build_hardening_gate_report,
    classify_gitleaks_findings,
    load_red_team_payloads,
    red_team_payload_summary,
    summarize_findings,
    summarize_pip_audit_results,
    summarize_trivy_results,
)
from finharness.project_paths import ROOT

COMMAND_TIMEOUT_SECONDS = 120.0


def run_command(
    command: list[str],
    *,
    cwd: Path,
    timeout_seconds: float = COMMAND_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    env = os.environ.copy()
    src_path = str(cwd / "src")
    env["PYTHONPATH"] = (
        src_path
        if not env.get("PYTHONPATH")
        else f"{src_path}{os.pathsep}{env['PYTHONPATH']}"
    )
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        return {
            "command": command,
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc),
            "tool_missing": True,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "returncode": 124,
            "stdout": str(exc.output or ""),
            "stderr": f"command timed out after {timeout_seconds} seconds",
            "tool_missing": False,
            "timed_out": True,
        }
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "tool_missing": False,
        "timed_out": False,
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
    scanner_error = (
        bool(result.get("tool_missing"))
        or bool(result.get("timed_out"))
        or int(result["returncode"]) not in {0, 1}
    )
    return {
        "tool": "gitleaks",
        "returncode": result["returncode"],
        "tool_missing": result.get("tool_missing", False),
        "timed_out": result.get("timed_out", False),
        "scanner_error": scanner_error,
        "summary": summary.as_dict(),
        "release_blocked": scanner_error or summary.release_blocked,
        "finding_rules": sorted({item.rule_id for item in classified}),
        "blocking_files": sorted(
            {item.file for item in classified if item.bucket == "project_blocking"}
        ),
        "warning_files_sample": sorted(
            {item.file for item in classified if item.bucket != "project_blocking"}
        )[:25],
        "raw_report_ref": str(report_path),
    }


def run_trivy(*, cwd: Path, report_path: Path) -> dict[str, Any]:
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
    summary = summarize_trivy_results(payload)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    vulnerabilities = int(summary["vulnerability_count"])
    misconfigurations = int(summary["misconfiguration_count"])
    scanner_error = (
        bool(result.get("tool_missing"))
        or bool(result.get("timed_out"))
        or int(result["returncode"]) != 0
    )
    return {
        "tool": "trivy",
        "returncode": result["returncode"],
        "tool_missing": result.get("tool_missing", False),
        "timed_out": result.get("timed_out", False),
        "scanner_error": scanner_error,
        "vulnerabilities": vulnerabilities,
        "misconfigurations": misconfigurations,
        "summary_ref": str(report_path),
        "release_blocked": scanner_error or vulnerabilities > 0 or misconfigurations > 0,
    }


def run_pip_audit(*, cwd: Path, report_path: Path) -> dict[str, Any]:
    """Audit installed project dependencies for known advisories via pip-audit.

    pip-audit needs network access to its advisory backend. Fail-closed: a
    missing tool, a timeout, an unexpected return code, or unparseable output all
    block the release rather than passing silently.
    """
    result = run_command(
        [
            "uv",
            "run",
            "--with",
            "pip-audit",
            "pip-audit",
            "--format",
            "json",
            "--progress-spinner",
            "off",
        ],
        cwd=cwd,
    )
    payload: dict[str, Any] = {}
    parsed_ok = False
    stdout = result["stdout"].strip()
    if stdout.startswith("{"):
        try:
            payload = json.loads(stdout)
            parsed_ok = True
        except json.JSONDecodeError:
            parsed_ok = False
    summary = summarize_pip_audit_results(payload)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    vulnerable_packages = int(summary["vulnerable_package_count"])
    # pip-audit exits 0 when clean and 1 when advisories are found; anything else
    # (or unparseable output) means the scanner itself did not run cleanly.
    scanner_error = (
        bool(result.get("tool_missing"))
        or bool(result.get("timed_out"))
        or not parsed_ok
        or int(result["returncode"]) not in {0, 1}
    )
    return {
        "tool": "pip-audit",
        "returncode": result["returncode"],
        "tool_missing": result.get("tool_missing", False),
        "timed_out": result.get("timed_out", False),
        "scanner_error": scanner_error,
        "vulnerability_count": int(summary["vulnerability_count"]),
        "vulnerable_packages": vulnerable_packages,
        "summary_ref": str(report_path),
        "release_blocked": scanner_error or vulnerable_packages > 0,
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
        "tool_missing": result.get("tool_missing", False),
        "timed_out": result.get("timed_out", False),
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
            "pip-audit",
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
    parser.add_argument(
        "--trivy-report-path",
        type=Path,
        default=ROOT / "data" / "receipts" / "hardening" / "latest-trivy-summary.json",
    )
    parser.add_argument(
        "--pip-audit-report-path",
        type=Path,
        default=ROOT / "data" / "receipts" / "hardening" / "latest-pip-audit-summary.json",
    )
    args = parser.parse_args()

    selected = set(args.checks)
    # pip-audit is intentionally NOT part of "all": it needs network access to its
    # advisory backend, so it stays an explicit opt-in check to keep the default
    # gate (task hardening:gate / security:scan) deterministic and offline-safe.
    if "all" in selected:
        selected = {"dependency", "gitleaks", "trivy", "redteam", "tools", "dryrun"}

    checks: list[dict[str, Any]] = []
    if "dependency" in selected:
        checks.append(run_dependency_check(cwd=ROOT))
    if "gitleaks" in selected:
        checks.append(run_gitleaks(cwd=ROOT, report_path=args.gitleaks_report_path))
    if "trivy" in selected:
        checks.append(run_trivy(cwd=ROOT, report_path=args.trivy_report_path))
    if "pip-audit" in selected:
        checks.append(run_pip_audit(cwd=ROOT, report_path=args.pip_audit_report_path))
    if "redteam" in selected:
        checks.append(run_redteam_unit_checks(cwd=ROOT))
    if "tools" in selected:
        checks.append(run_redteam_tool_readiness(cwd=ROOT))
    if "dryrun" in selected:
        checks.append(run_promptfoo_redteam_dryrun_validation(cwd=ROOT))

    report = build_hardening_gate_report(
        checks=checks,
        generated_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    write_report(report, args.report_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["release_blocked"] else 0


if __name__ == "__main__":
    sys.exit(main())
