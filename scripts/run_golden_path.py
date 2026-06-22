"""Golden Path — end-to-end receipt-consumption demo (S4).

Proves a governed evidence chain can be *read back*, not just written. In an isolated
tempdir, with synthetic state (public symbols, no real ledger, no network, no execution):

    seed -> decisions:scan -> attest + annotation + compare_mark -> read review models
    -> REPLAY the proposal and review-event receipt FILES (not the DB) -> bounded summary

Manual semantics: setup failure (no candidates) -> non-zero; a chain that cannot be
replayed -> exit 0 with ``replayed: false`` (it discloses an unreadable chain, it does not
crash). The CI happy-path test instead requires ``replayed: true``; a fault-injection test
deletes a receipt and asserts ``replayed: false``.
"""

from __future__ import annotations

import json
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from finharness.allocation import record_allocation_candidates
from finharness.review_read import read_compare_marks, read_proposal_timeline
from finharness.statecore.models import Account, CashflowEvent, Position, Snapshot
from finharness.statecore.proposals import (
    create_governed_attestation,
    create_governed_review_event,
)
from finharness.statecore.store import init_state_core, write_records

_AS_OF = date(2026, 6, 20)


class GoldenPathSetupError(RuntimeError):
    """Seed/scan did not produce the expected candidates — a harness/setup failure."""


def _seed(engine: Any, root: Path) -> None:
    """Synthetic state that deterministically triggers concentration_high + cash_buffer_low.

    source_refs point at real synthetic receipt files so the replay file-existence check has
    something concrete to verify. Public symbols only; no real ledger.
    """
    synth = root / "receipts" / "synthetic"
    synth.mkdir(parents=True, exist_ok=True)
    portfolio_ref = synth / "portfolio.json"
    cashflow_ref = synth / "cashflow.json"
    portfolio_ref.write_text(json.dumps({"synthetic": "portfolio"}), encoding="utf-8")
    cashflow_ref.write_text(json.dumps({"synthetic": "cashflow"}), encoding="utf-8")
    p_ref, c_ref = str(portfolio_ref), str(cashflow_ref)

    account = Account(account_id="gp", kind="broker", venue="synthetic", display_name="Golden")
    snapshot = Snapshot(
        snapshot_id="s",
        kind="portfolio",
        as_of_utc="2026-06-19T00:00:00+00:00",
        source_refs=[p_ref],
    )
    positions = [
        Position(position_id="spy", snapshot_id="s", account_id="gp", symbol="SPY",
                 quantity=Decimal("80"), market_value=Decimal("8000"), source_refs=[p_ref]),
        Position(position_id="aapl", snapshot_id="s", account_id="gp", symbol="AAPL",
                 quantity=Decimal("20"), market_value=Decimal("2000"), source_refs=[p_ref]),
        Position(position_id="cash", snapshot_id="s", account_id="gp", symbol="USD",
                 quantity=Decimal("5000"), market_value=Decimal("5000"), source_refs=[c_ref]),
    ]
    cashflows = [
        CashflowEvent(cashflow_id="salary", description="Salary", amount=Decimal("5000"),
                      currency="USD", event_date="2026-07-15", category="income",
                      frequency="monthly", source_refs=[c_ref]),
        CashflowEvent(cashflow_id="rent", description="Rent", amount=Decimal("-7000"),
                      currency="USD", event_date="2026-07-01", category="expense",
                      frequency="monthly", source_refs=[c_ref]),
    ]
    write_records([account, snapshot, *positions, *cashflows], engine=engine)


def _looks_like_path_ref(ref: str) -> bool:
    return ("/" in ref or ref.endswith(".json")) and not ref.strip().startswith(("http", "{"))


def _replay_receipt(ref: str, *, kind: str, hash_path: tuple[str, ...]) -> list[str]:
    """Read a receipt FILE back and verify its level-precise schema. Returns gaps (empty=ok)."""
    gaps: list[str] = []
    path = Path(ref)
    if not path.exists():
        return [f"receipt file missing: {path.name}"]
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [f"receipt file unreadable: {path.name}"]
    if payload.get("kind") != kind:
        gaps.append(f"{path.name}: kind != {kind}")
    node: Any = payload
    for key in hash_path:
        node = node.get(key) if isinstance(node, dict) else None
    if not node:
        gaps.append(f"{path.name}: missing content_hash at {'.'.join(hash_path)}")
    if (payload.get("governance") or {}).get("execution_allowed") is not False:
        gaps.append(f"{path.name}: governance.execution_allowed must be false")
    return gaps


