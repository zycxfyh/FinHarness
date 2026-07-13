"""Shared Artifact Store contract, integrity, and recovery tests."""

from __future__ import annotations

import json
import tempfile
import unittest
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from unittest.mock import patch

from finharness.artifact_store import (
    ArtifactConflictError,
    ArtifactNotFoundError,
    LocalArtifactStore,
)


def _concurrent_put(root: str, content: bytes) -> tuple[str, str]:
    store = LocalArtifactStore(root)
    try:
        descriptor = store.put(
            artifact_id="artifact:concurrent",
            content=content,
            artifact_schema="finharness.concurrent",
            artifact_schema_version="1",
            media_type="application/octet-stream",
            owner_domain="test",
        )
        return "ok", descriptor.content_sha256
    except ArtifactConflictError as exc:
        return "conflict", str(exc)


class ArtifactStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = LocalArtifactStore(self.root)
        self.addCleanup(self.tmp.cleanup)

    def _put(self, artifact_id: str = "artifact:decision:1"):
        return self.store.put(
            artifact_id=artifact_id,
            content=b'{"decision":"review"}',
            artifact_schema="finharness.decision_record",
            artifact_schema_version="1",
            media_type="application/json",
            owner_domain="decision",
            source_refs=("receipt:source:1",),
            metadata={"case_id": "case:1", "trace_id": "trace:index-only"},
            created_at_utc="2026-07-13T00:00:00+00:00",
        )

    def test_put_is_content_addressed_immutable_and_idempotent(self) -> None:
        first = self._put()
        second = self._put()
        self.assertEqual(first, second)
        self.assertEqual(self.store.read(first.artifact_id), b'{"decision":"review"}')
        self.assertEqual(len(first.content_sha256), 64)
        with self.assertRaises(ArtifactConflictError):
            self.store.put(
                artifact_id=first.artifact_id,
                content=b"different",
                artifact_schema=first.artifact_schema,
                artifact_schema_version="1",
                media_type="application/json",
                owner_domain="decision",
                created_at_utc=first.created_at_utc,
            )

    def test_trace_id_is_metadata_and_cannot_replace_immutable_artifact(self) -> None:
        descriptor = self._put()
        self.assertEqual(descriptor.metadata["trace_id"], "trace:index-only")
        self.assertNotEqual(descriptor.artifact_id, descriptor.metadata["trace_id"])
        self.assertEqual(self.store.read(descriptor.artifact_id), b'{"decision":"review"}')

    def test_descriptor_listing_filters_without_trusting_the_index(self) -> None:
        descriptor = self._put()
        (self.root / "index.json").write_text("{bad json", encoding="utf-8")
        self.assertEqual(
            self.store.list_descriptors(
                owner_domain="decision",
                artifact_schema="finharness.decision_record",
            ),
            (descriptor,),
        )

    def test_destructive_fixtures_detect_missing_stale_schema_and_orphans(self) -> None:
        descriptor = self._put()
        object_path = (
            self.root
            / "objects"
            / descriptor.content_sha256[:2]
            / (descriptor.content_sha256 + ".bin")
        )
        object_path.unlink()
        (self.root / "objects" / "aa").mkdir(parents=True)
        (self.root / "objects" / "aa" / ("a" * 64 + ".bin")).write_bytes(b"orphan")
        (self.root / "index.json").write_text(
            json.dumps(
                {
                    "schema": "finharness.artifact_index.v1",
                    "artifacts": {descriptor.artifact_id: "0" * 64, "missing": "f" * 64},
                }
            )
        )
        report = self.store.audit(expected_schemas={"finharness.decision_record": {"2"}})
        codes = {finding.code for finding in report.findings}
        self.assertEqual(
            codes,
            {"missing_bytes", "orphan_bytes", "schema_version_mismatch", "stale_index"},
        )
        self.assertFalse(report.ok)
        with self.assertRaises(ArtifactNotFoundError):
            self.store.read(descriptor.artifact_id)

    def test_recovery_rebuilds_index_and_emits_replay_evidence(self) -> None:
        first = self._put("artifact:one")
        second = self._put("artifact:two")
        (self.root / "index.json").write_text(
            json.dumps(
                {
                    "schema": "finharness.artifact_index.v1",
                    "artifacts": {"stale": "0" * 64},
                }
            )
        )
        receipt = self.store.recover_index()
        self.assertFalse(receipt.before.ok)
        self.assertTrue(receipt.after.ok)
        self.assertEqual(receipt.repaired_artifact_ids, (first.artifact_id, second.artifact_id))
        self.assertTrue((self.root / "recovery" / f"{receipt.recovery_id}.json").is_file())
        self.assertEqual(self.store.read(first.artifact_id), b'{"decision":"review"}')

    def test_invalid_descriptor_blocks_recovery_without_destroying_evidence(self) -> None:
        descriptor = self._put()
        descriptor_path = self.root / "descriptors" / f"{descriptor.artifact_id}.json"
        descriptor_path.write_text("{bad json", encoding="utf-8")
        report = self.store.audit()
        self.assertIn("invalid_descriptor", {finding.code for finding in report.findings})
        with self.assertRaisesRegex(RuntimeError, "invalid descriptors"):
            self.store.recover_index()

    def test_conflicting_cross_process_puts_have_one_winner(self) -> None:
        with ProcessPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    _concurrent_put,
                    [str(self.root), str(self.root)],
                    [b"winner-a", b"winner-b"],
                )
            )
        self.assertEqual(sorted(status for status, _ in results), ["conflict", "ok"])
        persisted = self.store.read("artifact:concurrent")
        self.assertIn(persisted, {b"winner-a", b"winner-b"})

    def test_idempotent_cross_process_puts_converge(self) -> None:
        with ProcessPoolExecutor(max_workers=4) as executor:
            results = list(
                executor.map(
                    _concurrent_put,
                    [str(self.root)] * 8,
                    [b"same-content"] * 8,
                )
            )
        self.assertEqual({status for status, _ in results}, {"ok"})
        self.assertEqual(len({value for _, value in results}), 1)
        self.assertEqual(self.store.read("artifact:concurrent"), b"same-content")

    def test_put_index_work_does_not_scan_historical_descriptors(self) -> None:
        with patch.object(
            self.store,
            "_descriptor_map",
            side_effect=AssertionError("put must not scan all descriptors"),
        ):
            descriptor = self._put("artifact:bounded")
        self.assertEqual(self.store.descriptor(descriptor.artifact_id), descriptor)
        self.assertTrue(self.store.audit().ok)

    def test_interrupted_index_update_is_recoverable_and_retry_repairs_it(self) -> None:
        with (
            patch.object(self.store, "_write_index_entry", side_effect=OSError("disk full")),
            self.assertRaisesRegex(OSError, "disk full"),
        ):
            self._put("artifact:interrupted")
        report = self.store.audit()
        self.assertIn("orphan_descriptor", {finding.code for finding in report.findings})
        descriptor = self._put("artifact:interrupted")
        self.assertEqual(self.store.descriptor(descriptor.artifact_id), descriptor)
        self.assertTrue(self.store.audit().ok)

    def test_recovery_compacts_incremental_entries_into_checkpoint(self) -> None:
        self._put("artifact:one")
        self._put("artifact:two")
        self.assertTrue(any((self.root / "index-entries").glob("*.json")))
        receipt = self.store.recover_index()
        self.assertTrue(receipt.after.ok)
        self.assertFalse(any((self.root / "index-entries").glob("*.json")))
        self.assertTrue((self.root / "index.json").is_file())


if __name__ == "__main__":
    unittest.main()
