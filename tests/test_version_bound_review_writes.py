"""Failing tests for version-bound governed review writes (DEC-CAS-01 / #390).

These tests EXPECT TO FAIL on the current main because:
- ScaffoldRevision / ReviewEvent routes lack version fields
- No same-transaction version check + write boundary
- No bound_proposal_version_id on rows

Run: PYTHONPATH=src uv run python -m unittest tests.test_version_bound_review_writes
"""

from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from finharness.api.app import create_app
from finharness.identity import (
    IDEMPOTENCY_HEADER,
    OperatorContext,
    PrincipalIdentity,
    TestIdentityProvider,
)
from finharness.statecore.models import Attestation, Proposal, ReviewEvent
from finharness.statecore.proposal_version import (
    CurrentProposalVersion,
    resolve_current_proposal_version,
)
from finharness.statecore.store import init_state_core
from tests._scaffold import VALID_SCAFFOLD


def _alice_context() -> OperatorContext:
    return OperatorContext(
        principal=PrincipalIdentity(principal_id="principal:alice", provider_id="test"),
        authentication_method="test_bearer",
        authenticated_at_utc=datetime.now(UTC).isoformat(),
    )


def _headers(key: str) -> dict[str, str]:
    return {"Authorization": "Bearer alice", IDEMPOTENCY_HEADER: key}


# -- helpers ----------------------------------------------------------