def run_golden_path(root: Path) -> dict[str, Any]:
    """Orchestrate the full loop and replay the receipts. Importable by tests."""
    engine = init_state_core(root / "state-core.sqlite")
    receipt_root = root / "receipts" / "state-core"
    try:
        _seed(engine, root)
        _report, writes = record_allocation_candidates(
            engine, receipt_root=receipt_root, as_of_date=_AS_OF
        )
        by_kind = {write.proposal.kind: write for write in writes}
        required = {"concentration_high", "cash_buffer_low"}
        if len(writes) < 2 or not required.issubset(by_kind):
            raise GoldenPathSetupError(
                f"expected concentration_high + cash_buffer_low, got {sorted(by_kind)}"
            )
        concentration = by_kind["concentration_high"]
        cash_buffer = by_kind["cash_buffer_low"]

        create_governed_attestation(
            proposal_id=concentration.proposal.proposal_id, decision="approved",
            attester="operator", reason="reviewed concentration", engine=engine,
            receipt_root=receipt_root,
        )
        annotation = create_governed_review_event(
            proposal_id=concentration.proposal.proposal_id, kind="annotation",
            attester="operator", reason="watch single-name risk",
            text="SPY dominates the book", engine=engine, receipt_root=receipt_root,
        )
        create_governed_review_event(
            proposal_id=concentration.proposal.proposal_id, kind="compare_mark",
            attester="operator", reason="compare vs cash buffer",
            compare_with=cash_buffer.proposal.proposal_id, engine=engine,
            receipt_root=receipt_root,
        )

        timeline = read_proposal_timeline(engine, concentration.proposal.proposal_id)
        compare_pairs = read_compare_marks(engine)
    finally:
        engine.dispose()

    replay_gaps = replay_chain(concentration.receipt_ref, annotation.receipt_ref)

    return {
        "ok": True,
        "proposals": len(writes),
        "detector_kinds": sorted(by_kind),
        "compare_pairs": len(compare_pairs),
        "timeline_entries": len(timeline.entries) if timeline else 0,
        "proposal_receipt_ref": concentration.receipt_ref,
        "review_event_receipt_ref": annotation.receipt_ref,
        "replayed": not replay_gaps,
        "replay_gaps": replay_gaps,
        "artifact_root": str(root),
        "cleanup_hint": f"rm -rf {root}",
        "execution_allowed": False,
    }


def replay_chain(proposal_ref: str, review_event_ref: str) -> list[str]:
    """Read the proposal + review-event receipt FILES back and verify the chain replays.

    Returns gaps (empty == replayed). A missing/corrupt/wrong-schema receipt yields a gap
    rather than a crash, so a broken chain reports ``replayed: false``.
    """
    gaps = _replay_receipt(
        proposal_ref, kind="state_core_proposal", hash_path=("content_hash",)
    )
    gaps += _replay_receipt(
        review_event_ref,
        kind="state_core_review_event",
        hash_path=("review_event", "content_hash"),
    )
    # review-event receipt source_refs must include the proposal receipt ref and its own ref.
    review_path = Path(review_event_ref)
    if review_path.exists():
        try:
            ann_payload = json.loads(review_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            ann_payload = {}
        ann_refs = (ann_payload.get("review_event") or {}).get("source_refs") or []
        if proposal_ref not in ann_refs:
            gaps.append("review-event source_refs missing proposal receipt ref")
        if review_event_ref not in ann_refs:
            gaps.append("review-event source_refs missing own receipt ref")
    # path-like source_refs on the proposal receipt must resolve to real files.
    proposal_path = Path(proposal_ref)
    if proposal_path.exists():
        try:
            prop_payload = json.loads(proposal_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            prop_payload = {}
        for ref in (prop_payload.get("proposal") or {}).get("source_refs") or []:
            if _looks_like_path_ref(ref) and not Path(ref).exists():
                gaps.append(f"proposal source_ref file missing: {Path(ref).name}")
    return gaps


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="finharness-golden-path-"))
    try:
        summary = run_golden_path(root)
    except GoldenPathSetupError as exc:
        print(json.dumps({"ok": False, "error": f"setup: {exc}", "artifact_root": str(root)}))
        return 1
    except Exception as exc:  # harness failure -> non-zero, sanitized
        print(
            json.dumps(
                {"ok": False, "error": f"golden-path failure: {type(exc).__name__}",
                 "artifact_root": str(root)}
            )
        )
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    # Manual semantics: a chain that cannot be replayed discloses (exit 0), never crashes.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
