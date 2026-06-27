from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_control_certification import main as certification_main

from finharness.control_owner import (
    CONTROL_BASELINE_INVARIANTS,
    NON_CERTIFICATION_STATEMENT,
    ControlCertification,
    ControlCertificationError,
    audit_overdue,
    certify_controls,
    latest_certification,
    load_certifications,
)


def baseline_evidence(returncode: int = 0, tests_run: int = 8) -> dict[str, object]:
    return {
        "command": ["python", "-m", "unittest"],
        "test_modules": ["tests.test_governance_invariants"],
        "returncode": returncode,
        "tests_run": tests_run,
        "failures": 0 if returncode == 0 else 1,
        "errors": 0,
    }


class ControlOwnerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name) / "state"
        self.receipts = Path(self.tmp.name) / "receipts"
        self.addCleanup(self.tmp.cleanup)

    def certify(self, **overrides) -> ControlCertification:
        kwargs = {
            "control_owner": "Jane Control",
            "review_cadence_days": 30,
            "baseline_passed": True,
            "baseline_evidence": baseline_evidence(),
            "state_root": self.state,
            "receipt_root": self.receipts,
            "created_at_utc": "2026-06-16T00:00:00+00:00",
        }
        kwargs.update(overrides)
        return certify_controls(**kwargs)

    def test_empty_owner_is_refused_before_receipt(self) -> None:
        with self.assertRaises(ControlCertificationError):
            self.certify(control_owner="  ")

        self.assertFalse(self.state.exists())
        self.assertFalse(self.receipts.exists())

    def test_successful_baseline_writes_certified_receipt(self) -> None:
        certification = self.certify()

        self.assertEqual(certification.status, "certified")
        self.assertEqual(certification.control_owner, "Jane Control")
        self.assertTrue(certification.baseline_passed)
        self.assertEqual(certification.controls_in_force, CONTROL_BASELINE_INVARIANTS)
        self.assertEqual(certification.next_review_due_utc, "2026-07-16T00:00:00+00:00")
        self.assertNotIn("execution_allowed", ControlCertification.model_fields)

        receipts = list(self.receipts.glob("*.json"))
        self.assertEqual(len(receipts), 1)
        payload = json.loads(receipts[0].read_text(encoding="utf-8"))
        self.assertEqual(payload["kind"], "control_owner_certification")
        self.assertEqual(
            payload["certification"]["certification_id"],
            certification.certification_id,
        )
        self.assertEqual(payload["certification"]["control_owner"], "Jane Control")
        self.assertIn(
            "not live-trading authorization",
            payload["not_claimed"][2].lower(),
        )

    def test_failed_baseline_is_recorded_as_not_certified(self) -> None:
        certification = self.certify(
            baseline_passed=False,
            baseline_evidence=baseline_evidence(returncode=1),
        )

        self.assertEqual(certification.status, "not_certified")
        self.assertFalse(certification.baseline_passed)
        self.assertEqual(len(list(self.receipts.glob("*.json"))), 1)

    def test_load_latest_and_audit_overdue(self) -> None:
        first = self.certify(created_at_utc="2026-06-01T00:00:00+00:00")
        second = self.certify(created_at_utc="2026-06-16T00:00:00+00:00")

        self.assertEqual(len(load_certifications(self.state)), 2)
        self.assertEqual(latest_certification(self.state), second)
        self.assertEqual(
            audit_overdue(now_utc="2026-07-02T00:00:00+00:00", state_root=self.state),
            [first.certification_id],
        )

    def test_non_certification_statement_disclaims_broader_authority(self) -> None:
        lowered = NON_CERTIFICATION_STATEMENT.lower()
        self.assertIn("not sec/finra/legal compliance", lowered)
        self.assertIn("not a release approval", lowered)
        self.assertIn("not live-trading authorization", lowered)

    def test_cli_empty_owner_fails_closed_without_receipt(self) -> None:
        with patch("finharness.control_owner.CONTROL_CERTIFICATION_STATE_ROOT", self.state):
            rc = certification_main(["--owner", " ", "--cadence-days", "30"])

        self.assertEqual(rc, 1)
        self.assertFalse(self.state.exists())

    def test_cli_failed_baseline_exits_nonzero_after_failed_receipt(self) -> None:
        with (
            patch("scripts.run_control_certification.run_baseline_tests") as run_baseline,
            patch("finharness.control_owner.CONTROL_CERTIFICATION_STATE_ROOT", self.state),
            patch("finharness.control_owner.CONTROL_CERTIFICATION_RECEIPT_ROOT", self.receipts),
        ):
            run_baseline.return_value = baseline_evidence(returncode=1)
            rc = certification_main(["--owner", "Jane Control", "--cadence-days", "30"])

        self.assertEqual(rc, 1)
        loaded = load_certifications(self.state)
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].status, "not_certified")


if __name__ == "__main__":
    unittest.main()