def _create_proposal(client: TestClient, *, key: str, body: dict | None = None) -> dict:
    payload = body or {
        "kind": "allocation",
        "claim": "Version-bound test proposal",
        "decision_scaffold": VALID_SCAFFOLD,
        "source_refs": ["test:version-bound"],
    }
    resp = client.post("/proposals", headers=_headers(key), json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["proposal"]


def _current_version(proposal_id: str, engine, receipt_root) -> CurrentProposalVersion:
    return resolve_current_proposal_version(
        proposal_id, engine=engine, receipt_root=receipt_root
    )


def _version_pair(version: CurrentProposalVersion) -> dict[str, str]:
    return {
        "expected_proposal_version_id": version.proposal_version_id,
        "expected_proposal_receipt_ref": version.receipt_ref,
    }


# -- Attestation ------------------------------------------------------


class AttestationVersionBindingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = init_state_core(self.root / "state.sqlite")
        self.addCleanup(self.engine.dispose)
        self.receipt_root = str(self.root / "receipts")
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=self.receipt_root,
            identity_provider=TestIdentityProvider({"alice": _alice_context()}),
        )
        self.client = TestClient(self.app)

    # -- request contract ----------------------------------------------

    def test_missing_version_id_returns_422(self) -> None:
        proposal = _create_proposal(self.client, key="k-att-mv1")
        ver = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        resp = self.client.post(
            f"/proposals/{proposal['proposal_id']}/attest",
            headers=_headers("k-att-mv1b"),
            json={
                "decision": "approved",
                "reason": "missing version id",
                "expected_proposal_receipt_ref": ver.receipt_ref,
            },
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_missing_receipt_ref_returns_422(self) -> None:
        proposal = _create_proposal(self.client, key="k-att-mr1")
        ver = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        resp = self.client.post(
            f"/proposals/{proposal['proposal_id']}/attest",
            headers=_headers("k-att-mr1b"),
            json={
                "decision": "approved",
                "reason": "missing receipt ref",
                "expected_proposal_version_id": ver.proposal_version_id,
            },
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_missing_both_version_fields_returns_422(self) -> None:
        proposal = _create_proposal(self.client, key="k-att-mb1")

        resp = self.client.post(
            f"/proposals/{proposal['proposal_id']}/attest",
            headers=_headers("k-att-mb1b"),
            json={"decision": "approved", "reason": "no version fields at all"},
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_blank_version_id_returns_422(self) -> None:
        proposal = _create_proposal(self.client, key="k-att-bv1")
        ver = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        resp = self.client.post(
            f"/proposals/{proposal['proposal_id']}/attest",
            headers=_headers("k-att-bv1b"),
            json={
                "decision": "approved",
                "reason": "blank version id",
                "expected_proposal_version_id": "",
                "expected_proposal_receipt_ref": ver.receipt_ref,
            },
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_extra_fields_returns_422(self) -> None:
        proposal = _create_proposal(self.client, key="k-att-ef1")
        ver = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        resp = self.client.post(
            f"/proposals/{proposal['proposal_id']}/attest",
            headers=_headers("k-att-ef1b"),
            json={
                "decision": "approved",
                "reason": "extra field",
                **_version_pair(ver),
                "not_a_real_field": 42,
            },
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    # -- fresh success -------------------------------------------------

    def test_attestation_with_current_version_succeeds(self) -> None:
        proposal = _create_proposal(self.client, key="k-att-ok1")
        ver = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        resp = self.client.post(
            f"/proposals/{proposal['proposal_id']}/attest",
            headers=_headers("k-att-ok1b"),
            json={
                "decision": "approved",
                "reason": "current version attestation",
                **_version_pair(ver),
            },
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertFalse(data["execution_allowed"])

        # Row binding
        with Session(self.engine) as s:
            att = s.exec(
                select(Attestation).where(
                    Attestation.attestation_id == data["attestation"]["attestation_id"]
                )
            ).one()
            self.assertEqual(att.bound_proposal_version_id, ver.proposal_version_id)
            self.assertEqual(att.bound_proposal_receipt_ref, ver.receipt_ref)

    # -- stale version -------------------------------------------------

    def test_attestation_with_stale_version_returns_409(self) -> None:
        proposal = _create_proposal(self.client, key="k-att-stale1")
        v1 = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        # Advance proposal to v2 via scaffold revision
        self.client.patch(
            f"/proposals/{proposal['proposal_id']}/decision-scaffold",
            headers=_headers("k-att-rev1"),
            json={
                "reason": "advancing to v2",
                "decision_scaffold": {**VALID_SCAFFOLD, "thesis": "v2 thesis"},
                **_version_pair(v1),
            },
        )

        # Now try to attest using stale v1 pair
        resp = self.client.post(
            f"/proposals/{proposal['proposal_id']}/attest",
            headers=_headers("k-att-stale1b"),
            json={
                "decision": "approved",
                "reason": "stale version attestation",
                **_version_pair(v1),
            },
        )
        self.assertEqual(resp.status_code, 409, resp.text)
        detail = resp.json()["detail"]
        self.assertIn("proposal_version_conflict", detail["code"])

        # Zero domain effect
        with Session(self.engine) as s:
            count = s.exec(
                select(Attestation).where(Attestation.proposal_id == proposal["proposal_id"])
            )
            self.assertEqual(len(list(count)), 0)

    # -- mismatched pair ------------------------------------------------

    def test_old_version_with_current_receipt_fails(self) -> None:
        proposal = _create_proposal(self.client, key="k-att-mp1")
        v1 = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        # Advance
        resp2 = self.client.patch(
            f"/proposals/{proposal['proposal_id']}/decision-scaffold",
            headers=_headers("k-att-mprev1"),
            json={
                "reason": "advancing",
                "decision_scaffold": {**VALID_SCAFFOLD, "thesis": "v2"},
                **_version_pair(v1),
            },
        )
        self.assertEqual(resp2.status_code, 200, resp2.text)
        v2 = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        # Old version_id + current receipt_ref
        resp = self.client.post(
            f"/proposals/{proposal['proposal_id']}/attest",
            headers=_headers("k-att-mp1b"),
            json={
                "decision": "approved",
                "reason": "mismatched pair",
                "expected_proposal_version_id": v1.proposal_version_id,
                "expected_proposal_receipt_ref": v2.receipt_ref,
            },
        )
        self.assertEqual(resp.status_code, 409, resp.text)

    # -- revert content hash --------------------------------------------

    def test_revert_content_produces_new_version_identity(self) -> None:
        proposal = _create_proposal(self.client, key="k-att-rev1")
        v1 = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        # v2: different scaffold
        v2_scaffold = {**VALID_SCAFFOLD, "thesis": "v2 different thesis"}
        resp2 = self.client.patch(
            f"/proposals/{proposal['proposal_id']}/decision-scaffold",
            headers=_headers("k-att-rev1b"),
            json={
                "reason": "to v2",
                "decision_scaffold": v2_scaffold,
                **_version_pair(v1),
            },
        )
        self.assertEqual(resp2.status_code, 200, resp2.text)

        # v3: revert to v1 scaffold
        resp3 = self.client.patch(
            f"/proposals/{proposal['proposal_id']}/decision-scaffold",
            headers=_headers("k-att-rev1c"),
            json={
                "reason": "revert to v1",
                "decision_scaffold": VALID_SCAFFOLD,
                **_version_pair(
                    _current_version(
                        proposal["proposal_id"], self.engine, self.receipt_root
                    )
                ),
            },
        )
        self.assertEqual(resp3.status_code, 200, resp3.text)
        v3 = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        # Content hash may differ (source_refs change), but version_id differs
        self.assertNotEqual(v3.proposal_version_id, v1.proposal_version_id)

        # v1 expectation against v3 must fail
        resp = self.client.post(
            f"/proposals/{proposal['proposal_id']}/attest",
            headers=_headers("k-att-rev1d"),
            json={
                "decision": "approved",
                "reason": "v1 expectation against v3 content",
                **_version_pair(v1),
            },
        )
        self.assertEqual(resp.status_code, 409, resp.text)

    # -- zero domain effect on conflict ---------------------------------

    def test_stale_conflict_produces_zero_domain_effects(self) -> None:
        proposal = _create_proposal(self.client, key="k-att-zd1")
        v1 = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        # Advance
        self.client.patch(
            f"/proposals/{proposal['proposal_id']}/decision-scaffold",
            headers=_headers("k-att-zdrev1"),
            json={
                "reason": "v2",
                "decision_scaffold": {**VALID_SCAFFOLD, "thesis": "v2"},
                **_version_pair(v1),
            },
        )

        resp = self.client.post(
            f"/proposals/{proposal['proposal_id']}/attest",
            headers=_headers("k-att-zd1b"),
            json={"decision": "approved", "reason": "stale", **_version_pair(v1)},
        )
        self.assertEqual(resp.status_code, 409)

        # No attestation row
        with Session(self.engine) as s:
            atts = list(
                s.exec(
                    select(Attestation).where(
                        Attestation.proposal_id == proposal["proposal_id"]
                    )
                )
            )
            self.assertEqual(len(atts), 0)


# -- Scaffold Revision -------------------------------------------------


class ScaffoldRevisionVersionBindingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = init_state_core(self.root / "state.sqlite")
        self.addCleanup(self.engine.dispose)
        self.receipt_root = str(self.root / "receipts")
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=self.receipt_root,
            identity_provider=TestIdentityProvider({"alice": _alice_context()}),
        )
        self.client = TestClient(self.app)

    def _patch(self, proposal_id: str, key: str, ver, scaffold: dict) -> any:
        return self.client.patch(
            f"/proposals/{proposal_id}/decision-scaffold",
            headers=_headers(key),
            json={
                "reason": "scaffold revision",
                "decision_scaffold": scaffold,
                **_version_pair(ver),
            },
        )

    # -- request contract -----------------------------------------------

    def test_missing_version_id_returns_422(self) -> None:
        proposal = _create_proposal(self.client, key="k-sc-mv1")
        ver = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        resp = self.client.patch(
            f"/proposals/{proposal['proposal_id']}/decision-scaffold",
            headers=_headers("k-sc-mv1b"),
            json={
                "reason": "no version id",
                "decision_scaffold": {**VALID_SCAFFOLD, "thesis": "new"},
                "expected_proposal_receipt_ref": ver.receipt_ref,
            },
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_missing_receipt_ref_returns_422(self) -> None:
        proposal = _create_proposal(self.client, key="k-sc-mr1")
        ver = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        resp = self.client.patch(
            f"/proposals/{proposal['proposal_id']}/decision-scaffold",
            headers=_headers("k-sc-mr1b"),
            json={
                "reason": "no receipt ref",
                "decision_scaffold": {**VALID_SCAFFOLD, "thesis": "new"},
                "expected_proposal_version_id": ver.proposal_version_id,
            },
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    # -- fresh success --------------------------------------------------

    def test_scaffold_revision_with_current_version_succeeds(self) -> None:
        proposal = _create_proposal(self.client, key="k-sc-ok1")
        ver = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        resp = self._patch(
            proposal["proposal_id"],
            "k-sc-ok1b",
            ver,
            {**VALID_SCAFFOLD, "thesis": "revised thesis"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertFalse(data["execution_allowed"])

        # Response includes admitted + resulting versions
        self.assertIn("admitted_proposal_version", data)
        self.assertIn("resulting_proposal_version", data)
        self.assertEqual(
            data["admitted_proposal_version"]["proposal_version_id"],
            ver.proposal_version_id,
        )

    # -- stale version --------------------------------------------------

    def test_scaffold_revision_with_stale_version_returns_409(self) -> None:
        proposal = _create_proposal(self.client, key="k-sc-stale1")
        v1 = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        # v1 -> v2
        resp1 = self._patch(
            proposal["proposal_id"],
            "k-sc-stale-rev1",
            v1,
            {**VALID_SCAFFOLD, "thesis": "v2"},
        )
        self.assertEqual(resp1.status_code, 200)

        # Stale v1 expectation
        resp = self._patch(
            proposal["proposal_id"],
            "k-sc-stale1b",
            v1,
            {**VALID_SCAFFOLD, "thesis": "should fail"},
        )
        self.assertEqual(resp.status_code, 409, resp.text)
        detail = resp.json()["detail"]
        self.assertIn("proposal_version_conflict", detail["code"])


# -- ReviewEvent -------------------------------------------------------


class ReviewEventVersionBindingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = init_state_core(self.root / "state.sqlite")
        self.addCleanup(self.engine.dispose)
        self.receipt_root = str(self.root / "receipts")
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=self.receipt_root,
            identity_provider=TestIdentityProvider({"alice": _alice_context()}),
        )
        self.client = TestClient(self.app)

    def _event(
        self, proposal_id: str, key: str, kind: str, ver, reason: str = "review"
    ) -> any:
        return self.client.post(
            f"/proposals/{proposal_id}/review-events",
            headers=_headers(key),
            json={"kind": kind, "reason": reason, **_version_pair(ver)},
        )

    # -- request contract -----------------------------------------------

    def test_missing_version_id_returns_422(self) -> None:
        proposal = _create_proposal(self.client, key="k-re-mv1")
        ver = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        resp = self.client.post(
            f"/proposals/{proposal['proposal_id']}/review-events",
            headers=_headers("k-re-mv1b"),
            json={
                "kind": "annotation",
                "reason": "no version id",
                "expected_proposal_receipt_ref": ver.receipt_ref,
            },
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    def test_missing_receipt_ref_returns_422(self) -> None:
        proposal = _create_proposal(self.client, key="k-re-mr1")
        ver = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        resp = self.client.post(
            f"/proposals/{proposal['proposal_id']}/review-events",
            headers=_headers("k-re-mr1b"),
            json={
                "kind": "annotation",
                "reason": "no receipt ref",
                "expected_proposal_version_id": ver.proposal_version_id,
            },
        )
        self.assertEqual(resp.status_code, 422, resp.text)

    # -- fresh success --------------------------------------------------

    def test_review_event_with_current_version_succeeds(self) -> None:
        proposal = _create_proposal(self.client, key="k-re-ok1")
        ver = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        resp = self._event(proposal["proposal_id"], "k-re-ok1b", "annotation", ver)
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()
        self.assertFalse(data["execution_allowed"])

        # Row binding
        with Session(self.engine) as s:
            ev = s.exec(
                select(ReviewEvent).where(
                    ReviewEvent.review_event_id == data["review_event"]["review_event_id"]
                )
            ).one()
            self.assertEqual(ev.bound_proposal_version_id, ver.proposal_version_id)
            self.assertEqual(ev.bound_proposal_receipt_ref, ver.receipt_ref)

    # -- stale version --------------------------------------------------

    def test_review_event_with_stale_version_returns_409(self) -> None:
        proposal = _create_proposal(self.client, key="k-re-stale1")
        v1 = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)

        # Advance via scaffold revision
        self.client.patch(
            f"/proposals/{proposal['proposal_id']}/decision-scaffold",
            headers=_headers("k-re-stale-rev1"),
            json={
                "reason": "v2",
                "decision_scaffold": {**VALID_SCAFFOLD, "thesis": "v2"},
                **_version_pair(v1),
            },
        )

        resp = self._event(proposal["proposal_id"], "k-re-stale1b", "annotation", v1)
        self.assertEqual(resp.status_code, 409, resp.text)

        # Zero domain effect
        with Session(self.engine) as s:
            evs = list(
                s.exec(
                    select(ReviewEvent).where(ReviewEvent.proposal_id == proposal["proposal_id"])
                )
            )
            self.assertEqual(len(evs), 0)


# -- Concurrent Revision Race -------------------------------------------


class ConcurrentVersionRaceTest(unittest.TestCase):
    """Deterministic concurrent-race test using real SQLite + thread coordination.

    Scaffold writer commits v2 first, then stale attestation must get 409."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = init_state_core(self.root / "state.sqlite")
        self.addCleanup(self.engine.dispose)
        self.receipt_root = str(self.root / "receipts")
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=self.receipt_root,
            identity_provider=TestIdentityProvider({"alice": _alice_context()}),
        )
        self.client = TestClient(self.app)

    def test_scaffold_wins_attestation_stale(self) -> None:
        """Scaffold writer commits v2 first; stale attestation gets 409."""
        proposal = _create_proposal(self.client, key="k-racekey2")
        v1 = _current_version(proposal["proposal_id"], self.engine, self.receipt_root)
        pid = proposal["proposal_id"]

        scaffold_done = threading.Event()

        results: dict[str, int] = {}

        def do_scaffold() -> None:
            resp = self.client.patch(
                f"/proposals/{pid}/decision-scaffold",
                headers=_headers("k-racescn2"),
                json={
                    "reason": "race scaffold first",
                    "decision_scaffold": {**VALID_SCAFFOLD, "thesis": "race v2"},
                    **_version_pair(v1),
                },
            )
            scaffold_done.set()
            results["scaffold"] = resp.status_code

        def do_attest() -> None:
            scaffold_done.wait()  # scaffold commits first
            resp = self.client.post(
                f"/proposals/{pid}/attest",
                headers=_headers("k-raceatt2"),
                json={
                    "decision": "approved",
                    "reason": "stale attest",
                    **_version_pair(v1),
                },
            )
            results["attest"] = resp.status_code

        t1 = threading.Thread(target=do_scaffold)
        t2 = threading.Thread(target=do_attest)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Scaffold succeeds with v1 expectation
        self.assertEqual(results["scaffold"], 200)

        # Attestation with stale v1 gets 409
        self.assertEqual(results["attest"], 409)

        # Zero attestation domain effect
        with Session(self.engine) as s:
            atts = list(
                s.exec(select(Attestation).where(Attestation.proposal_id == pid))
            )
            self.assertEqual(len(atts), 0)

        # Proposal advanced to v2
        v_final = _current_version(pid, self.engine, self.receipt_root)
        self.assertNotEqual(v_final.proposal_version_id, v1.proposal_version_id)


# -- Immediate Transaction Tests ---------------------------------------


class ImmediateTransactionTest(unittest.TestCase):
    """Prove the immediate_state_core_session context manager."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = init_state_core(self.root / "state.sqlite")
        self.addCleanup(self.engine.dispose)

    def test_commit_persists_row(self) -> None:
        from finharness.statecore.store import immediate_state_core_session

        prop = Proposal(proposal_id="imt-test-1", kind="test", claim="txn commit test")
        with immediate_state_core_session(self.engine) as session:
            session.add(prop)

        with Session(self.engine) as s:
            row = s.get(Proposal, "imt-test-1")
            self.assertIsNotNone(row)

    def test_exception_rolls_back(self) -> None:
        from finharness.statecore.store import (
            StateCoreStoreError,
            immediate_state_core_session,
        )

        with (
            self.assertRaises(StateCoreStoreError),
            immediate_state_core_session(self.engine) as session,
        ):
            session.add(
                Proposal(proposal_id="imt-rollback", kind="test", claim="rollback")
            )
            raise StateCoreStoreError("forced")

        with Session(self.engine) as s:
            row = s.get(Proposal, "imt-rollback")
            self.assertIsNone(row)

    def test_flush_failure_wrapped(self) -> None:
        from finharness.statecore.store import (
            StateCoreStoreError,
            immediate_state_core_session,
        )

        # First: successfully persist a row in its own transaction
        with immediate_state_core_session(self.engine) as session:
            session.add(
                Proposal(proposal_id="imt-pk1", kind="test", claim="first")
            )

        # Second: try to insert the same PK twice in one transaction
        with (
            self.assertRaises(StateCoreStoreError),
            immediate_state_core_session(self.engine) as session,
        ):
            session.add(
                Proposal(proposal_id="imt-pk2", kind="test", claim="dup")
            )
            # Add a second row with the SAME primary key
            session.add(
                Proposal(proposal_id="imt-pk2", kind="test", claim="dup2")
            )

        # Only the first transaction's row survives
        with Session(self.engine) as s:
            self.assertIsNotNone(s.get(Proposal, "imt-pk1"))
            self.assertIsNone(s.get(Proposal, "imt-pk2"))
