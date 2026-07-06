"""Structural validation for the governed engineering debt register."""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "governance" / "debt-register.json"

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
    "target_pr",
    "created_at",
    "review_due",
}

OPTIONAL_FIELDS = {
    "resolution_ref",
    "owner",
    "evidence_refs",
    "last_reviewed_at",
}

ALLOWED_STATUSES = {"accepted", "active", "blocked", "resolved", "deferred"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2", "P3"}
ALLOWED_CATEGORIES = {
    "governance-boundary",
    "receipt-integrity",
    "tooling",
    "dependency-management",
    "statecore-structure",
    "frontend-structure",
    "documentation-governance",
}
ALLOWED_SURFACES = {
    "api",
    "paper-validation",
    "statecore",
    "frontend",
    "taskfile",
    "dependencies",
    "toolchain",
    "governance",
}

EXPECTED_DEBT_COUNT = 8
ID_PATTERN = r"^ENG-DEBT-\d{4}$"


def _register() -> dict:
    return json.loads(REGISTER.read_text(encoding="utf-8"))


class DebtRegisterTest(unittest.TestCase):
    def test_register_file_exists(self) -> None:
        self.assertTrue(REGISTER.exists(), f"missing debt register: {REGISTER}")

    def test_register_top_level_shape(self) -> None:
        register = _register()
        self.assertEqual(
            register["schema"], "finharness.engineering_debt_register.v1"
        )
        self.assertEqual(register["status"], "current")
        self.assertIn("updated", register)
        self.assertIn("description", register)

    def test_allowed_values_are_non_empty_sets(self) -> None:
        register = _register()
        self.assertTrue(register["allowed_statuses"])
        self.assertTrue(register["allowed_priorities"])
        self.assertTrue(register["allowed_categories"])
        self.assertTrue(register["allowed_surfaces"])

    def test_allowed_values_match_expected_sets(self) -> None:
        register = _register()
        self.assertEqual(set(register["allowed_statuses"]), ALLOWED_STATUSES)
        self.assertEqual(set(register["allowed_priorities"]), ALLOWED_PRIORITIES)
        self.assertEqual(set(register["allowed_categories"]), ALLOWED_CATEGORIES)
        self.assertEqual(set(register["allowed_surfaces"]), ALLOWED_SURFACES)

    def test_debts_is_non_empty_list(self) -> None:
        debts = _register()["debts"]
        self.assertIsInstance(debts, list)
        self.assertGreater(len(debts), 0)

    def test_debt_count_matches_expected(self) -> None:
        debts = _register()["debts"]
        self.assertEqual(
            len(debts),
            EXPECTED_DEBT_COUNT,
            f"expected {EXPECTED_DEBT_COUNT} debts, got {len(debts)}",
        )

    def test_debt_ids_are_unique(self) -> None:
        ids = [d["id"] for d in _register()["debts"]]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate debt IDs: {ids}")

    def test_debt_ids_match_pattern(self) -> None:
        import re

        pattern = re.compile(ID_PATTERN)
        for debt in _register()["debts"]:
            with self.subTest(debt_id=debt["id"]):
                self.assertRegex(
                    debt["id"],
                    pattern,
                    f"id must match {ID_PATTERN}",
                )

    def test_every_debt_has_all_required_fields(self) -> None:
        for debt in _register()["debts"]:
            with self.subTest(debt_id=debt.get("id", "MISSING_ID")):
                actual = set(debt)
                missing = REQUIRED_FIELDS - actual
                extra = actual - REQUIRED_FIELDS - OPTIONAL_FIELDS
                self.assertEqual(
                    missing,
                    set(),
                    f"missing required fields: {missing}",
                )
                self.assertEqual(
                    extra,
                    set(),
                    f"unexpected extra fields: {extra}",
                )

    def test_status_is_allowed(self) -> None:
        for debt in _register()["debts"]:
            with self.subTest(debt_id=debt["id"]):
                self.assertIn(debt["status"], ALLOWED_STATUSES)

    def test_priority_is_allowed(self) -> None:
        for debt in _register()["debts"]:
            with self.subTest(debt_id=debt["id"]):
                self.assertIn(debt["priority"], ALLOWED_PRIORITIES)

    def test_category_is_allowed(self) -> None:
        for debt in _register()["debts"]:
            with self.subTest(debt_id=debt["id"]):
                self.assertIn(debt["category"], ALLOWED_CATEGORIES)

    def test_surface_is_allowed(self) -> None:
        for debt in _register()["debts"]:
            with self.subTest(debt_id=debt["id"]):
                self.assertIn(debt["surface"], ALLOWED_SURFACES)

    def test_non_goals_is_non_empty_list(self) -> None:
        for debt in _register()["debts"]:
            with self.subTest(debt_id=debt["id"]):
                self.assertIsInstance(debt["non_goals"], list)
                self.assertGreater(
                    len(debt["non_goals"]),
                    0,
                    "non_goals must be a non-empty list",
                )

    def test_accepted_and_active_debts_have_next_action(self) -> None:
        for debt in _register()["debts"]:
            if debt["status"] in ("accepted", "active"):
                with self.subTest(debt_id=debt["id"]):
                    self.assertTrue(
                        debt["next_action"].strip(),
                        f"status={debt['status']} requires next_action",
                    )

    def test_resolved_debts_have_resolution_ref(self) -> None:
        for debt in _register()["debts"]:
            if debt["status"] == "resolved":
                with self.subTest(debt_id=debt["id"]):
                    self.assertIn("resolution_ref", debt)
                    self.assertTrue(
                        str(debt["resolution_ref"]).strip(),
                        "resolved debt requires resolution_ref",
                    )

    def test_dates_are_iso_format(self) -> None:
        for debt in _register()["debts"]:
            with self.subTest(debt_id=debt["id"]):
                date.fromisoformat(debt["created_at"])
                date.fromisoformat(debt["review_due"])

    def test_review_due_not_before_created_at(self) -> None:
        for debt in _register()["debts"]:
            with self.subTest(debt_id=debt["id"]):
                created = date.fromisoformat(debt["created_at"])
                due = date.fromisoformat(debt["review_due"])
                self.assertGreaterEqual(
                    due,
                    created,
                    f"review_due {debt['review_due']} is before created_at {debt['created_at']}",
                )

    def test_blocked_debts_have_blocked_by_entries(self) -> None:
        for debt in _register()["debts"]:
            if debt["status"] == "blocked":
                with self.subTest(debt_id=debt["id"]):
                    self.assertIsInstance(debt["blocked_by"], list)
                    self.assertGreater(
                        len(debt["blocked_by"]),
                        0,
                        "blocked debt must have at least one blocked_by reference",
                    )

    def test_blocked_by_references_are_valid_debt_ids(self) -> None:
        all_ids = {d["id"] for d in _register()["debts"]}
        for debt in _register()["debts"]:
            for ref_id in debt["blocked_by"]:
                with self.subTest(debt_id=debt["id"], blocked_by=ref_id):
                    self.assertIn(
                        ref_id,
                        all_ids,
                        f"blocked_by references unknown debt id: {ref_id}",
                    )

    def test_text_fields_are_non_empty(self) -> None:
        text_fields = (
            "title",
            "current_state",
            "desired_state",
            "risk_if_ignored",
        )
        for debt in _register()["debts"]:
            for field in text_fields:
                with self.subTest(debt_id=debt["id"], field=field):
                    self.assertTrue(
                        str(debt[field]).strip(),
                        f"{field} must be non-empty",
                    )

    def test_blocked_by_and_introduced_by_are_lists(self) -> None:
        for debt in _register()["debts"]:
            with self.subTest(debt_id=debt["id"]):
                self.assertIsInstance(debt["blocked_by"], list)
                if "introduced_by" in debt:
                    self.assertIsInstance(debt["introduced_by"], list)


if __name__ == "__main__":
    unittest.main()
