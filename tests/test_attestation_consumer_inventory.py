"""Contract tests for the attestation consumer inventory verifier."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.verify_attestation_consumer_inventory import validate_inventory

_PARENT = Path(__file__).resolve().parents[1]
REAL_INV = _PARENT / "docs" / "governance" / "attestation-consumers.json"


def _c(overrides: dict | None = None) -> dict:
    base = {
        "consumer_id": "ATT-CONS-001", "path": "src/finharness/statecore/models.py",
        "symbol": "Attestation", "line_start": 169, "line_end": 186,
        "match_terms": ["Attestation"], "role": "schema_model",
        "current_behavior": "Test.", "decision_semantics": "legacy_unbound_decision",
        "version_binding": "proposal_id_only", "authority_effect": "None.",
        "risk": "low", "disposition": "preserve", "target_owner": "N/A",
        "prerequisites": [], "recommended_change": "Test recommendation.",
        "test_implications": [], "evidence": ["t:1"],
    }
    if overrides is not None:
        base.update(overrides)
    return base


def _inv(consumers, **kw):
    roles = {}
    disps = {}
    hc = 0
    for c in consumers:
        roles[c["role"]] = roles.get(c["role"], 0) + 1
        disps[c["disposition"]] = disps.get(c["disposition"], 0) + 1
        if c["risk"] in ("high", "critical"):
            hc += 1
    return {
        "schema": "finharness.attestation_consumer_inventory.v1",
        "baseline_sha": "x",
        "scope": {"source_roots": ["src"], "scan_terms": ["Attestation"]},
        "summary": {
            "total_consumers": len(consumers),
            "by_role": roles, "by_disposition": disps,
            "high_or_critical_count": hc,
        },
        "consumers": consumers, "exclusions": [], "unclassified_hits": [], **kw,
    }


def _tmp_validate(data, root=None):
    if root is None:
        root = _PARENT
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as fh:
        json.dump(data, fh)
        fh.flush()
        p = Path(fh.name)
    failures = validate_inventory(p, root=root)
    p.unlink()
    return failures


class TestInventory(unittest.TestCase):

    # ── positive ──────────────────────────────────────────────────────

    def test_real_inventory_passes(self):
        f = validate_inventory(REAL_INV)
        self.assertEqual(f, [], f"Real inventory must pass: {f}")

    # ── structural ────────────────────────────────────────────────────

    def test_duplicate_id_fails(self):
        f = _tmp_validate(_inv([_c(), _c({"consumer_id": "ATT-CONS-001"})]))
        self.assertTrue(any("duplicate" in x for x in f), f)

    def test_unknown_role_fails(self):
        f = _tmp_validate(_inv([_c({"role": "bad"})]))
        self.assertTrue(any("unknown role" in x for x in f), f)

    def test_missing_path_fails(self):
        f = _tmp_validate(_inv([_c({"path": "nope.py"})]))
        self.assertTrue(any("does not exist" in x for x in f), f)

    def test_empty_change_fails(self):
        f = _tmp_validate(_inv([_c({"recommended_change": ""})]))
        self.assertTrue(any("recommended_change is empty" in x for x in f), f)

    def test_unclassified_fails(self):
        f = _tmp_validate(_inv([_c()], unclassified_hits=[{"f": "x"}]))
        self.assertTrue(any("unclassified_hits" in x for x in f), f)

    # ── ID sequence ───────────────────────────────────────────────────

    def test_non_contiguous_ids_fail(self):
        data = _inv([_c({"consumer_id": "ATT-CONS-001"}),
                      _c({"consumer_id": "ATT-CONS-003"})])
        f = _tmp_validate(data)
        self.assertTrue(any("expected" in x for x in f), f)

    def test_bad_id_format_fails(self):
        f = _tmp_validate(_inv([_c({"consumer_id": "BAD-001"})]))
        self.assertTrue(any("invalid consumer_id format" in x for x in f), f)

    # ── summary drift ─────────────────────────────────────────────────

    def test_total_count_drift_fails(self):
        f = _tmp_validate(_inv([_c()],
            summary={"total_consumers": 99, "by_role": {"schema_model": 1},
                     "by_disposition": {"preserve": 1}, "high_or_critical_count": 0}))
        self.assertTrue(any("total_consumers" in x for x in f), f)

    def test_by_role_drift_fails(self):
        f = _tmp_validate(_inv([_c()],
            summary={"total_consumers": 1, "by_role": {"wrong": 1},
                     "by_disposition": {"preserve": 1}, "high_or_critical_count": 0}))
        self.assertTrue(any("by_role" in x for x in f), f)

    def test_by_disposition_drift_fails(self):
        f = _tmp_validate(_inv([_c()],
            summary={"total_consumers": 1, "by_role": {"schema_model": 1},
                     "by_disposition": {"wrong": 1}, "high_or_critical_count": 0}))
        self.assertTrue(any("by_disposition" in x for x in f), f)

    def test_high_critical_drift_fails(self):
        c = _c({"risk": "high"})
        f = _tmp_validate(_inv([c],
            summary={"total_consumers": 1, "by_role": {"schema_model": 1},
                     "by_disposition": {"preserve": 1}, "high_or_critical_count": 0}))
        self.assertTrue(any("high_or_critical_count" in x for x in f), f)

    # ── exclusion validation ──────────────────────────────────────────

    def test_exclusion_missing_path_fails(self):
        f = _tmp_validate(_inv([_c()],
            exclusions=[{"path": "nope.py", "match_line": 1, "term": "x", "reason": "test"}]))
        self.assertTrue(any("path does not exist" in x for x in f), f)

    # ── same-file blind spot ──────────────────────────────────────────

    def test_same_file_uncovered_hit_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "src" / "finharness"
            src.mkdir(parents=True)
            (src / "example.py").write_text("""from finharness.statecore.models import Attestation

def existing_consumer():
    return Attestation

def newly_added_consumer():
    return Attestation
""")
            c = _c({"path": "src/finharness/example.py", "line_start": 3, "line_end": 4})
            data = _inv([c])
            data["scope"]["scan_terms"] = ["Attestation"]
            data["scope"]["source_roots"] = ["src"]
            f = _tmp_validate(data, root=root)
            self.assertTrue(
                any("unregistered hit" in x for x in f),
                f"Second consumer not detected: {f}",
            )

    # ── unregistered probe ────────────────────────────────────────────

    def test_unregistered_probe_fails(self):
        probe = _PARENT / "src" / "finharness" / "_attestation_inventory_probe.py"
        try:
            probe.write_text("from finharness.statecore.models import Attestation\n")
            f = validate_inventory(REAL_INV)
            self.assertTrue(any("_attestation_inventory_probe" in x for x in f), str(f))
        finally:
            if probe.exists():
                probe.unlink()
