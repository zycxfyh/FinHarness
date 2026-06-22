from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finharness.authorization import (
    AuthorizationRegistryError,
    authorize,
    credential_field_hits,
    load_authorization_registry,
)


class AuthorizationRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.registry_path = self.root / "authorized-operators.json"
        self.registry_path.write_text(
            json.dumps(
                {
                    "schema_version": "finharness.authorization_registry.v1",
                    "registry_version": "test-v1",
                    "updated_at_utc": "2026-06-18T00:00:00+00:00",
                    "operators": [
                        {
                            "operator_id": "alice",
                            "display_name": "Alice",
                            "scopes": ["risk_review", "paper_execution"],
                            "environments": ["paper"],
                        }
                    ],
                    "accounts": [
                        {
                            "account_id": "acct_paper",
                            "venue": "paper_review",
                            "environment": "paper",
                            "operator_id": "alice",
                            "scopes": ["risk_review"],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        self.addCleanup(self.tmp.cleanup)

    def test_registered_operator_account_scope_environment_is_allowed(self) -> None:
        decision = authorize(
            operator_id="alice",
            account_id="acct_paper",
            environment="paper",
            scope="risk_review",
            registry_path=self.registry_path,
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.registry_version, "test-v1")
        self.assertFalse(decision.execution_allowed)
        self.assertIn("Not execution authorization.", decision.non_claims)

    def test_unregistered_operator_fails_closed(self) -> None:
        decision = authorize(
            operator_id="bob",
            account_id="acct_paper",
            environment="paper",
            scope="risk_review",
            registry_path=self.registry_path,
        )

        self.assertFalse(decision.allowed)
        self.assertIn("operator is not registered", decision.reason)
        self.assertFalse(decision.execution_allowed)

    def test_account_operator_mismatch_fails_closed(self) -> None:
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        payload["operators"].append(
            {
                "operator_id": "bob",
                "display_name": "Bob",
                "scopes": ["risk_review"],
                "environments": ["paper"],
            }
        )
        self.registry_path.write_text(json.dumps(payload), encoding="utf-8")

        decision = authorize(
            operator_id="bob",
            account_id="acct_paper",
            environment="paper",
            scope="risk_review",
            registry_path=self.registry_path,
        )

        self.assertFalse(decision.allowed)
        self.assertIn("belongs to operator alice", decision.reason)

    def test_scope_and_environment_are_fail_closed(self) -> None:
        scope = authorize(
            operator_id="alice",
            account_id="acct_paper",
            environment="paper",
            scope="paper_execution",
            registry_path=self.registry_path,
        )
        environment = authorize(
            operator_id="alice",
            account_id="acct_paper",
            environment="live",
            scope="risk_review",
            registry_path=self.registry_path,
        )

        self.assertFalse(scope.allowed)
        self.assertIn("account acct_paper is not registered for scope", scope.reason)
        self.assertFalse(environment.allowed)
        self.assertIn("environment live", environment.reason)

    def test_missing_registry_returns_blocking_decision(self) -> None:
        decision = authorize(
            operator_id="alice",
            account_id="acct_paper",
            environment="paper",
            scope="risk_review",
            registry_path=self.root / "missing.json",
        )

        self.assertFalse(decision.allowed)
        self.assertIn("authorization registry unreadable", decision.reason)

    def test_registry_rejects_credential_like_field_names(self) -> None:
        bad_path = self.root / "bad.json"
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        payload["operators"][0]["api_token"] = "not-allowed"
        bad_path.write_text(json.dumps(payload), encoding="utf-8")

        with self.assertRaises(AuthorizationRegistryError):
            load_authorization_registry(bad_path)

    def test_default_registry_and_decision_have_no_credential_field_names(self) -> None:
        registry = load_authorization_registry()
        decision = authorize(
            operator_id="paper_operator",
            account_id="paper_account",
            environment="paper",
            scope="risk_review",
        )

        self.assertEqual(credential_field_hits(registry), [])
        self.assertEqual(credential_field_hits(decision), [])
        self.assertTrue(decision.allowed)


if __name__ == "__main__":
    unittest.main()
