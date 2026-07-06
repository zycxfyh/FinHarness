"""P4 decision-scaffold forcing gate — required-field enforcement and derivation.

Covers the product value of P4: a governed (needs_human_confirm) proposal cannot
become confirm-ready without the four required scaffold fields, and the auto-creators
derive real scaffolds from their own signals.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finharness.allocation import AllocationCandidate, CandidateOption, _candidate_scaffold
from finharness.api.app import create_app
from finharness.daily_change_brief import _change_scaffold
from finharness.local_operator import LocalOperatorContext
from finharness.statecore.decision_scaffold import (
    REQUIRED_FIELDS,
    DecisionScaffold,
    DecisionScaffoldError,
    ensure_forcing,
    is_complete,
    missing_required,
    normalize,
)
from finharness.statecore.models import Proposal
from finharness.statecore.observations import Observation
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import init_state_core, read_all
from tests._scaffold import VALID_SCAFFOLD
from tests.asgi_test_client import AsgiTestClient


class DecisionScaffoldModuleTest(unittest.TestCase):
    def test_missing_required_lists_blanks_in_canonical_order(self) -> None:
        self.assertEqual(missing_required({}), list(REQUIRED_FIELDS))
        partial = {"decision_intent": "x", "thesis": "  ", "do_nothing_case": "y"}
        # blank thesis counts as missing; risk_if_wrong absent.
        self.assertEqual(missing_required(partial), ["thesis", "risk_if_wrong"])

    def test_is_complete(self) -> None:
        self.assertTrue(is_complete(VALID_SCAFFOLD))
        self.assertFalse(is_complete({"decision_intent": "only one"}))

    def test_normalize_drops_unknown_and_blank_keeps_known(self) -> None:
        out = normalize({**VALID_SCAFFOLD, "unknown": "z", "emotion": "  ", "review_date": "2026"})
        self.assertNotIn("unknown", out)
        self.assertNotIn("emotion", out)  # blank dropped
        self.assertEqual(out["review_date"], "2026")

    def test_ensure_forcing_raises_listing_missing(self) -> None:
        with self.assertRaises(DecisionScaffoldError) as ctx:
            ensure_forcing({"decision_intent": "x", "thesis": "y"})
        message = str(ctx.exception)
        self.assertIn("do_nothing_case", message)
        self.assertIn("risk_if_wrong", message)


class DecisionScaffoldModelTest(unittest.TestCase):
    """The typed Pydantic model that backs ``ensure_forcing``."""

    def test_required_missing_raises(self) -> None:
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            DecisionScaffold.model_validate({"decision_intent": "x", "thesis": "y"})

    def test_blank_required_raises(self) -> None:
        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            DecisionScaffold.model_validate({**VALID_SCAFFOLD, "risk_if_wrong": "   "})

    def test_optional_blank_or_none_excluded_from_dict(self) -> None:
        model = DecisionScaffold.model_validate(
            {**VALID_SCAFFOLD, "emotion": "  ", "review_date": None}
        )
        out = model.to_dict()
        self.assertNotIn("emotion", out)
        self.assertNotIn("review_date", out)

    def test_unknown_field_dropped_not_rejected(self) -> None:
        model = DecisionScaffold.model_validate({**VALID_SCAFFOLD, "unknown": "z"})
        self.assertNotIn("unknown", model.to_dict())

    def test_valid_scaffold_to_dict_equals_legacy_contract(self) -> None:
        # The model's storage form is equivalent to the old normalize() output.
        model = DecisionScaffold.model_validate(VALID_SCAFFOLD)
        self.assertEqual(model.to_dict(), normalize(VALID_SCAFFOLD))
        self.assertEqual(model.to_dict(), VALID_SCAFFOLD)


class CreateGovernedProposalForcingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.receipt_root = self.root / "receipts"
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def test_missing_scaffold_is_fail_closed_and_writes_nothing(self) -> None:
        with self.assertRaises(DecisionScaffoldError):
            create_governed_proposal(
                kind="cash_buffer_low",
                claim="Cash is low",
                evidence={"runway": 1.0},
                engine=self.engine,
                receipt_root=self.receipt_root,
                proposal_id="p_missing",
            )
        # Fail-closed before any persistence: no row, no receipt file.
        self.assertEqual(read_all(Proposal, engine=self.engine), [])
        self.assertFalse((self.receipt_root / "proposals").exists())

    def test_complete_scaffold_persists_in_db_and_receipt(self) -> None:
        write = create_governed_proposal(
            kind="cash_buffer_low",
            claim="Cash is low",
            evidence={"runway": 1.0},
            decision_scaffold=VALID_SCAFFOLD,
            engine=self.engine,
            receipt_root=self.receipt_root,
            proposal_id="p_ok",
        )
        rows = read_all(Proposal, engine=self.engine)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].decision_scaffold, VALID_SCAFFOLD)

        payload = json.loads(Path(write.receipt_ref).read_text(encoding="utf-8"))
        self.assertEqual(payload["proposal"]["decision_scaffold"], VALID_SCAFFOLD)


class DerivedScaffoldTest(unittest.TestCase):
    def test_allocation_candidate_scaffold_is_complete_and_derived(self) -> None:
        candidate = AllocationCandidate(
            detector_kind="concentration_high",
            dimension="stock",
            claim="Top holding is over the concentration threshold.",
            evidence={},
            assumptions=(),
            limitations=(),
            options=(
                CandidateOption(
                    kind="do_nothing",
                    label="Hold the current allocation",
                    cost="concentration risk persists",
                    reversibility="n/a",
                ),
                CandidateOption(
                    kind="stock",
                    label="Trim the top holding (human review)",
                    cost="transaction and possible tax cost",
                    reversibility="hard",
                ),
            ),
            key_risks=("trimming a winner forgoes upside",),
            reversibility="hard",
        )
        scaffold = _candidate_scaffold(candidate)

        self.assertTrue(is_complete(scaffold))
        # Derived, not boilerplate: do-nothing comes from the explicit do_nothing option,
        # risk from the candidate's key risks, intent/thesis from the claim + action.
        self.assertIn("Hold the current allocation", scaffold["do_nothing_case"])
        self.assertIn("forgoes upside", scaffold["risk_if_wrong"])
        self.assertIn("Trim the top holding", scaffold["thesis"])

    def test_daily_change_scaffold_carries_status_and_observation_count(self) -> None:
        observations = (
            Observation(
                kind="material_move",
                detail="SPY moved materially",
                numbers={},
                threshold={},
                crossed=True,
            ),
            Observation(
                kind="concentration",
                detail="concentration crossed",
                numbers={},
                threshold={},
                crossed=True,
            ),
        )
        scaffold = _change_scaffold("material", observations)

        self.assertTrue(is_complete(scaffold))
        self.assertIn("material", scaffold["risk_if_wrong"])
        self.assertIn("2", scaffold["do_nothing_case"])


class ApiForcingTest(unittest.TestCase):
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

    def test_post_without_scaffold_is_422_and_writes_nothing(self) -> None:
        resp = self.client.post(
            "/proposals",
            json={"kind": "rebalance_review", "claim": "Review concentration."},
        )
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(read_all(Proposal, engine=self.engine), [])

    def test_post_with_scaffold_succeeds_and_round_trips(self) -> None:
        resp = self.client.post(
            "/proposals",
            json={
                "kind": "rebalance_review",
                "claim": "Review concentration.",
                "decision_scaffold": VALID_SCAFFOLD,
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["proposal"]["decision_scaffold"], VALID_SCAFFOLD)

    def test_patch_scaffold_adds_counter_evidence_revision_and_unblocks_approval(
        self,
    ) -> None:
        created = self.client.post(
            "/proposals",
            json={
                "kind": "concentration_high",
                "claim": "Top holding is above the user's cap.",
                "evidence": {"top_holding_weight": 0.55},
                "decision_scaffold": VALID_SCAFFOLD,
            },
        )
        self.assertEqual(created.status_code, 200)
        proposal_id = created.json()["proposal"]["proposal_id"]
        first_receipt = created.json()["receipt_ref"]

        blocked = self.client.post(
            f"/proposals/{proposal_id}/attest",
            json={
                "decision": "approved",
                "attester": "Jane Control",
                "reason": "Approval attempted before counter-evidence.",
            },
        )
        self.assertEqual(blocked.status_code, 422)
        self.assertIn("counter_evidence", blocked.json()["detail"])

        revised = self.client.patch(
            f"/proposals/{proposal_id}/decision-scaffold",
            json={
                "attester": "Jane Control",
                "reason": "Added falsification condition before approval.",
                "decision_scaffold": {
                    "counter_evidence": (
                        "If top holding weight falls below 40%, the thesis is stale."
                    )
                },
                "source_refs": ["review-note://weekly-control"],
            },
        )
        self.assertEqual(revised.status_code, 200)
        revised_body = revised.json()
        self.assertFalse(revised_body["execution_allowed"])
        self.assertEqual(revised_body["previous_receipt_ref"], first_receipt)
        self.assertEqual(revised_body["changed_scaffold_fields"], ["counter_evidence"])
        self.assertEqual(
            revised_body["proposal"]["decision_scaffold"]["counter_evidence"],
            "If top holding weight falls below 40%, the thesis is stale.",
        )

        receipt_payload = json.loads(Path(revised_body["receipt_ref"]).read_text(encoding="utf-8"))
        self.assertEqual(receipt_payload["supersedes"], first_receipt)
        self.assertEqual(receipt_payload["revision_context"]["kind"], "decision_scaffold_revision")
        self.assertEqual(receipt_payload["revision_context"]["attester"], "Jane Control")
        self.assertFalse(receipt_payload["revision_context"]["execution_allowed"])

        revisions = self.client.get(f"/proposals/{proposal_id}/revisions")
        self.assertEqual(revisions.status_code, 200)
        self.assertEqual(len(revisions.json()["revisions"]), 2)

        approved = self.client.post(
            f"/proposals/{proposal_id}/attest",
            json={
                "decision": "approved",
                "attester": "Jane Control",
                "reason": "Counter-evidence is now recorded; approval is review-only.",
            },
        )
        self.assertEqual(approved.status_code, 200)
        self.assertFalse(approved.json()["execution_allowed"])

    def test_patch_scaffold_rejects_unknown_or_noop_fields(self) -> None:
        created = self.client.post(
            "/proposals",
            json={
                "kind": "rebalance_review",
                "claim": "Review concentration.",
                "decision_scaffold": VALID_SCAFFOLD,
            },
        )
        self.assertEqual(created.status_code, 200)
        proposal_id = created.json()["proposal"]["proposal_id"]

        unknown = self.client.patch(
            f"/proposals/{proposal_id}/decision-scaffold",
            json={
                "attester": "Jane Control",
                "reason": "Trying an unknown field.",
                "decision_scaffold": {"broker_order_type": "market"},
            },
        )
        self.assertEqual(unknown.status_code, 422)
        self.assertIn("unknown decision-scaffold field", unknown.json()["detail"])

        noop = self.client.patch(
            f"/proposals/{proposal_id}/decision-scaffold",
            json={
                "attester": "Jane Control",
                "reason": "Trying an empty revision.",
                "decision_scaffold": {"counter_evidence": "   "},
            },
        )
        self.assertEqual(noop.status_code, 422)
        self.assertIn("at least one non-blank field", noop.json()["detail"])


if __name__ == "__main__":
    unittest.main()
