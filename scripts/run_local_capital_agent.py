#!/usr/bin/env python3
"""Run one bounded read-only Capital World audit over the local StateCore."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from finharness.agent_work_loop import (
    AgentWorkRequest,
    AgentWorkToolRequest,
    run_agent_work_loop,
)
from finharness.capital_world_audit import (
    CapitalWorldAudit,
    build_capital_world_audit,
    load_tool_envelopes_from_artifacts,
    normalized_audit_contract,
)
from finharness.config import load_settings
from finharness.openai_capital_audit_port import run_openai_capital_world_audit
from finharness.project_paths import ROOT
from finharness.statecore.receipt_index import DEFAULT_RECEIPT_ROOT
from finharness.statecore.store import (
    DEFAULT_STATE_CORE_DB_PATH,
    STATE_CORE_DB_ENV_VAR,
)

try:
    from scripts.run_capital_readonly_dogfood import logical_sqlite_digest
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    from run_capital_readonly_dogfood import logical_sqlite_digest

SCHEMA = "finharness.local_capital_agent_run.v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def receipt_tree_manifest(root: Path) -> dict[str, str]:
    """Hash domain receipt JSON files without following symlinks."""
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*.json"))
        if path.is_file() and not path.is_symlink()
    }


@contextmanager
def _state_core_environment(path: Path) -> Iterator[None]:
    previous = os.environ.get(STATE_CORE_DB_ENV_VAR)
    os.environ[STATE_CORE_DB_ENV_VAR] = str(path)
    load_settings.cache_clear()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(STATE_CORE_DB_ENV_VAR, None)
        else:
            os.environ[STATE_CORE_DB_ENV_VAR] = previous
        load_settings.cache_clear()


def default_output_root(now: datetime | None = None) -> Path:
    observed = (now or datetime.now(UTC)).astimezone(UTC)
    stamp = observed.strftime("%Y%m%dT%H%M%S%fZ")
    return ROOT / ".artifacts" / "agent-runs" / stamp


def run_local_capital_agent(
    *,
    state_db: Path,
    output_root: Path,
    domain_receipt_root: Path = DEFAULT_RECEIPT_ROOT,
) -> dict[str, Any]:
    state_db = state_db.resolve()
    if not state_db.is_file():
        raise RuntimeError(f"StateCore database does not exist: {state_db}")
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    db_digest_before = logical_sqlite_digest(state_db)
    domain_receipts_before = receipt_tree_manifest(domain_receipt_root)
    with _state_core_environment(state_db):
        work_result = run_agent_work_loop(
            request=AgentWorkRequest(
                goal="Audit the current FinHarness Capital World without changing it",
                profile_name="default",
                objective=(
                    "Separate observed facts, inferences, unsupported claims, blockers, "
                    "counter-evidence, and semantic stop conditions"
                ),
                work_type="evidence_triage",
                receipt_root=str(output_root),
                tool_requests=[
                    AgentWorkToolRequest(
                        tool_name="get_capital_context_projection",
                        arguments={"open_proposals_limit": 5},
                    )
                ],
                max_steps=4,
                max_tool_calls=2,
            )
        )

    db_digest_after = logical_sqlite_digest(state_db)
    domain_receipts_after = receipt_tree_manifest(domain_receipt_root)
    if db_digest_before != db_digest_after:
        raise RuntimeError("read-only Agent changed the logical StateCore digest")
    if domain_receipts_before != domain_receipts_after:
        raise RuntimeError("read-only Agent changed domain receipts")
    if not work_result.capital_world_audit_ref:
        raise RuntimeError("Agent Work Loop omitted CapitalWorldAudit")

    audit_path = output_root / work_result.capital_world_audit_ref
    audit = CapitalWorldAudit.model_validate_json(audit_path.read_text(encoding="utf-8"))
    replay_envelopes = load_tool_envelopes_from_artifacts(
        receipt_root=output_root,
        artifact_refs=work_result.tool_result_refs,
    )
    replay = build_capital_world_audit(
        goal=work_result.goal,
        tool_envelopes=replay_envelopes,
    )
    replay_equal = normalized_audit_contract(audit) == normalized_audit_contract(replay)
    if not replay_equal:
        raise RuntimeError("persisted tool artifacts do not replay the same audit contract")

    model_attempt = run_openai_capital_world_audit(audit)
    if model_attempt.status == "rejected":
        raise RuntimeError(
            "configured model failed deterministic audit invariants: "
            + ",".join(model_attempt.findings)
        )
    tool_artifacts = [
        json.loads((output_root / ref).read_text(encoding="utf-8"))
        for ref in work_result.tool_result_refs
    ]
    all_read_only = all(item.get("side_effect") == "read" for item in tool_artifacts)
    if not all_read_only:
        raise RuntimeError("local Capital Agent dispatched a non-read tool")
    if work_result.execution_allowed or audit.execution_allowed:
        raise RuntimeError("local Capital Agent crossed the execution boundary")

    return {
        "schema": SCHEMA,
        "state_core": {
            "path": str(state_db),
            "logical_digest_before": db_digest_before,
            "logical_digest_after": db_digest_after,
            "logical_digest_unchanged": db_digest_before == db_digest_after,
        },
        "domain_receipts": {
            "root": str(domain_receipt_root.resolve()),
            "unchanged": domain_receipts_before == domain_receipts_after,
            "file_count": len(domain_receipts_after),
        },
        "work": {
            "work_id": work_result.work_id,
            "outcome": work_result.outcome,
            "stop_reason": work_result.stop_reason,
            "audit_ref": work_result.capital_world_audit_ref,
            "audit_disposition": work_result.audit_disposition,
            "tool_result_refs": work_result.tool_result_refs,
            "all_tool_side_effects_read": all_read_only,
        },
        "audit": {
            "world_id": audit.world_id,
            "basis_digest": audit.basis_digest,
            "world_status": audit.world_status,
            "disposition": audit.disposition,
            "observed_count": len(audit.observed),
            "inferred_count": len(audit.inferred),
            "unsupported_count": len(audit.unsupported),
            "blockers": audit.blockers,
            "data_gaps": audit.data_gaps,
            "stop_conditions": audit.stop_conditions,
            "required_evaluations": audit.required_evaluations,
        },
        "hermetic_replay": {
            "same_typed_contract": replay_equal,
            "replay_audit_id": replay.audit_id,
        },
        "real_model": model_attempt.model_dump(mode="json"),
        "output_root": str(output_root),
        "execution_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-db", type=Path, default=DEFAULT_STATE_CORE_DB_PATH)
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--domain-receipt-root", type=Path, default=DEFAULT_RECEIPT_ROOT)
    args = parser.parse_args()
    result = run_local_capital_agent(
        state_db=args.state_db,
        output_root=args.output_root or default_output_root(),
        domain_receipt_root=args.domain_receipt_root,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
