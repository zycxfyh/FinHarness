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
from finharness.statecore.models import (
    Account,
    CashflowEvent,
    InsurancePolicy,
    Liability,
    Position,
    Proposal,
    ReceiptIndex,
    Snapshot,
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


if __name__ == "__main__":
    unittest.main()
