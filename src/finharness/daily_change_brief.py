"""Deterministic daily portfolio-change brief runtime loop."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from sqlalchemy import Engine

from finharness.market_data import ROOT
from finharness.runtime_log import get_logger
from finharness.statecore.diff import SnapshotDiff, diff_snapshots
from finharness.statecore.models import ReceiptIndex, Snapshot
from finharness.statecore.observations import (
    Observation,
    ObservationThresholds,
    build_observations,
)
from finharness.statecore.proposals import GovernedProposalWrite, create_governed_proposal
from finharness.statecore.receipt_io import atomic_write_json, atomic_write_text
from finharness.statecore.snapshot_ingest import ingest_portfolio_snapshot_from_receipt
from finharness.statecore.snapshots import latest_portfolio_snapshot, portfolio_positions
from finharness.statecore.store import upsert_records

DEFAULT_MARKDOWN_PATH = ROOT / "docs" / "operations" / "daily-change-brief-latest.md"
DEFAULT_STATE_CORE_RECEIPT_ROOT = ROOT / "data" / "receipts" / "state-core"
DEFAULT_BRIEF_RECEIPT_ROOT = ROOT / "data" / "receipts" / "daily-change-brief"
DESCRIPTIVE_NON_CLAIMS = [
    "Descriptive state change only.",
    "Not a market prediction.",
    "Not trading advice.",
    "Not execution authorization.",
]

BriefStatus = Literal["baseline", "quiet", "observations"]


@dataclass(frozen=True)
class DailyChangeBriefResult:
    status: BriefStatus
    after_snapshot_id: str
    before_snapshot_id: str | None
    proposal_id: str
    proposal_receipt_ref: str
    markdown_ref: str
    receipt_ref: str
    observation_count: int
    execution_allowed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _safe_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in value)


def _run_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:12]


def _date_from_as_of(as_of_utc: str) -> str:
    return _safe_id(as_of_utc[:10].replace("-", ""))


def _observation_dicts(observations: tuple[Observation, ...]) -> list[dict[str, Any]]:
    return [observation.as_dict() for observation in observations]


def _claim(status: BriefStatus, observations: tuple[Observation, ...]) -> str:
    if status == "baseline":
        return "Observed baseline portfolio snapshot; no prior portfolio snapshot was available."
    if status == "quiet":
        return "Observed no threshold-crossing portfolio state changes."
    return f"Observed {len(observations)} threshold-crossing portfolio state changes."


def _render_markdown(
    *,
    status: BriefStatus,
    after_snapshot: Snapshot,
    before_snapshot: Snapshot | None,
    diff: SnapshotDiff | None,
    observations: tuple[Observation, ...],
    thresholds: ObservationThresholds,
    proposal: GovernedProposalWrite,
) -> str:
    lines = [
        "# Daily Change Brief",
        "",
        f"- Status: `{status}`",
        f"- After snapshot: `{after_snapshot.snapshot_id}` at `{after_snapshot.as_of_utc}`",
        f"- Before snapshot: `{before_snapshot.snapshot_id if before_snapshot else 'baseline'}`",
        f"- Proposal: `{proposal.proposal.proposal_id}`",
        f"- Execution allowed: `{str(proposal.execution_allowed).lower()}`",
        "",
        "## Non-Claims",
        "",
        *[f"- {item}" for item in DESCRIPTIVE_NON_CLAIMS],
        "",
        "## Thresholds",
        "",
    ]
    for key, value in thresholds.as_dict().items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Observations", ""])
    if status == "baseline":
        lines.append("- Baseline snapshot recorded; no prior portfolio snapshot was available.")
    elif not observations:
        lines.append("- No threshold-crossing portfolio state changes.")
    else:
        for observation in observations:
            lines.append(f"- `{observation.kind}`: {observation.detail}")
    lines.extend(["", "## Diff", ""])
    if diff is None:
        lines.append("- No diff was computed for the baseline run.")
    else:
        lines.extend(
            [
                f"- Total market value before: `{diff.total_market_value_before}`",
                f"- Total market value after: `{diff.total_market_value_after}`",
                f"- Total market value delta: `{diff.total_market_value_delta}`",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def _source_refs(
    *,
    portfolio_receipt: Path,
    after_snapshot: Snapshot,
    before_snapshot: Snapshot | None,
) -> list[str]:
    refs = [_display_path(portfolio_receipt)]
    refs.extend(after_snapshot.source_refs)
    if before_snapshot is not None:
        refs.extend(before_snapshot.source_refs)
    return sorted(set(refs))


def _brief_receipt_payload(
    *,
    receipt_id: str,
    status: BriefStatus,
    after_snapshot: Snapshot,
    before_snapshot: Snapshot | None,
    diff: SnapshotDiff | None,
    observations: tuple[Observation, ...],
    thresholds: ObservationThresholds,
    proposal: GovernedProposalWrite,
    markdown_ref: str,
    source_refs: list[str],
) -> dict[str, Any]:
    return {
        "receipt_id": receipt_id,
        "kind": "daily_change_brief",
        "created_at_utc": after_snapshot.as_of_utc,
        "status": status,
        "after_snapshot_id": after_snapshot.snapshot_id,
        "before_snapshot_id": before_snapshot.snapshot_id if before_snapshot else None,
        "diff": diff.as_dict() if diff else None,
        "observations": _observation_dicts(observations),
        "thresholds": thresholds.as_dict(),
        "proposal_id": proposal.proposal.proposal_id,
        "proposal_receipt_ref": proposal.receipt_ref,
        "markdown_ref": markdown_ref,
        "source_refs": source_refs,
        "non_claims": DESCRIPTIVE_NON_CLAIMS,
        "execution_allowed": False,
    }


def run_daily_change_brief(
    *,
    portfolio_receipt: str | Path,
    engine: Engine,
    thresholds: ObservationThresholds | None = None,
    state_core_receipt_root: str | Path = DEFAULT_STATE_CORE_RECEIPT_ROOT,
    brief_receipt_root: str | Path = DEFAULT_BRIEF_RECEIPT_ROOT,
    markdown_path: str | Path = DEFAULT_MARKDOWN_PATH,
) -> DailyChangeBriefResult:
    """Run ingest -> diff -> deterministic observations -> governed proposal."""
    logger = get_logger(__name__)
    active_thresholds = thresholds or ObservationThresholds()
    receipt_path = Path(portfolio_receipt)
    after_snapshot = ingest_portfolio_snapshot_from_receipt(receipt_path, engine=engine)
    before_snapshot = latest_portfolio_snapshot(
        engine=engine,
        before=after_snapshot.as_of_utc,
    )
    diff: SnapshotDiff | None = None
    observations: tuple[Observation, ...] = ()
    if before_snapshot is None:
        status: BriefStatus = "baseline"
    else:
        diff = diff_snapshots(
            before_snapshot.snapshot_id,
            after_snapshot.snapshot_id,
            engine=engine,
        )
        current_positions = portfolio_positions(after_snapshot.snapshot_id, engine=engine)
        observations = build_observations(
            diff,
            current_positions,
            thresholds=active_thresholds,
        )
        status = "observations" if observations else "quiet"

    identity = {
        "kind": "daily_change_brief",
        "after_snapshot_id": after_snapshot.snapshot_id,
        "before_snapshot_id": before_snapshot.snapshot_id if before_snapshot else None,
        "thresholds": active_thresholds.as_dict(),
    }
    run_hash = _run_hash(identity)
    run_date = _date_from_as_of(after_snapshot.as_of_utc)
    proposal_id = _safe_id(f"prop_daily_change_brief_{run_date}_{run_hash}")
    source_refs = _source_refs(
        portfolio_receipt=receipt_path,
        after_snapshot=after_snapshot,
        before_snapshot=before_snapshot,
    )
    proposal = create_governed_proposal(
        kind="daily_change_brief",
        claim=_claim(status, observations),
        evidence={
            "status": status,
            "before_snapshot_id": before_snapshot.snapshot_id if before_snapshot else None,
            "after_snapshot_id": after_snapshot.snapshot_id,
            "diff": diff.as_dict() if diff else None,
            "observations": _observation_dicts(observations),
            "thresholds": active_thresholds.as_dict(),
        },
        limitations={
            "deterministic_only": True,
            "llm_used": False,
            "broker_called_by_loop": False,
        },
        non_claims=DESCRIPTIVE_NON_CLAIMS,
        source_refs=source_refs,
        engine=engine,
        receipt_root=state_core_receipt_root,
        proposal_id=proposal_id,
        created_at_utc=after_snapshot.as_of_utc,
        idempotent=True,
    )
    markdown_target = Path(markdown_path)
    markdown_ref = _display_path(markdown_target)
    atomic_write_text(
        markdown_target,
        _render_markdown(
            status=status,
            after_snapshot=after_snapshot,
            before_snapshot=before_snapshot,
            diff=diff,
            observations=observations,
            thresholds=active_thresholds,
            proposal=proposal,
        ),
    )
    brief_receipt_id = _safe_id(f"receipt_daily_change_brief_{run_date}_{run_hash}")
    brief_receipt_path = Path(brief_receipt_root) / f"{brief_receipt_id}.json"
    brief_payload = _brief_receipt_payload(
        receipt_id=brief_receipt_id,
        status=status,
        after_snapshot=after_snapshot,
        before_snapshot=before_snapshot,
        diff=diff,
        observations=observations,
        thresholds=active_thresholds,
        proposal=proposal,
        markdown_ref=markdown_ref,
        source_refs=source_refs,
    )
    atomic_write_json(brief_receipt_path, brief_payload)
    brief_receipt_ref = _display_path(brief_receipt_path)
    upsert_records(
        [
            ReceiptIndex(
                receipt_id=brief_receipt_id,
                kind="daily_change_brief",
                path=brief_receipt_ref,
                created_at_utc=after_snapshot.as_of_utc,
                source_refs=[brief_receipt_ref],
                refs=[proposal.receipt_ref, *source_refs],
            )
        ],
        engine=engine,
    )
    logger.info(
        "daily_change_brief_completed",
        status=status,
        after_snapshot_id=after_snapshot.snapshot_id,
        before_snapshot_id=before_snapshot.snapshot_id if before_snapshot else None,
        observation_count=len(observations),
        proposal_id=proposal.proposal.proposal_id,
        execution_allowed=False,
    )
    return DailyChangeBriefResult(
        status=status,
        after_snapshot_id=after_snapshot.snapshot_id,
        before_snapshot_id=before_snapshot.snapshot_id if before_snapshot else None,
        proposal_id=proposal.proposal.proposal_id,
        proposal_receipt_ref=proposal.receipt_ref,
        markdown_ref=markdown_ref,
        receipt_ref=brief_receipt_ref,
        observation_count=len(observations),
        execution_allowed=False,
    )
