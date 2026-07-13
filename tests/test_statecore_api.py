# ruff: noqa: C901
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from finharness.api.app import create_app
from finharness.local_operator import LocalOperatorContext
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
            local_operator_context=LocalOperatorContext("test_harness"),
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

    def test_openapi_exposes_only_allowed_non_execution_routes(self) -> None:
        """The local API is read + governed non-execution write.

        Every route must appear in the allowlist with an explicit semantic
        class: ``read``, ``state_changing``, or ``validation_only``.

        No route may carry live-execution, broker-submission, or
        authorization semantics — those are forbidden at the path level and
        asserted below.
        """
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        schema = response.json()
        paths = schema["paths"]

        allowed_routes = {
            "/health": {"methods": {"get": "read"}},
            "/exposure": {"methods": {"get": "read"}},
            "/brief/daily": {"methods": {"get": "read"}},
            "/dashboard/summary": {"methods": {"get": "read"}},
            "/brief/latest": {"methods": {"get": "read"}},
            "/state/accounts": {"methods": {"get": "read"}},
            "/state/positions": {"methods": {"get": "read"}},
            "/state/liabilities": {"methods": {"get": "read"}},
            "/state/goals": {"methods": {"get": "read"}},
            "/state/cashflows": {"methods": {"get": "read"}},
            "/state/tax-events": {"methods": {"get": "read"}},
            "/state/insurance": {"methods": {"get": "read"}},
            "/state/documents": {"methods": {"get": "read"}},
            "/snapshots": {"methods": {"get": "read"}},
            "/diff": {"methods": {"get": "read"}},
            "/receipts": {"methods": {"get": "read"}},
            "/receipts/{receipt_id}": {"methods": {"get": "read"}},
            "/timeline": {"methods": {"get": "read"}},
            "/controls/status": {"methods": {"get": "read"}},
            "/controls/limits": {"methods": {"get": "read"}},
            "/data/catalog": {"methods": {"get": "read"}},
            "/data/catalog/{dataset_key}": {"methods": {"get": "read"}},
            "/data/gaps": {"methods": {"get": "read"}},
            "/data/quality": {"methods": {"get": "read"}},
            "/data/quality/{dataset_key}": {"methods": {"get": "read"}},
            "/data/sources": {"methods": {"get": "read"}},
            "/proposals": {
                "methods": {"get": "read", "post": "state_changing"},
            },
            "/proposals/{proposal_id}": {"methods": {"get": "read"}},
            "/proposals/{proposal_id}/queue-checks": {"methods": {"get": "read"}},
            "/proposals/{proposal_id}/review-task": {"methods": {"get": "read"}},
            "/proposals/{proposal_id}/revisions": {"methods": {"get": "read"}},
            "/proposals/{proposal_id}/decision-scaffold": {
                "methods": {"patch": "state_changing"},
            },
            "/proposals/{proposal_id}/attest": {
                "methods": {"post": "state_changing"},
            },
            "/proposals/{proposal_id}/timeline": {"methods": {"get": "read"}},
            "/proposals/{proposal_id}/review-events": {
                "methods": {"post": "state_changing"},
            },
            "/scaffold-revision-candidates/{candidate_id}/preflight": {
                "methods": {"get": "read"},
            },
            "/scaffold-revision-candidates/{candidate_id}/apply": {
                "methods": {"post": "state_changing"},
            },
            "/proposals/{proposal_id}/action-intents": {
                "methods": {"post": "state_changing"},
            },
            "/action-intents/{action_intent_id}": {"methods": {"get": "read"}},
            "/action-intents/{action_intent_id}/preflight": {
                "methods": {"get": "read"},
            },
            "/action-intents/{action_intent_id}/authority-bindings": {
                "methods": {"post": "state_changing"},
            },
            "/action-intent-authority-bindings/{binding_id}": {
                "methods": {"get": "read"},
            },
            "/action-intents/{action_intent_id}/simulation-reports": {
                "methods": {"post": "state_changing"},
            },
            "/action-intent-simulation-reports/{simulation_report_id}": {
                "methods": {"get": "read"},
            },
            "/action-intent-simulation-reports/{simulation_report_id}/trade-plan-candidates": {
                "methods": {"post": "state_changing"},
            },
            "/trade-plan-candidates/{trade_plan_candidate_id}": {
                "methods": {"get": "read"},
            },
            "/trade-plan-candidates/{trade_plan_candidate_id}/capital-objective-fits": {
                "methods": {"post": "state_changing"},
            },
            "/capital-objective-fits/{capital_objective_fit_id}": {
                "methods": {"get": "read"},
            },
            "/trade-plan-candidates/{trade_plan_candidate_id}/review-gates": {
                "methods": {"post": "state_changing"},
            },
            "/trade-plan-review-gates/{review_gate_id}": {
                "methods": {"get": "read"},
            },
            "/trade-plan-candidates/{trade_plan_candidate_id}/paper-order-ticket-candidates": {
                "methods": {"post": "state_changing"},
            },
            "/paper-order-ticket-candidates": {"methods": {"get": "read"}},
            "/paper-order-ticket-candidates/{paper_order_ticket_id}": {
                "methods": {"get": "read"},
            },
            "/paper-order-ticket-candidates/{paper_order_ticket_id}/simulated-executions": {
                "methods": {"post": "state_changing"},
            },
            "/paper-execution-receipts": {"methods": {"get": "read"}},
            "/paper-execution-receipts/{paper_execution_id}": {
                "methods": {"get": "read"},
            },
            "/paper-accounts": {
                "methods": {"get": "read", "post": "state_changing"},
            },
            "/paper-accounts/{paper_account_id}": {"methods": {"get": "read"}},
            "/paper-accounts/{paper_account_id}/positions": {
                "methods": {"get": "read"},
            },
            "/paper-accounts/{paper_account_id}/execution-applications": {
                "methods": {"post": "state_changing"},
            },
            "/review/retrospective": {"methods": {"get": "read"}},
            "/review/compare-marks": {"methods": {"get": "read"}},
            "/review/queue": {"methods": {"get": "read"}},
            "/risk/register": {"methods": {"get": "read"}},
            "/ips/current": {"methods": {"get": "read"}},
            "/ips/draft": {"methods": {"post": "state_changing"}},
            "/ips/check": {"methods": {"get": "read"}},
            "/capital-mandates": {
                "methods": {"post": "state_changing"},
            },
            "/capital-mandates/current": {"methods": {"get": "read"}},
            "/capital-mandates/{capital_mandate_id}": {"methods": {"get": "read"}},
            "/capital-mandates/{capital_mandate_id}/suspend": {
                "methods": {"post": "state_changing"},
            },
            "/capital-mandates/{capital_mandate_id}/resume": {
                "methods": {"post": "state_changing"},
            },
            "/capital-mandates/{capital_mandate_id}/revoke": {
                "methods": {"post": "state_changing"},
            },
            "/agent-authority-grants": {
                "methods": {"get": "read", "post": "state_changing"},
            },
            "/agent-authority-grants/{grant_id}": {"methods": {"get": "read"}},
            "/agent-authority-grants/{grant_id}/validate": {
                "methods": {"post": "validation_only"},
            },
            # ── Execution Kernel routes ──
            "/execution/order-drafts": {
                "methods": {"post": "state_changing"},
            },
            "/execution/order-drafts/{order_draft_id}/pretrade-checks": {
                "methods": {"post": "state_changing"},
            },
            "/execution/order-drafts/{order_draft_id}/approvals": {
                "methods": {"post": "state_changing"},
            },
            "/execution/order-drafts/{order_draft_id}/stage": {
                "methods": {"post": "state_changing"},
            },
            "/execution/orders/{execution_order_id}/submit": {
                "methods": {"post": "state_changing"},
            },
            "/execution/orders/{execution_order_id}": {
                "methods": {"get": "read"},
            },
            "/execution/orders": {
                "methods": {"get": "read"},
            },
            "/execution/reports/{execution_report_id}": {
                "methods": {"get": "read"},
            },
        }

        # Path set must match exactly.
        self.assertEqual(set(paths), set(allowed_routes))

        # Each path must expose exactly the declared methods.
        for path, spec in allowed_routes.items():
            actual_methods = set(paths[path])
            expected_methods = set(spec["methods"])
            self.assertEqual(
                actual_methods,
                expected_methods,
                f"{path}: expected methods {expected_methods}, got {actual_methods}",
            )

        # Operation-level semantic class assertions.
        read_ops = 0
        state_changing_ops = 0
        validation_only_ops = 0

        for path, spec in allowed_routes.items():
            for method, semantic in spec["methods"].items():
                method_upper = method.upper()
                if semantic == "read":
                    read_ops += 1
                    self.assertEqual(
                        method_upper,
                        "GET",
                        f"read operation at {path} must be GET, got {method_upper}",
                    )
                elif semantic == "state_changing":
                    state_changing_ops += 1
                    self.assertIn(
                        method_upper,
                        {"POST", "PATCH"},
                        f"state_changing at {path} must be POST/PATCH, got {method_upper}",
                    )
                elif semantic == "validation_only":
                    validation_only_ops += 1
                    self.assertEqual(
                        path,
                        "/agent-authority-grants/{grant_id}/validate",
                        "only agent-authority-grant validate may be validation_only",
                    )
                    self.assertEqual(
                        method_upper,
                        "POST",
                        f"validation_only operation at {path} must be POST",
                    )

        self.assertEqual(read_ops, 60, f"expected 60 read ops, got {read_ops}")
        self.assertEqual(
            state_changing_ops,
            26,
            f"expected 26 state_changing ops, got {state_changing_ops}",
        )
        self.assertEqual(
            validation_only_ops,
            1,
            f"expected 1 validation_only op, got {validation_only_ops}",
        )

        # No external live-execution, broker-submission, or authorization endpoints
        # outside the canonical Execution Kernel surface (/execution/*).
        for path in paths:
            if path.startswith("/execution/"):
                continue  # canonical Execution Kernel — allowed
            for forbidden in (
                "authorize",
                "authorization",
                "broker",
                "execute",
                "live",
                "submit",
                "transfer",
            ):
                self.assertNotIn(forbidden, path)

        # Any path containing "order" must be in the paper-only candidate list
        # or in the canonical Execution Kernel surface.
        order_candidate_paths = {
            "/action-intent-simulation-reports/{simulation_report_id}/trade-plan-candidates",
            "/trade-plan-candidates/{trade_plan_candidate_id}",
            "/trade-plan-candidates/{trade_plan_candidate_id}/paper-order-ticket-candidates",
            "/paper-order-ticket-candidates",
            "/paper-order-ticket-candidates/{paper_order_ticket_id}",
            "/paper-order-ticket-candidates/{paper_order_ticket_id}/simulated-executions",
            # Canonical Execution Kernel
            "/execution/order-drafts",
            "/execution/order-drafts/{order_draft_id}/pretrade-checks",
            "/execution/order-drafts/{order_draft_id}/approvals",
            "/execution/order-drafts/{order_draft_id}/stage",
            "/execution/orders/{execution_order_id}",
            "/execution/orders/{execution_order_id}/submit",
            "/execution/orders",
        }
        for path in paths:
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
            "CatalogDetailResponse",
            "CatalogListResponse",
            "DataCatalogEntry",
            "DataGap",
            "DataGapsResponse",
            "DataQualityDetailResponse",
            "DataQualityFinding",
            "DataQualityListResponse",
            "DataQualityReport",
            "DataSourceRegistryEntry",
            "DocumentRef",
            "FinancialGoal",
            "InsurancePolicy",
            "Liability",
            "PaperAccount",
            "PaperAccountCreateRequest",
            "PaperAccountCreateResponse",
            "PaperAccountExecutionApplicationCreateRequest",
            "PaperAccountExecutionApplicationCreateResponse",
            "PaperAccountListResponse",
            "PaperAccountResponse",
            "PaperExecutionCreateRequest",
            "PaperExecutionCreateResponse",
            "PaperExecutionListResponse",
            "PaperExecutionReceipt",
            "PaperOrderTicketCandidate",
            "PaperOrderTicketCandidateCreateRequest",
            "PaperOrderTicketCandidateCreateResponse",
            "PaperOrderTicketCandidateListResponse",
            "PaperOrderTicketCandidateResponse",
            "PaperPosition",
            "PaperPositionListResponse",
            "TradePlanCandidate",
            "Position",
            "Proposal",
            "ReceiptIndex",
            "Snapshot",
            "SourcesResponse",
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
        self.assertTrue(controls.json()["api_execution_endpoints_present"])
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


