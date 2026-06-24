"""Ephemeral seeded cockpit server for the D8 browser golden-path smoke.

Boots the read-only FinHarness API against a throwaway tempdir state seeded with a
minimal-but-real proposal chain (mirrors the Golden Path seed: synthetic public symbols,
no real ledger, no network, no execution). The browser smoke loads ``/cockpit`` against
this server and asserts the golden paths render non-blank.

Run directly (the Playwright .cjs smoke spawns this):

    PYTHONPATH=src COCKPIT_SMOKE_PORT=8766 uv run python scripts/run_cockpit_smoke_server.py

Not part of ``task check``. CI-only execution target (see D8 mini-RFC).
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import uvicorn

from finharness.allocation import record_allocation_candidates
from finharness.api.app import create_app
from finharness.statecore.models import (
    Account,
    CashflowEvent,
    Position,
    Snapshot,
)
from finharness.statecore.proposals import (
    create_governed_attestation,
    create_governed_review_event,
)
from finharness.statecore.store import init_state_core, write_records

_AS_OF = date(2026, 6, 20)


def _seed(engine, root: Path) -> None:
    """Synthetic state that deterministically yields concentration_high + cash_buffer_low.

    Mirrors ``scripts/run_golden_path._seed`` (public symbols only, no real ledger) so the
    seeded cockpit shows real Overview/Exposure/Proposals content, not an empty state.
    """
    synth = root / "receipts" / "synthetic"
    synth.mkdir(parents=True, exist_ok=True)
    p_ref = str(synth / "portfolio.json")
    c_ref = str(synth / "cashflow.json")
    (synth / "portfolio.json").write_text(json.dumps({"synthetic": "portfolio"}), encoding="utf-8")
    (synth / "cashflow.json").write_text(json.dumps({"synthetic": "cashflow"}), encoding="utf-8")

    account = Account(account_id="gp", kind="broker", venue="synthetic", display_name="Smoke")
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


def build_seeded_app():
    """Build a cockpit app over a seeded ephemeral state with a real proposal + review chain."""
    root = Path(tempfile.mkdtemp(prefix="cockpit_smoke_"))
    engine = init_state_core(root / "state-core.sqlite")
    receipt_root = root / "receipts" / "state-core"
    _seed(engine, root)

    _report, writes = record_allocation_candidates(
        engine, receipt_root=receipt_root, as_of_date=_AS_OF
    )
    by_kind = {write.proposal.kind: write for write in writes}
    concentration = by_kind["concentration_high"]
    cash_buffer = by_kind["cash_buffer_low"]

    # Give the Proposals detail real revision/review content to render (not an empty state).
    # P5: the high-risk concentration proposal has no counter-evidence, so it cannot be
    # approved (fail-closed). The human declines to confirm it blind; a rejection is not gated.
    create_governed_attestation(
        proposal_id=concentration.proposal.proposal_id, decision="rejected",
        attester="operator", reason="high-risk; not confirming without counter-evidence",
        engine=engine, receipt_root=receipt_root,
    )
    # The low-risk cash-buffer proposal is the one the human confirms (non-execution).
    create_governed_attestation(
        proposal_id=cash_buffer.proposal.proposal_id, decision="approved",
        attester="operator", reason="reviewed cash buffer",
        engine=engine, receipt_root=receipt_root,
    )
    create_governed_review_event(
        proposal_id=concentration.proposal.proposal_id, kind="annotation",
        attester="operator", reason="seed smoke", text="SPY dominates the book",
        engine=engine, receipt_root=receipt_root,
    )
    # A compare_mark so the read-only Compare view renders real content, not an empty state.
    create_governed_review_event(
        proposal_id=concentration.proposal.proposal_id, kind="compare_mark",
        attester="operator", reason="seed smoke", compare_with=cash_buffer.proposal.proposal_id,
        engine=engine, receipt_root=receipt_root,
    )
    return create_app(state_core_engine=engine, receipt_root=str(receipt_root))


app = build_seeded_app()


if __name__ == "__main__":
    port = int(os.environ.get("COCKPIT_SMOKE_PORT", "8766"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
