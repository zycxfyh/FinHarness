"""Target contract tests for #374 canonical valuation assessment.

Every test asserts the CORRECT future contract. They FAIL on current main
because adapters derive valuation_status independently and the materializer
does not enforce canonical assessment at the commit boundary.
"""

from __future__ import annotations

import contextlib
import copy
import csv
import json
import re
import tempfile
import unittest
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from finharness.artifact_store import LocalArtifactStore
from finharness.beancount_adapter import ingest_beancount_ledger
from finharness.personal_finance import ingest_personal_finance_export
from finharness.position_valuation import valuation_blockers
from finharness.project_paths import ROOT
from finharness.statecore.models import (
    ImportBatch,
    Position,
    ReceiptIndex,
    ReceiptManifest,
    Snapshot,
)
from finharness.statecore.snapshot_ingest import ingest_broker_read_receipt
from finharness.statecore.store import (
    StateCoreStoreError,
    init_state_core,
    materialize_import_batch,
    read_all,
)

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "valuation"

TYPED_CSV_COLUMNS = [
    "account_id", "account_name", "account_kind", "venue",
    "symbol", "instrument_type", "instrument_venue",
    "quantity", "market_value", "cost_basis", "currency", "as_of_utc",
    "unit_price", "valuation_currency", "price_currency",
    "valued_at_utc", "price_source_ref",
    "fx_rate", "fx_as_of_utc", "fx_source_ref",
    "effective_at_utc", "observed_at_utc",
]

# Full #374 canonical valuation finding closed set.
VALUATION_CODES = frozenset({
    "valuation_unpriced",
    "valuation_fx_missing",
    "valuation_stale",
    "valuation_unknown_legacy",
    "market_value_missing",
    "unit_price_missing",
    "valuation_currency_missing",
    "price_currency_missing",
    "valued_at_utc_missing",
    "price_source_ref_missing",
    "fx_rate_missing",
    "fx_as_of_utc_missing",
    "fx_source_ref_missing",
    "fx_rate_not_positive",
    "valued_at_invalid",
    "valued_at_not_timezone_aware",
    "fx_as_of_invalid",
    "fx_as_of_not_timezone_aware",
    "valuation_components_do_not_reconcile",
    "market_price_stale",
    "fx_stale",
    "valued_at_after_evaluation",
    "fx_as_of_after_evaluation",
})

_VALUATION_CODE_PATTERN = re.compile(
    r"^(valuation_|market_value_|unit_price_|valuation_currency_|"
    r"price_currency_|valued_at_|price_source_|fx_|market_price_)"
)


def _typed_row(overrides: dict | None = None) -> dict[str, str]:
    row = {
        "account_id": "acct", "account_name": "Test", "account_kind": "broker",
        "venue": "test", "symbol": "SPY", "instrument_type": "equity",
        "instrument_venue": "ARCX",
        "quantity": "2", "market_value": "100", "cost_basis": "90",
        "currency": "USD", "as_of_utc": "2025-06-20T08:00:00+00:00",
        "unit_price": "50", "valuation_currency": "USD", "price_currency": "USD",
        "valued_at_utc": "2025-06-20T07:00:00+00:00",
        "price_source_ref": "fixture:test",
        "fx_rate": "", "fx_as_of_utc": "", "fx_source_ref": "",
        "effective_at_utc": "2025-06-20T08:00:00+00:00",
        "observed_at_utc": "2025-06-20T08:00:00+00:00",
    }
    if overrides:
        row.update(overrides)
    return row


def _pos_by_symbol(engine, symbol):
    return next(p for p in read_all(Position, engine=engine) if p.symbol == symbol)


def exactly_one(iterable: Iterable[Any]) -> Any:
    """Return the sole item or raise a decisive AssertionError."""
    items = list(iterable)
    if len(items) != 1:
        raise AssertionError(
            f"expected exactly one match, got {len(items)}: {items!r}"
        )
    return items[0]


def _finding_get(finding: Any, key: str) -> Any:
    if isinstance(finding, dict):
        return finding.get(key)
    return getattr(finding, key, None)


def _normalize_valuation_finding(finding: Any) -> tuple:
    """Normalize to (code, severity, record_type, record_number, field)."""
    return (
        _finding_get(finding, "code") or "",
        _finding_get(finding, "severity") or "",
        _finding_get(finding, "record_type"),
        _finding_get(finding, "record_number"),
        _finding_get(finding, "field"),
    )


