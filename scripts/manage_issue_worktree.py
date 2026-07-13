"""Manage the serial FinHarness issue branch and worktree lifecycle."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ISSUE_BRANCH_RE = re.compile(r"^agent/(?P<issue>[1-9][0-9]*)-(?P<slug>[a-z0-9][a-z0-9-]*)$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


class LifecycleError(RuntimeError):
    """Raised when a lifecycle command would be ambiguous or unsafe."""


@dataclass(frozen=True)
class WorktreeRecord:
    path: Path
    head: str
    branch: str | None
    prunable: bool = False


@dataclass(frozen=True)
class PullRequestState:
    number: int
    state: str
    head_oid: str
    url: str


@dataclass(frozen=True)
class IssueState:
    number: int
    state: str
    title: str
    url: str


Runner = Callable[[list[str], Path], str]


def run(command: list[str], cwd: Path) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise LifecycleError(f"command failed ({' '.join(command)}): {detail}")
    return completed.stdout


def parse_worktrees(raw: str) -> list[WorktreeRecord]:
    records: list[WorktreeRecord] = []
    fields: dict[str, str] = {}
    flags: set[str] = set()

    def flush() -> None:
        if not fields:
            return
        branch_ref = fields.get("branch")
        branch = branch_ref.removeprefix("refs/heads/") if branch_ref else None
        records.append(
            WorktreeRecord(
                path=Path(fields["worktree"]).resolve(),
                head=fields.get("HEAD", ""),
                branch=branch,
                prunable="prunable" in flags or "prunable" in fields,
            )
        )
        fields.clear()
        flags.clear()

    for line in [*raw.splitlines(), ""]:
        if not line:
            flush()
            continue
        key, separator, value = line.partition(" ")
        if separator:
            fields[key] = value
        else:
            flags.add(key)
    return records


def load_worktrees(cwd: Path, *, runner: Runner = run) -> list[WorktreeRecord]:
    return parse_worktrees(runner(["git", "worktree", "list", "--porcelain"], cwd))


def main_worktree(records: list[WorktreeRecord]) -> WorktreeRecord:
    matches = [record for record in records if record.branch == "main" and not record.prunable]
    if len(matches) != 1:
        raise LifecycleError(f"expected exactly one active main worktree, found {len(matches)}")
    return matches[0]


def issue_worktree(records: list[WorktreeRecord], issue: int) -> WorktreeRecord:
    matches = []
    for record in records:
        if record.branch is None:
            continue
        match = ISSUE_BRANCH_RE.fullmatch(record.branch)
        if match and int(match.group("issue")) == issue:
            matches.append(record)
    if len(matches) != 1:
        raise LifecycleError(
            f"expected exactly one worktree for issue #{issue}, found {len(matches)}"
        )
    return matches[0]


def expected_names(main: WorktreeRecord, issue: int, slug: str) -> tuple[str, Path]:
    if issue < 1:
        raise LifecycleError("issue number must be positive")
    if not SLUG_RE.fullmatch(slug):
        raise LifecycleError("slug must contain lowercase letters, digits, and hyphens only")
    branch = f"agent/{issue}-{slug}"
    path = main.path.with_name(f"{main.path.name}-{issue}")
    return branch, path


def load_issue(main: Path, issue: int, *, runner: Runner = run) -> IssueState:
    raw = runner(
        ["gh", "issue", "view", str(issue), "--json", "number,state,title,url"],
        main,
    )
    payload = json.loads(raw)
    return IssueState(
        number=int(payload["number"]),
        state=str(payload["state"]),
        title=str(payload["title"]),
        url=str(payload["url"]),
    )


def load_merged_pr(main: Path, branch: str, *, runner: Runner = run) -> PullRequestState:
    raw = runner(
        [
            "gh",
            "pr",
            "list",
            "--head",
            branch,
            "--state",
            "merged",
            "--limit",
            "2",
            "--json",
            "number,state,headRefOid,url",
        ],
        main,
    )
    payload: list[dict[str, Any]] = json.loads(raw)
    if len(payload) != 1:
        raise LifecycleError(f"expected one merged PR for {branch}, found {len(payload)}")
    item = payload[0]
    return PullRequestState(
        number=int(item["number"]),
        state=str(item["state"]),
        head_oid=str(item["headRefOid"]),
        url=str(item["url"]),
    )


def validate_numbering(record: WorktreeRecord, issue: int, main: WorktreeRecord) -> list[str]:
    findings: list[str] = []
    expected_path = main.path.with_name(f"{main.path.name}-{issue}")
    if record.path != expected_path:
        findings.append(f"worktree path mismatch: expected {expected_path}, found {record.path}")
    if record.branch is None:
        findings.append("worktree has no branch")
    else:
        match = ISSUE_BRANCH_RE.fullmatch(record.branch)
        if match is None or int(match.group("issue")) != issue:
            findings.append(f"branch does not match issue #{issue}: {record.branch}")
    if record.prunable:
        findings.append("worktree metadata is prunable")
    return findings


def dirty_paths(record: WorktreeRecord, *, runner: Runner = run) -> list[str]:
    raw = runner(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        record.path,
    )
    return [line for line in raw.splitlines() if line]


def start_issue(
    cwd: Path,
    issue: int,
    slug: str,
    *,
    runner: Runner = run,
) -> dict[str, object]:
    records = load_worktrees(cwd, runner=runner)
    main = main_worktree(records)
    state = load_issue(main.path, issue, runner=runner)
    if state.state != "OPEN":
        raise LifecycleError(f"issue #{issue} is not open: {state.state}")
    branch, path = expected_names(main, issue, slug)
    if any(record.branch == branch for record in records):
        raise LifecycleError(f"branch is already checked out: {branch}")
    if any(record.path == path for record in records) or path.exists():
        raise LifecycleError(f"worktree path already exists: {path}")
    runner(["git", "fetch", "origin", "--prune"], main.path)
    runner(
        ["git", "worktree", "add", "-b", branch, str(path), "origin/main"],
        main.path,
    )
    return {"action": "created", "issue": issue, "branch": branch, "path": str(path)}


def finish_issue(
    cwd: Path,
    issue: int,
    *,
    apply: bool,
    runner: Runner = run,
) -> dict[str, object]:
    records = load_worktrees(cwd, runner=runner)
    main = main_worktree(records)
    record = issue_worktree(records, issue)
    findings = validate_numbering(record, issue, main)
    dirty = (
        []
        if record.prunable or not record.path.exists()
        else dirty_paths(record, runner=runner)
    )
    if dirty:
        findings.append(f"worktree is dirty ({len(dirty)} path(s))")
    state = load_issue(main.path, issue, runner=runner)
    if state.state != "CLOSED":
        findings.append(f"issue #{issue} is not closed: {state.state}")
    if record.branch is None:
        findings.append("worktree branch is unavailable")
        pr = None
    else:
        pr = load_merged_pr(main.path, record.branch, runner=runner)
        if pr.state != "MERGED":
            findings.append(f"PR #{pr.number} is not merged: {pr.state}")
        if pr.head_oid != record.head:
            findings.append(
                f"local head differs from merged PR head: {record.head} != {pr.head_oid}"
            )
    if findings:
        raise LifecycleError("; ".join(findings))

    plan = [
        ["git", "worktree", "remove", str(record.path)],
        ["git", "branch", "-D", str(record.branch)],
        ["git", "worktree", "prune"],
    ]
    if apply:
        for command in plan:
            runner(command, main.path)
    return {
        "action": "cleaned" if apply else "preview",
        "issue": issue,
        "pr": pr.number if pr else None,
        "branch": record.branch,
        "path": str(record.path),
        "commands": plan,
    }


def status_report(cwd: Path, issue: int | None, *, runner: Runner = run) -> dict[str, object]:
    records = load_worktrees(cwd, runner=runner)
    main = main_worktree(records)
    selected = records
    if issue is not None:
        selected = [issue_worktree(records, issue)]
    items: list[dict[str, object]] = []
    for record in selected:
        match = ISSUE_BRANCH_RE.fullmatch(record.branch or "")
        record_issue = int(match.group("issue")) if match else None
        findings = (
            validate_numbering(record, record_issue, main)
            if record_issue is not None
            else ([] if record.branch == "main" else ["not a numbered issue branch"])
        )
        dirty = (
            []
            if record.prunable or not record.path.exists()
            else dirty_paths(record, runner=runner)
        )
        if dirty:
            findings.append(f"dirty ({len(dirty)} path(s))")
        items.append(
            {
                "path": str(record.path),
                "branch": record.branch,
                "head": record.head,
                "issue": record_issue,
                "ok": not findings,
                "findings": findings,
            }
        )
    return {"main": str(main.path), "ok": all(item["ok"] for item in items), "worktrees": items}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start", help="Create an issue worktree")
    start.add_argument("issue", type=int)
    start.add_argument("--slug", required=True)
    status = subparsers.add_parser("status", help="Audit issue worktrees")
    status.add_argument("issue", nargs="?", type=int)
    finish = subparsers.add_parser("finish", help="Safely clean a merged issue worktree")
    finish.add_argument("issue", type=int)
    finish.add_argument("--apply", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        cwd = Path.cwd().resolve()
        if args.command == "start":
            report = start_issue(cwd, args.issue, args.slug)
        elif args.command == "status":
            report = status_report(cwd, args.issue)
        else:
            report = finish_issue(cwd, args.issue, apply=args.apply)
    except LifecycleError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2))
        return 1
    print(json.dumps({"ok": True, **report}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
