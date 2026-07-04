from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finharness.api.app import create_app
from finharness.observability import TRACE_HEADER, is_safe_trace_id
from finharness.statecore.models import (
    Account,
    Attestation,
    CashflowEvent,
    DocumentRef,
    FinancialGoal,
    InsurancePolicy,
    Liability,
    Position,
    Proposal,
    ReceiptIndex,
    Snapshot,
    TaxEvent,
)
from finharness.statecore.proposals import create_governed_proposal
from finharness.statecore.store import (
    StateCoreStoreError,
    init_state_core,
    read_all,
    write_records,
)
from tests._scaffold import VALID_SCAFFOLD
from tests.asgi_test_client import AsgiTestClient


class StateCoreApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "state-core.sqlite"
        self.receipt_root = self.root / "receipts" / "state-core"
        self.engine = init_state_core(self.db_path)
        self._seed_state()
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
        )
        self.client = AsgiTestClient(self.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _seed_state(self) -> None:
        account = Account(
            account_id="acct_api",
            kind="broker",
            venue="alpaca-paper",
            display_name="API Account",
            source_refs=["data/receipts/before.json"],
        )
        before = Snapshot(
            snapshot_id="snap_before",
            kind="portfolio",
            as_of_utc="2026-06-17T09:00:00+00:00",
            payload={"source": "broker_read"},
            source_refs=["data/receipts/before.json"],
        )
        after = Snapshot(
            snapshot_id="snap_after",
            kind="portfolio",
            as_of_utc="2026-06-17T10:00:00+00:00",
            payload={"source": "broker_read"},
            source_refs=["data/receipts/after.json"],
        )
        receipt = ReceiptIndex(
            receipt_id="receipt_after",
            kind="broker_read",
            path="data/receipts/after.json",
            created_at_utc="2026-06-17T10:00:00+00:00",
            source_refs=["data/receipts/after.json"],
        )
        brief_receipt = ReceiptIndex(
            receipt_id="receipt_daily_brief",
            kind="daily_change_brief",
            path="data/receipts/daily-change-brief/latest.json",
            created_at_utc="2026-06-17T10:05:00+00:00",
            source_refs=["data/receipts/after.json"],
        )
        positions = [
            Position(
                position_id="pos_before_spy",
                snapshot_id=before.snapshot_id,
                account_id=account.account_id,
                symbol="SPY",
                quantity=1.0,
                market_value=100.0,
                source_refs=["data/receipts/before.json"],
            ),
            Position(
                position_id="pos_after_spy",
                snapshot_id=after.snapshot_id,
                account_id=account.account_id,
                symbol="SPY",
                quantity=1.5,
                market_value=155.0,
                source_refs=["data/receipts/after.json"],
            ),
            Position(
                position_id="pos_after_aapl",
                snapshot_id=after.snapshot_id,
                account_id=account.account_id,
                symbol="AAPL",
                quantity=4.0,
                market_value=80.0,
                source_refs=["data/receipts/after.json"],
            ),
        ]
        liability = Liability(
            liability_id="liab_api",
            name="API Liability",
            liability_type="loan",
            balance=1200.0,
            currency="USD",
            source_refs=["data/receipts/after.json"],
        )
        goal = FinancialGoal(
            goal_id="goal_api",
            name="API Goal",
            target_amount=5000.0,
            current_amount=1250.0,
            currency="USD",
            source_refs=["data/receipts/after.json"],
        )
        cashflow = CashflowEvent(
            cashflow_id="cashflow_api",
            description="API Cashflow",
            amount=250.0,
            currency="USD",
            event_date="2026-06-30",
            category="income",
            source_refs=["data/receipts/after.json"],
        )
        tax_event = TaxEvent(
            tax_event_id="tax_api",
            event_type="estimated_payment",
            jurisdiction="US",
            due_date="2026-06-15",
            estimated_amount=100.0,
            currency="USD",
            source_refs=["data/receipts/after.json"],
        )
        insurance = InsurancePolicy(
            policy_id="policy_api",
            policy_type="home",
            provider="Example Mutual",
            coverage_amount=100000.0,
            premium_amount=1000.0,
            currency="USD",
            source_refs=["data/receipts/after.json"],
        )
        document = DocumentRef(
            document_id="doc_api",
            document_type="insurance_policy",
            title="API Document",
            path="documents/api.pdf",
            related_object_id="policy_api",
            source_refs=["data/receipts/after.json"],
        )
        write_records(
            [
                account,
                before,
                after,
                receipt,
                brief_receipt,
                *positions,
                liability,
                goal,
                cashflow,
                tax_event,
                insurance,
                document,
            ],
            engine=self.engine,
        )

    def test_read_only_state_endpoints_return_pydantic_state_models(self) -> None:
        accounts = self.client.get("/state/accounts")
        positions = self.client.get("/state/positions", params={"snapshot_id": "snap_after"})
        liabilities = self.client.get("/state/liabilities")
        goals = self.client.get("/state/goals")
        cashflows = self.client.get("/state/cashflows")
        tax_events = self.client.get("/state/tax-events")
        insurance = self.client.get("/state/insurance")
        documents = self.client.get("/state/documents")
        snapshots = self.client.get("/snapshots", params={"kind": "portfolio"})
        receipt = self.client.get("/receipts/receipt_after")

        self.assertEqual(accounts.status_code, 200)
        self.assertEqual(accounts.json()[0]["account_id"], "acct_api")

        self.assertEqual(positions.status_code, 200)
        self.assertEqual([row["symbol"] for row in positions.json()], ["AAPL", "SPY"])

        self.assertEqual(liabilities.status_code, 200)
        self.assertEqual(liabilities.json()[0]["liability_id"], "liab_api")

        self.assertEqual(goals.status_code, 200)
        self.assertEqual(goals.json()[0]["goal_id"], "goal_api")

        self.assertEqual(cashflows.status_code, 200)
        self.assertEqual(cashflows.json()[0]["cashflow_id"], "cashflow_api")

        self.assertEqual(tax_events.status_code, 200)
        self.assertEqual(tax_events.json()[0]["tax_event_id"], "tax_api")

        self.assertEqual(insurance.status_code, 200)
        self.assertEqual(insurance.json()[0]["policy_id"], "policy_api")

        self.assertEqual(documents.status_code, 200)
        self.assertEqual(documents.json()[0]["document_id"], "doc_api")

        self.assertEqual(snapshots.status_code, 200)
        self.assertEqual(
            [row["snapshot_id"] for row in snapshots.json()],
            ["snap_before", "snap_after"],
        )

        self.assertEqual(receipt.status_code, 200)
        self.assertEqual(receipt.json()["path"], "data/receipts/after.json")

    def test_diff_endpoint_returns_descriptive_diff_only(self) -> None:
        response = self.client.get(
            "/diff",
            params={
                "before_snapshot_id": "snap_before",
                "after_snapshot_id": "snap_after",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["execution_allowed"])
        self.assertEqual(body["total_market_value_before"], 100.0)
        self.assertEqual(body["total_market_value_after"], 235.0)
        self.assertEqual(body["total_market_value_delta"], 135.0)
        self.assertEqual([row["symbol"] for row in body["added"]], ["AAPL"])
        self.assertEqual([row["symbol"] for row in body["changed"]], ["SPY"])
        self.assertIn("Descriptive state diff only.", body["non_claims"])

    def test_missing_read_targets_return_not_found(self) -> None:
        receipt = self.client.get("/receipts/not_here")
        diff = self.client.get(
            "/diff",
            params={
                "before_snapshot_id": "snap_before",
                "after_snapshot_id": "snap_missing",
            },
        )

        self.assertEqual(receipt.status_code, 404)
        self.assertEqual(diff.status_code, 404)

    def test_openapi_exists_and_exposes_only_read_methods(self) -> None:
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        schema = response.json()
        paths = schema["paths"]
        allowed_methods = {
            "/health": {"get"},
            "/exposure": {"get"},
            "/brief/daily": {"get"},
            "/dashboard/summary": {"get"},
            "/brief/latest": {"get"},
            "/state/accounts": {"get"},
            "/state/positions": {"get"},
            "/state/liabilities": {"get"},
            "/state/goals": {"get"},
            "/state/cashflows": {"get"},
            "/state/tax-events": {"get"},
            "/state/insurance": {"get"},
            "/state/documents": {"get"},
            "/snapshots": {"get"},
            "/diff": {"get"},
            "/receipts": {"get"},
            "/receipts/{receipt_id}": {"get"},
            "/timeline": {"get"},
            "/controls/status": {"get"},
            "/controls/limits": {"get"},
            "/proposals": {"get", "post"},
            "/proposals/{proposal_id}": {"get"},
            "/proposals/{proposal_id}/queue-checks": {"get"},
            "/proposals/{proposal_id}/review-task": {"get"},
            "/proposals/{proposal_id}/revisions": {"get"},
            "/proposals/{proposal_id}/decision-scaffold": {"patch"},
            "/proposals/{proposal_id}/attest": {"post"},
            "/proposals/{proposal_id}/timeline": {"get"},
            "/proposals/{proposal_id}/review-events": {"post"},
            "/scaffold-revision-candidates/{candidate_id}/preflight": {"get"},
            "/scaffold-revision-candidates/{candidate_id}/apply": {"post"},
            "/proposals/{proposal_id}/action-intents": {"post"},
            "/action-intents/{action_intent_id}": {"get"},
            "/action-intents/{action_intent_id}/preflight": {"get"},
            "/action-intents/{action_intent_id}/authority-bindings": {"post"},
            "/action-intent-authority-bindings/{binding_id}": {"get"},
            "/action-intents/{action_intent_id}/simulation-reports": {"post"},
            "/action-intent-simulation-reports/{simulation_report_id}": {"get"},
            "/action-intent-simulation-reports/{simulation_report_id}/trade-plan-candidates": {
                "post"
            },
            "/trade-plan-candidates/{trade_plan_candidate_id}": {"get"},
            "/trade-plan-candidates/{trade_plan_candidate_id}/capital-objective-fits": {"post"},
            "/capital-objective-fits/{capital_objective_fit_id}": {"get"},
            "/trade-plan-candidates/{trade_plan_candidate_id}/review-gates": {"post"},
            "/trade-plan-review-gates/{review_gate_id}": {"get"},
            "/review/retrospective": {"get"},
            "/review/compare-marks": {"get"},
            "/review/queue": {"get"},
            "/risk/register": {"get"},
            "/ips/current": {"get"},
            "/ips/draft": {"post"},
            "/ips/check": {"get"},
            "/capital-mandates": {"post"},
            "/capital-mandates/current": {"get"},
            "/capital-mandates/{capital_mandate_id}": {"get"},
            "/agent-authority-grants": {"get", "post"},
            "/agent-authority-grants/{grant_id}": {"get"},
            "/agent-authority-grants/{grant_id}/validate": {"post"},
        }
        self.assertEqual(set(paths), set(allowed_methods))
        for path, methods in paths.items():
            self.assertEqual(set(methods), allowed_methods[path])
        order_candidate_paths = {
            "/action-intent-simulation-reports/{simulation_report_id}/trade-plan-candidates",
            "/trade-plan-candidates/{trade_plan_candidate_id}",
        }
        for path in paths:
            for forbidden in ("authorize", "execute", "live", "transfer"):
                self.assertNotIn(forbidden, path)
            if "order" in path:
                self.assertIn(path, order_candidate_paths)

        schemas = schema["components"]["schemas"]
        for model_name in (
            "Account",
            "ActionIntent",
            "ActionIntentAuthorityBinding",
            "ActionIntentAuthorityBindingResult",
            "ActionIntentSimulationReport",
            "AgentAuthorityGrant",
            "AgentAuthorityGrantValidationResult",
            "Attestation",
            "CapitalObjectiveFit",
            "CashflowEvent",
            "DocumentRef",
            "FinancialGoal",
            "InsurancePolicy",
            "Liability",
            "TradePlanCandidate",
            "Position",
            "Proposal",
            "ReceiptIndex",
            "Snapshot",
            "TaxEvent",
        ):
            self.assertIn(model_name, schemas)

    def test_health_and_trace_header_are_non_authority_observability(self) -> None:
        response = self.client.get(
            "/health",
            headers={TRACE_HEADER: "trace_test_state_api"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers[TRACE_HEADER], "trace_test_state_api")
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertFalse(body["execution_allowed"])
        self.assertIn("Not execution authorization.", body["non_claims"])

    def test_malformed_trace_header_is_not_echoed(self) -> None:
        malicious = "Bearer sk-1234567890abcdef\nInjected: yes"
        response = self.client.get("/health", headers={TRACE_HEADER: malicious})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(is_safe_trace_id(response.headers[TRACE_HEADER]))
        self.assertNotEqual(response.headers[TRACE_HEADER], malicious)

    def test_cockpit_static_frontend_is_served_by_api_origin(self) -> None:
        frontend_index = Path(__file__).resolve().parents[1] / "frontend" / "index.html"
        mounted_paths = {getattr(route, "path", "") for route in self.app.routes}

        self.assertIn("/cockpit", mounted_paths)
        text = frontend_index.read_text(encoding="utf-8")
        self.assertIn("FinHarness Cockpit", text)
        self.assertIn("execution_allowed=false", text)
        # The Exposure view is wired into the cockpit shell.
        self.assertIn('data-view="exposure"', text)
        self.assertIn('id="exposure-view"', text)

    def test_cockpit_renders_allocation_candidate_detail(self) -> None:
        app_js = Path(__file__).resolve().parents[1] / "frontend" / "app.js"
        text = app_js.read_text(encoding="utf-8")
        # Capital-allocation candidates render their dimension/options/evidence in
        # the existing proposal detail view (no separate Decisions view/endpoint).
        self.assertIn("renderCandidateDetail", text)
        self.assertIn("evidence.options", text)
        self.assertIn("evidence.dimension", text)
        self.assertIn("renderRevisionHistory", text)
        self.assertIn("/revisions", text)
        # Revision history shows a read-only per-version diff (why a candidate changed).
        self.assertIn("describeRevisionChanges", text)
        self.assertIn("Changes from previous", text)

    def test_product_bff_read_endpoints_return_non_authority_summary(self) -> None:
        dashboard = self.client.get("/dashboard/summary")
        brief = self.client.get("/brief/latest")
        receipts = self.client.get("/receipts", params={"kind": "daily_change_brief"})
        timeline = self.client.get("/timeline")
        controls = self.client.get("/controls/status")
        limits = self.client.get("/controls/limits")

        self.assertEqual(dashboard.status_code, 200)
        dashboard_body = dashboard.json()
        self.assertFalse(dashboard_body["execution_allowed"])
        self.assertEqual(dashboard_body["account_count"], 1)
        self.assertEqual(dashboard_body["latest_snapshot_id"], "snap_after")
        self.assertEqual(dashboard_body["position_count"], 2)
        self.assertEqual(dashboard_body["total_market_value"], 235.0)
        self.assertEqual(dashboard_body["latest_brief_receipt_id"], "receipt_daily_brief")
        self.assertEqual(dashboard_body["liability_count"], 1)
        self.assertEqual(dashboard_body["liability_balance_total"], 1200.0)
        self.assertEqual(dashboard_body["goal_count"], 1)
        self.assertEqual(dashboard_body["cashflow_count"], 1)
        self.assertEqual(dashboard_body["tax_event_count"], 1)
        self.assertEqual(dashboard_body["insurance_policy_count"], 1)
        self.assertEqual(dashboard_body["document_count"], 1)
        self.assertIn("Not execution authorization.", dashboard_body["non_claims"])

        self.assertEqual(brief.status_code, 200)
        self.assertFalse(brief.json()["execution_allowed"])
        self.assertTrue(brief.json()["available"])
        self.assertEqual(brief.json()["receipt"]["receipt_id"], "receipt_daily_brief")

        self.assertEqual(receipts.status_code, 200)
        self.assertEqual([row["receipt_id"] for row in receipts.json()], ["receipt_daily_brief"])

        self.assertEqual(timeline.status_code, 200)
        self.assertTrue(timeline.json())
        self.assertTrue(all(not row["execution_allowed"] for row in timeline.json()))
        self.assertIn("receipt:daily_change_brief", {row["event_type"] for row in timeline.json()})

        self.assertEqual(controls.status_code, 200)
        self.assertFalse(controls.json()["execution_allowed"])
        self.assertFalse(controls.json()["api_execution_endpoints_present"])
        self.assertFalse(controls.json()["proposal_approval_is_execution_authorization"])

        self.assertEqual(limits.status_code, 200)
        self.assertFalse(limits.json()["execution_allowed"])
        self.assertFalse(limits.json()["raising_limits_via_api_allowed"])
        self.assertEqual(limits.json()["configured_limits"], [])

    def test_timeline_limit_is_applied(self) -> None:
        full = self.client.get("/timeline")
        limited = self.client.get("/timeline", params={"limit": 1})

        self.assertEqual(full.status_code, 200)
        self.assertGreater(len(full.json()), 1)
        self.assertEqual(limited.status_code, 200)
        self.assertEqual(len(limited.json()), 1)
        # The single entry is the newest across all sources (correct merge).
        self.assertEqual(limited.json()[0], full.json()[0])

    def test_exposure_endpoint_is_read_only_and_internally_consistent(self) -> None:
        response = self.client.get("/exposure")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["execution_allowed"])
        self.assertIn("Not execution authorization.", body["non_claims"])
        # Reflects the seeded liability, and net worth is assets - liabilities.
        self.assertEqual(body["total_liabilities"], 1200.0)
        self.assertAlmostEqual(
            body["net_worth"], body["total_assets"] - body["total_liabilities"], places=6
        )
        self.assertTrue(body["holdings"])

    def test_daily_brief_endpoint_assembles_read_only_sections(self) -> None:
        response = self.client.get("/brief/daily")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["execution_allowed"])
        self.assertIn("Not execution authorization.", body["non_claims"])
        self.assertTrue(body["headline"])
        # P3 v1: ten fixed slots.
        section_titles = [section["title"] for section in body["sections"]]
        self.assertEqual(len(section_titles), 10)
        self.assertIn("Net worth snapshot", section_titles)
        self.assertIn("Concentration risks", section_titles)
        self.assertIn("Do-nothing option", section_titles)
        self.assertIn("Review prompts", section_titles)

    def test_create_proposal_writes_db_receipt_and_index_without_authority(self) -> None:
        response = self.client.post(
            "/proposals",
            json={
                "kind": "rebalance_review",
                "claim": "Review concentration before any human decision.",
                "evidence": {"snapshot_id": "snap_after"},
                "assumptions": {"operator_review": "required"},
                "limitations": {"data_scope": "sample"},
                "non_claims": ["No profitability claim."],
                "source_refs": ["data/receipts/after.json"],
                "decision_scaffold": VALID_SCAFFOLD,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["execution_allowed"])
        self.assertFalse(body["proposal"]["execution_allowed"])
        self.assertIn("Not execution authorization.", body["proposal"]["non_claims"])

        proposals = read_all(Proposal, engine=self.engine)
        receipts = read_all(ReceiptIndex, engine=self.engine)
        self.assertEqual(len(proposals), 1)
        self.assertFalse(proposals[0].execution_allowed)
        self.assertEqual(proposals[0].receipt_ref, body["receipt_ref"])
        self.assertEqual(len(receipts), 3)
        proposal_receipt = next(
            receipt for receipt in receipts if receipt.kind == "state_core_proposal"
        )
        self.assertEqual(proposal_receipt.path, body["receipt_ref"])

        receipt_path = Path(body["receipt_ref"])
        self.assertTrue(receipt_path.exists())
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "state_core_proposal")
        self.assertFalse(payload["governance"]["execution_allowed"])
        self.assertTrue(payload["governance"]["human_review_required"])
        self.assertTrue(payload["governance"]["not_execution_authorization"])

    def test_proposal_request_cannot_smuggle_execution_authority(self) -> None:
        response = self.client.post(
            "/proposals",
            json={
                "kind": "rebalance_review",
                "claim": "Review concentration.",
                "execution_allowed": True,
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(read_all(Proposal, engine=self.engine), [])

    def test_attestation_requires_reason_and_approval_is_not_execution_auth(self) -> None:
        created = self.client.post(
            "/proposals",
            json={
                "kind": "rebalance_review",
                "claim": "Review concentration before any human decision.",
                "source_refs": ["data/receipts/after.json"],
                "decision_scaffold": VALID_SCAFFOLD,
            },
        )
        proposal_id = created.json()["proposal"]["proposal_id"]

        rejected = self.client.post(
            f"/proposals/{proposal_id}/attest",
            json={
                "decision": "approved",
                "attester": "Jane Control",
                "reason": "   ",
            },
        )
        self.assertEqual(rejected.status_code, 422)
        self.assertEqual(read_all(Attestation, engine=self.engine), [])

        position_count = len(read_all(Position, engine=self.engine))
        approved = self.client.post(
            f"/proposals/{proposal_id}/attest",
            json={
                "decision": "approved",
                "attester": "Jane Control",
                "reason": "I reviewed the evidence; this records review only.",
            },
        )

        self.assertEqual(approved.status_code, 200)
        body = approved.json()
        self.assertFalse(body["execution_allowed"])
        self.assertTrue(body["approved_is_not_execution_authorization"])
        self.assertFalse(body["proposal"]["execution_allowed"])
        self.assertEqual(body["attestation"]["decision"], "approved")
        self.assertEqual(len(read_all(Position, engine=self.engine)), position_count)

        proposals = read_all(Proposal, engine=self.engine)
        attestations = read_all(Attestation, engine=self.engine)
        self.assertEqual(len(proposals), 1)
        self.assertEqual(len(attestations), 1)
        self.assertFalse(proposals[0].execution_allowed)
        self.assertIn(proposals[0].receipt_ref, attestations[0].source_refs)

        receipt_path = Path(body["receipt_ref"])
        self.assertTrue(receipt_path.exists())
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "state_core_attestation")
        self.assertFalse(payload["governance"]["execution_allowed"])
        self.assertTrue(payload["governance"]["approved_is_not_execution_authorization"])

    def test_proposal_review_queue_and_detail_remain_non_executing(self) -> None:
        created = self.client.post(
            "/proposals",
            json={
                "kind": "rebalance_review",
                "claim": "Review concentration before any human decision.",
                "source_refs": ["data/receipts/after.json"],
                "decision_scaffold": VALID_SCAFFOLD,
            },
        )
        proposal_id = created.json()["proposal"]["proposal_id"]

        open_list = self.client.get("/proposals", params={"status": "open"})
        detail = self.client.get(f"/proposals/{proposal_id}")

        self.assertEqual(open_list.status_code, 200)
        self.assertEqual(len(open_list.json()), 1)
        self.assertTrue(open_list.json()[0]["open_for_review"])
        self.assertFalse(open_list.json()[0]["execution_allowed"])
        self.assertFalse(open_list.json()[0]["proposal"]["execution_allowed"])
        self.assertEqual(detail.status_code, 200)
        self.assertTrue(detail.json()["open_for_review"])
        self.assertFalse(detail.json()["execution_allowed"])

        approved = self.client.post(
            f"/proposals/{proposal_id}/attest",
            json={
                "decision": "approved",
                "attester": "Jane Control",
                "reason": "I reviewed the evidence; this records review only.",
            },
        )
        attested_list = self.client.get("/proposals", params={"status": "attested"})
        updated_detail = self.client.get(f"/proposals/{proposal_id}")

        self.assertEqual(approved.status_code, 200)
        self.assertEqual(attested_list.status_code, 200)
        self.assertEqual(len(attested_list.json()), 1)
        self.assertFalse(attested_list.json()[0]["open_for_review"])
        self.assertFalse(attested_list.json()[0]["execution_allowed"])
        self.assertEqual(updated_detail.status_code, 200)
        self.assertFalse(updated_detail.json()["open_for_review"])
        self.assertEqual(updated_detail.json()["attestations"][0]["decision"], "approved")
        self.assertFalse(updated_detail.json()["execution_allowed"])

    def test_proposal_revisions_follow_supersedes_chain_without_authority(self) -> None:
        proposal_id = "alloc_cash_buffer_low_2026-06-20"
        first = create_governed_proposal(
            kind="cash_buffer_low",
            claim="Cash covers 1.0 months.",
            evidence={"runway": 1.0},
            source_refs=["data/receipts/snap.json"],
            decision_scaffold=VALID_SCAFFOLD,
            engine=self.engine,
            receipt_root=self.receipt_root,
            proposal_id=proposal_id,
            idempotent=True,
        )
        second = create_governed_proposal(
            kind="cash_buffer_low",
            claim="Cash covers 0.5 months.",
            evidence={"runway": 0.5},
            source_refs=["data/receipts/snap.json"],
            decision_scaffold=VALID_SCAFFOLD,
            engine=self.engine,
            receipt_root=self.receipt_root,
            proposal_id=proposal_id,
            idempotent=True,
        )

        response = self.client.get(f"/proposals/{proposal_id}/revisions")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["execution_allowed"])
        self.assertEqual(body["proposal_id"], proposal_id)
        self.assertEqual(len(body["revisions"]), 2)
        self.assertEqual(body["revisions"][0]["receipt_ref"], second.receipt_ref)
        self.assertEqual(body["revisions"][0]["supersedes"], first.receipt_ref)
        self.assertEqual(body["revisions"][0]["proposal"]["claim"], "Cash covers 0.5 months.")
        self.assertEqual(body["revisions"][1]["receipt_ref"], first.receipt_ref)
        self.assertIsNone(body["revisions"][1]["supersedes"])
        self.assertFalse(body["revisions"][0]["execution_allowed"])
        self.assertFalse(body["revisions"][1]["proposal"]["execution_allowed"])

    def test_proposal_db_failure_cleans_orphan_receipt_best_effort(self) -> None:
        with patch(
            "finharness.statecore.proposals.write_records",
            side_effect=StateCoreStoreError("forced db failure"),
        ):
            response = self.client.post(
                "/proposals",
                json={
                    "kind": "rebalance_review",
                    "claim": "Review concentration before any human decision.",
                    "decision_scaffold": VALID_SCAFFOLD,
                },
            )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(read_all(Proposal, engine=self.engine), [])
        self.assertEqual(list((self.receipt_root / "proposals").glob("*.json")), [])

    def test_attestation_db_failure_cleans_new_receipt_but_keeps_proposal_receipt(self) -> None:
        created = self.client.post(
            "/proposals",
            json={
                "kind": "rebalance_review",
                "claim": "Review concentration before any human decision.",
                "decision_scaffold": VALID_SCAFFOLD,
            },
        )
        proposal_receipt_ref = Path(created.json()["receipt_ref"])
        proposal_id = created.json()["proposal"]["proposal_id"]

        with patch(
            "finharness.statecore.proposals.write_records",
            side_effect=StateCoreStoreError("forced db failure"),
        ):
            response = self.client.post(
                f"/proposals/{proposal_id}/attest",
                json={
                    "decision": "approved",
                    "attester": "Jane Control",
                    "reason": "Review-only approval.",
                },
            )

        self.assertEqual(response.status_code, 500)
        self.assertTrue(proposal_receipt_ref.exists())
        self.assertEqual(read_all(Attestation, engine=self.engine), [])
        self.assertEqual(list((self.receipt_root / "attestations").glob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