def _is_valuation_shaped_code(code: str) -> bool:
    if not code:
        return False
    if code in VALUATION_CODES:
        return True
    if "valuation" in code:
        return True
    if code.endswith("_stale"):
        return True
    return bool(_VALUATION_CODE_PATTERN.match(code))


def _valuation_finding_tuples(findings) -> list[tuple]:
    """Extract closed-set valuation findings as sorted normalized tuples.

    Unknown valuation-shaped codes fail loudly so the contract set is updated.
    """
    tuples: list[tuple] = []
    unknown: list[str] = []
    for finding in findings or ():
        code = _finding_get(finding, "code") or ""
        if code in VALUATION_CODES:
            tuples.append(_normalize_valuation_finding(finding))
        elif _is_valuation_shaped_code(code):
            unknown.append(code)
    if unknown:
        raise AssertionError(
            "unknown valuation finding code(s) not in #374 closed set; "
            f"update VALUATION_CODES contract: {sorted(set(unknown))}"
        )
    return sorted(tuples)


def _assert_import_surface_agreement(
    test, result, engine, artifact_store, *,
    symbol, expected_status, expected_completeness,
    expected_codes,
):
    """Verify batch/snapshot/receipt/result agreement for target Position.

    Selects import surfaces by result identity so multi-batch (delta) DBs work.
    """
    batch = exactly_one(
        batch
        for batch in read_all(ImportBatch, engine=engine)
        if batch.batch_id == result.batch_id
    )
    manifest = exactly_one(
        manifest
        for manifest in read_all(ReceiptManifest, engine=engine)
        if manifest.batch_id == result.batch_id
    )
    snapshot = exactly_one(
        snapshot
        for snapshot in read_all(Snapshot, engine=engine)
        if snapshot.snapshot_id == manifest.snapshot_id
    )
    pos = _pos_by_symbol(engine, symbol)
    test.assertEqual(
        pos.valuation_status,
        expected_status,
        f"{symbol} status: {pos.valuation_status} != {expected_status}",
    )
    bc = batch.completeness_status
    sc = snapshot.payload.get("completeness_status")
    test.assertEqual(bc, expected_completeness)
    test.assertEqual(sc, expected_completeness)
    test.assertEqual(result.completeness_status, expected_completeness)
    receipt_bytes = artifact_store.read(manifest.receipt_artifact_id)
    receipt_payload = json.loads(receipt_bytes)
    rc = receipt_payload.get("completeness_status")
    test.assertEqual(rc, expected_completeness)

    batch_tuples = _valuation_finding_tuples(getattr(batch, "findings", None))
    snap_tuples = _valuation_finding_tuples(snapshot.payload.get("findings"))
    receipt_tuples = _valuation_finding_tuples(receipt_payload.get("findings"))
    test.assertEqual(
        Counter(batch_tuples),
        Counter(snap_tuples),
        f"batch={batch_tuples} != snapshot={snap_tuples}",
    )
    test.assertEqual(
        Counter(batch_tuples),
        Counter(receipt_tuples),
        f"batch={batch_tuples} != receipt={receipt_tuples}",
    )
    present_codes = [item[0] for item in batch_tuples]
    for code in expected_codes:
        test.assertIn(
            code,
            present_codes,
            f"{code} missing from batch valuation findings: {batch_tuples}",
        )
    if not expected_codes:
        test.assertEqual(
            batch_tuples,
            [],
            f"expected empty valuation findings, got {batch_tuples}",
        )


# ============================================================================
# Positive controls
# ============================================================================


class CompleteValuationPositiveControlTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.receipt_root = self.root / "receipts"
        self.store = LocalArtifactStore(self.receipt_root / "artifact-store")

    def _csv(self, rows):
        path = self.root / "export.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TYPED_CSV_COLUMNS)
            w.writeheader()
            for row in rows:
                w.writerow(row)
        return path

    def test_complete_direct_valuation_passes(self):
        result = ingest_personal_finance_export(
            self._csv([_typed_row()]), engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        pos = _pos_by_symbol(self.engine, "SPY")
        self.assertEqual(pos.valuation_status, "valued")
        self.assertEqual(valuation_blockers(pos), ())
        self.assertEqual(result.completeness_status, "complete")
        _assert_import_surface_agreement(
            self, result, self.engine, self.store,
            symbol="SPY", expected_status="valued",
            expected_completeness="complete",
            expected_codes=(),
        )

    def test_complete_converted_valuation_passes(self):
        result = ingest_personal_finance_export(
            self._csv([_typed_row({
                "valuation_currency": "USD", "price_currency": "EUR",
                "unit_price": "50", "market_value": "110",
                "fx_rate": "1.10", "fx_as_of_utc": "2025-06-20T07:00:00+00:00",
                "fx_source_ref": "fixture:fx",
            })]), engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )
        pos = _pos_by_symbol(self.engine, "SPY")
        self.assertEqual(pos.valuation_status, "valued_converted")
        self.assertEqual(valuation_blockers(pos), ())
        self.assertEqual(result.completeness_status, "complete")
        _assert_import_surface_agreement(
            self, result, self.engine, self.store,
            symbol="SPY", expected_status="valued_converted",
            expected_completeness="complete",
            expected_codes=(),
        )


class BrokerSnapshotTimePositiveControlTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.import_root = (
            self.root / "receipts" / "capital-imports" / "broker-read")
        self.store = LocalArtifactStore(self.import_root / "artifact-store")

    def test_snapshot_wide_valuation_time_is_inherited(self):
        payload = {
            "receipt_id": "rec", "kind": "broker_read",
            "created_at_utc": "2025-06-20T09:00:00+00:00",
            "effective_at_utc": "2025-06-20T09:00:00+00:00",
            "observed_at_utc": "2025-06-20T09:00:00+00:00",
            "valued_at_utc": "2025-06-20T09:00:00+00:00",
            "broker": "manual", "environment": "paper",
            "account": {"id": "acct", "status": "ACTIVE"},
            "positions": [{
                "symbol": "SPY", "qty": "2", "market_value": "100",
                "unit_price": "50", "currency": "USD",
                "asset_class": "equity", "exchange": "ARCX",
                "price_source_ref": "fixture:test",
            }],
        }
        path = self.root / "broker-read" / "portfolio.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        result = ingest_broker_read_receipt(
            path, engine=self.engine,
            receipt_root=self.import_root, artifact_store=self.store,
        )
        pos = _pos_by_symbol(self.engine, "SPY")
        self.assertEqual(pos.valued_at_utc, "2025-06-20T09:00:00+00:00")
        self.assertEqual(pos.valuation_status, "valued")
        self.assertEqual(valuation_blockers(pos), ())
        self.assertEqual(result.completeness_status, "complete")
        _assert_import_surface_agreement(
            self, result, self.engine, self.store,
            symbol="SPY", expected_status="valued",
            expected_completeness="complete",
            expected_codes=(),
        )


# ============================================================================
# CSV contract tests
# ============================================================================


class CsvValuationContractTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.receipt_root = self.root / "receipts"
        self.store = LocalArtifactStore(self.receipt_root / "artifact-store")

    def _csv(self, rows):
        path = self.root / "export.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TYPED_CSV_COLUMNS)
            w.writeheader()
            for row in rows:
                w.writerow(row)
        return path

    def _ingest(self, rows):
        return ingest_personal_finance_export(
            self._csv(rows), engine=self.engine,
            receipt_root=self.receipt_root,
            artifact_store=self.store,
        )

    def test_missing_valued_at_utc_produces_unpriced_and_blocked(self):
        result = self._ingest([_typed_row({"valued_at_utc": ""})])
        pos = _pos_by_symbol(self.engine, "SPY")
        self.assertIsNone(pos.valued_at_utc)
        self.assertEqual(pos.valuation_status, "unpriced")
        blockers = valuation_blockers(pos)
        self.assertIn("valued_at_utc_missing", blockers)
        self.assertEqual(result.completeness_status, "blocked")
        _assert_import_surface_agreement(
            self, result, self.engine, self.store,
            symbol="SPY", expected_status="unpriced",
            expected_completeness="blocked",
            expected_codes={"valued_at_utc_missing"},
        )

    def test_missing_price_source_ref_produces_unpriced_and_blocked(self):
        result = self._ingest([_typed_row({"price_source_ref": ""})])
        pos = _pos_by_symbol(self.engine, "SPY")
        self.assertIsNone(pos.price_source_ref)
        self.assertEqual(pos.valuation_status, "unpriced")
        blockers = valuation_blockers(pos)
        self.assertIn("price_source_ref_missing", blockers)
        self.assertEqual(result.completeness_status, "blocked")
        _assert_import_surface_agreement(
            self, result, self.engine, self.store,
            symbol="SPY", expected_status="unpriced",
            expected_completeness="blocked",
            expected_codes={"price_source_ref_missing"},
        )

    def test_component_mismatch_produces_unpriced_and_blocked(self):
        result = self._ingest([_typed_row({"market_value": "99"})])
        pos = _pos_by_symbol(self.engine, "SPY")
        expected_calc = pos.quantity * pos.unit_price
        self.assertNotEqual(expected_calc, pos.market_value)
        self.assertNotEqual(pos.valuation_status, "valued")
        blockers = valuation_blockers(pos)
        self.assertIn("valuation_components_do_not_reconcile", blockers)
        self.assertEqual(result.completeness_status, "blocked")
        _assert_import_surface_agreement(
            self, result, self.engine, self.store,
            symbol="SPY", expected_status="unpriced",
            expected_completeness="blocked",
            expected_codes={"valuation_components_do_not_reconcile"},
        )


