from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from finharness.api.app import create_app
from finharness.statecore.store import init_state_core
from tests._scaffold import VALID_SCAFFOLD
from tests.asgi_test_client import AsgiTestClient

# Field set of a /proposals list item before R2b — the default response must keep exactly
# these keys (no archive field leaks into the legacy shape).
_PROPOSAL_ITEM_KEYS = {
    "proposal",
    "attestations",
    "open_for_review",
    "agent_review",
    "queue_checks",
    "non_claims",
    "execution_allowed",
}


class ReviewWorkspaceApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts" / "state-core"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.app = create_app(
            state_core_engine=self.engine, receipt_root=str(self.receipt_root)
        )
        self.client = AsgiTestClient(self.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _create_proposal(self, claim: str) -> str:
        resp = self.client.post(
            "/proposals",
            json={
                "kind": "rebalance_review",
                "claim": claim,
                "evidence": {"k": 1},
                "decision_scaffold": VALID_SCAFFOLD,
            },
        )
        self.assertEqual(resp.status_code, 200)
        return resp.json()["proposal"]["proposal_id"]

    def _add_event(self, proposal_id: str, kind: str, **body) -> object:
        return self.client.post(
            f"/proposals/{proposal_id}/review-events",
            json={"kind": kind, "attester": "operator", "reason": "weekly review", **body},
        )

    # --- default /proposals response unchanged by archive (snapshot lock) -------------
    def test_default_list_keeps_legacy_shape_and_includes_archived(self) -> None:
        keep = self._create_proposal("keep me active")
        archived = self._create_proposal("archive me")
        before = self.client.get("/proposals").json()
        self.assertEqual({item["proposal"]["proposal_id"] for item in before}, {keep, archived})
        for item in before:
            self.assertEqual(set(item), _PROPOSAL_ITEM_KEYS)

        self.assertEqual(self._add_event(archived, "archive").status_code, 200)

        after = self.client.get("/proposals").json()
        # Default (archive=all) still returns BOTH, with the legacy field set unchanged.
        self.assertEqual({item["proposal"]["proposal_id"] for item in after}, {keep, archived})
        for item in after:
            self.assertEqual(set(item), _PROPOSAL_ITEM_KEYS)

    def test_archive_filter_is_explicit_opt_in(self) -> None:
        keep = self._create_proposal("keep")
        archived = self._create_proposal("archived")
        self._add_event(archived, "archive")

        active = self.client.get("/proposals", params={"archive": "active"}).json()
        self.assertEqual({i["proposal"]["proposal_id"] for i in active}, {keep})
        only_archived = self.client.get("/proposals", params={"archive": "archived"}).json()
        self.assertEqual({i["proposal"]["proposal_id"] for i in only_archived}, {archived})

    # --- merged timeline + derived is_archived ---------------------------------------
    def test_timeline_merges_attestation_and_review_events(self) -> None:
        pid = self._create_proposal("review me")
        self.client.post(
            f"/proposals/{pid}/attest",
            json={"decision": "approved", "attester": "operator", "reason": "looks fine"},
        )
        self._add_event(pid, "annotation", text="watch the rate path")

        body = self.client.get(f"/proposals/{pid}/timeline").json()
        self.assertFalse(body["is_archived"])
        sources = {e["source_type"] for e in body["entries"]}
        self.assertEqual(sources, {"attestation", "review_event"})
        # newest-first, deterministic
        stamps = [e["created_at_utc"] for e in body["entries"]]
        self.assertEqual(stamps, sorted(stamps, reverse=True))

    def test_archive_then_reopen_toggles_is_archived(self) -> None:
        pid = self._create_proposal("toggle me")
        self._add_event(pid, "archive")
        self.assertTrue(self.client.get(f"/proposals/{pid}/timeline").json()["is_archived"])
        self._add_event(pid, "reopen")
        self.assertFalse(self.client.get(f"/proposals/{pid}/timeline").json()["is_archived"])

    # --- write endpoint failures -----------------------------------------------------
    def test_review_event_unknown_proposal_404(self) -> None:
        self.assertEqual(self._add_event("nope", "annotation").status_code, 404)

    def test_compare_mark_missing_target_422(self) -> None:
        pid = self._create_proposal("c")
        self.assertEqual(self._add_event(pid, "compare_mark").status_code, 422)

    def test_unknown_kind_rejected_422(self) -> None:
        pid = self._create_proposal("d")
        self.assertEqual(self._add_event(pid, "delete").status_code, 422)

    def test_review_events_never_carry_execution(self) -> None:
        pid = self._create_proposal("e")
        body = self._add_event(pid, "annotation", text="note").json()
        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["review_event"]["execution_allowed"])


if __name__ == "__main__":
    unittest.main()
