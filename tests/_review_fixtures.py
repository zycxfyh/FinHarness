"""Shared fixtures for Review-System tests (timeline / retrospective / compare).

One reusable setup so each Review slice does not re-build its own proposal/attestation/
review-event scaffolding. Used by test_review_read and future R4 compare tests.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from finharness.statecore.proposal_version import (
    ProposalVersionExpectation,
    resolve_current_proposal_version,
)
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

    def _version_expectation(self, proposal_id: str) -> ProposalVersionExpectation:
        current = resolve_current_proposal_version(
            proposal_id, engine=self.engine, receipt_root=self.receipt_root
        )
        return ProposalVersionExpectation(
            proposal_id=proposal_id,
            proposal_version_id=current.proposal_version_id,
            receipt_ref=current.receipt_ref,
        )

    def proposal(
        self,
        proposal_id: str,
        *,
        kind: str = "cash_buffer_low",
        claim: str | None = None,
        evidence: dict[str, Any] | None = None,
        source_refs: list[str] | None = None,
    ) -> Any:
        return create_governed_proposal(
            kind=kind,
            claim=claim or f"{proposal_id} claim",
            evidence=evidence or {"k": 1},
            decision_scaffold={
                "decision_intent": f"Review {proposal_id}",
                "thesis": f"{proposal_id} surfaced by the {kind} detector",
                "do_nothing_case": "Leave it; the surfaced condition persists.",
                "risk_if_wrong": "Acting may incur cost or forgo upside.",
            },
            source_refs=source_refs or [],
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
            expectation=self._version_expectation(proposal_id),
            engine=self.engine,
            receipt_root=self.receipt_root,
        )

    def event(self, proposal_id: str, kind: str, **kw: Any) -> Any:
        return create_governed_review_event(
            proposal_id=proposal_id,
            kind=kind,  # type: ignore[arg-type]
            attester="operator",
            reason="reviewed",
            expectation=self._version_expectation(proposal_id),
            engine=self.engine,
            receipt_root=self.receipt_root,
            **kw,
        )