# ============================================================================
# Broker contract tests
# ============================================================================


class BrokerValuationContractTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.import_root = (
            self.root / "receipts" / "capital-imports" / "broker-read")
        self.store = LocalArtifactStore(self.import_root / "artifact-store")

    def _base_payload(self):
        return {
            "receipt_id": "rec", "kind": "broker_read",
            "created_at_utc": "2025-06-20T09:00:00+00:00",
            "effective_at_utc": "2025-06-20T09:00:00+00:00",
            "observed_at_utc": "2025-06-20T09:00:00+00:00",
            "valued_at_utc": "2025-06-20T09:00:00+00:00",
            "broker": "manual", "environment": "paper",
            "account": {"id": "acct", "status": "ACTIVE"},
            "positions": [{
                "symbol": "SPY", "qty": "2", "market_value": "100",
                "unit_price": "50", "currency": "USD",
                "asset_class": "equity", "exchange": "ARCX",
                "price_source_ref": "fixture:test",
            }],
        }

    def _ingest(self, payload):
        path = self.root / "broker-read" / "portfolio.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return ingest_broker_read_receipt(
            path, engine=self.engine,
            receipt_root=self.import_root, artifact_store=self.store,
        )

    def test_component_mismatch_produces_unpriced(self):
        payload = self._base_payload()
        payload["positions"][0]["market_value"] = "99"
        self._ingest(payload)
        pos = _pos_by_symbol(self.engine, "SPY")
        expected = pos.quantity * pos.unit_price
        self.assertNotEqual(expected, pos.market_value)
        self.assertNotEqual(pos.valuation_status, "valued")


# ============================================================================
# Canonical blocker isolation
# ============================================================================


class ValuationBlockersIsolationTest(unittest.TestCase):

    def test_stored_valued_with_missing_time_not_admitted(self):
        pos = Position(
            position_id="pos_iso", snapshot_id="snap", account_id="acct",
            symbol="SPY", quantity=2, market_value=100, cost_basis=90,
            valuation_currency="USD", unit_price=50, price_currency="USD",
            valued_at_utc=None, price_source_ref="fixture:test",
            as_of_utc="2025-06-20T08:00:00+00:00",
            valuation_status="valued",
        )
        blockers = valuation_blockers(pos)
        self.assertIn("valuation_unpriced", blockers)
        self.assertIn("valued_at_utc_missing", blockers)

    def test_stored_valued_with_missing_source_not_admitted(self):
        pos = Position(
            position_id="pos_iso2", snapshot_id="snap", account_id="acct",
            symbol="SPY", quantity=2, market_value=100, cost_basis=90,
            valuation_currency="USD", unit_price=50, price_currency="USD",
            valued_at_utc="2025-06-20T08:00:00+00:00", price_source_ref=None,
            as_of_utc="2025-06-20T08:00:00+00:00",
            valuation_status="valued",
        )
        blockers = valuation_blockers(pos)
        self.assertIn("valuation_unpriced", blockers)
        self.assertIn("price_source_ref_missing", blockers)


# ============================================================================
# Delta carry-forward
# ============================================================================


class DeltaCarryForwardContractTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.receipt_root = self.root / "receipts"
        self.store = LocalArtifactStore(self.receipt_root / "artifact-store")

    def _csv(self, rows):
        path = self.root / "export.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TYPED_CSV_COLUMNS)
            w.writeheader()
            for row in rows:
                w.writerow(row)
        return path

    def test_carried_position_produces_stale_and_blocked(self):
        old_time = "2025-06-19T07:00:00+00:00"
        new_time = "2025-06-20T08:00:00+00:00"
        result1 = ingest_personal_finance_export(
            self._csv([_typed_row({
                "account_id": "acct_a", "symbol": "AAA",
                "valued_at_utc": old_time, "as_of_utc": old_time,
            })]), engine=self.engine,
            receipt_root=self.receipt_root, artifact_store=self.store,
        )
        batch1_id = result1.batch_id
        result2 = ingest_personal_finance_export(
            self._csv([_typed_row({
                "account_id": "acct_b", "symbol": "BBB",
                "valued_at_utc": new_time, "as_of_utc": new_time,
            })]), engine=self.engine,
            receipt_root=self.receipt_root, artifact_store=self.store,
            coverage_mode="delta", supersedes_batch_id=batch1_id,
            correction_reason="add position B",
        )
        aaa = _pos_by_symbol(self.engine, "AAA")
        _pos_by_symbol(self.engine, "BBB")
        self.assertEqual(aaa.valuation_status, "stale")
        blockers = valuation_blockers(aaa)
        self.assertIn("market_price_stale", blockers)
        self.assertEqual(result2.completeness_status, "blocked")
        _assert_import_surface_agreement(
            self, result2, self.engine, self.store,
            symbol="AAA", expected_status="stale",
            expected_completeness="blocked",
            expected_codes={"market_price_stale"},
        )


# ============================================================================
# Beancount contract tests
# ============================================================================


class BeancountValuationContractTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.receipt_root = self.root / "receipts"
        self.store = LocalArtifactStore(self.receipt_root / "artifact-store")

    def _ingest(self, fixture_path):
        return ingest_beancount_ledger(
            fixture_path, engine=self.engine,
            receipt_root=self.receipt_root, artifact_store=self.store,
        )

    def test_unrelated_commodity_price_does_not_refresh_other_holding(self):
        result = self._ingest(FIXTURE_DIR / "unrelated_price.beancount")
        aaa = _pos_by_symbol(self.engine, "AAA")
        bbb = _pos_by_symbol(self.engine, "BBB")
        self.assertEqual(aaa.valued_at_utc, "2025-06-10T00:00:00+00:00")
        self.assertEqual(bbb.valued_at_utc, "2025-06-20T00:00:00+00:00")
        self.assertEqual(aaa.valuation_status, "stale")
        blockers = valuation_blockers(aaa)
        self.assertIn("market_price_stale", blockers)
        self.assertEqual(result.completeness_status, "blocked")
        _assert_import_surface_agreement(
            self, result, self.engine, self.store,
            symbol="AAA", expected_status="stale",
            expected_completeness="blocked",
            expected_codes={"market_price_stale"},
        )

    def test_distinct_price_times_produce_distinct_valued_at_utc(self):
        self._ingest(FIXTURE_DIR / "distinct_price_times.beancount")
        aaa = _pos_by_symbol(self.engine, "AAA")
        bbb = _pos_by_symbol(self.engine, "BBB")
        self.assertEqual(aaa.valued_at_utc, "2025-06-18T00:00:00+00:00")
        self.assertEqual(bbb.valued_at_utc, "2025-06-15T00:00:00+00:00")


# ============================================================================
# Direct materializer: three source kinds
# ============================================================================


