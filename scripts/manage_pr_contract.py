"""Render or inspect an optional concise pull-request summary."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

SECTION_RE = re.compile(r"^## (?P<name>[^\n]+)\n(?P<body>.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)


class SummaryError(RuntimeError):
    """Raised when optional PR metadata cannot be loaded or rendered."""


def _meaningful(value: str) -> bool:
    without_comments = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL).strip()
    return bool(without_comments)


def validate_body(body: str) -> list[str]:
    """Return advisory findings; PR prose never blocks a candidate."""
    if not _meaningful(body):
        return ["pull-request body has no human-readable summary"]

    sections = {match["name"].strip(): match["body"].strip() for match in SECTION_RE.finditer(body)}
    findings: list[str] = []
    summary = sections.get("Summary") or sections.get("Scope") or ""
    validation = sections.get("Validation") or sections.get("Validation evidence") or ""
    if not _meaningful(summary):
        findings.append("summary is empty")
    if not _meaningful(validation):
        findings.append("validation is not recorded")
    return findings


def render_contract(
    *,
    scope: str,
    validation: list[str],
    changed_files: list[str],
    consequences: str | None = None,
    issue: int | None = None,
    risk: str | None = None,
    classification: str | None = None,
    negative_evidence: str | None = None,
    persistence: str | None = None,
    rollback: str | None = None,
) -> str:
    """Render the new summary while accepting the former caller signature."""
    del issue, risk, classification
    files = ", ".join(changed_files) if changed_files else "none"
    checks = "\n".join(f"- {item}" for item in validation) or "- Not recorded."
    if consequences is None:
        legacy = [item for item in (negative_evidence, persistence, rollback) if item]
        consequences = "\n".join(f"- {item}" for item in legacy)
    if not consequences:
        consequences = "N/A — no persistent or external consequence recorded."
    return f"""## Summary

{scope}

Changed files: {files}

## Validation

{checks}

## Consequences and recovery

{consequences}
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
        raise SummaryError(f"git {' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def _changed_files() -> list[str]:
    output = _git("diff", "--name-only", "origin/main...HEAD")
    return [line for line in output.splitlines() if line]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    render = subparsers.add_parser("render", help="Render an optional concise PR summary")
    render.add_argument("--scope", required=True)
    render.add_argument("--validation", action="append", default=[])
    render.add_argument("--consequences")
    for name in (
        "--issue",
        "--risk",
        "--classification",
        "--negative-evidence",
        "--persistence",
        "--rollback",
    ):
        render.add_argument(name, help=argparse.SUPPRESS)

    check = subparsers.add_parser("check", help="Report advisory PR-summary findings")
    source = check.add_mutually_exclusive_group(required=True)
    source.add_argument("--event", type=Path)
    source.add_argument("--body-file", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.command == "render":
            body = render_contract(
                scope=args.scope,
                validation=args.validation,
                consequences=args.consequences,
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
    except (SummaryError, OSError, json.JSONDecodeError) as exc:
        print(f"PR summary inspection error: {exc}")
        return 2

    findings = validate_body(body)
    if findings:
        print("PR summary advisory findings:")
        for finding in findings:
            print(f"  - {finding}")
    else:
        print("PR summary is readable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
