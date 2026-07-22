#!/usr/bin/env python3
"""Prove canonical capital review, blocked data, restart, and replay paths."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

try:
    from scripts.serve_local_cockpit import build_app
except ModuleNotFoundError:  # Direct `python scripts/...` execution.
    from serve_local_cockpit import build_app

from finharness.allocation import record_allocation_candidates
from finharness.artifact_store import LocalArtifactStore
from finharness.daily_brief import record_daily_brief
from finharness.personal_finance import ingest_personal_finance_export
from finharness.project_paths import ROOT
from finharness.research_enrichment import NoopResearchEnricher
from finharness.statecore.import_models import ImportBatch
from finharness.statecore.store import init_state_core, read_all

SCHEMA = "finharness.capital_review_acceptance.v1"
FIXTURE_ROOT = ROOT / "tests" / "fixtures" / "capital_review"


class AcceptanceFailure(RuntimeError):
    """A supported product journey violated its public contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceFailure(message)


def _materialize(name: str, destination: Path, now: datetime) -> None:
    text = (FIXTURE_ROOT / name).read_text(encoding="utf-8")
    text = text.replace("{{AS_OF_UTC}}", now.isoformat()).replace(
        "{{VALUED_AT_UTC}}", (now - timedelta(minutes=5)).isoformat()
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def _app_args(db: Path, receipts: Path, mode: str) -> argparse.Namespace:
    return argparse.Namespace(
        mode=mode,
        host="127.0.0.1",
        port=8765,
        state_db=db,
        receipt_root=receipts,
        operator_id="capital-review-acceptance-human",
    )


def _record_candidate(engine: Any, receipts: Path):
    return record_allocation_candidates(
        engine,
        receipt_root=receipts,
        enricher=NoopResearchEnricher(),
    )[1]


def _admitted(root: Path, now: datetime) -> dict[str, Any]:
    workspace = root / "admitted"
    db = workspace / "state.sqlite"
    receipts = workspace / "receipts"
    source = workspace / "admitted.csv"
    _materialize("admitted.csv.template", source, now)

    engine = init_state_core(db)
    try:
        imported = ingest_personal_finance_export(source, engine=engine, receipt_root=receipts)
        brief, brief_receipt = record_daily_brief(engine, receipt_root=receipts)
        writes = _record_candidate(engine, receipts)
    finally:
        engine.dispose()

    _require(imported.completeness_status == "complete", "admitted import is incomplete")
    _require(len(writes) == 1, f"expected one candidate, got {len(writes)}")
    candidate = writes[0]
    proposal_id = candidate.proposal.proposal_id
    proposal_receipts_before = sorted((receipts / "proposals").glob("*.json"))
    _require(len(proposal_receipts_before) == 1, "expected one proposal receipt")

    app = build_app(_app_args(db, receipts, "review"))
    with TestClient(app) as client:
        _require(client.get("/cockpit/").status_code == 200, "cockpit did not load")
        ready_response = client.get("/ready/truth")
        ready = ready_response.json()
        _require(ready_response.status_code == 200, "capital truth is not usable")
        _require(ready["capital_truth_admission"] == "admitted", "truth not admitted")
        positions_response = client.get(
            "/state/positions", params={"snapshot_id": imported.snapshot_id}
        )
        _require(positions_response.status_code == 200, "positions unavailable")
        positions = positions_response.json()
        _require(len(positions) == 2, "expected SPY and cash positions")
        exposure = client.get("/exposure").json()
        _require(exposure["asset_valuation_admitted"] is True, "valuation not admitted")
        _require(exposure["total_assets"] == 10000.0, "unexpected total assets")
        proposals = client.get("/proposals").json()
        _require(len(proposals) == 1, "candidate not visible through proposals")
        queue = client.get("/review/queue").json()
        _require(len(queue["items"]) == 1, "candidate not visible in review queue")
        block_codes = {block["code"] for block in proposals[0]["queue_checks"]["blocks"]}
        _require(
            "counter_evidence_needed" not in block_codes,
            "canonical candidate lacks counter-evidence",
        )
        revision = client.get(f"/proposals/{proposal_id}/revisions").json()["revisions"][0]
        response = client.post(
            f"/proposals/{proposal_id}/attest",
            json={
                "decision": "deferred",
                "reason": "Canonical synthetic capital-review acceptance",
                "expected_proposal_version_id": revision["receipt_id"],
                "expected_proposal_receipt_ref": revision["receipt_ref"],
            },
        )
        _require(response.status_code == 200, "human review write failed")
        review = response.json()
        attestation = review["attestation"]
        timeline_before = client.get(f"/proposals/{proposal_id}/timeline").json()
        global_timeline = client.get("/timeline").json()
    app.state.state_core_engine.dispose()

    restarted = build_app(_app_args(db, receipts, "review"))
    with TestClient(restarted) as client:
        detail = client.get(f"/proposals/{proposal_id}").json()
        timeline_after = client.get(f"/proposals/{proposal_id}/timeline").json()
        _require(len(detail["attestations"]) == 1, "review duplicated or disappeared")
        _require(
            detail["attestations"][0]["attestation_id"] == attestation["attestation_id"],
            "restart changed attestation identity",
        )
        _require(timeline_after == timeline_before, "restart changed review timeline")
        replay_writes = _record_candidate(restarted.state.state_core_engine, receipts)
        proposals_after = client.get("/proposals").json()
    restarted.state.state_core_engine.dispose()

    _require(len(replay_writes) == 1, "replay did not resolve canonical candidate")
    _require(replay_writes[0].proposal.proposal_id == proposal_id, "proposal identity changed")
    _require(replay_writes[0].receipt_ref == candidate.receipt_ref, "receipt identity changed")
    _require(
        sorted((receipts / "proposals").glob("*.json")) == proposal_receipts_before,
        "replay wrote a duplicate proposal receipt",
    )
    _require(len(proposals_after) == 1, "replay created a duplicate proposal")
    for path, label in (
        (Path(imported.receipt_ref), "import"),
        (Path(brief_receipt), "brief"),
        (Path(review["receipt_ref"]), "review"),
    ):
        _require(path.is_file(), f"{label} receipt missing")

    return {
        "status": "passed",
        "truth_status": ready["status"],
        "capital_truth_admission": ready["capital_truth_admission"],
        "position_count": len(positions),
        "total_assets": exposure["total_assets"],
        "brief_headline": brief.headline,
        "proposal_id": proposal_id,
        "proposal_receipt": Path(candidate.receipt_ref).name,
        "decision": attestation["decision"],
        "attestation_id": attestation["attestation_id"],
        "timeline_entries": len(timeline_before["entries"]),
        "global_timeline_entries": len(global_timeline),
        "restart_recovered": True,
        "replay_reused_identity": True,
        "execution_allowed": False,
    }


def _blocked(root: Path, now: datetime) -> dict[str, Any]:
    workspace = root / "blocked"
    db = workspace / "state.sqlite"
    receipts = workspace / "receipts"
    source = workspace / "blocked.csv"
    _materialize("blocked.csv.template", source, now)

    engine = init_state_core(db)
    try:
        imported = ingest_personal_finance_export(source, engine=engine, receipt_root=receipts)
        brief, brief_receipt = record_daily_brief(engine, receipt_root=receipts)
        writes = _record_candidate(engine, receipts)
        batches = list(read_all(ImportBatch, engine=engine))
    finally:
        engine.dispose()

    _require(imported.completeness_status == "blocked", "blocked import was not blocked")
    _require(writes == (), "blocked valuation produced a candidate")
    _require(len(batches) == 1, "blocked import batch is not durable")
    store = LocalArtifactStore(receipts / "artifact-store")
    descriptor = store.descriptor(batches[0].source_artifact_id)
    retained_source = store.read(batches[0].source_artifact_id)
    _require(retained_source == source.read_bytes(), "raw blocked source was not preserved")

    app = build_app(_app_args(db, receipts, "read-only"))
    with TestClient(app) as client:
        ready_response = client.get("/ready/truth")
        ready = ready_response.json()
        exposure = client.get("/exposure").json()
        proposals = client.get("/proposals").json()
        timeline = client.get("/timeline").json()
    app.state.state_core_engine.dispose()

    _require(ready_response.status_code == 503, "blocked truth looked usable")
    _require(ready["status"] == "blocked", "truth status is not blocked")
    _require(ready["evidence_integrity"] == "intact", "blocked evidence is not intact")
    _require(exposure["asset_valuation_admitted"] is False, "blocked valuation admitted")
    _require(exposure["total_assets"] is None, "unsupported asset total emitted")
    _require(exposure["net_worth"] is None, "unsupported net worth emitted")
    _require(proposals == [], "blocked data appeared as a proposal")
    _require(Path(imported.receipt_ref).is_file(), "blocked import receipt missing")
    _require(Path(brief_receipt).is_file(), "blocked brief receipt missing")

    return {
        "status": "passed",
        "truth_status": ready["status"],
        "capital_truth_admission": ready["capital_truth_admission"],
        "evidence_integrity": ready["evidence_integrity"],
        "import_completeness": imported.completeness_status,
        "source_artifact_id": descriptor.artifact_id,
        "source_bytes_preserved": len(retained_source),
        "valuation_blockers": exposure["asset_valuation_blockers"],
        "candidate_count": 0,
        "suppressed_fields": ["total_assets", "net_worth", "concentration"],
        "next_action": (
            "Provide market_value, unit_price, valued_at_utc, and price_source_ref, "
            "then re-import the same explicit workspace."
        ),
        "timeline_entries": len(timeline),
        "brief_headline": brief.headline,
        "execution_allowed": False,
    }


def run_acceptance(
    workspace_root: Path | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    observed_at = (now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if workspace_root is None:
        temporary = tempfile.TemporaryDirectory(prefix="finharness-capital-review-")
        root = Path(temporary.name)
        preserved = False
    else:
        root = workspace_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        if any(root.iterdir()):
            raise AcceptanceFailure(f"workspace root must be empty: {root}")
        preserved = True
    try:
        return {
            "schema": SCHEMA,
            "ok": True,
            "observed_at_utc": observed_at.isoformat(),
            "journeys": {
                "admitted_review_and_restart": _admitted(root, observed_at),
                "blocked_data": _blocked(root, observed_at),
            },
            "workspace_preserved": preserved,
            "workspace_root": str(root) if preserved else None,
            "execution_allowed": False,
        }
    finally:
        if temporary is not None:
            temporary.cleanup()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path)
    args = parser.parse_args()
    try:
        result = run_acceptance(args.workspace_root)
    except (AcceptanceFailure, OSError, ValueError) as exc:
        result = {
            "schema": SCHEMA,
            "ok": False,
            "error": str(exc),
            "execution_allowed": False,
        }
        print(json.dumps(result, indent=2))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
