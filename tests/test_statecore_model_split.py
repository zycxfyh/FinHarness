"""Semantic contract for the STATECORE-01 bounded-context extraction."""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from sqlmodel import SQLModel

from finharness.statecore import models
from finharness.statecore import personal_finance_models as personal

ROOT = Path(__file__).resolve().parents[1]


class StateCoreModelSplitTest(unittest.TestCase):
    def test_personal_finance_module_does_not_depend_on_compatibility_models(self) -> None:
        path = ROOT / "src/finharness/statecore/personal_finance_models.py"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        }
        self.assertIn("finharness.statecore.model_base", imported_modules)
        self.assertNotIn("finharness.statecore.models", imported_modules)

    def test_compatibility_reexports_preserve_class_identity(self) -> None:
        names = (
            "Account",
            "Snapshot",
            "Position",
            "Liability",
            "FinancialGoal",
            "CashflowEvent",
            "TaxEvent",
            "InsurancePolicy",
            "DocumentRef",
        )
        for name in names:
            with self.subTest(name=name):
                self.assertIs(getattr(models, name), getattr(personal, name))

    def test_personal_finance_table_metadata_remains_registered(self) -> None:
        expected_tables = {
            "accounts",
            "snapshots",
            "positions",
            "liabilities",
            "financial_goals",
            "cashflow_events",
            "tax_events",
            "insurance_policies",
            "document_refs",
        }
        self.assertTrue(expected_tables.issubset(SQLModel.metadata.tables))


if __name__ == "__main__":
    unittest.main()
