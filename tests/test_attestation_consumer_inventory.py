"""Contract tests for the attestation consumer inventory verifier."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.verify_attestation_consumer_inventory import validate_inventory

_PARENT = Path(__file__).resolve().parents[1]
REAL_INV = _PARENT / "docs" / "governance" / "attestation-consumers.json"


def _consumer(overrides: dict | None = None) -> dict:
    base = {
        "consumer_id": "ATT-CONS-001",
        "path": "src/finharness/statecore/models.py",
        "symbol": "Attestation",
        "line_start": 169,
        "role": "schema_model",
        "current_behavior": "Test.",
        "decision_semantics": "legacy_unbound_decision",
        "version_binding": "proposal_id_only",
        "authority_effect": "None.",
        "risk": "low",
        "disposition": "preserve",
        "target_owner": "N/A",
        "prerequisites": [],
        "recommended_change": "Test recommendation.",
        "test_implications": [],
        "evidence": ["t:1"],
    }
    if overrides:
        base.update(overrides)
    return base


def _inv(consumers: list[dict], **kw) -> dict:
    return {
        "schema": "finharness.attestation_consumer_inventory.v1",
        "baseline_sha": "x",
        "scope": {"source_roots": ["src"], "scan_terms": ["Attestation"]},
        "summary": {
            "total_consumers": len(consumers),
            "by_role": {}, "by_disposition": {},
            "high_or_critical_count": 0,
        },
        "consumers": consumers,
        "exclusions": [],
        "unclassified_hits": [],
        **kw,
    }


def _tmp_validate(data: dict) -> list[str]:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
        json.dump(data, fh)
        fh.flush()
        p = Path(fh.name)
    failures = validate_inventory(p)
    p.unlink()
    return failures


class AttestationConsumerInventoryTest(unittest.TestCase):

    def test_real_inventory_passes(self) -> None:
        f = validate_inventory(REAL_INV)
        self.assertEqual(f, [], f"Real inventory must pass: {f}")

    def test_duplicate_id_fails(self) -> None:
        f = _tmp_validate(_inv([_consumer(), _consumer({"consumer_id": "ATT-CONS-001"})]))
        self.assertTrue(any("duplicate" in x for x in f), f)

    def test_unknown_role_fails(self) -> None:
        f = _tmp_validate(_inv([_consumer({"role": "bad"})]))
        self.assertTrue(any("unknown role" in x for x in f), f)

    def test_missing_path_fails(self) -> None:
        f = _tmp_validate(_inv([_consumer({"path": "nope.py"})]))
        self.assertTrue(any("does not exist" in x for x in f), f)

    def test_empty_change_fails(self) -> None:
        f = _tmp_validate(_inv([_consumer({"recommended_change": ""})]))
        self.assertTrue(any("recommended_change is empty" in x for x in f), f)

    def test_summary_drift_fails(self) -> None:
        data = _inv([_consumer()],
                    summary={"total_consumers": 99, "by_role": {},
                             "by_disposition": {}, "high_or_critical_count": 0})
        f = _tmp_validate(data)
        self.assertTrue(any("total_consumers" in x for x in f), f)

    def test_unclassified_fails(self) -> None:
        data = _inv([_consumer()], unclassified_hits=[{"file": "x", "reason": "?"}])
        f = _tmp_validate(data)
        self.assertTrue(any("unclassified_hits" in x for x in f), f)

    def test_unregistered_probe_fails(self) -> None:
        probe = _PARENT / "src" / "finharness" / "_attestation_inventory_probe.py"
        try:
            probe.write_text("from finharness.statecore.models import Attestation\n")
            f = validate_inventory(REAL_INV)
            self.assertTrue(
                any("_attestation_inventory_probe" in x for x in f), str(f))
        finally:
            if probe.exists():
                probe.unlink()