class DirectMaterializerValuationRejectionTest(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.engine = init_state_core(self.root / "state-core.sqlite")
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.tmp.cleanup)
        self.import_root = (
            self.root / "receipts" / "capital-imports" / "broker-read")
        self.store = LocalArtifactStore(self.import_root / "artifact-store")

    def _assert_db_empty(self):
        self.assertEqual(list(read_all(ImportBatch, engine=self.engine)), [])
        self.assertEqual(list(read_all(ReceiptManifest, engine=self.engine)), [])
        self.assertEqual(list(read_all(Snapshot, engine=self.engine)), [])
        self.assertEqual(list(read_all(Position, engine=self.engine)), [])
        self.assertEqual(list(read_all(ReceiptIndex, engine=self.engine)), [])

    def _capture(self, patch_target, ingest_fn, source_kind):
        """Generic envelope capture: patch, ingest, verify captured keys."""
        from unittest.mock import patch

        captured = {}

        def patched(records, *, source, batch, manifest, artifact_store, engine):
            captured["records"] = copy.deepcopy(list(records))
            captured["source"] = source
            captured["batch"] = copy.deepcopy(batch)
            captured["manifest"] = copy.deepcopy(manifest)
            captured["store"] = artifact_store
            raise StateCoreStoreError("capture-only")

        with patch(patch_target, patched), contextlib.suppress(StateCoreStoreError):
            ingest_fn()
        for key in ("records", "source", "batch", "manifest", "store"):
            self.assertIn(key, captured, f"capture missing {key} for {source_kind}")
        self.assertEqual(captured["source"], source_kind)
        positions = [r for r in captured["records"]
                     if isinstance(r, Position)]
        self.assertGreaterEqual(len(positions), 1,
                                f"no Position in captured records for {source_kind}")
        self._assert_db_empty()
        return captured

    def _capture_broker_envelope(self):
        payload = {
            "receipt_id": "rec_cap", "kind": "broker_read",
            "created_at_utc": "2025-06-20T09:00:00+00:00",
            "effective_at_utc": "2025-06-20T09:00:00+00:00",
            "observed_at_utc": "2025-06-20T09:00:00+00:00",
            "valued_at_utc": "2025-06-20T09:00:00+00:00",
            "broker": "manual", "environment": "paper",
            "account": {"id": "acct_cap", "status": "ACTIVE"},
            "positions": [{
                "symbol": "SPY", "qty": "2", "market_value": "100",
                "unit_price": "50", "currency": "USD",
                "asset_class": "equity", "exchange": "ARCX",
                "price_source_ref": "fixture:capture",
            }],
        }
        path = self.root / "broker-read" / "portfolio.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")

        def _ingest():
            ingest_broker_read_receipt(
                path, engine=self.engine,
                receipt_root=self.import_root, artifact_store=self.store,
            )
        return self._capture(
            "finharness.statecore.snapshot_ingest.materialize_import_batch",
            _ingest, "broker_read",
        )

    def _capture_csv_envelope(self):
        csv_root = self.root / "receipts_csv"
        path = self.root / "export.csv"
        with path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=TYPED_CSV_COLUMNS)
            w.writeheader()
            w.writerow(_typed_row())

        def _ingest():
            ingest_personal_finance_export(
                path, engine=self.engine,
                receipt_root=csv_root,
                artifact_store=LocalArtifactStore(
                    csv_root / "artifact-store"),
            )
        return self._capture(
            "finharness.personal_finance.materialize_import_batch",
            _ingest, "personal_finance_export",
        )

    def _capture_beancount_envelope(self):
        bean_root = self.root / "receipts_bean"
        fixture = FIXTURE_DIR / "distinct_price_times.beancount"

        def _ingest():
            ingest_beancount_ledger(
                fixture, engine=self.engine,
                receipt_root=bean_root,
                artifact_store=LocalArtifactStore(
                    bean_root / "artifact-store"),
            )
        return self._capture(
            "finharness.beancount_adapter.materialize_import_batch",
            _ingest, "beancount_ledger",
        )

    def test_csv_forged_valued_missing_time_rejected(self):
        cap = self._capture_csv_envelope()
        for r in cap["records"]:
            if isinstance(r, Position):
                r.valued_at_utc = None
                r.valuation_status = "valued"
        with self.assertRaisesRegex(StateCoreStoreError, "valuation_"):
            materialize_import_batch(
                cap["records"], source=cap["source"],
                batch=cap["batch"], manifest=cap["manifest"],
                artifact_store=cap["store"], engine=self.engine,
            )
        self._assert_db_empty()

    def test_beancount_forged_valued_missing_source_rejected(self):
        cap = self._capture_beancount_envelope()
        for r in cap["records"]:
            if isinstance(r, Position):
                r.price_source_ref = None
                r.valuation_status = "valued"
        with self.assertRaisesRegex(StateCoreStoreError, "valuation_"):
            materialize_import_batch(
                cap["records"], source=cap["source"],
                batch=cap["batch"], manifest=cap["manifest"],
                artifact_store=cap["store"], engine=self.engine,
            )
        self._assert_db_empty()

    def test_broker_forged_valued_component_mismatch_rejected(self):
        cap = self._capture_broker_envelope()
        for r in cap["records"]:
            if isinstance(r, Position):
                r.market_value = r.quantity * r.unit_price + 1
                r.valuation_status = "valued"
        with self.assertRaisesRegex(StateCoreStoreError, "valuation_"):
            materialize_import_batch(
                cap["records"], source=cap["source"],
                batch=cap["batch"], manifest=cap["manifest"],
                artifact_store=cap["store"], engine=self.engine,
            )
        self._assert_db_empty()


if __name__ == "__main__":
    unittest.main()
