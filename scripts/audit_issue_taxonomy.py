"""Audit open GitHub Issues for canonical backlog taxonomy cardinality."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Sequence
from typing import Any

TAXONOMY = {
    "plane": frozenset(
        {
            "plane:truth",
            "plane:knowledge",
            "plane:judgment",
            "plane:control",
            "plane:agent",
            "plane:action-learning",
            "plane:product",
            "plane:assurance",
        }
    ),
    "kind": frozenset(
        {
            "type:adr",
            "type:containment",
            "type:deferred-gate",
            "type:experiment",
            "type:feature",
            "type:integration",
            "type:migration",
            "type:product-validation",
            "type:program",
            "type:research",
        }
    ),
    "lifecycle": frozenset(
        {
            "status:active",
            "status:dormant",
            "status:deferred",
            "status:temporary",
        }
    ),
}
PREFIXES = {"plane": "plane:", "kind": "type:", "lifecycle": "status:"}


class IssueAuditError(RuntimeError):
    """Raised when GitHub Issue truth cannot be loaded."""


def _label_names(issue: dict[str, Any]) -> set[str]:
    labels = issue.get("labels", [])
    return {str(label.get("name", "") if isinstance(label, dict) else label) for label in labels}


def validate_issues(issues: Sequence[dict[str, Any]]) -> list[str]:
    """Return deterministic findings for missing, multiple, or unknown labels."""
    findings: list[str] = []
    for issue in sorted(issues, key=lambda item: int(item["number"])):
        number = int(issue["number"])
        labels = _label_names(issue)
        for dimension, allowed in TAXONOMY.items():
            selected = sorted(label for label in labels if label.startswith(PREFIXES[dimension]))
            if len(selected) != 1:
                findings.append(
                    f"#{number} {dimension}: expected exactly one label, "
                    f"found {len(selected)} ({', '.join(selected) or 'none'})"
                )
            elif selected[0] not in allowed:
                findings.append(f"#{number} {dimension}: unknown label {selected[0]}")
    return findings


def load_open_issues(repository: str | None = None) -> list[dict[str, Any]]:
    """Load live open-Issue metadata through the repository-native GitHub CLI."""
    command = [
        "gh",
        "issue",
        "list",
        "--state",
        "open",
        "--limit",
        "1000",
        "--json",
        "number,title,labels",
    ]
    if repository:
        command.extend(("--repo", repository))
    completed = subprocess.run(command, check=False, capture_output=True, text=True)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise IssueAuditError(f"failed to load GitHub Issue truth: {detail}")
    payload = json.loads(completed.stdout)
    if not isinstance(payload, list):
        raise IssueAuditError("GitHub Issue truth must be a JSON list")
    return payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit open Issues for one plane, kind, and lifecycle label."
    )
    parser.add_argument("--repo", help="GitHub OWNER/REPO; defaults to the current checkout")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        issues = load_open_issues(args.repo)
    except (IssueAuditError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 2
    findings = validate_issues(issues)
    print(
        json.dumps(
            {
                "schema": "finharness.issue_taxonomy_audit.v1",
                "repository": args.repo or "current-checkout",
                "open_issue_count": len(issues),
                "finding_count": len(findings),
                "findings": findings,
                "ok": not findings,
            },
            indent=2,
        )
    )
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
