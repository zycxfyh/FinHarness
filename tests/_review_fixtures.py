"""Shared fixtures for Review-System tests (timeline / retrospective / compare).

One reusable setup so each Review slice does not re-build its own proposal/attestation/
review-event scaffolding. Used by test_review_read and future R4 compare tests.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from finharness.statecore.proposals import (
    create_governed_attestation,
    create_governed_proposal,
    create_governed_review_event,
)
from finharness.statecore.store import init_state_core


class ReviewFixture:
    """Tempdir-backed state core with helpers to seed Review-System records."""

    def __init__(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts" / "state-core"
        self.engine = init_state_core(self.root / "state-core.sqlite")

    def cleanup(self) -> None:
        self.engine.dispose()
        self.tmp.cleanup()

    def proposal(self, proposal_id: str, *, kind: str = "cash_buffer_low") -> Any:
        return create_governed_proposal(
            kind=kind,
            claim=f"{proposal_id} claim",
            evidence={"k": 1},
            decision_scaffold={
                "decision_intent": f"Review {proposal_id}",
                "thesis": f"{proposal_id} surfaced by the {kind} detector",
                "do_nothing_case": "Leave it; the surfaced condition persists.",
                "risk_if_wrong": "Acting may incur cost or forgo upside.",
            },
            engine=self.engine,
            receipt_root=self.receipt_root,
            proposal_id=proposal_id,
            idempotent=True,
        )

    def attest(self, proposal_id: str, *, decision: str = "approved") -> Any:
        return create_governed_attestation(
            proposal_id=proposal_id,
            decision=decision,  # type: ignore[arg-type]
            attester="operator",
            reason="reviewed",
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

    def event(self, proposal_id: str, kind: str, **kw: Any) -> Any:
        return create_governed_review_event(
            proposal_id=proposal_id,
            kind=kind,  # type: ignore[arg-type]
            attester="operator",
            reason="reviewed",
            engine=self.engine,
            receipt_root=self.receipt_root,
            **kw,
        )
