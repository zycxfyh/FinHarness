"""Tests for agent receipt search v0.1.

v0.1 (PR #211): Adds receipt search index tests.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

import finharness.agent_receipt_search as receipt_search
from finharness.agent_receipt_search import (
    AgentReceiptSearchResult,
    ReceiptSearchIndexUnavailableError,
    build_receipt_search_index,
    search_agent_receipts,
    search_receipt_index,
    search_receipt_index_with_status,
    update_receipt_search_index,
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

    def test_scan_search_does_not_hide_corrupt_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broken = root / "agent-runs" / "broken.json"
            broken.parent.mkdir(parents=True)
            broken.write_text("{broken", encoding="utf-8")
            with pytest.raises(ReceiptSearchIndexUnavailableError, match="unreadable"):
                search_agent_receipts(receipt_root=root, query="missing")


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

    def test_search_index_reports_missing_instead_of_false_complete_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            index_path = Path(tmp) / "nonexistent.jsonl"
            response = search_receipt_index_with_status(index_path, "test")
            assert response.results == []
            assert response.index_status.freshness == "missing"
            with pytest.raises(ReceiptSearchIndexUnavailableError, match="manifest is missing"):
                search_receipt_index(index_path, "test")

    def test_incremental_update_reads_only_the_supplied_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in range(1000):
                self._write_receipt(
                    root,
                    "agent-runs",
                    {"receipt_id": f"ar_{index:04d}", "goal": f"history {index}"},
                )
            index_path = write_receipt_search_index(root)
            new_path = self._write_receipt(
                root,
                "agent-runs",
                {"receipt_id": "ar_new", "goal": "incremental needle"},
            )
            with patch(
                "finharness.agent_receipt_search._entry_from_path",
                wraps=receipt_search._entry_from_path,
            ) as extract:
                update_receipt_search_index(root, [str(Path(new_path).relative_to(root))])
            assert extract.call_count == 1
            response = search_receipt_index_with_status(index_path, "needle")
            assert response.index_status.complete
            assert [result.receipt_id for result in response.results] == ["ar_new"]

    def test_interrupted_manifest_commit_preserves_previous_generation(self) -> None:
        from finharness.statecore import receipt_io

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = self._write_receipt(
                root, "agent-runs", {"receipt_id": "ar_old", "goal": "old truth"}
            )
            index_path = write_receipt_search_index(root)
            previous_manifest = index_path.read_bytes()
            second = self._write_receipt(
                root, "agent-runs", {"receipt_id": "ar_new", "goal": "new truth"}
            )
            real_atomic_write = receipt_io.atomic_write_json
            calls = 0

            def fail_manifest(path: Path, payload: dict) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated crash before manifest commit")
                real_atomic_write(path, payload)

            with (
                patch.object(receipt_io, "atomic_write_json", side_effect=fail_manifest),
                pytest.raises(OSError, match="simulated crash"),
            ):
                update_receipt_search_index(
                    root,
                    [str(Path(first).relative_to(root)), str(Path(second).relative_to(root))],
                )
            assert index_path.read_bytes() == previous_manifest
            assert len(search_receipt_index(index_path, "old truth")) == 1
            assert search_receipt_index(index_path, "new truth") == []

    def test_corrupt_source_is_explicitly_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            corrupt = root / "agent-runs" / "broken.json"
            corrupt.parent.mkdir(parents=True)
            corrupt.write_text("{broken", encoding="utf-8")
            index_path = write_receipt_search_index(root)
            response = search_receipt_index_with_status(index_path, "anything")
            assert response.index_status.freshness == "incomplete"
            assert response.index_status.unreadable_source_count == 1
            assert response.index_status.unreadable_sources == ["agent-runs/broken.json"]
            with pytest.raises(ReceiptSearchIndexUnavailableError, match="unreadable"):
                search_receipt_index(index_path, "anything")

    def test_corrupt_committed_segment_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_receipt(root, "agent-runs", {"receipt_id": "ar_1", "goal": "old"})
            index_path = write_receipt_search_index(root)
            second = self._write_receipt(
                root, "agent-runs", {"receipt_id": "ar_2", "goal": "new"}
            )
            update_receipt_search_index(root, [str(Path(second).relative_to(root))])
            manifest = json.loads(index_path.read_text(encoding="utf-8"))
            segment = root / ".receipt-index" / f"update-{manifest['generation']:020d}.json"
            segment.write_text('{"partial":', encoding="utf-8")
            response = search_receipt_index_with_status(index_path, "old")
            assert response.results == []
            assert response.index_status.freshness == "corrupt"
            with pytest.raises(ReceiptSearchIndexUnavailableError, match="corrupt"):
                search_receipt_index(index_path, "old")

    def test_rebuild_converges_with_incremental_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._write_receipt(root, "agent-runs", {"receipt_id": "ar_1", "goal": "SPY"})
            index_path = write_receipt_search_index(root)
            second = self._write_receipt(
                root, "evaluation-reports", {"receipt_id": "ev_1", "goal": "SPY"}
            )
            update_receipt_search_index(root, [str(Path(second).relative_to(root))])
            incremental = search_receipt_index_with_status(index_path, "SPY")
            write_receipt_search_index(root)
            rebuilt = search_receipt_index_with_status(index_path, "SPY")
            assert {item.receipt_id for item in incremental.results} == {
                item.receipt_id for item in rebuilt.results
            }
            assert rebuilt.index_status.generation == rebuilt.index_status.checkpoint_generation

    def test_legacy_jsonl_migrates_once_through_recovery_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt = self._write_receipt(
                root, "agent-runs", {"receipt_id": "ar_legacy", "goal": "legacy"}
            )
            index_path = root / "receipt-index.jsonl"
            index_path.write_text('{"receipt_id":"legacy-line"}\n', encoding="utf-8")
            update_receipt_search_index(root, [str(Path(receipt).relative_to(root))])
            response = search_receipt_index_with_status(index_path, "legacy")
            assert response.index_status.complete
            assert [item.receipt_id for item in response.results] == ["ar_legacy"]

    def test_agent_terminal_path_uses_incremental_owner(self) -> None:
        root = Path(__file__).resolve().parents[1]
        source = (root / "src/finharness/agent_work_loop.py").read_text(encoding="utf-8")
        assert "update_receipt_search_index" in source
        assert "write_receipt_search_index" not in source

    def test_index_entry_model_is_frozen(self) -> None:
        from finharness.agent_receipt_search import ReceiptSearchIndexEntry

        e = ReceiptSearchIndexEntry(
            receipt_id="r1", receipt_kind="agent_run", file_path="/tmp/r.json",
        )
        with pytest.raises(ValidationError, match="frozen"):
            e.receipt_id = "x"  # type: ignore[misc]
