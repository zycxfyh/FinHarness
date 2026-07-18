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
    ProposalVersionExpectation,
    ProposalVersionResolutionError,
    require_current_proposal_version_in_session,
    resolve_current_proposal_version,
)
from finharness.statecore.proposals import (
    create_governed_attestation,
    create_governed_review_event,
    revise_governed_proposal_scaffold,
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


class RealConcurrentRaceTest(unittest.TestCase):
    """Prove atomicity under real concurrent writers using BEGIN IMMEDIATE.

    Uses the service layer directly with threading.Event coordination.
    The first writer to enter BEGIN IMMEDIATE holds the SQLite write lock;
    the second blocks, then reads current state and sees the conflict.
    """

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.receipt_root_path = self.root / "receipts"
        self.engine = init_state_core(self.root / "state.sqlite")
        self.addCleanup(self.engine.dispose)

        from finharness.statecore.proposals import create_governed_proposal

        write = create_governed_proposal(
            kind="allocation",
            claim="Race test proposal",
            evidence={},
            decision_scaffold=VALID_SCAFFOLD,
            engine=self.engine,
            receipt_root=str(self.receipt_root_path),
            proposal_id="race-prop-1",
        )
        self.proposal_id = write.proposal.proposal_id
        self.v1 = resolve_current_proposal_version(
            self.proposal_id,
            engine=self.engine,
            receipt_root=str(self.receipt_root_path),
        )
        self.v1_expectation = ProposalVersionExpectation(
            proposal_id=self.proposal_id,
            proposal_version_id=self.v1.proposal_version_id,
            receipt_ref=self.v1.receipt_ref,
        )

    @staticmethod
    def _build_scaffold_in_session(
        session: Session,
        existing: Proposal,
        thesis: str,
        receipt_root: str,
    ) -> None:
        from finharness.statecore.proposals import (
            _build_proposal_revision,
            _content_hash,
        )
        from finharness.statecore.receipt_io import atomic_write_json

        merged = {**VALID_SCAFFOLD, "thesis": thesis}
        ch = _content_hash(
            kind=existing.kind, claim=existing.claim,
            evidence=existing.evidence, assumptions=existing.assumptions,
            limitations=existing.limitations, non_claims=existing.non_claims,
            source_refs=existing.source_refs, decision_scaffold=merged,
        )
        built = _build_proposal_revision(
            existing=existing, merged_scaffold=merged, content_hash=ch,
            supersedes=existing.receipt_ref, source_refs=existing.source_refs,
            revision_context={"kind": "test", "reason": "race"},
            receipt_root=receipt_root,
        )
        atomic_write_json(built.receipt_path, built.receipt_payload)
        session.merge(built.proposal)
        session.add(built.receipt_index)

    def test_scaffold_wins_attestation_stale_real_race(self) -> None:
        from finharness.statecore.store import immediate_state_core_session

        A_got_lock = threading.Event()
        A_may_commit = threading.Event()
        saw_conflict: list[bool] = []

        def scaffold() -> None:
            with immediate_state_core_session(self.engine) as session:
                require_current_proposal_version_in_session(
                    self.v1_expectation, proposal_id=self.proposal_id,
                    session=session, receipt_root=str(self.receipt_root_path),
                )
                A_got_lock.set()
                A_may_commit.wait(timeout=5)
                existing = session.get(Proposal, self.proposal_id)
                assert existing is not None
                self._build_scaffold_in_session(
                    session, existing, "race v2", str(self.receipt_root_path),
                )

        def attest() -> None:
            assert A_got_lock.wait(timeout=5)
            try:
                create_governed_attestation(
                    proposal_id=self.proposal_id, decision="approved",
                    attester="tester", reason="should fail",
                    expectation=self.v1_expectation, engine=self.engine,
                    receipt_root=str(self.receipt_root_path),
                )
            except ProposalVersionResolutionError:
                saw_conflict.append(True)

        t1 = threading.Thread(target=scaffold)
        t2 = threading.Thread(target=attest)
        t1.start()
        assert A_got_lock.wait(timeout=5)
        t2.start()
        A_may_commit.set()
        t1.join(timeout=5)
        t2.join(timeout=5)
        self.assertTrue(saw_conflict)
        with Session(self.engine) as s:
            self.assertEqual(
                len(list(s.exec(select(Attestation).where(
                    Attestation.proposal_id == self.proposal_id)))), 0)

    def test_attestation_wins_scaffold_succeeds_real_race(self) -> None:
        from finharness.statecore.store import immediate_state_core_session

        A_got_lock = threading.Event()
        A_may_commit = threading.Event()
        scaffold_ok: list[bool] = []

        def attest() -> None:
            with immediate_state_core_session(self.engine) as session:
                require_current_proposal_version_in_session(
                    self.v1_expectation, proposal_id=self.proposal_id,
                    session=session, receipt_root=str(self.receipt_root_path),
                )
                A_got_lock.set()
                A_may_commit.wait(timeout=5)
                att = Attestation(
                    attestation_id="att-race-win", proposal_id=self.proposal_id,
                    attester="tester", reason="race", decision="approved",
                    bound_proposal_version_id=self.v1.proposal_version_id,
                    bound_proposal_receipt_ref=self.v1.receipt_ref,
                )
                session.add(att)

        def scaffold() -> None:
            assert A_got_lock.wait(timeout=5)
            try:
                revise_governed_proposal_scaffold(
                    proposal_id=self.proposal_id,
                    scaffold_patch={"thesis": "race v2"},
                    attester="tester", reason="race",
                    expectation=self.v1_expectation, engine=self.engine,
                    receipt_root=str(self.receipt_root_path),
                )
                scaffold_ok.append(True)
            except ProposalVersionResolutionError:
                pass

        t1 = threading.Thread(target=attest)
        t2 = threading.Thread(target=scaffold)
        t1.start()
        assert A_got_lock.wait(timeout=5)
        t2.start()
        A_may_commit.set()
        t1.join(timeout=5)
        t2.join(timeout=5)
        self.assertTrue(scaffold_ok)
        with Session(self.engine) as s:
            att = s.get(Attestation, "att-race-win")
            self.assertIsNotNone(att)
            self.assertEqual(att.bound_proposal_version_id, self.v1.proposal_version_id)
        vf = resolve_current_proposal_version(
            self.proposal_id, engine=self.engine,
            receipt_root=str(self.receipt_root_path),
        )
        self.assertNotEqual(vf.proposal_version_id, self.v1.proposal_version_id)

    def test_two_scaffold_writers_one_wins(self) -> None:
        committed: list[str] = []
        lock = threading.Lock()

        def writer(thesis: str) -> None:
            try:
                revise_governed_proposal_scaffold(
                    proposal_id=self.proposal_id,
                    scaffold_patch={"thesis": thesis},
                    attester="tester", reason=f"race {thesis}",
                    expectation=self.v1_expectation, engine=self.engine,
                    receipt_root=str(self.receipt_root_path),
                )
                with lock:
                    committed.append(thesis)
            except ProposalVersionResolutionError:
                pass

        t1 = threading.Thread(target=writer, args=("race v2a",))
        t2 = threading.Thread(target=writer, args=("race v2b",))
        t1.start()
        t2.start()
        t1.join(timeout=5)
        t2.join(timeout=5)
        self.assertEqual(len(committed), 1)
        vf = resolve_current_proposal_version(
            self.proposal_id, engine=self.engine,
            receipt_root=str(self.receipt_root_path),
        )
        self.assertNotEqual(vf.proposal_version_id, self.v1.proposal_version_id)

    def test_scaffold_vs_review_event_stale_loses(self) -> None:
        from finharness.statecore.store import immediate_state_core_session

        A_got_lock = threading.Event()
        A_may_commit = threading.Event()
        review_conflict: list[bool] = []

        def scaffold() -> None:
            with immediate_state_core_session(self.engine) as session:
                require_current_proposal_version_in_session(
                    self.v1_expectation, proposal_id=self.proposal_id,
                    session=session, receipt_root=str(self.receipt_root_path),
                )
                A_got_lock.set()
                A_may_commit.wait(timeout=5)
                existing = session.get(Proposal, self.proposal_id)
                assert existing is not None
                self._build_scaffold_in_session(
                    session, existing, "race v2", str(self.receipt_root_path),
                )

        def review() -> None:
            assert A_got_lock.wait(timeout=5)
            try:
                create_governed_review_event(
                    proposal_id=self.proposal_id, kind="annotation",
                    attester="tester", reason="should fail",
                    expectation=self.v1_expectation, engine=self.engine,
                    receipt_root=str(self.receipt_root_path),
                )
            except ProposalVersionResolutionError:
                review_conflict.append(True)

        t1 = threading.Thread(target=scaffold)
        t2 = threading.Thread(target=review)
        t1.start()
        assert A_got_lock.wait(timeout=5)
        t2.start()
        A_may_commit.set()
        t1.join(timeout=5)
        t2.join(timeout=5)
        self.assertTrue(review_conflict)
        with Session(self.engine) as s:
            self.assertEqual(
                len(list(s.exec(select(ReviewEvent).where(
                    ReviewEvent.proposal_id == self.proposal_id)))), 0)


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
