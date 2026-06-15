from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finharness.receipt_usage_audit import (
    build_receipt_usage_audit,
    collect_references,
    write_receipt_usage_audit,
)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class ReceiptUsageAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        write_json(
            self.root / "data/receipts/risk-gates/r1.json",
            {"kind": "risk_gate_processing", "created_at_utc": "2026-06-01T00:00:00Z"},
        )
        write_json(
            self.root / "data/receipts/executions/e1.json",
            {"kind": "execution_processing", "created_at_utc": "2026-06-01T00:00:00Z"},
        )
        write_json(
            self.root / "data/receipts/validations/v1.json",
            {"kind": "validation_processing", "created_at_utc": "2026-06-01T00:00:00Z"},
        )

        write_text(
            self.root / "docs/reviews/2026-06-review.md",
            "Receipt: data/receipts/risk-gates/r1.json\n",
        )
        write_text(
            self.root / "docs/lessons/drafts/2026-06-draft.md",
            "Source: data/receipts/executions/e1.json\n",
        )
        write_text(
            self.root / "docs/reports/report.md",
            "Missing: data/receipts/missing/nope.json\n",
        )

    def test_collects_normalized_references(self) -> None:
        references = collect_references(self.root)
        self.assertIn("data/receipts/risk-gates/r1.json", references)
        self.assertEqual(
            references["data/receipts/risk-gates/r1.json"][0]["consumer_kind"],
            "review",
        )

    def test_list_shaped_receipt_does_not_crash_audit(self) -> None:
        # gitleaks redacted reports are top-level JSON arrays; the audit must
        # stay robust and classify them by their parent directory, not crash.
        path = self.root / "data/receipts/hardening/latest-gitleaks-redacted.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps([{"RuleID": "x", "File": "y"}]), encoding="utf-8")

        audit = build_receipt_usage_audit(self.root)

        self.assertIn("hardening", audit["summary"]["receipt_kind_counts"])

    def test_audit_classifies_consumed_draft_and_unreferenced(self) -> None:
        audit = build_receipt_usage_audit(self.root)
        by_path = {item["path"]: item for item in audit["receipts"]}

        self.assertEqual(
            by_path["data/receipts/risk-gates/r1.json"]["usage_status"], "consumed"
        )
        self.assertEqual(
            by_path["data/receipts/risk-gates/r1.json"]["evidence_layer"],
            "durable_consumed",
        )
        self.assertEqual(
            by_path["data/receipts/executions/e1.json"]["usage_status"],
            "draft_consumed",
        )
        self.assertEqual(
            by_path["data/receipts/executions/e1.json"]["evidence_layer"],
            "candidate_or_draft",
        )
        self.assertEqual(
            by_path["data/receipts/validations/v1.json"]["usage_status"],
            "unreferenced",
        )
        self.assertEqual(
            by_path["data/receipts/validations/v1.json"]["evidence_layer"],
            "generated_runtime_or_unlinked",
        )
        self.assertEqual(audit["summary"]["missing_reference_count"], 1)
        self.assertEqual(
            audit["summary"]["evidence_surface_counts"],
            {
                "candidate_or_draft": 1,
                "durable_consumed": 1,
                "generated_runtime_or_unlinked": 1,
                "missing_reference": 1,
            },
        )

    def test_write_audit_outputs_receipt_json(self) -> None:
        audit = build_receipt_usage_audit(self.root)
        refs = write_receipt_usage_audit(audit, root=self.root)
        path = Path(refs["receipt"])
        self.assertTrue(path.exists())
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["workflow"], "finharness_receipt_usage_audit_v1")


if __name__ == "__main__":
    unittest.main()
