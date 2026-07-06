"""Structural validation for the receipt-backed write registry."""

from __future__ import annotations

import importlib
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "governance" / "receipt-backed-write-registry.json"

REQUIRED_FIELDS = {
    "id",
    "bounded_context",
    "module",
    "file",
    "function",
    "route_refs",
    "db_write_models",
    "db_write_call",
    "receipt_kind",
    "receipt_subdir",
    "receipt_payload_builder",
    "receipt_indexed",
    "receipt_index_builder",
    "stale_guard",
    "failure_cleanup",
    "execution_allowed",
    "behavior_change",
}

ID_PATTERN = re.compile(r"^RBW-\d{4}$")

REPRESENTATIVE_FUNCTIONS = {
    "create_governed_proposal",
    "create_governed_attestation",
    "create_governed_review_event",
    "create_governed_action_intent",
}


def _registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _import_module(module_name: str):
    return importlib.import_module(module_name)


class ReceiptBackedWriteRegistryTest(unittest.TestCase):
    def test_register_file_exists(self) -> None:
        self.assertTrue(REGISTRY.exists(), f"missing registry: {REGISTRY}")

    def test_top_level_shape(self) -> None:
        reg = _registry()
        self.assertEqual(
            reg["schema"], "finharness.receipt_backed_write_registry.v1"
        )
        self.assertEqual(reg["status"], "current")
        self.assertEqual(reg["debt_ref"], "ENG-DEBT-0003")
        self.assertIn("updated", reg)
        self.assertIn("description", reg)

    def test_entries_is_non_empty_list(self) -> None:
        entries = _registry()["entries"]
        self.assertIsInstance(entries, list)
        self.assertGreater(len(entries), 0)

    def test_ids_are_unique(self) -> None:
        ids = [e["id"] for e in _registry()["entries"]]
        self.assertEqual(len(ids), len(set(ids)), f"duplicate IDs: {ids}")

    def test_ids_match_pattern(self) -> None:
        for entry in _registry()["entries"]:
            with self.subTest(entry_id=entry["id"]):
                self.assertRegex(entry["id"], ID_PATTERN)

    def test_every_entry_has_all_required_fields(self) -> None:
        for entry in _registry()["entries"]:
            with self.subTest(entry_id=entry.get("id", "MISSING")):
                actual = set(entry)
                missing = REQUIRED_FIELDS - actual
                self.assertEqual(missing, set(), f"missing fields: {missing}")

    def test_file_paths_exist(self) -> None:
        for entry in _registry()["entries"]:
            path = ROOT / entry["file"]
            with self.subTest(entry_id=entry["id"], file=entry["file"]):
                self.assertTrue(path.exists(), f"file not found: {path}")

    def test_modules_can_be_imported(self) -> None:
        for entry in _registry()["entries"]:
            with self.subTest(entry_id=entry["id"], module=entry["module"]):
                try:
                    _import_module(entry["module"])
                except ImportError as exc:
                    self.fail(f"cannot import {entry['module']}: {exc}")

    def test_functions_exist_on_module(self) -> None:
        for entry in _registry()["entries"]:
            with self.subTest(entry_id=entry["id"], function=entry["function"]):
                mod = _import_module(entry["module"])
                self.assertTrue(
                    hasattr(mod, entry["function"]),
                    f"{entry['module']} has no attribute {entry['function']}",
                )
                self.assertTrue(
                    callable(getattr(mod, entry["function"])),
                    f"{entry['function']} is not callable",
                )

    def test_execution_allowed_is_false(self) -> None:
        for entry in _registry()["entries"]:
            with self.subTest(entry_id=entry["id"]):
                self.assertFalse(entry["execution_allowed"])

    def test_behavior_change_is_false(self) -> None:
        for entry in _registry()["entries"]:
            with self.subTest(entry_id=entry["id"]):
                self.assertFalse(entry["behavior_change"])

    def test_receipt_indexed_is_true(self) -> None:
        for entry in _registry()["entries"]:
            with self.subTest(entry_id=entry["id"]):
                self.assertTrue(entry["receipt_indexed"])

    def test_db_write_models_is_non_empty_and_includes_ReceiptIndex(self) -> None:
        for entry in _registry()["entries"]:
            with self.subTest(entry_id=entry["id"]):
                models = entry["db_write_models"]
                self.assertIsInstance(models, list)
                self.assertGreater(len(models), 0)
                self.assertIn(
                    "ReceiptIndex",
                    models,
                    "every receipt-backed write must include ReceiptIndex in db_write_models",
                )

    def test_receipt_kind_non_empty(self) -> None:
        for entry in _registry()["entries"]:
            with self.subTest(entry_id=entry["id"]):
                self.assertTrue(entry["receipt_kind"].strip())

    def test_receipt_subdir_non_empty(self) -> None:
        for entry in _registry()["entries"]:
            with self.subTest(entry_id=entry["id"]):
                self.assertTrue(entry["receipt_subdir"].strip())

    def test_stale_guard_is_explicit(self) -> None:
        for entry in _registry()["entries"]:
            with self.subTest(entry_id=entry["id"]):
                guard = entry["stale_guard"]
                self.assertTrue(guard.strip())
                if "not applicable" in guard.lower():
                    self.assertIn(
                        "not applicable",
                        guard,
                        f"stale_guard says not applicable without reason: {guard}",
                    )

    def test_failure_cleanup_is_explicit(self) -> None:
        for entry in _registry()["entries"]:
            with self.subTest(entry_id=entry["id"]):
                cleanup = entry["failure_cleanup"]
                self.assertTrue(cleanup.strip())
                if "not applicable" in cleanup.lower():
                    self.assertIn(
                        "not applicable",
                        cleanup,
                        f"failure_cleanup says not applicable without reason: {cleanup}",
                    )

    def test_route_refs_is_non_empty_list(self) -> None:
        for entry in _registry()["entries"]:
            with self.subTest(entry_id=entry["id"]):
                refs = entry["route_refs"]
                self.assertIsInstance(refs, list)
                self.assertGreater(len(refs), 0)

    def test_representative_functions_covered(self) -> None:
        registered = {e["function"] for e in _registry()["entries"]}
        missing = REPRESENTATIVE_FUNCTIONS - registered
        self.assertEqual(
            missing,
            set(),
            f"representative functions not registered: {missing}",
        )

    def test_no_validation_only_posts_in_registry(self) -> None:
        for entry in _registry()["entries"]:
            for route in entry["route_refs"]:
                with self.subTest(entry_id=entry["id"], route=route):
                    self.assertNotIn(
                        "validate",
                        route.lower(),
                        "validation-only POST must not be in receipt-backed write registry",
                    )

    def test_no_read_only_get_in_registry(self) -> None:
        for entry in _registry()["entries"]:
            for route in entry["route_refs"]:
                with self.subTest(entry_id=entry["id"], route=route):
                    method = route.split()[0].upper()
                    self.assertNotEqual(
                        method,
                        "GET",
                        "read-only GET must not be in receipt-backed write registry",
                    )


if __name__ == "__main__":
    unittest.main()
