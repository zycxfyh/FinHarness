"""Tests for agent receipt search v0."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from finharness.agent_receipt_search import search_agent_receipts


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
                "receipt_id": "ar_001",
                "goal": "Explain SPY exposure",
                "outcome": "succeeded",
                "stop_reason": "goal_met",
                "created_at_utc": "2026-07-01T00:00:00Z",
            })
            results = search_agent_receipts(
                receipt_root=root,
                query="SPY",
            )
            assert len(results) == 1
            assert results[0].receipt_id == "ar_001"
            assert "goal" in results[0].matched_on

    def test_search_by_outcome_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_receipt(root, "agent-runs", {
                "receipt_id": "ar_002",
                "goal": "Check risk",
                "outcome": "partial",
                "stop_reason": "tool_unavailable",
                "created_at_utc": "2026-07-02T00:00:00Z",
            })
            results = search_agent_receipts(receipt_root=root, query="partial")
            assert len(results) == 1

    def test_search_by_evaluation_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_receipt(root, "evaluation-reports", {
                "receipt_id": "ev_001",
                "goal": "Evaluate plan",
                "status": "block",
                "created_at_utc": "2026-07-03T00:00:00Z",
            })
            results = search_agent_receipts(receipt_root=root, query="block")
            assert len(results) == 1
            assert results[0].outcome_or_status == "block"

    def test_empty_query_returns_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results = search_agent_receipts(
                receipt_root=Path(tmp),
                query="   ",
            )
            assert results == []

    def test_missing_root_returns_empty(self) -> None:
        results = search_agent_receipts(
            receipt_root="/nonexistent/path",
            query="test",
        )
        assert results == []

    def test_limit_respected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(5):
                self._write_receipt(root, "agent-runs", {
                    "receipt_id": f"ar_{i:03d}",
                    "goal": f"Task {i} about SPY",
                    "outcome": "succeeded",
                })
            results = search_agent_receipts(
                receipt_root=root,
                query="SPY",
                limit=2,
            )
            assert len(results) == 2

    def test_kind_filter_restricts_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_receipt(root, "agent-runs", {
                "receipt_id": "ar_001",
                "goal": "SPY run",
                "outcome": "succeeded",
            })
            self._write_receipt(root, "evaluation-reports", {
                "receipt_id": "ev_001",
                "goal": "SPY evaluation",
                "status": "pass",
            })
            results = search_agent_receipts(
                receipt_root=root,
                query="SPY",
                kinds=["agent_run"],
            )
            assert len(results) == 1
            assert results[0].receipt_kind == "agent_run"

    def test_model_is_frozen(self) -> None:
        import pytest
        from pydantic import ValidationError

        from finharness.agent_receipt_search import AgentReceiptSearchResult

        r = AgentReceiptSearchResult(
            receipt_id="x",
            receipt_kind="agent_run",
            file_path="/tmp/x.json",
        )
        with pytest.raises(ValidationError, match="frozen"):
            r.receipt_id = "hijacked"  # type: ignore[misc]

    def test_execution_allowed_never_in_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_receipt(root, "agent-runs", {
                "receipt_id": "ar_001",
                "goal": "SPY run",
                "outcome": "succeeded",
                "execution_allowed": False,
            })
            results = search_agent_receipts(receipt_root=root, query="SPY")
            assert len(results) == 1
            # SearchResult has no execution_allowed field at all
            assert not hasattr(results[0], "execution_allowed")
