from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from finharness.agent_tools import draft_agent_review_note_from_context_payload
from finharness.api.app import create_app
from finharness.local_operator import LocalOperatorContext
from finharness.statecore.proposal_version import (
    ProposalVersionResolutionError,
    resolve_current_proposal_version,
)
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
            state_core_engine=self.engine, receipt_root=str(self.receipt_root),
            local_operator_context=LocalOperatorContext("test_harness"),
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
                "source_refs": ["context://review_workspace_api"],
                "decision_scaffold": VALID_SCAFFOLD,
            },
        )
        self.assertEqual(resp.status_code, 200)
        return resp.json()["proposal"]["proposal_id"]

    def _add_event(self, proposal_id: str, kind: str, **body) -> object:
        version = self._version_fields(proposal_id)
        return self.client.post(
            f"/proposals/{proposal_id}/review-events",
            json={"kind": kind, "reason": "weekly review", **version, **body},
        )

    def _version_fields(self, proposal_id: str) -> dict[str, str]:
        try:
            version = resolve_current_proposal_version(
                proposal_id,
                engine=self.engine,
                receipt_root=self.receipt_root,
            )
        except ProposalVersionResolutionError:
            return {
                "expected_proposal_version_id": "unknown-version",
                "expected_proposal_receipt_ref": "unknown-receipt",
            }
        return {
            "expected_proposal_version_id": version.proposal_version_id,
            "expected_proposal_receipt_ref": version.receipt_ref,
        }

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
            json={
                "decision": "approved",
                "reason": "looks fine",
                **self._version_fields(pid),
            },
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

    def test_review_task_lifecycle_derives_evidence_requests(self) -> None:
        resp = self.client.post(
            "/proposals",
            json={
                "kind": "rebalance_review",
                "claim": "review evidence gap",
                "evidence": {"data_gap": True},
                "source_refs": ["context://capital_summary"],
                "decision_scaffold": VALID_SCAFFOLD,
            },
        )
        self.assertEqual(resp.status_code, 200)
        pid = resp.json()["proposal"]["proposal_id"]

        body = self.client.get(f"/proposals/{pid}/review-task").json()

        self.assertEqual(body["task_id"], f"review_task:{pid}")
        self.assertEqual(body["state"], "needs_evidence")
        self.assertEqual(body["queue_check_state"], "block")
        self.assertEqual(body["block_codes"], ["data_gap"])
        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["authority_transition"])
        self.assertEqual(len(body["evidence_requests"]), 1)
        request = body["evidence_requests"][0]
        self.assertEqual(request["request_id"], f"evidence_request:{pid}:data_gap")
        self.assertEqual(request["code"], "data_gap")
        self.assertEqual(request["status"], "open")
        self.assertIn("human_attestation", request["blocked_transitions"])
        self.assertFalse(request["execution_allowed"])

    def test_review_task_lifecycle_ready_completed_and_archived_states(self) -> None:
        pid = self._create_proposal("ready lifecycle")
        self._add_event(pid, "annotation", text="watch this")

        ready = self.client.get(f"/proposals/{pid}/review-task").json()
        self.assertEqual(ready["state"], "ready_for_review")
        self.assertEqual(ready["latest_event_kind"], "annotation")
        self.assertFalse(ready["execution_allowed"])

        attested = self.client.post(
            f"/proposals/{pid}/attest",
            json={
                "decision": "rejected",
                "reason": "human review recorded",
                **self._version_fields(pid),
            },
        )
        self.assertEqual(attested.status_code, 200)

        completed = self.client.get(f"/proposals/{pid}/review-task").json()
        self.assertEqual(completed["state"], "completed")
        self.assertFalse(completed["open_for_review"])
        self.assertFalse(completed["execution_allowed"])

        archived_id = self._create_proposal("archived lifecycle")
        self._add_event(archived_id, "archive")
        archived = self.client.get(f"/proposals/{archived_id}/review-task").json()
        self.assertEqual(archived["state"], "archived")
        self.assertTrue(archived["is_archived"])
        self.assertFalse(archived["execution_allowed"])

    def test_review_queue_triage_exposes_agent_review_notes_and_closed_filter(self) -> None:
        active_id = self._create_proposal("active queue note")
        attested_id = self._create_proposal("attested queue note")
        archived_id = self._create_proposal("archived queue note")
        draft_agent_review_note_from_context_payload(
            proposal_id=active_id,
            review_kind="risk_check",
            suggested_severity="high",
            summary="Review the cash timing evidence.",
            rationale="The proposal does not cite a cashflow context pack.",
            findings=["Proposal source refs are present."],
            risks=["Cash timing could change the review outcome."],
            open_questions=["Is the cashflow context current?"],
            evidence_refs=["evidence://cashflow"],
            source_refs=["context://proposal_timeline"],
            context_pack_refs=["context_pack://proposal_timeline"],
            data_gaps=["No cashflow context pack cited."],
            engine=self.engine,
            receipt_root=self.receipt_root,
        )
        self.client.post(
            f"/proposals/{attested_id}/attest",
            json={
                "decision": "approved",
                "reason": "human review recorded",
                **self._version_fields(attested_id),
            },
        )
        self._add_event(archived_id, "archive")

        active = self.client.get("/review/queue").json()
        self.assertFalse(active["execution_allowed"])
        self.assertFalse(active["authority_transition"])
        self.assertIn("not approval", " ".join(active["non_claims"]))
        self.assertEqual({item["proposal_id"] for item in active["items"]}, {active_id})
        item = active["items"][0]
        self.assertEqual(item["priority"], "high")
        self.assertEqual(item["review_note_count"], 1)
        self.assertEqual(item["latest_review_note_summary"], "Review the cash timing evidence.")
        self.assertEqual(item["open_questions"], ["Is the cashflow context current?"])
        self.assertFalse(item["execution_allowed"])
        self.assertFalse(item["authority_transition"])

        all_items = self.client.get(
            "/review/queue",
            params={"include_closed": "true"},
        ).json()
        statuses = {item["proposal_id"]: item["status"] for item in all_items["items"]}
        self.assertEqual(statuses[attested_id], "reviewed")
        self.assertEqual(statuses[archived_id], "archived")


if __name__ == "__main__":
    unittest.main()
