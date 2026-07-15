"""Render or validate the concise FinHarness pull-request contract."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

ISSUE_BRANCH_RE = re.compile(r"^agent/(?P<issue>[1-9][0-9]*)-[a-z0-9][a-z0-9-]*$")
SECTION_RE = re.compile(r"^## (?P<name>[^\n]+)\n(?P<body>.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
PLACEHOLDER_RE = re.compile(r"(?:TODO|TBD|<[^>]+>|Closes #\s*$)", re.IGNORECASE)
AMBIGUOUS_COMMIT_CLAIM_RE = re.compile(r"\bexact[- ]head\b", re.IGNORECASE)
REQUIRED_SECTIONS = {
    "Issue linkage",
    "Scope",
    "Risk and classification",
    "Validation evidence",
    "Manual safety evidence",
}


class ContractError(RuntimeError):
    """Raised when PR metadata cannot be rendered safely."""


def validate_body(body: str) -> list[str]:
    sections = {match["name"].strip(): match["body"].strip() for match in SECTION_RE.finditer(body)}
    findings = [f"missing section: {name}" for name in sorted(REQUIRED_SECTIONS - set(sections))]
    if findings:
        return findings

    if AMBIGUOUS_COMMIT_CLAIM_RE.search(body):
        findings.append(
            "replace ambiguous `exact-head` language with PR head, merge ref, or "
            "final main commit plus the full SHA"
        )

    if not re.search(r"(?m)^(?:Closes|Refs) #[1-9][0-9]*\s*$", sections["Issue linkage"]):
        findings.append("Issue linkage must contain `Closes #N` or `Refs #N`")
    _require_meaningful(sections, "Scope", findings)
    risk = sections["Risk and classification"]
    if not re.search(r"(?m)^Classification: C[0-3]\s*$", risk):
        findings.append("Risk and classification must contain `Classification: C0` through `C3`")
    if not re.search(r"(?mi)^Risk: (?:low|medium|high|critical)\s*$", risk):
        findings.append("Risk and classification must contain a low/medium/high/critical Risk")
    _require_meaningful(sections, "Validation evidence", findings)
    manual = sections["Manual safety evidence"]
    for label in ("Negative evidence", "Persistence/restart", "Rollback"):
        match = re.search(rf"(?mi)^- {re.escape(label)}:\s*(.+)$", manual)
        if match is None or not _meaningful(match.group(1)):
            findings.append(f"Manual safety evidence needs a reasoned `{label}` value")
    return findings


def _meaningful(value: str) -> bool:
    without_comments = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL).strip()
    return bool(without_comments) and PLACEHOLDER_RE.search(without_comments) is None


def _require_meaningful(sections: dict[str, str], name: str, findings: list[str]) -> None:
    if not _meaningful(sections[name]):
        findings.append(f"{name} must contain non-placeholder evidence")


def render_contract(
    *,
    issue: int,
    scope: str,
    risk: str,
    classification: str,
    validation: list[str],
    negative_evidence: str,
    persistence: str,
    rollback: str,
    changed_files: list[str],
) -> str:
    files = ", ".join(changed_files) if changed_files else "none"
    checks = "\n".join(f"- {item}" for item in validation)
    return f"""## Issue linkage

Closes #{issue}

## Scope

{scope}

Changed files: {files}

## Risk and classification

Classification: {classification}
Risk: {risk}

## Validation evidence

{checks}

## Manual safety evidence

- Negative evidence: {negative_evidence}
- Persistence/restart: {persistence}
- Rollback: {rollback}
"""


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise ContractError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def _derive_issue() -> int:
    branch = _git("branch", "--show-current")
    match = ISSUE_BRANCH_RE.fullmatch(branch)
    if match is None:
        raise ContractError(f"cannot derive issue number from branch: {branch}")
    return int(match.group("issue"))


def _changed_files() -> list[str]:
    output = _git("diff", "--name-only", "origin/main...HEAD")
    return [line for line in output.splitlines() if line]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    render = subparsers.add_parser("render", help="Render a PR body from branch metadata")
    render.add_argument("--issue", type=int)
    render.add_argument("--scope", required=True)
    render.add_argument("--risk", choices=("low", "medium", "high", "critical"), required=True)
    render.add_argument("--classification", choices=("C0", "C1", "C2", "C3"), required=True)
    render.add_argument("--validation", action="append", required=True)
    render.add_argument("--negative-evidence", required=True)
    render.add_argument("--persistence", required=True)
    render.add_argument("--rollback", required=True)
    check = subparsers.add_parser("check", help="Validate a PR body")
    source = check.add_mutually_exclusive_group(required=True)
    source.add_argument("--event", type=Path)
    source.add_argument("--body-file", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "render":
            body = render_contract(
                issue=args.issue or _derive_issue(),
                scope=args.scope,
                risk=args.risk,
                classification=args.classification,
                validation=args.validation,
                negative_evidence=args.negative_evidence,
                persistence=args.persistence,
                rollback=args.rollback,
                changed_files=_changed_files(),
            )
            print(body, end="")
            return 0
        if args.event:
            payload = json.loads(args.event.read_text(encoding="utf-8"))
            body = payload.get("pull_request", {}).get("body") or ""
        else:
            body = args.body_file.read_text(encoding="utf-8")
    except (ContractError, OSError, json.JSONDecodeError) as exc:
        print(f"PR contract error: {exc}")
        return 1

    findings = validate_body(body)
    if findings:
        print("PR contract findings:")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print("PR contract is complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
