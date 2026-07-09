"""Tests for agent receipt search v0.1.

v0.1 (PR #211): Adds receipt search index tests.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from finharness.agent_receipt_search import (
    AgentReceiptSearchResult,
    build_receipt_search_index,
    search_agent_receipts,
    search_receipt_index,
    write_receipt_search_index,
)


class TestAgentReceiptSearch:

    def _write_receipt(self, root: Path, subdir: str, data: dict) -> str:
        d = root / subdir
        d.mkdir(parents=True, exist_ok=True)
        rid = data.get("receipt_id", "r_default")
        path = d / f"{rid}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def test_search_by_goal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_receipt(root, "agent-runs", {
                "receipt_id": "ar_001", "goal": "Explain SPY exposure",
                "outcome": "succeeded", "stop_reason": "goal_met",
                "created_at_utc": "2026-07-01T00:00:00Z",
            })
            results = search_agent_receipts(receipt_root=root, query="SPY")
            assert len(results) == 1

    def test_kind_filter_restricts_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_receipt(root, "agent-runs", {
                "receipt_id": "ar_001", "goal": "SPY run", "outcome": "succeeded",
            })
            self._write_receipt(root, "evaluation-reports", {
                "receipt_id": "ev_001", "goal": "SPY eval", "status": "pass",
            })
            results = search_agent_receipts(
                receipt_root=root, query="SPY", kinds=["agent_run"],
            )
            assert len(results) == 1
            assert results[0].receipt_kind == "agent_run"

    def test_model_is_frozen(self) -> None:
        r = AgentReceiptSearchResult(
            receipt_id="x", receipt_kind="agent_run", file_path="/tmp/x.json",
        )
        with pytest.raises(ValidationError, match="frozen"):
            r.receipt_id = "hijacked"  # type: ignore[misc]


class TestReceiptSearchIndex:
    """Tests for JSONL receipt search index (new in v0.1)."""

    def _write_receipt(self, root: Path, subdir: str, data: dict) -> str:
        d = root / subdir
        d.mkdir(parents=True, exist_ok=True)
        rid = data.get("receipt_id", "r_default")
        path = d / f"{rid}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return str(path)

    def test_build_index_covers_agent_run_and_evaluation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_receipt(root, "agent-runs", {
                "receipt_id": "ar_001", "goal": "Test", "outcome": "succeeded",
            })
            self._write_receipt(root, "evaluation-reports", {
                "receipt_id": "ev_001", "status": "block",
            })
            entries = build_receipt_search_index(root)
            kinds = {e.receipt_kind for e in entries}
            assert "agent_run" in kinds
            assert "evaluation_report" in kinds

    def test_build_index_covers_domain_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_receipt(root, "domain-memory", {
                "receipt_id": "dm_001", "content": "test memory",
                "status": "attested",
            })
            entries = build_receipt_search_index(root)
            assert any(e.receipt_kind == "domain_memory" for e in entries)

    def test_write_and_search_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_receipt(root, "agent-runs", {
                "receipt_id": "ar_001", "goal": "SPY exposure review",
                "outcome": "succeeded", "source_refs": ["ref://spy"],
            })
            index_path = write_receipt_search_index(root)
            assert index_path.exists()
            results = search_receipt_index(index_path, "SPY")
            assert len(results) == 1
            assert results[0].receipt_id == "ar_001"

    def test_search_index_by_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_receipt(root, "evaluation-reports", {
                "receipt_id": "ev_001", "status": "block",
            })
            self._write_receipt(root, "evaluation-reports", {
                "receipt_id": "ev_002", "status": "pass",
            })
            index_path = write_receipt_search_index(root)
            results = search_receipt_index(index_path, "block")
            assert len(results) == 1
            assert results[0].receipt_id == "ev_001"

    def test_search_index_by_kind_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_receipt(root, "agent-runs", {
                "receipt_id": "ar_001", "goal": "SPY run",
            })
            self._write_receipt(root, "evaluation-reports", {
                "receipt_id": "ev_001", "goal": "SPY eval",
            })
            index_path = write_receipt_search_index(root)
            results = search_receipt_index(index_path, "SPY", kinds=["agent_run"])
            assert len(results) == 1
            assert results[0].receipt_kind == "agent_run"

    def test_search_index_returns_empty_for_missing_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results = search_receipt_index(Path(tmp) / "nonexistent.jsonl", "test")
            assert results == []

    def test_index_entry_model_is_frozen(self) -> None:
        from finharness.agent_receipt_search import ReceiptSearchIndexEntry

        e = ReceiptSearchIndexEntry(
            receipt_id="r1", receipt_kind="agent_run", file_path="/tmp/r.json",
        )
        with pytest.raises(ValidationError, match="frozen"):
            e.receipt_id = "x"  # type: ignore[misc]
