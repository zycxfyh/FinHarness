"""Structural and repository-truth validation for engineering debt."""

from __future__ import annotations

import json
import re
import unittest
from datetime import date
from pathlib import Path

import yaml
from scripts.verify_debt_register import VERIFIERS, verify_register

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "governance" / "debt-register.json"
LEGACY_LEDGER = ROOT / "docs" / "governance" / "execution-spine-debt-ledger.yml"

REQUIRED_FIELDS = {
    "id",
    "title",
    "status",
    "priority",
    "category",
    "surface",
    "current_state",
    "desired_state",
    "risk_if_ignored",
    "next_action",
    "non_goals",
    "blocked_by",
    "introduced_by",
    "target_slice",
    "created_at",
    "last_reviewed_at",
    "review_due",
    "evidence_refs",
    "verification",
}
OPTIONAL_FIELDS = {"resolution_ref"}

ALLOWED_STATUSES = {"active", "blocked", "deferred", "resolved"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2", "P3"}
ALLOWED_CATEGORIES = {
    "architecture-inventory",
    "dependency-management",
    "documentation-governance",
    "execution-control",
    "frontend-structure",
    "governance-boundary",
    "receipt-integrity",
    "statecore-structure",
    "tooling",
}
ALLOWED_SURFACES = {
    "api",
    "architecture",
    "dependencies",
    "execution",
    "frontend",
    "paper-validation",
    "statecore",
    "taskfile",
    "toolchain",
}

EXPECTED_DEBT_COUNT = 10
ID_PATTERN = re.compile(r"^ENG-DEBT-\d{4}$")


def _register() -> dict:
    return json.loads(REGISTER.read_text(encoding="utf-8"))


class DebtRegisterTest(unittest.TestCase):
    def test_register_file_exists(self) -> None:
        self.assertTrue(REGISTER.exists(), f"missing debt register: {REGISTER}")

    def test_register_is_the_only_current_ledger(self) -> None:
        register = _register()
        legacy = yaml.safe_load(LEGACY_LEDGER.read_text(encoding="utf-8"))
        self.assertEqual(register["schema"], "finharness.engineering_debt_register.v2")
        self.assertEqual(register["status"], "current")
        self.assertTrue(register["canonical"])
        self.assertEqual(
            register["supersedes"],
            ["docs/governance/execution-spine-debt-ledger.yml"],
        )
        self.assertEqual(legacy["status"], "superseded")
        self.assertEqual(legacy["superseded_by"], "docs/governance/debt-register.json")

    def test_verification_contract_points_to_executable_script(self) -> None:
        contract = _register()["verification_contract"]
        script = ROOT / contract["script"]
        self.assertTrue(script.exists())
        self.assertEqual(script, ROOT / "scripts" / "verify_debt_register.py")
        self.assertTrue(contract["rule"].strip())

    def test_allowed_values_match_schema(self) -> None:
        register = _register()
        self.assertEqual(set(register["allowed_statuses"]), ALLOWED_STATUSES)
        self.assertEqual(set(register["allowed_priorities"]), ALLOWED_PRIORITIES)
        self.assertEqual(set(register["allowed_categories"]), ALLOWED_CATEGORIES)
        self.assertEqual(set(register["allowed_surfaces"]), ALLOWED_SURFACES)

    def test_debt_count_and_ids_are_stable(self) -> None:
        debts = _register()["debts"]
        ids = [debt["id"] for debt in debts]
        self.assertEqual(len(debts), EXPECTED_DEBT_COUNT)
        self.assertEqual(len(ids), len(set(ids)))
        for debt_id in ids:
            with self.subTest(debt_id=debt_id):
                self.assertRegex(debt_id, ID_PATTERN)

    def test_every_debt_has_only_schema_fields(self) -> None:
        for debt in _register()["debts"]:
            with self.subTest(debt_id=debt.get("id", "MISSING_ID")):
                actual = set(debt)
                self.assertEqual(REQUIRED_FIELDS - actual, set())
                self.assertEqual(actual - REQUIRED_FIELDS - OPTIONAL_FIELDS, set())

    def test_enumerated_values_are_allowed(self) -> None:
        for debt in _register()["debts"]:
            with self.subTest(debt_id=debt["id"]):
                self.assertIn(debt["status"], ALLOWED_STATUSES)
                self.assertIn(debt["priority"], ALLOWED_PRIORITIES)
                self.assertIn(debt["category"], ALLOWED_CATEGORIES)
                self.assertIn(debt["surface"], ALLOWED_SURFACES)

    def test_text_and_list_fields_are_non_empty(self) -> None:
        text_fields = (
            "title",
            "current_state",
            "desired_state",
            "risk_if_ignored",
            "next_action",
            "target_slice",
            "verification",
        )
        list_fields = ("introduced_by", "non_goals", "evidence_refs")
        for debt in _register()["debts"]:
            with self.subTest(debt_id=debt["id"]):
                for field in text_fields:
                    self.assertTrue(str(debt[field]).strip(), f"empty {field}")
                for field in list_fields:
                    self.assertIsInstance(debt[field], list)
                    self.assertTrue(debt[field], f"empty {field}")
                self.assertIsInstance(debt["blocked_by"], list)

    def test_evidence_refs_exist(self) -> None:
        for debt in _register()["debts"]:
            for ref in debt["evidence_refs"]:
                with self.subTest(debt_id=debt["id"], evidence_ref=ref):
                    self.assertTrue((ROOT / ref).exists(), f"missing evidence: {ref}")

    def test_named_verifiers_are_complete_and_unique(self) -> None:
        names = [debt["verification"] for debt in _register()["debts"]]
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(set(names), set(VERIFIERS))

    def test_status_claims_match_repository_verifiers(self) -> None:
        self.assertEqual(verify_register(ROOT, REGISTER), [])

    def test_resolved_debts_have_resolution_refs(self) -> None:
        for debt in _register()["debts"]:
            if debt["status"] == "resolved":
                with self.subTest(debt_id=debt["id"]):
                    self.assertTrue(str(debt.get("resolution_ref", "")).strip())
            else:
                self.assertNotIn("resolution_ref", debt)

    def test_dates_are_ordered_iso_dates(self) -> None:
        for debt in _register()["debts"]:
            with self.subTest(debt_id=debt["id"]):
                created = date.fromisoformat(debt["created_at"])
                reviewed = date.fromisoformat(debt["last_reviewed_at"])
                due = date.fromisoformat(debt["review_due"])
                self.assertGreaterEqual(reviewed, created)
                self.assertGreaterEqual(due, reviewed)

    def test_blocked_by_references_are_valid_and_acyclic_at_one_hop(self) -> None:
        debts = {debt["id"]: debt for debt in _register()["debts"]}
        for debt in debts.values():
            if debt["status"] == "blocked":
                self.assertTrue(debt["blocked_by"])
            for ref_id in debt["blocked_by"]:
                with self.subTest(debt_id=debt["id"], blocked_by=ref_id):
                    self.assertIn(ref_id, debts)
                    self.assertNotEqual(ref_id, debt["id"])


if __name__ == "__main__":
    unittest.main()
