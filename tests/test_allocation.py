from __future__ import annotations

import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from finharness.allocation import (
    compute_allocation_candidates,
    record_allocation_candidates,
)
from finharness.exposure import compute_exposure
from finharness.research_enrichment import ProviderResearchEnricher
from finharness.research_evidence import (
    REQUIRED_NON_CLAIMS,
    ResearchEvidence,
    ResearchEvidenceRequest,
    ResearchEvidenceResult,
)
from finharness.statecore.models import (
    Account,
    CashflowEvent,
    InsurancePolicy,
    Liability,
    Position,
    Proposal,
    ReceiptIndex,
    Snapshot,
    TaxEvent,
)
from finharness.statecore.store import init_state_core, read_all, write_records


class AllocationCandidateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)

    def _seed_triggering(self) -> None:
        account = Account(account_id="brk", kind="broker", venue="m", display_name="Brk")
        snapshot = Snapshot(
            snapshot_id="s", kind="portfolio", as_of_utc="2026-06-19T00:00:00+00:00"
        )
        positions = [
            Position(
                position_id="spy",
                snapshot_id="s",
                account_id="brk",
                symbol="SPY",
                quantity=Decimal("10"),
                market_value=Decimal("8000"),
            ),
            Position(
                position_id="aapl",
                snapshot_id="s",
                account_id="brk",
                symbol="AAPL",
                quantity=Decimal("5"),
                market_value=Decimal("2000"),
            ),
            Position(
                position_id="cash",
                snapshot_id="s",
                account_id="brk",
                symbol="USD",
                quantity=Decimal("5000"),
                market_value=Decimal("5000"),
            ),
        ]
        cashflows = [
            CashflowEvent(
                cashflow_id="salary",
                description="Salary",
                amount=Decimal("5000"),
                currency="USD",
                event_date="2026-07-15",
                category="income",
                frequency="monthly",
            ),
            CashflowEvent(
                cashflow_id="rent",
                description="Rent",
                amount=Decimal("-7000"),
                currency="USD",
                event_date="2026-07-01",
                category="expense",
                frequency="monthly",
            ),
        ]
        write_records([account, snapshot, *positions, *cashflows], engine=self.engine)

    def test_both_detectors_fire_with_governed_non_executing_candidates(self) -> None:
        self._seed_triggering()
        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))

        candidates = compute_allocation_candidates(report)
        by_kind = {candidate.detector_kind: candidate for candidate in candidates}

        # Cash runway 5000 / 2000 = 2.5 months < 6-month target; SPY 8000/15000 = 53% >= 40%.
        self.assertEqual(set(by_kind), {"cash_buffer_low", "concentration_high"})

        cash = by_kind["cash_buffer_low"]
        concentration = by_kind["concentration_high"]
        self.assertEqual(cash.dimension, "flow")
        self.assertEqual(concentration.dimension, "stock")

        for candidate in candidates:
            self.assertFalse(candidate.execution_allowed)
            kinds = [option.kind for option in candidate.options]
            # do-nothing is always present, and flow precedes stock (reversibility order).
            self.assertIn("do_nothing", kinds)
            self.assertLess(kinds.index("flow"), kinds.index("stock"))
            # Evidence is reconstructible, not claimed exact.
            self.assertIn("source_refs", candidate.evidence)
            self.assertEqual(candidate.evidence["as_of_date"], "2026-06-20")
            self.assertIn("float_descriptive", candidate.evidence["metric_precision"])

    def test_rate_exposure_candidate_fires_on_high_rate_debt(self) -> None:
        account = Account(account_id="brk", kind="broker", venue="m", display_name="Brk")
        snapshot = Snapshot(
            snapshot_id="s", kind="portfolio", as_of_utc="2026-06-19T00:00:00+00:00"
        )
        position = Position(
            position_id="cash",
            snapshot_id="s",
            account_id="brk",
            symbol="USD",
            quantity=Decimal("1000"),
            market_value=Decimal("1000"),
        )
        high = Liability(
            liability_id="card",
            name="Card",
            liability_type="card",
            balance=Decimal("5000"),
            currency="USD",
            interest_rate=Decimal("0.18"),
        )
        low = Liability(
            liability_id="mortgage",
            name="Mortgage",
            liability_type="mortgage",
            balance=Decimal("1000"),
            currency="USD",
            interest_rate=Decimal("0.03"),
        )
        write_records([account, snapshot, position, high, low], engine=self.engine)

        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))
        candidates = {c.detector_kind: c for c in compute_allocation_candidates(report)}

        # Blended rate (5000@18% + 1000@3%) / 6000 = 15.5% >= 10% flag.
        self.assertIn("rate_exposure_high", candidates)
        rate = candidates["rate_exposure_high"]
        self.assertEqual(rate.dimension, "stock")
        self.assertFalse(rate.execution_allowed)
        option_kinds = [option.kind for option in rate.options]
        self.assertIn("do_nothing", option_kinds)
        self.assertLess(option_kinds.index("flow"), option_kinds.index("stock"))
        self.assertEqual(rate.evidence["interest_bearing_debt_total"], 6000.0)

    def test_low_rate_debt_does_not_trigger_rate_candidate(self) -> None:
        account = Account(account_id="brk", kind="broker", venue="m", display_name="Brk")
        snapshot = Snapshot(
            snapshot_id="s", kind="portfolio", as_of_utc="2026-06-19T00:00:00+00:00"
        )
        mortgage = Liability(
            liability_id="mortgage",
            name="Mortgage",
            liability_type="mortgage",
            balance=Decimal("100000"),
            currency="USD",
            interest_rate=Decimal("0.04"),
        )
        write_records([account, snapshot, mortgage], engine=self.engine)

        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))
        kinds = {c.detector_kind for c in compute_allocation_candidates(report)}
        self.assertNotIn("rate_exposure_high", kinds)

    def test_cash_overweight_candidate_fires_only_after_buffer_target(self) -> None:
        account = Account(account_id="brk", kind="broker", venue="m", display_name="Brk")
        snapshot = Snapshot(
            snapshot_id="s", kind="portfolio", as_of_utc="2026-06-19T00:00:00+00:00"
        )
        cash = Position(
            position_id="cash",
            snapshot_id="s",
            account_id="brk",
            symbol="USD",
            quantity=Decimal("8000"),
            market_value=Decimal("8000"),
        )
        cashflows = [
            CashflowEvent(
                cashflow_id="salary",
                description="Salary",
                amount=Decimal("4000"),
                currency="USD",
                event_date="2026-07-15",
                category="income",
                frequency="monthly",
            ),
            CashflowEvent(
                cashflow_id="rent",
                description="Rent",
                amount=Decimal("-1000"),
                currency="USD",
                event_date="2026-07-01",
                category="expense",
                frequency="monthly",
            ),
        ]
        write_records([account, snapshot, cash, *cashflows], engine=self.engine)

        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))
        candidates = {c.detector_kind: c for c in compute_allocation_candidates(report)}

        self.assertEqual(set(candidates), {"cash_overweight"})
        candidate = candidates["cash_overweight"]
        self.assertEqual(candidate.dimension, "stock")
        self.assertFalse(candidate.execution_allowed)
        self.assertEqual(candidate.evidence["cash_weight"], 1.0)
        self.assertEqual(candidate.evidence["cash_runway_months"], 8.0)
        self.assertEqual(candidate.evidence["cash_overweight_threshold"], 0.5)
        option_kinds = [option.kind for option in candidate.options]
        self.assertIn("do_nothing", option_kinds)
        self.assertLess(option_kinds.index("flow"), option_kinds.index("stock"))
        self.assertIn("float_descriptive", candidate.evidence["metric_precision"])

    def test_low_cash_runway_blocks_cash_overweight_candidate(self) -> None:
        account = Account(account_id="brk", kind="broker", venue="m", display_name="Brk")
        snapshot = Snapshot(
            snapshot_id="s", kind="portfolio", as_of_utc="2026-06-19T00:00:00+00:00"
        )
        cash = Position(
            position_id="cash",
            snapshot_id="s",
            account_id="brk",
            symbol="USD",
            quantity=Decimal("5000"),
            market_value=Decimal("5000"),
        )
        rent = CashflowEvent(
            cashflow_id="rent",
            description="Rent",
            amount=Decimal("-7000"),
            currency="USD",
            event_date="2026-07-01",
            category="expense",
            frequency="monthly",
        )
        write_records([account, snapshot, cash, rent], engine=self.engine)

        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))
        candidates = {c.detector_kind: c for c in compute_allocation_candidates(report)}

        self.assertIn("cash_buffer_low", candidates)
        self.assertNotIn("cash_overweight", candidates)

    def _insurance_scan(self, *policies: InsurancePolicy):
        write_records(list(policies), engine=self.engine)
        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))
        return report, {c.detector_kind: c for c in compute_allocation_candidates(report)}

    def test_insurance_gap_fires_on_missing_renewal(self) -> None:
        report, candidates = self._insurance_scan(
            InsurancePolicy(
                policy_id="home",
                policy_type="home",
                provider="Acme",
                coverage_amount=Decimal("500000"),
                currency="USD",
                renewal_date=None,
                status="active",
            )
        )
        self.assertIn("insurance_gap", candidates)
        gap = candidates["insurance_gap"]
        self.assertEqual(gap.dimension, "flow")
        self.assertFalse(gap.execution_allowed)
        option_kinds = [option.kind for option in gap.options]
        self.assertIn("do_nothing", option_kinds)
        self.assertLess(option_kinds.index("flow"), option_kinds.index("stock"))
        self.assertTrue(any("missing renewal" in g for g in gap.evidence["review_gaps"]))
        self.assertEqual(report.insurance_active_count, 1)

    def test_insurance_gap_candidate_carries_policy_source_refs(self) -> None:
        # Regression: report.source_refs used to come only from the portfolio
        # snapshot, so insurance-only candidates lost their policy provenance and
        # shipped empty source_refs (breaks the "evidence reconstructible" line).
        report, candidates = self._insurance_scan(
            InsurancePolicy(
                policy_id="home",
                policy_type="home",
                provider="Acme",
                coverage_amount=Decimal("500000"),
                currency="USD",
                renewal_date=None,
                status="active",
                source_refs=["receipt_policy_home"],
            )
        )
        self.assertIn("insurance_gap", candidates)
        evidence_refs = candidates["insurance_gap"].evidence["source_refs"]
        self.assertIn("receipt_policy_home", evidence_refs)
        self.assertIn("receipt_policy_home", report.source_refs)

    def test_insurance_gap_fires_on_expired_renewal(self) -> None:
        _report, candidates = self._insurance_scan(
            InsurancePolicy(
                policy_id="auto",
                policy_type="auto",
                provider="Acme",
                coverage_amount=Decimal("30000"),
                currency="USD",
                renewal_date="2026-01-01",
                status="active",
            )
        )
        self.assertIn("insurance_gap", candidates)
        self.assertTrue(
            any("is past" in g for g in candidates["insurance_gap"].evidence["review_gaps"])
        )

    def test_healthy_active_policy_does_not_fire_insurance_gap(self) -> None:
        _report, candidates = self._insurance_scan(
            InsurancePolicy(
                policy_id="home",
                policy_type="home",
                provider="Acme",
                coverage_amount=Decimal("500000"),
                currency="USD",
                renewal_date="2026-12-01",
                status="active",
            )
        )
        self.assertNotIn("insurance_gap", candidates)

    def test_policies_on_record_but_none_active_fires_insurance_gap(self) -> None:
        report, candidates = self._insurance_scan(
            InsurancePolicy(
                policy_id="old",
                policy_type="home",
                provider="Acme",
                coverage_amount=Decimal("500000"),
                currency="USD",
                renewal_date="2026-12-01",
                status="cancelled",
            )
        )
        self.assertIn("insurance_gap", candidates)
        self.assertTrue(
            any("none active" in g for g in candidates["insurance_gap"].evidence["review_gaps"])
        )
        self.assertEqual(report.insurance_active_count, 0)

    def test_zero_policies_is_data_gap_not_insurance_candidate(self) -> None:
        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))
        kinds = {c.detector_kind for c in compute_allocation_candidates(report)}
        self.assertNotIn("insurance_gap", kinds)
        self.assertIn("no insurance policy on record", report.data_gaps)
        self.assertEqual(report.insurance_active_count, 0)

    def _tax_scan(self, *tax_events: TaxEvent):
        write_records(list(tax_events), engine=self.engine)
        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))
        return report, {c.detector_kind: c for c in compute_allocation_candidates(report)}

    def test_tax_window_fires_on_upcoming_unhandled_deadline(self) -> None:
        _report, candidates = self._tax_scan(
            TaxEvent(
                tax_event_id="q3",
                event_type="estimated_payment",
                jurisdiction="US",
                due_date="2026-07-15",
                estimated_amount=Decimal("1200"),
                currency="USD",
                status="planned",
            )
        )
        self.assertIn("tax_window", candidates)
        tax = candidates["tax_window"]
        self.assertEqual(tax.dimension, "flow")
        self.assertFalse(tax.execution_allowed)
        option_kinds = [option.kind for option in tax.options]
        self.assertIn("do_nothing", option_kinds)
        self.assertLess(option_kinds.index("flow"), option_kinds.index("stock"))
        self.assertTrue(any("within" in g for g in tax.evidence["review_gaps"]))

    def test_tax_window_does_not_fire_when_handled(self) -> None:
        _report, candidates = self._tax_scan(
            TaxEvent(
                tax_event_id="q3",
                event_type="estimated_payment",
                jurisdiction="US",
                due_date="2026-07-15",
                estimated_amount=Decimal("1200"),
                currency="USD",
                status="paid",
            )
        )
        self.assertNotIn("tax_window", candidates)

    def test_tax_window_fires_on_missing_estimated_amount(self) -> None:
        # Far-future due date (beyond the 90-day window) isolates the amount gap.
        _report, candidates = self._tax_scan(
            TaxEvent(
                tax_event_id="q4",
                event_type="estimated_payment",
                jurisdiction="US",
                due_date="2026-12-15",
                estimated_amount=None,
                currency="USD",
                status="planned",
            )
        )
        self.assertIn("tax_window", candidates)
        gaps = candidates["tax_window"].evidence["review_gaps"]
        self.assertTrue(any("amount not recorded" in g for g in gaps))

    def test_tax_window_fires_on_past_due_unhandled(self) -> None:
        _report, candidates = self._tax_scan(
            TaxEvent(
                tax_event_id="q1",
                event_type="estimated_payment",
                jurisdiction="US",
                due_date="2026-01-01",
                estimated_amount=Decimal("500"),
                currency="USD",
                status="planned",
            )
        )
        self.assertIn("tax_window", candidates)
        self.assertTrue(
            any("is past" in g for g in candidates["tax_window"].evidence["review_gaps"])
        )

    def test_tax_window_fires_on_missing_due_date(self) -> None:
        _report, candidates = self._tax_scan(
            TaxEvent(
                tax_event_id="nodate",
                event_type="filing",
                jurisdiction="US",
                due_date="",
                currency="USD",
                status="planned",
            )
        )
        self.assertIn("tax_window", candidates)
        gaps = candidates["tax_window"].evidence["review_gaps"]
        self.assertTrue(any("missing due date" in g for g in gaps))

    def test_tax_window_fires_on_unverifiable_due_date(self) -> None:
        _report, candidates = self._tax_scan(
            TaxEvent(
                tax_event_id="baddate",
                event_type="filing",
                jurisdiction="US",
                due_date="not-a-date",
                currency="USD",
                status="planned",
            )
        )
        self.assertIn("tax_window", candidates)
        gaps = candidates["tax_window"].evidence["review_gaps"]
        self.assertTrue(any("unverifiable due date" in g for g in gaps))

    def test_tax_window_candidate_carries_event_source_refs(self) -> None:
        report, candidates = self._tax_scan(
            TaxEvent(
                tax_event_id="q3",
                event_type="estimated_payment",
                jurisdiction="US",
                due_date="2026-07-15",
                estimated_amount=Decimal("1200"),
                currency="USD",
                status="planned",
                source_refs=["receipt_tax_q3"],
            )
        )
        self.assertIn("tax_window", candidates)
        self.assertIn("receipt_tax_q3", candidates["tax_window"].evidence["source_refs"])
        self.assertIn("receipt_tax_q3", report.source_refs)

    def test_zero_tax_events_is_data_gap_not_tax_candidate(self) -> None:
        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))
        kinds = {c.detector_kind for c in compute_allocation_candidates(report)}
        self.assertNotIn("tax_window", kinds)
        self.assertIn("no tax event on record", report.data_gaps)

    def test_candidate_provenance_is_domain_scoped(self) -> None:
        # Each detector must carry only its own domain's source refs, not a global
        # blob. Distinct refs per domain make any cross-domain leak visible.
        account = Account(account_id="brk", kind="broker", venue="m", display_name="Brk")
        snapshot = Snapshot(
            snapshot_id="s",
            kind="portfolio",
            as_of_utc="2026-06-19T00:00:00+00:00",
            source_refs=["r_snap"],
        )
        write_records(
            [
                account,
                snapshot,
                Position(
                    position_id="spy", snapshot_id="s", account_id="brk", symbol="SPY",
                    quantity=Decimal("10"), market_value=Decimal("8000"), source_refs=["r_sec"],
                ),
                Position(
                    position_id="aapl", snapshot_id="s", account_id="brk", symbol="AAPL",
                    quantity=Decimal("5"), market_value=Decimal("2000"), source_refs=["r_sec"],
                ),
                Position(
                    position_id="cash", snapshot_id="s", account_id="brk", symbol="USD",
                    quantity=Decimal("1000"), market_value=Decimal("1000"), source_refs=["r_cash"],
                ),
                CashflowEvent(
                    cashflow_id="salary", description="Salary", amount=Decimal("1000"),
                    currency="USD", event_date="2026-07-15", category="income",
                    frequency="monthly", source_refs=["r_flow"],
                ),
                CashflowEvent(
                    cashflow_id="rent", description="Rent", amount=Decimal("-3000"),
                    currency="USD", event_date="2026-07-01", category="expense",
                    frequency="monthly", source_refs=["r_flow"],
                ),
                Liability(
                    liability_id="card", name="Card", liability_type="card",
                    balance=Decimal("5000"), currency="USD", interest_rate=Decimal("0.18"),
                    source_refs=["r_liab"],
                ),
                InsurancePolicy(
                    policy_id="home", policy_type="home", provider="Acme",
                    coverage_amount=Decimal("500000"), currency="USD", renewal_date=None,
                    status="active", source_refs=["r_ins"],
                ),
                TaxEvent(
                    tax_event_id="q3", event_type="estimated_payment", jurisdiction="US",
                    due_date="2026-07-15", estimated_amount=Decimal("1200"), currency="USD",
                    status="planned", source_refs=["r_tax"],
                ),
            ],
            engine=self.engine,
        )

        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))
        by_kind = {c.detector_kind: c for c in compute_allocation_candidates(report)}

        def refs(kind: str) -> set[str]:
            return set(by_kind[kind].evidence["source_refs"])

        # Snapshot ref backs the cash total, so cash-domain candidates carry it too.
        self.assertEqual(refs("cash_buffer_low"), {"r_snap", "r_cash", "r_flow"})
        self.assertEqual(refs("concentration_high"), {"r_snap", "r_sec", "r_cash"})
        self.assertEqual(refs("rate_exposure_high"), {"r_liab"})
        self.assertEqual(refs("insurance_gap"), {"r_ins"})
        self.assertEqual(refs("tax_window"), {"r_tax"})
        # Explicit leakage guards across domains.
        self.assertNotIn("r_liab", refs("cash_buffer_low"))
        self.assertNotIn("r_tax", refs("insurance_gap"))
        self.assertNotIn("r_ins", refs("tax_window"))
        self.assertNotIn("r_flow", refs("rate_exposure_high"))
        # Report-level source_refs stays the global union (API invariant).
        self.assertEqual(
            set(report.source_refs),
            {"r_snap", "r_sec", "r_cash", "r_flow", "r_liab", "r_tax", "r_ins"},
        )

    def test_cash_overweight_provenance_includes_cashflow(self) -> None:
        snapshot = Snapshot(
            snapshot_id="s",
            kind="portfolio",
            as_of_utc="2026-06-19T00:00:00+00:00",
            source_refs=["r_snap"],
        )
        write_records(
            [
                Account(account_id="brk", kind="broker", venue="m", display_name="Brk"),
                snapshot,
                Position(
                    position_id="cash", snapshot_id="s", account_id="brk", symbol="USD",
                    quantity=Decimal("8000"), market_value=Decimal("8000"), source_refs=["r_cash"],
                ),
                CashflowEvent(
                    cashflow_id="salary", description="Salary", amount=Decimal("4000"),
                    currency="USD", event_date="2026-07-15", category="income",
                    frequency="monthly", source_refs=["r_flow"],
                ),
                CashflowEvent(
                    cashflow_id="rent", description="Rent", amount=Decimal("-1000"),
                    currency="USD", event_date="2026-07-01", category="expense",
                    frequency="monthly", source_refs=["r_flow"],
                ),
            ],
            engine=self.engine,
        )

        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))
        by_kind = {c.detector_kind: c for c in compute_allocation_candidates(report)}

        # The claim cites cash_runway_months (derived from cashflows), so the
        # candidate must carry the cashflow ref to stay reconstructible.
        self.assertIn("cash_overweight", by_kind)
        overweight_refs = set(by_kind["cash_overweight"].evidence["source_refs"])
        self.assertEqual(overweight_refs, {"r_snap", "r_cash", "r_flow"})
        self.assertIn("r_flow", overweight_refs)

    def test_cash_buffer_does_not_fire_without_a_portfolio_snapshot(self) -> None:
        # Cashflows but no snapshot: cash_total is an unverified 0, so cash_buffer
        # must not assert a runway claim it cannot reconstruct; it becomes a data gap.
        write_records(
            [
                CashflowEvent(
                    cashflow_id="salary", description="Salary", amount=Decimal("1000"),
                    currency="USD", event_date="2026-07-15", category="income",
                    frequency="monthly", source_refs=["r_flow"],
                ),
                CashflowEvent(
                    cashflow_id="rent", description="Rent", amount=Decimal("-3000"),
                    currency="USD", event_date="2026-07-01", category="expense",
                    frequency="monthly", source_refs=["r_flow"],
                ),
            ],
            engine=self.engine,
        )

        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))
        kinds = {c.detector_kind for c in compute_allocation_candidates(report)}

        self.assertNotIn("cash_buffer_low", kinds)
        self.assertFalse(report.cash_total_verified)
        self.assertIn("no portfolio snapshot on record; cash total not verified", report.data_gaps)

    def test_quiet_state_emits_no_candidates(self) -> None:
        # No cashflows -> runway not computed; no holdings -> no concentration.
        report = compute_exposure(self.engine, as_of_date=date(2026, 6, 20))
        self.assertEqual(compute_allocation_candidates(report), ())

    def test_record_writes_governed_proposals_and_is_idempotent(self) -> None:
        self._seed_triggering()
        receipt_root = self.root / "receipts"

        report, writes = record_allocation_candidates(
            self.engine, receipt_root=receipt_root, as_of_date=date(2026, 6, 20)
        )
        self.assertEqual(report.as_of_date, "2026-06-20")
        self.assertEqual(len(writes), 2)
        for write in writes:
            self.assertFalse(write.execution_allowed)

        proposals = read_all(Proposal, engine=self.engine)
        receipts = read_all(ReceiptIndex, engine=self.engine)
        # Detector name goes in Proposal.kind; receipt kind stays state_core_proposal.
        self.assertEqual(
            {proposal.kind for proposal in proposals},
            {"cash_buffer_low", "concentration_high"},
        )
        self.assertTrue(all(not proposal.execution_allowed for proposal in proposals))
        self.assertTrue(
            all(receipt.kind == "state_core_proposal" for receipt in receipts)
        )

        # Re-scan the same as-of date: stable ids upsert, no duplicates.
        record_allocation_candidates(
            self.engine, receipt_root=receipt_root, as_of_date=date(2026, 6, 20)
        )
        self.assertEqual(len(read_all(Proposal, engine=self.engine)), 2)

    def test_default_path_keeps_pre_re3_research_shape(self) -> None:
        # RE3 default (no-op enricher) must not change proposal evidence shape: the
        # research_evidence key stays present and empty (as today), and no gaps key or
        # extra source_refs appear. Omitting/adding a key would change content hashes.
        self._seed_triggering()
        record_allocation_candidates(
            self.engine, receipt_root=self.root / "receipts", as_of_date=date(2026, 6, 20)
        )
        proposals = {p.kind: p for p in read_all(Proposal, engine=self.engine)}
        for kind in ("cash_buffer_low", "concentration_high"):
            evidence = proposals[kind].evidence
            self.assertIn("research_evidence", evidence)
            self.assertEqual(evidence["research_evidence"], [])
            self.assertNotIn("research_evidence_gaps", evidence)

    def test_opt_in_enrichment_attaches_research_only_to_concentration(self) -> None:
        # Capability routing: opt-in enrichment attaches descriptive evidence to the
        # concentration candidate (using its top_symbol) and leaves unrelated candidates
        # untouched — the provider is never called for them.
        self._seed_triggering()
        provider = _RecordingProvider()
        enricher = ProviderResearchEnricher(provider=provider)
        record_allocation_candidates(
            self.engine,
            receipt_root=self.root / "receipts",
            as_of_date=date(2026, 6, 20),
            enricher=enricher,
        )
        proposals = {p.kind: p for p in read_all(Proposal, engine=self.engine)}

        # Only the concentration candidate is routed, with its own top_symbol (SPY).
        self.assertEqual([req.subject for req in provider.calls], ["SPY"])

        concentration = proposals["concentration_high"].evidence
        self.assertEqual(len(concentration["research_evidence"]), 1)
        self.assertEqual(
            concentration["research_evidence"][0]["kind"], "historical_risk_profile"
        )
        # Research source_ref is appended to the proposal-level source_refs.
        self.assertIn(
            "data/receipts/market-data/spy.json",
            proposals["concentration_high"].source_refs,
        )

        # Unrelated candidate: provider not called, shape unchanged.
        self.assertEqual(proposals["cash_buffer_low"].evidence["research_evidence"], [])
        self.assertNotIn(
            "research_evidence_gaps", proposals["cash_buffer_low"].evidence
        )


class _RecordingProvider:
    """Fake RE2 provider for the opt-in wiring test; records requests, returns one item."""

    def __init__(self) -> None:
        self.calls: list[ResearchEvidenceRequest] = []

    def provide(self, request: ResearchEvidenceRequest) -> ResearchEvidenceResult:
        self.calls.append(request)
        item = ResearchEvidence(
            kind="historical_risk_profile",
            claim=(
                f"Over the trailing 3 years, {request.subject}'s observed realized "
                "volatility was 18%."
            ),
            evidence_grade="historical_market_data",
            value={
                "realized_volatility": 0.18,
                "max_drawdown": -0.34,
                "conditional_var": -0.03,
                "average_volume": 1_000_000.0,
            },
            time_window="trailing_3y",
            source_refs=("data/receipts/market-data/spy.json",),
            non_claims=REQUIRED_NON_CLAIMS["historical_market_data"],
        )
        return ResearchEvidenceResult(items=(item,))


if __name__ == "__main__":
    unittest.main()
