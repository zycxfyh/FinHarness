from __future__ import annotations

import unittest
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from finharness.statecore.identities import (
    account_identity,
    cross_account_duplicate_findings,
    identity_alias,
    instrument_identity,
)
from finharness.statecore.models import Account, IdentityAlias, Position
from finharness.statecore.store import (
    StateCoreStoreError,
    init_state_core,
    read_all,
    upsert_records,
)


class CanonicalIdentityTest(unittest.TestCase):
    def test_same_account_name_from_two_sources_cannot_collide(self) -> None:
        first, _ = account_identity(source_namespace="broker:alpha", source_native_id="Retirement")
        second, _ = account_identity(source_namespace="ledger:beta", source_native_id="Retirement")
        self.assertNotEqual(first.canonical_account_id, second.canonical_account_id)

    def test_same_symbol_different_venue_or_type_cannot_collide(self) -> None:
        nyse, _ = instrument_identity(
            symbol="ABC",
            instrument_type="equity",
            venue="XNYS",
            quote_currency="USD",
            provider_namespace="feed:a",
        )
        option, _ = instrument_identity(
            symbol="ABC",
            instrument_type="option",
            venue="XNYS",
            quote_currency="USD",
            provider_namespace="feed:a",
        )
        nasdaq, _ = instrument_identity(
            symbol="ABC",
            instrument_type="equity",
            venue="XNAS",
            quote_currency="USD",
            provider_namespace="feed:a",
        )
        self.assertEqual(len({nyse.instrument_id, option.instrument_id, nasdaq.instrument_id}), 3)

    def test_alias_mapping_is_deterministic_auditable_and_versioned(self) -> None:
        kwargs = {
            "identity_kind": "instrument",
            "provider_namespace": "broker:alpha",
            "provider_alias": "ABC.US",
            "canonical_id": "instr_123",
            "source_refs": ["receipt:a"],
        }
        first = identity_alias(**kwargs)
        replay = identity_alias(**kwargs)
        revised = identity_alias(**kwargs, mapping_version="finharness.identity_alias.v1")
        self.assertEqual(first.alias_id, replay.alias_id)
        self.assertEqual(first.canonical_id, replay.canonical_id)
        self.assertNotEqual(first.alias_id, revised.alias_id)
        self.assertEqual(first.source_refs, ["receipt:a"])

    def test_alias_retarget_is_rejected_instead_of_silently_overwritten(self) -> None:
        with TemporaryDirectory() as directory:
            engine = init_state_core(Path(directory) / "state.sqlite")
            first = identity_alias(
                identity_kind="instrument",
                provider_namespace="feed:a",
                provider_alias="ABC",
                canonical_id="instr_first",
            )
            conflict = identity_alias(
                identity_kind="instrument",
                provider_namespace="feed:a",
                provider_alias="ABC",
                canonical_id="instr_other",
            )
            upsert_records([first], engine=engine)
            with self.assertRaisesRegex(StateCoreStoreError, "immutable"):
                upsert_records([conflict], engine=engine)
            aliases = read_all(IdentityAlias, engine=engine)
            self.assertEqual(aliases[0].canonical_id, "instr_first")
            engine.dispose()

    def test_cross_account_duplicate_detection_uses_canonical_keys(self) -> None:
        accounts = [
            Account(
                account_id="provider-a",
                canonical_account_id="acct_shared",
                kind="broker",
                venue="a",
                display_name="Retirement",
            ),
            Account(
                account_id="provider-b",
                canonical_account_id="acct_shared",
                kind="broker",
                venue="b",
                display_name="Retirement",
            ),
        ]
        positions = [
            Position(
                position_id=f"p-{index}",
                snapshot_id="snapshot",
                account_id=account.account_id,
                instrument_id="instr_shared",
                symbol="ABC",
                quantity=Decimal("1"),
                market_value=Decimal("10"),
            )
            for index, account in enumerate(accounts)
        ]
        findings = cross_account_duplicate_findings(accounts=accounts, positions=positions)
        self.assertEqual([finding.code for finding in findings], ["cross_account_duplicate"])
        self.assertEqual(findings[0].severity, "blocking")

    def test_unresolved_identity_is_a_structured_readiness_finding(self) -> None:
        account = Account(
            account_id="legacy",
            kind="broker",
            venue="legacy",
            display_name="Legacy",
        )
        position = Position(
            position_id="legacy-position",
            snapshot_id="snapshot",
            account_id="legacy",
            symbol="ABC",
            quantity=Decimal("1"),
            market_value=Decimal("10"),
        )
        finding = cross_account_duplicate_findings(accounts=[account], positions=[position])[0]
        self.assertEqual(finding.code, "instrument_identity_unresolved")
        self.assertEqual(finding.record_id, "legacy-position")


if __name__ == "__main__":
    unittest.main()
