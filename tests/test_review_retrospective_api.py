from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finharness.api.app import create_app
from finharness.local_operator import LocalOperatorContext
from finharness.rule_change_ledger import RuleChange
from finharness.statecore.store import init_state_core
from tests.asgi_test_client import AsgiTestClient


def _annual_review_payload(*, created_at: str, lessons_closed: int, lessons_open: list[str]):
    return {
        "receipt_id": f"receipt_annual_{created_at}",
        "kind": "annual_review",
        "created_at_utc": created_at,
        "as_of_date": "2026-06-22",
        "period_label": "2025",
        "lessons_total": lessons_closed + len(lessons_open),
        "lessons_closed": lessons_closed,
        "lessons_open": lessons_open,
        "untraceable_rule_changes": [],
        "data_gaps": [],
        "execution_allowed": False,
    }


class ReviewRetrospectiveApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts" / "state-core"
        self.annual_root = self.root / "receipts" / "annual-review"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.app = create_app(state_core_engine=self.engine, receipt_root=str(self.receipt_root), local_operator_context=LocalOperatorContext("test_harness"))
        self.client = AsgiTestClient(self.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _write_annual(self, name: str, payload: dict) -> None:
        self.annual_root.mkdir(parents=True, exist_ok=True)
        (self.annual_root / name).write_text(json.dumps(payload), encoding="utf-8")

    def _write_rule_change(self, change: RuleChange) -> None:
        # Canonical ledger lives under data/state/rule-changes (sibling of receipts).
        state_root = self.root / "state" / "rule-changes"
        state_root.mkdir(parents=True, exist_ok=True)
        (state_root / f"{change.rule_change_id}.json").write_text(
            json.dumps(change.model_dump(mode="json")), encoding="utf-8"
        )

    def test_empty_when_no_annual_review_receipt(self) -> None:
        body = self.client.get("/review/retrospective").json()
        self.assertIsNone(body["retrospective"])
        self.assertEqual(body["rule_changes"], [])
        self.assertFalse(body["execution_allowed"])

    def test_latest_receipt_selected_and_fields_pass_through(self) -> None:
        self._write_annual(
            "a.json",
            _annual_review_payload(
                created_at="2026-01-01T00:00:00+00:00", lessons_closed=1, lessons_open=["old"]
            ),
        )
        self._write_annual(
            "b.json",
            _annual_review_payload(
                created_at="2026-06-01T00:00:00+00:00", lessons_closed=3, lessons_open=["L1", "L2"]
            ),
        )
        body = self.client.get("/review/retrospective").json()
        retro = body["retrospective"]
        # newest by created_at_utc wins, and closure fields pass through unchanged.
        self.assertEqual(retro["period_label"], "2025")
        self.assertEqual(retro["lessons_closed"], 3)
        self.assertEqual(retro["lessons_open"], ["L1", "L2"])
        self.assertEqual(retro["created_at_utc"], "2026-06-01T00:00:00+00:00")
        # provenance: which receipt this retrospective came from (replayable)
        self.assertTrue(body["retrospective_receipt_ref"])
        self.assertIn("b.json", body["retrospective_receipt_ref"])

    def test_rule_change_drill_down_reflects_status_and_traceability(self) -> None:
        self._write_rule_change(
            RuleChange(
                rule_change_id="rulechg_traceable",
                created_at_utc="2026-06-01T00:00:00+00:00",
                rule_target="guard.hard_stop_drawdown_pct",
                change_kind="threshold",
                rationale="human reviewed",
                attester="operator",
                lesson_draft_id="lesson_1",
                lesson_doc_ref="docs/lessons/2026-06-18-x.md",
                receipt_refs=["data/receipts/lessons/l1.json"],
                status="active",
            )
        )
        self._write_rule_change(
            RuleChange(
                rule_change_id="rulechg_untraceable",
                created_at_utc="2026-06-02T00:00:00+00:00",
                rule_target="guard.max_position_pct",
                change_kind="threshold",
                rationale="hand-fed, no lesson",
                attester="operator",
                status="reverted",
            )
        )
        body = self.client.get("/review/retrospective").json()
        by_id = {rc["rule_change_id"]: rc for rc in body["rule_changes"]}
        self.assertEqual(set(by_id), {"rulechg_traceable", "rulechg_untraceable"})
        self.assertEqual(by_id["rulechg_traceable"]["status"], "active")
        self.assertTrue(by_id["rulechg_traceable"]["traceable"])
        self.assertEqual(by_id["rulechg_untraceable"]["status"], "reverted")
        self.assertFalse(by_id["rulechg_untraceable"]["traceable"])

    def test_corrupt_receipt_becomes_data_gap_not_crash(self) -> None:
        self._write_annual(
            "good.json",
            _annual_review_payload(
                created_at="2026-06-01T00:00:00+00:00", lessons_closed=0, lessons_open=[]
            ),
        )
        self.annual_root.mkdir(parents=True, exist_ok=True)
        (self.annual_root / "bad.json").write_text("{not json", encoding="utf-8")
        resp = self.client.get("/review/retrospective")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsNotNone(body["retrospective"])  # good one still selected
        self.assertTrue(any("bad.json" in gap for gap in body["data_gaps"]))

    def test_non_annual_kind_is_ignored(self) -> None:
        self._write_annual(
            "other.json", {"kind": "something_else", "created_at_utc": "2030-01-01T00:00:00+00:00"}
        )
        body = self.client.get("/review/retrospective").json()
        self.assertIsNone(body["retrospective"])


if __name__ == "__main__":
    unittest.main()
