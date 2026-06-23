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

    def write_receipt(self, relative_path: str, payload: dict[str, Any]) -> Path:
        path = self.receipt_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path