class WriteCapabilityGateTest(unittest.TestCase):
    """Tests that the write capability gate is fail-closed by default."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "state-core.sqlite"
        self.receipt_root = self.root / "receipts" / "state-core"
        self.engine = init_state_core(self.db_path)
        # fail-closed: no local_operator_context
        self.app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
        )
        self.client = AsgiTestClient(self.app)
        self.addCleanup(self.client.close)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def test_state_changing_without_operator_context_returns_403(self) -> None:
        response = self.client.post(
            "/proposals",
            json={
                "kind": "debt_fix",
                "claim": "should be gated",
                "evidence": {"source": "test"},
            },
        )
        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertEqual(body["detail"]["code"], "write_capability_required")
        self.assertFalse(body["detail"]["execution_allowed"])
        self.assertFalse(body["detail"]["authority_transition"])

    def test_validation_only_post_succeeds_without_operator_context(self) -> None:
        # /agent-authority-grants/{id}/validate is validation_only, not state_changing;
        # it returns a structured validation result (allowed=false) for nonexistent grants
        response = self.client.post(
            "/agent-authority-grants/nonexistent/validate",
            json={"requested_scope": {"allowed_asset_classes": ["crypto"]}},
        )
        # 200 because the validation endpoint runs and returns results
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["allowed"])

    def test_get_routes_succeed_without_operator_context(self) -> None:
        for path in ("/health", "/exposure", "/proposals", "/ips/current"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertIn(response.status_code, {200, 404})

    def test_invalid_operator_context_fails_closed(self) -> None:
        app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
            local_operator_context="not-a-context",  # type: ignore[arg-type]
        )
        client = AsgiTestClient(app)
        self.addCleanup(client.close)
        response = client.post(
            "/proposals",
            json={
                "kind": "debt_fix",
                "claim": "invalid context must not enable writes",
                "evidence": {"source": "test"},
            },
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"]["code"], "write_capability_required"
        )
        self.assertFalse(response.json()["detail"]["execution_allowed"])
        self.assertFalse(response.json()["detail"]["authority_transition"])

    def test_explicit_operator_context_allows_writes(self) -> None:
        app = create_app(
            state_core_engine=self.engine,
            receipt_root=str(self.receipt_root),
            local_operator_context=LocalOperatorContext("test_operator"),
        )
        client = AsgiTestClient(app)
        self.addCleanup(client.close)
        response = client.post(
            "/proposals",
            json={
                "kind": "debt_fix",
                "claim": "with operator context, writes work",
                "evidence": {"source": "test", "options": []},
            },
        )
        self.assertIn(
            response.status_code,
            {200, 422},
            f"gate allowed write but payload may be invalid: {response.status_code}",
        )

    def test_all_state_changing_routes_have_write_capability_dependency(self) -> None:
        """Verify every state_changing route rejects writes without operator context."""

        state_changing_routes = {
            ("POST", "/proposals"),
            ("PATCH", "/proposals/{proposal_id}/decision-scaffold"),
            ("POST", "/proposals/{proposal_id}/attest"),
            ("POST", "/proposals/{proposal_id}/review-events"),
            ("POST", "/scaffold-revision-candidates/{candidate_id}/apply"),
            ("POST", "/proposals/{proposal_id}/action-intents"),
            ("POST", "/action-intents/{action_intent_id}/authority-bindings"),
            ("POST", "/action-intents/{action_intent_id}/simulation-reports"),
            (
                "POST",
                "/action-intent-simulation-reports/{simulation_report_id}"
                "/trade-plan-candidates",
            ),
            (
                "POST",
                "/trade-plan-candidates/{trade_plan_candidate_id}"
                "/capital-objective-fits",
            ),
            ("POST", "/trade-plan-candidates/{trade_plan_candidate_id}/review-gates"),
            (
                "POST",
                "/trade-plan-candidates/{trade_plan_candidate_id}"
                "/paper-order-ticket-candidates",
            ),
            (
                "POST",
                "/paper-order-ticket-candidates/{paper_order_ticket_id}"
                "/simulated-executions",
            ),
            ("POST", "/paper-accounts"),
            ("POST", "/paper-accounts/{paper_account_id}/execution-applications"),
            ("POST", "/agent-authority-grants"),
            ("POST", "/capital-mandates"),
            ("POST", "/capital-mandates/{capital_mandate_id}/suspend"),
            ("POST", "/capital-mandates/{capital_mandate_id}/resume"),
            ("POST", "/capital-mandates/{capital_mandate_id}/revoke"),
            ("POST", "/ips/draft"),
            # Canonical Execution Kernel
            ("POST", "/execution/order-drafts"),
            ("POST", "/execution/order-drafts/{order_draft_id}/pretrade-checks"),
            ("POST", "/execution/order-drafts/{order_draft_id}/approvals"),
            ("POST", "/execution/order-drafts/{order_draft_id}/stage"),
            ("POST", "/execution/orders/{execution_order_id}/submit"),
        }

        # Use OpenAPI schema to verify allowed route set
        openapi = self.client.get("/openapi.json")
        self.assertEqual(openapi.status_code, 200)
        paths = openapi.json()["paths"]

        # Every state_changing route in the OpenAPI must match expectations
        openapi_state_changing = set()
        for path, methods in paths.items():
            for method in methods:
                if method.upper() in ("POST", "PATCH"):
                    openapi_state_changing.add((method.upper(), path))

        missing = state_changing_routes - openapi_state_changing
        extra = openapi_state_changing - state_changing_routes - {
            ("POST", "/agent-authority-grants/{grant_id}/validate"),
        }
        self.assertEqual(missing, set(), f"routes not in OpenAPI: {missing}")
        self.assertEqual(extra, set(), f"unexpected state_changing routes: {extra}")

        # Verify each state_changing handler rejects writes without operator context
        for method, path in state_changing_routes:
            with self.subTest(method=method, path=path):
                # Build a test path with concrete IDs
                test_path = path.replace("{proposal_id}", "nonexistent")
                test_path = test_path.replace("{action_intent_id}", "nonexistent")
                test_path = test_path.replace("{simulation_report_id}", "nonexistent")
                test_path = test_path.replace("{trade_plan_candidate_id}", "nonexistent")
                test_path = test_path.replace("{paper_order_ticket_id}", "nonexistent")
                test_path = test_path.replace("{paper_account_id}", "nonexistent")
                test_path = test_path.replace("{candidate_id}", "nonexistent")
                test_path = test_path.replace("{grant_id}", "nonexistent")
                test_path = test_path.replace("{capital_mandate_id}", "nonexistent")
                test_path = test_path.replace("{binding_id}", "nonexistent")
                test_path = test_path.replace("{review_gate_id}", "nonexistent")
                test_path = test_path.replace("{capital_objective_fit_id}", "nonexistent")

                if method == "POST":
                    response = self.client.post(
                        test_path,
                        json={"placeholder": True},
                    )
                else:
                    response = self.client.patch(
                        test_path,
                        json={"placeholder": True},
                    )
                self.assertEqual(
                    response.status_code,
                    403,
                    f"{method} {path} must return 403 without operator context, "
                    f"got {response.status_code}",
                )

    def test_read_and_validation_only_routes_never_gated(self) -> None:
        """Prove GET and validation-only POST routes are never gated."""
        state_changing = {
            ("POST", "/proposals"),
            ("PATCH", "/proposals/{proposal_id}/decision-scaffold"),
            ("POST", "/proposals/{proposal_id}/attest"),
            ("POST", "/proposals/{proposal_id}/review-events"),
            ("POST", "/scaffold-revision-candidates/{candidate_id}/apply"),
            ("POST", "/proposals/{proposal_id}/action-intents"),
            ("POST", "/action-intents/{action_intent_id}/authority-bindings"),
            ("POST", "/action-intents/{action_intent_id}/simulation-reports"),
            (
                "POST",
                "/action-intent-simulation-reports/{simulation_report_id}"
                "/trade-plan-candidates",
            ),
            (
                "POST",
                "/trade-plan-candidates/{trade_plan_candidate_id}"
                "/capital-objective-fits",
            ),
            ("POST", "/trade-plan-candidates/{trade_plan_candidate_id}/review-gates"),
            (
                "POST",
                "/trade-plan-candidates/{trade_plan_candidate_id}"
                "/paper-order-ticket-candidates",
            ),
            (
                "POST",
                "/paper-order-ticket-candidates/{paper_order_ticket_id}"
                "/simulated-executions",
            ),
            ("POST", "/paper-accounts"),
            ("POST", "/paper-accounts/{paper_account_id}/execution-applications"),
            ("POST", "/agent-authority-grants"),
            ("POST", "/capital-mandates"),
            ("POST", "/capital-mandates/{capital_mandate_id}/suspend"),
            ("POST", "/capital-mandates/{capital_mandate_id}/resume"),
            ("POST", "/capital-mandates/{capital_mandate_id}/revoke"),
            ("POST", "/ips/draft"),
            # Canonical Execution Kernel
            ("POST", "/execution/order-drafts"),
            ("POST", "/execution/order-drafts/{order_draft_id}/pretrade-checks"),
            ("POST", "/execution/order-drafts/{order_draft_id}/approvals"),
            ("POST", "/execution/order-drafts/{order_draft_id}/stage"),
            ("POST", "/execution/orders/{execution_order_id}/submit"),
        }
        validation_only = {("POST", "/agent-authority-grants/{grant_id}/validate")}

        openapi = self.client.get("/openapi.json")
        self.assertEqual(openapi.status_code, 200)
        paths = openapi.json()["paths"]

        for path, methods in paths.items():
            for method in methods:
                key = (method.upper(), path)
                if key in state_changing or key in validation_only:
                    continue
                with self.subTest(method=method.upper(), path=path):
                    if method.upper() == "GET":
                        target = path.replace("{proposal_id}", "nonexistent")
                        target = target.replace("{receipt_id}", "nonexistent")
                        target = target.replace("{dataset_key}", "nonexistent")
                        target = target.replace("{action_intent_id}", "nonexistent")
                        target = target.replace("{binding_id}", "nonexistent")
                        target = target.replace("{simulation_report_id}", "nonexistent")
                        target = target.replace("{trade_plan_candidate_id}", "nonexistent")
                        target = target.replace("{capital_objective_fit_id}", "nonexistent")
                        target = target.replace("{review_gate_id}", "nonexistent")
                        target = target.replace("{paper_order_ticket_id}", "nonexistent")
                        target = target.replace("{paper_execution_id}", "nonexistent")
                        target = target.replace("{paper_account_id}", "nonexistent")
                        target = target.replace("{grant_id}", "nonexistent")
                        target = target.replace("{capital_mandate_id}", "nonexistent")
                        target = target.replace("{candidate_id}", "nonexistent")
                        target = target.replace("{snapshot_id}", "nonexistent")
                        response = self.client.get(target)
                        self.assertNotEqual(
                            response.status_code,
                            403,
                            f"GET {path} must not be gated",
                        )


if __name__ == "__main__":
    unittest.main()
