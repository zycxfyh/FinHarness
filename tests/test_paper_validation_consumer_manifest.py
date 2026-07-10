"""Contract tests for the paper-validation consumer manifest.

SEC-02A: The paper-validation consumer manifest maps every real consumer
of the deprecated PaperValidation surface to a machine-checkable entry.
The audit module scans the codebase; the manifest is the canonical record.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "governance" / "paper-validation-consumers.json"

SURFACE_ROOTS = [
    "src/finharness/api/routes_paper_validation.py",
    "src/finharness/statecore/paper_accounts.py",
    "src/finharness/statecore/paper_order_tickets.py",
    "src/finharness/statecore/paper_executions.py",
]

EXPECTED_TOP_KEYS = {
    "schema",
    "status",
    "debt_ref",
    "surface_roots",
    "entries",
}
EXPECTED_ENTRY_KEYS = {
    "consumer_id",
    "kind",
    "path",
    "relation",
    "migration_state",
    "deletion_gate",
}
ALLOWED_KINDS = {
    "python_import",
    "api_router_registration",
    "domain_module_self",
    "test_reference",
    "legacy_bridge",
    "governance_reference",
    "architecture_reference",
    "write_registry",
}
ALLOWED_MIGRATION_STATES = {
    "legacy_required",
    "archeology_only",
    "delete_when_no_callers",
    "migrate_to_execution_kernel",
    "keep_until_routes_deleted",
    "remove_when_records_purged",
    "close_debt_when_boundary_complete",
}
SCAN_ROOTS = ["src", "scripts", "tests", "docs", "frontend", "Taskfile.yml"]


class PaperValidationConsumerManifestTest(unittest.TestCase):
    """Contract: manifest exists, has correct structure, and matches reality."""

    def test_manifest_file_exists(self) -> None:
        self.assertTrue(
            MANIFEST_PATH.exists(),
            f"Missing paper-validation consumer manifest: {MANIFEST_PATH}",
        )

    def test_manifest_has_correct_top_level_structure(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(set(manifest), EXPECTED_TOP_KEYS)
        self.assertEqual(
            manifest["schema"],
            "finharness.paper_validation_consumers.v1",
        )
        self.assertEqual(manifest["status"], "current")
        self.assertEqual(manifest["debt_ref"], "ENG-DEBT-0002")
        self.assertEqual(
            set(manifest["surface_roots"]),
            set(SURFACE_ROOTS),
        )

    def test_every_surface_root_exists_on_disk(self) -> None:
        for relative in SURFACE_ROOTS:
            with self.subTest(surface_root=relative):
                self.assertTrue(
                    (ROOT / relative).is_file(),
                    f"Surface root not found: {relative}",
                )

    def test_every_entry_has_required_keys_and_valid_values(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        entries = manifest["entries"]
        self.assertIsInstance(entries, list)
        self.assertGreater(len(entries), 0, "Manifest must have at least one entry")

        seen_ids: set[str] = set()
        for entry in entries:
            consumer_id = entry.get("consumer_id", "")
            with self.subTest(consumer_id=consumer_id):
                self.assertEqual(set(entry), EXPECTED_ENTRY_KEYS)

                # No duplicates
                self.assertNotIn(consumer_id, seen_ids,
                                 f"Duplicate consumer_id: {consumer_id}")
                seen_ids.add(consumer_id)

                # Valid kind
                self.assertIn(entry["kind"], ALLOWED_KINDS,
                              f"Unknown kind: {entry['kind']}")

                # Valid migration state
                self.assertIn(entry["migration_state"], ALLOWED_MIGRATION_STATES,
                              f"Unknown migration_state: {entry['migration_state']}")

                # Path is relative
                path_val = entry["path"]
                self.assertFalse(
                    Path(path_val).is_absolute(),
                    f"Path must be relative: {path_val}",
                )

                # relation and deletion_gate are non-empty strings
                self.assertTrue(entry["relation"].strip(),
                                "relation must not be empty")
                self.assertTrue(entry["deletion_gate"].strip(),
                                "deletion_gate must not be empty")

    def test_every_consumer_path_exists_on_disk(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        for entry in manifest["entries"]:
            path_val = entry["path"]
            with self.subTest(consumer_id=entry["consumer_id"], path=path_val):
                target = ROOT / path_val
                self.assertTrue(
                    target.exists(),
                    f"Consumer path does not exist: {path_val}",
                )

    def test_no_consumer_points_to_deleted_or_archived_file(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        for entry in manifest["entries"]:
            path_val = entry["path"]
            parts = Path(path_val).parts
            with self.subTest(consumer_id=entry["consumer_id"], path=path_val):
                self.assertNotIn(
                    "archive",
                    parts,
                    f"Consumer path must not reference archived file: {path_val}",
                )

    def test_scanner_detects_unregistered_paper_consumer(self) -> None:
        """Negative test: a consumer not in the manifest must be detected."""
        from finharness.paper_validation_boundary_audit import scan_paper_consumers

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            # Create a minimal paper routes module with an unregistered import
            tmp_src = tmp_root / "src" / "finharness" / "api"
            tmp_src.mkdir(parents=True)

            # A fake module that imports from routes_paper_validation
            (tmp_src / "__init__.py").write_text("")
            (tmp_src / "unregistered_consumer.py").write_text(
                "from finharness.api.routes_paper_validation import router\n"
            )

            # Create a fake manifest with no entry for the new consumer
            fake_manifest = tmp_root / "docs" / "governance"
            fake_manifest.mkdir(parents=True)
            (fake_manifest / "paper-validation-consumers.json").write_text(
                json.dumps({
                    "schema": "finharness.paper_validation_consumers.v1",
                    "status": "current",
                    "debt_ref": "ENG-DEBT-0002",
                    "surface_roots": SURFACE_ROOTS,
                    "entries": [
                        {
                            "consumer_id": "api-router-registration",
                            "kind": "api_router_registration",
                            "path": "src/finharness/api/app.py",
                            "relation": "includes_router",
                            "migration_state": "delete_when_no_callers",
                            "deletion_gate": "remove_include_router",
                        }
                    ],
                }),
            )

            findings = scan_paper_consumers(tmp_root)

            unregistered = [
                f for f in findings
                if f["code"] == "unregistered_paper_validation_consumer"
            ]
            self.assertGreater(
                len(unregistered), 0,
                "Scanner must detect consumers not in the manifest. "
                f"Findings: {findings}",
            )


if __name__ == "__main__":
    unittest.main()
