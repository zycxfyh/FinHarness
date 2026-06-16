"""Human action: certify the FinHarness control-owner baseline.

The script runs the discipline baseline tests, records their evidence, and writes
a control-owner receipt. Empty owner fails before any receipt is written.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime

from finharness.control_owner import (
    CONTROL_BASELINE_TEST_MODULES,
    ControlCertificationError,
    certify_controls,
)
from finharness.market_data import ROOT


def run_baseline_tests(test_modules: list[str]) -> dict[str, object]:
    command = [
        sys.executable,
        "-m",
        "unittest",
        *test_modules,
    ]
    started_at = datetime.now(UTC)
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    finished_at = datetime.now(UTC)
    combined = "\n".join([result.stdout, result.stderr])
    ran_match = re.search(r"Ran (?P<count>\d+) tests?", combined)
    failure_match = re.search(r"failures=(?P<count>\d+)", combined)
    error_match = re.search(r"errors=(?P<count>\d+)", combined)
    return {
        "command": command,
        "test_modules": test_modules,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
        "returncode": result.returncode,
        "tests_run": int(ran_match.group("count")) if ran_match else 0,
        "failures": int(failure_match.group("count")) if failure_match else 0,
        "errors": int(error_match.group("count")) if error_match else 0,
        "stdout_tail": result.stdout[-4000:],
        "stderr_tail": result.stderr[-4000:],
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Certify FinHarness control-owner discipline baseline."
    )
    parser.add_argument("--owner", required=True)
    parser.add_argument("--cadence-days", type=int, default=30)
    parser.add_argument(
        "--test-module",
        action="append",
        dest="test_modules",
        help="Override/add unittest module for certification evidence.",
    )
    ns = parser.parse_args(argv)

    if not ns.owner.strip():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "certification requires a named human control owner",
                    "receipt_written": False,
                    "execution_allowed": False,
                },
                ensure_ascii=False,
            )
        )
        return 1

    test_modules = ns.test_modules or CONTROL_BASELINE_TEST_MODULES
    baseline_evidence = run_baseline_tests(test_modules)
    baseline_passed = bool(
        baseline_evidence["returncode"] == 0 and baseline_evidence["tests_run"]
    )

    try:
        certification = certify_controls(
            control_owner=ns.owner,
            review_cadence_days=ns.cadence_days,
            baseline_passed=baseline_passed,
            baseline_evidence=baseline_evidence,
        )
    except ControlCertificationError as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "receipt_written": False,
                    "execution_allowed": False,
                },
                ensure_ascii=False,
            )
        )
        return 1

    output = {
        "ok": certification.status == "certified",
        "certification_id": certification.certification_id,
        "status": certification.status,
        "control_owner": certification.control_owner,
        "next_review_due_utc": certification.next_review_due_utc,
        "baseline_evidence": baseline_evidence,
        "receipt_ref": (
            "data/receipts/control-certifications/"
            f"receipt_{certification.certification_id}.json"
        ),
        "non_certification_statement": certification.non_certification_statement,
        "execution_allowed": False,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, default=str))
    return 0 if certification.status == "certified" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
