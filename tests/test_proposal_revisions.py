from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from finharness.statecore.proposal_revisions import walk_proposal_revisions


def _write_receipt(
    path: Path,
    *,
    proposal_id: str,
    supersedes: str | None = None,
    kind: str = "state_core_proposal",
    claim: str = "claim",
    content_hash: str = "hash",
    created_at: str = "2026-03-01T00:00:00+00:00",
) -> str:
    payload = {
        "kind": kind,
        "receipt_id": path.stem,
        "created_at_utc": created_at,
        "content_hash": content_hash,
        "supersedes": supersedes,
        "proposal": {"proposal_id": proposal_id, "claim": claim},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return str(path)


class WalkProposalRevisionsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def _ref(self, name: str) -> str:
        return str(self.root / name)

    def test_happy_chain_is_latest_first(self) -> None:
        first = self.root / "r1.json"
        second = self.root / "r2.json"
        _write_receipt(first, proposal_id="p", claim="v1", content_hash="h1")
        _write_receipt(
            second, proposal_id="p", supersedes=str(first), claim="v2", content_hash="h2"
        )

        walk = walk_proposal_revisions("p", str(second))

        self.assertTrue(walk.ok)
        self.assertEqual(walk.count, 2)
        self.assertEqual(walk.revisions[0].receipt_ref, str(second))
        self.assertEqual(walk.revisions[0].content_hash, "h2")
        self.assertEqual(walk.revisions[0].supersedes, str(first))
        self.assertEqual(walk.revisions[0].proposal["claim"], "v2")
        self.assertEqual(walk.revisions[1].receipt_ref, str(first))
        self.assertIsNone(walk.revisions[1].supersedes)

    def test_no_receipt_ref_is_anomaly_with_no_records(self) -> None:
        walk = walk_proposal_revisions("p", None)
        self.assertEqual(walk.count, 0)
        self.assertEqual([a.code for a in walk.anomalies], ["no_receipt_ref"])

    def test_missing_receipt(self) -> None:
        walk = walk_proposal_revisions("p", self._ref("nope.json"))
        self.assertEqual(walk.count, 0)
        self.assertEqual(walk.anomalies[0].code, "missing")

    def test_unreadable_receipt(self) -> None:
        bad = self.root / "bad.json"
        bad.write_text("{ not valid json", encoding="utf-8")
        walk = walk_proposal_revisions("p", str(bad))
        self.assertEqual(walk.anomalies[0].code, "unreadable")

    def test_wrong_kind(self) -> None:
        r = self.root / "r.json"
        _write_receipt(r, proposal_id="p", kind="something_else")
        walk = walk_proposal_revisions("p", str(r))
        self.assertEqual(walk.count, 0)
        self.assertEqual(walk.anomalies[0].code, "wrong_kind")

    def test_wrong_proposal_id(self) -> None:
        r = self.root / "r.json"
        _write_receipt(r, proposal_id="other")
        walk = walk_proposal_revisions("p", str(r))
        self.assertEqual(walk.count, 0)
        self.assertEqual(walk.anomalies[0].code, "wrong_proposal_id")

    def test_cycle_keeps_records_read_before_the_loop(self) -> None:
        a = self.root / "a.json"
        b = self.root / "b.json"
        _write_receipt(a, proposal_id="p", supersedes=str(b), content_hash="ha")
        _write_receipt(b, proposal_id="p", supersedes=str(a), content_hash="hb")

        walk = walk_proposal_revisions("p", str(a))

        self.assertEqual(walk.count, 2)
        self.assertEqual(walk.anomalies[0].code, "cycle")

    def test_max_revisions_guard(self) -> None:
        prev: str | None = None
        for i in range(3):
            p = self.root / f"r{i}.json"
            _write_receipt(p, proposal_id="p", supersedes=prev, content_hash=f"h{i}")
            prev = str(p)

        walk = walk_proposal_revisions("p", prev, max_revisions=2)

        self.assertEqual(walk.count, 2)
        self.assertEqual(walk.anomalies[0].code, "too_many")

    def test_allowed_roots_guard_rejects_outside_then_reads_when_unguarded(self) -> None:
        outside = self.root / "r.json"
        _write_receipt(outside, proposal_id="p")
        sandbox = self.root / "allowed"
        sandbox.mkdir()

        guarded = walk_proposal_revisions(
            "p", str(outside), allowed_roots=(sandbox.resolve(),)
        )
        self.assertEqual(guarded.count, 0)
        self.assertEqual(guarded.anomalies[0].code, "outside_allowed_roots")

        unguarded = walk_proposal_revisions("p", str(outside))
        self.assertTrue(unguarded.ok)
        self.assertEqual(unguarded.count, 1)

    def test_invalid_supersedes_keeps_record_then_stops(self) -> None:
        r = self.root / "r.json"
        _write_receipt(r, proposal_id="p")
        payload = json.loads(r.read_text(encoding="utf-8"))
        payload["supersedes"] = {"not": "a string"}
        r.write_text(json.dumps(payload), encoding="utf-8")

        walk = walk_proposal_revisions("p", str(r))

        self.assertEqual(walk.count, 1)
        self.assertIsNone(walk.revisions[0].supersedes)
        self.assertEqual(walk.anomalies[0].code, "invalid_supersedes")


if __name__ == "__main__":
    unittest.main()
