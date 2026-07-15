"""Verify and record the exact commit identity exercised by a CI job."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Literal

SCHEMA = "finharness.ci_commit_identity.v1"
DEFAULT_OUTPUT = Path(".artifacts/ci-commit-identity.json")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
MERGE_REF_RE = re.compile(r"^refs/pull/[1-9][0-9]*/merge$")
Claim = Literal["pr_head", "merge_ref", "main_commit"]


@dataclass(frozen=True)
class CIContext:
    repository: str
    event_name: str
    github_ref: str
    github_sha: str
    event: Mapping[str, Any]


class IdentityError(RuntimeError):
    """Raised when the checked-out commit does not satisfy the declared claim."""


def _require_sha(value: str, label: str) -> str:
    stripped = value.strip()
    normalized = stripped.lower()
    if stripped != normalized or SHA_RE.fullmatch(normalized) is None:
        raise IdentityError(f"{label} must be a full lowercase commit SHA")
    return normalized


def _pull_request(context: CIContext) -> Mapping[str, Any]:
    value = context.event.get("pull_request")
    if not isinstance(value, Mapping):
        raise IdentityError("pull_request event payload is required")
    return value


def _nested_sha(value: Mapping[str, Any], key: str) -> str:
    nested = value.get(key)
    if not isinstance(nested, Mapping) or not isinstance(nested.get("sha"), str):
        raise IdentityError(f"pull_request.{key}.sha is required")
    return _require_sha(str(nested["sha"]), f"pull_request.{key}.sha")


def _verify_pull_request_claim(
    *,
    claim: Literal["pr_head", "merge_ref"],
    checked: str,
    expected: str,
    github_sha: str,
    context: CIContext,
    errors: list[str],
) -> tuple[str | None, str | None]:
    if context.event_name != "pull_request":
        errors.append(f"{claim} requires a pull_request event")
        return None, None

    pull_request = _pull_request(context)
    pr_head_sha = _nested_sha(pull_request, "head")
    raw_merge_sha = pull_request.get("merge_commit_sha")
    merge_sha = (
        raw_merge_sha.lower()
        if isinstance(raw_merge_sha, str) and SHA_RE.fullmatch(raw_merge_sha.lower())
        else None
    )
    if claim == "pr_head":
        if expected != pr_head_sha:
            errors.append("expected SHA is not pull_request.head.sha")
        if github_sha != pr_head_sha and checked == github_sha:
            errors.append("PR-head proof checked out the synthetic merge-ref SHA")
        return pr_head_sha, merge_sha

    if MERGE_REF_RE.fullmatch(context.github_ref) is None:
        errors.append("merge-ref proof requires refs/pull/<number>/merge")
    if expected != github_sha:
        errors.append("merge-ref expected SHA is not GITHUB_SHA")
    if pr_head_sha == checked:
        errors.append("merge-ref proof checked out the PR-head SHA")
    return pr_head_sha, merge_sha


def _verify_main_claim(
    *,
    expected: str,
    github_sha: str,
    context: CIContext,
    errors: list[str],
) -> None:
    if context.event_name != "push":
        errors.append("main_commit requires a push event")
    if context.github_ref != "refs/heads/main":
        errors.append("main_commit requires refs/heads/main")
    if expected != github_sha:
        errors.append("main-commit expected SHA is not GITHUB_SHA")
    event_after = context.event.get("after")
    if not isinstance(event_after, str) or event_after.lower() != expected:
        errors.append("main-commit expected SHA is not the push event after SHA")


def verify_identity(
    *,
    claim: Claim,
    checked_out_sha: str,
    expected_sha: str,
    context: CIContext,
    command: str,
) -> dict[str, Any]:
    checked = _require_sha(checked_out_sha, "checked-out SHA")
    expected = _require_sha(expected_sha, "expected SHA")
    github_sha = _require_sha(context.github_sha, "GITHUB_SHA")
    errors: list[str] = []
    pr_head_sha: str | None = None
    merge_sha: str | None = None

    if checked != expected:
        errors.append(f"checked-out SHA {checked} does not equal expected SHA {expected}")

    if claim in {"pr_head", "merge_ref"}:
        pr_head_sha, merge_sha = _verify_pull_request_claim(
            claim=claim,
            checked=checked,
            expected=expected,
            github_sha=github_sha,
            context=context,
            errors=errors,
        )
    elif claim == "main_commit":
        _verify_main_claim(
            expected=expected,
            github_sha=github_sha,
            context=context,
            errors=errors,
        )
    else:  # pragma: no cover - argparse and typing constrain this branch.
        errors.append(f"unsupported claim: {claim}")

    return {
        "schema": SCHEMA,
        "claim": claim,
        "repository": context.repository,
        "commit_sha": checked,
        "expected_sha": expected,
        "ref_type": claim,
        "event_name": context.event_name,
        "github_ref": context.github_ref,
        "github_sha": github_sha,
        "pull_request_head_sha": pr_head_sha,
        "pull_request_merge_sha": merge_sha,
        "pull_request_merge_sha_matches_github_sha": (
            merge_sha == github_sha if merge_sha is not None else None
        ),
        "command": command,
        "result": "passed" if not errors else "failed",
        "errors": errors,
    }


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
        temp_path.replace(path)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise


def _git_head() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise IdentityError(f"git rev-parse HEAD failed: {detail}")
    return completed.stdout.strip()


def _load_context(env: Mapping[str, str]) -> CIContext:
    event_path = Path(env.get("GITHUB_EVENT_PATH", ""))
    if not event_path.is_file():
        raise IdentityError("GITHUB_EVENT_PATH must identify a readable event payload")
    try:
        event = json.loads(event_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IdentityError(f"cannot load GitHub event payload: {exc}") from exc
    if not isinstance(event, Mapping):
        raise IdentityError("GitHub event payload must be an object")
    return CIContext(
        repository=env.get("GITHUB_REPOSITORY", ""),
        event_name=env.get("GITHUB_EVENT_NAME", ""),
        github_ref=env.get("GITHUB_REF", ""),
        github_sha=env.get("GITHUB_SHA", ""),
        event=event,
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claim", choices=("pr_head", "merge_ref", "main_commit"), required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    payload: dict[str, Any]
    try:
        context = _load_context(os.environ)
        payload = verify_identity(
            claim=args.claim,
            checked_out_sha=_git_head(),
            expected_sha=args.expected_sha,
            context=context,
            command=args.command,
        )
    except IdentityError as exc:
        payload = {
            "schema": SCHEMA,
            "claim": args.claim,
            "repository": os.environ.get("GITHUB_REPOSITORY", ""),
            "commit_sha": "",
            "expected_sha": args.expected_sha,
            "ref_type": args.claim,
            "event_name": os.environ.get("GITHUB_EVENT_NAME", ""),
            "github_ref": os.environ.get("GITHUB_REF", ""),
            "github_sha": os.environ.get("GITHUB_SHA", ""),
            "pull_request_head_sha": None,
            "pull_request_merge_sha": None,
            "pull_request_merge_sha_matches_github_sha": None,
            "command": args.command,
            "result": "failed",
            "errors": [str(exc)],
        }
    _atomic_write_json(args.output, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["result"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
