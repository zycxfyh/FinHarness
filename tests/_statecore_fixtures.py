"""Shared fixtures for State-Core tests.

State Core tests repeat the same tempdir / sqlite / receipt-root setup in many
places. This helper is intentionally small: it standardizes the filesystem and
engine lifecycle without hiding the records each test is trying to exercise.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

from sqlalchemy.engine import Engine

from finharness.statecore.proposal_version import (
    ProposalVersionExpectation,
    resolve_current_proposal_version,
)
from finharness.statecore.store import init_state_core


class StateCoreFixture:
    """Tempdir-backed State Core database plus a receipt root."""

    def __init__(self, *, receipt_subdir: str = "receipts") -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "state-core.sqlite"
        self.receipt_root = self.root / receipt_subdir
        self.receipt_root.mkdir(parents=True, exist_ok=True)
        self.engine: Engine = init_state_core(self.db_path)

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

    def write_receipt(self, relative_path: str, payload: dict[str, Any]) -> Path:
        path = self.receipt_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path
