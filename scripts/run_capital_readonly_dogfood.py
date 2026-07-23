#!/usr/bin/env python3
"""Run one read-only Capital World Agent dogfood over pinned Federal Reserve SCF data."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.run_scf_capital_dogfood import (
        SCF_CITATION,
        SCF_SHA256,
        SCF_URL,
        load_scf_rows,
        select_household,
        write_finharness_export,
    )
except ModuleNotFoundError:  # Direct ``python scripts/...`` execution.
    from run_scf_capital_dogfood import (
        SCF_CITATION,
        SCF_SHA256,
        SCF_URL,
        load_scf_rows,
        select_household,
        write_finharness_export,
    )

from finharness.agent_work_loop import AgentWorkRequest, AgentWorkToolRequest, run_agent_work_loop
from finharness.capital_world_audit import (
    CapitalWorldAudit,
    build_capital_world_audit,
    load_tool_envelopes_from_artifacts,
    normalized_audit_contract,
)
from finharness.config import load_settings
from finharness.openai_capital_audit_port import run_openai_capital_world_audit
from finharness.personal_finance import ingest_personal_finance_export
from finharness.statecore.store import STATE_CORE_DB_ENV_VAR, init_state_core

SCHEMA = "finharness.capital_readonly_dogfood.v1"


def _download(destination: Path) -> None:
    request = urllib.request.Request(  # noqa: S310 - pinned Federal Reserve HTTPS URL
        SCF_URL,
        headers={"User-Agent": "FinHarness/capital-readonly-dogfood"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        destination.write_bytes(response.read())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_archive(path: Path, expected_sha256: str) -> str:
    digest = _sha256(path)
    if digest != expected_sha256:
        raise RuntimeError(f"SCF archive digest mismatch: {digest}")
    return digest


SQLITE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _sqlite_identifier(value: str) -> str:
    if not SQLITE_IDENTIFIER.fullmatch(value):
        raise RuntimeError(f"unsafe SQLite identifier: {value!r}")
    return value


def _json_value(value: object) -> object:
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    return value


def logical_sqlite_digest(path: Path) -> str:
    """Hash sorted logical rows, excluding SQLite implementation metadata."""
    connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        table_names = [
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        material: list[dict[str, object]] = []
        for table in table_names:
            quoted = _sqlite_identifier(table)
            columns = [
                str(row[1])
                for row in connection.execute(f'PRAGMA table_info("{quoted}")')
            ]
            rows = [
                [_json_value(value) for value in row]
                # Table names come only from sqlite_master and pass a strict
                # identifier allowlist; SQLite cannot bind identifiers.
                for row in connection.execute(
                    f'SELECT * FROM "{quoted}"'  # noqa: S608
                )
            ]
            rows.sort(key=lambda row: json.dumps(row, sort_keys=True, default=str))
            material.append({"table": table, "columns": columns, "rows": rows})
    finally:
        connection.close()
    encoded = json.dumps(
        material,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def receipt_manifest(root: Path) -> dict[str, str]:
    if not root.exists():
        return {}
    return {
        path.relative_to(root).as_posix(): _sha256(path)
        for path in sorted(root.rglob("*.json"))
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


def run_capital_readonly_dogfood(
    *,
    source_zip: Path,
    output_root: Path,
    expected_sha256: str = SCF_SHA256,
    now: datetime | None = None,
) -> dict[str, Any]:
    observed_at = (now or datetime.now(UTC)).astimezone(UTC)
    output_root.mkdir(parents=True, exist_ok=True)
    digest = _verify_archive(source_zip, expected_sha256)
    rows = load_scf_rows(source_zip)
    household, weighted_median = select_household(rows)
    source_csv = output_root / "scf-household.csv"
    export = write_finharness_export(
        household,
        source_csv,
        as_of_utc=observed_at.isoformat(),
    )

    db = output_root / "state.sqlite"
    domain_receipts = output_root / "domain-receipts"
    agent_receipts = output_root / "agent-receipts"
    engine = init_state_core(db)
    try:
        imported = ingest_personal_finance_export(
            source_csv,
            engine=engine,
            receipt_root=domain_receipts,
        )
    finally:
        engine.dispose()
    if imported.completeness_status != "complete":
        raise RuntimeError(
            f"SCF import is not complete: {imported.completeness_status}"
        )

    db_digest_before = logical_sqlite_digest(db)
    domain_receipts_before = receipt_manifest(domain_receipts)
    with _state_core_environment(db):
        work_result = run_agent_work_loop(
            request=AgentWorkRequest(
                goal="Audit the admitted SCF Capital World without changing it",
                profile_name="default",
                objective=(
                    "Separate observed facts, inferences, unsupported claims, blockers, "
                    "and stop conditions"
                ),
                work_type="evidence_triage",
                receipt_root=str(agent_receipts),
                tool_requests=[AgentWorkToolRequest(
                    tool_name="get_capital_context_projection",
                    arguments={"open_proposals_limit": 5},
                )],
                max_steps=4,
                max_tool_calls=2,
            )
        )

    db_digest_after = logical_sqlite_digest(db)
    domain_receipts_after = receipt_manifest(domain_receipts)
    if db_digest_before != db_digest_after:
        raise RuntimeError("read-only Agent changed the logical StateCore digest")
    if domain_receipts_before != domain_receipts_after:
        raise RuntimeError("read-only Agent changed domain receipts")
    if not work_result.capital_world_audit_ref:
        raise RuntimeError("Agent Work Loop omitted CapitalWorldAudit")
    audit = CapitalWorldAudit.model_validate_json(
        (agent_receipts / work_result.capital_world_audit_ref).read_text(encoding="utf-8")
    )
    replay_envelopes = load_tool_envelopes_from_artifacts(
        receipt_root=agent_receipts,
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

    tool_artifacts = [
        json.loads((agent_receipts / ref).read_text(encoding="utf-8"))
        for ref in work_result.tool_result_refs
    ]
    all_read_only = all(item.get("side_effect") == "read" for item in tool_artifacts)
    if not all_read_only:
        raise RuntimeError("capital-readonly dogfood dispatched a non-read tool")
    if work_result.execution_allowed or audit.execution_allowed:
        raise RuntimeError("capital-readonly dogfood crossed the execution boundary")

    return {
        "schema": SCHEMA,
        "dataset": {
            "url": SCF_URL,
            "sha256": digest,
            "citation": SCF_CITATION,
            "public_record_count": len(rows),
            "selection": (
                "closest eligible first-implicate household to weighted median NETWORTH"
            ),
        },
        "household": {
            "yy1": household["YY1"],
            "y1": household["Y1"],
            "age": household["AGE"],
            "income": household["INCOME"],
            "assets": household["ASSET"],
            "debt": household["DEBT"],
            "net_worth": household["NETWORTH"],
            "eligible_weighted_median_net_worth": str(weighted_median),
        },
        "import": {
            "batch_id": imported.batch_id,
            "snapshot_id": imported.snapshot_id,
            "completeness_status": imported.completeness_status,
            "source_ref": export["source_ref"],
            "conservation": {
                "asset_delta": export["asset_delta"],
                "debt_delta": export["debt_delta"],
            },
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
            "stop_conditions": audit.stop_conditions,
            "required_evaluations": audit.required_evaluations,
        },
        "hermetic_replay": {
            "same_typed_contract": replay_equal,
            "replay_audit_id": replay.audit_id,
        },
        "read_only_proof": {
            "logical_db_digest_before": db_digest_before,
            "logical_db_digest_after": db_digest_after,
            "logical_db_unchanged": db_digest_before == db_digest_after,
            "domain_receipts_before": domain_receipts_before,
            "domain_receipts_after": domain_receipts_after,
            "domain_receipts_unchanged": domain_receipts_before == domain_receipts_after,
        },
        "real_model": model_attempt.model_dump(mode="json"),
        "execution_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-zip", type=Path)
    parser.add_argument("--output-root", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="finharness-capital-readonly-") as tmp:
        output_root = args.output_root or Path(tmp) / "run"
        archive = args.source_zip or Path(tmp) / "scfp2022excel.zip"
        if args.source_zip is None:
            _download(archive)
        result = run_capital_readonly_dogfood(
            source_zip=archive,
            output_root=output_root,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
