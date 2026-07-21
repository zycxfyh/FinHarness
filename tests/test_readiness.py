from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from finharness.api.app import create_app
from finharness.artifact_store import LocalArtifactStore
from finharness.capital_truth import (
    CapitalTruthAdmissionStatus,
    EvidenceIntegrityStatus,
)
from finharness.import_provenance import prepare_import
from finharness.readiness import CapitalTruthReadiness
from finharness.statecore.import_identity import materialized_record_identities
from finharness.statecore.models import ReceiptIndex, Snapshot
from finharness.statecore.store import init_state_core, materialize_import_batch
from tests.asgi_test_client import AsgiTestClient


class ReadinessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db_path = self.root / "state-core.sqlite"
        self.receipt_root = self.root / "receipts"
        self.addCleanup(self.tmp.cleanup)

    def _client(self, **kwargs: object) -> AsgiTestClient:
        client = AsgiTestClient(create_app(**kwargs))
        self.addCleanup(client.close)
        return client

    def _materialize(
        self,
        *,
        observed_at: datetime | None = None,
        completeness_status: str = "complete",
    ):
        now = datetime.now(UTC)
        observed = observed_at or now
        created_at = now.isoformat()
        source = b"account_id,balance\nprimary,100\n"
        source_hash = hashlib.sha256(source).hexdigest()
        engine = init_state_core(self.db_path)
        self.addCleanup(engine.dispose)
        store = LocalArtifactStore(self.receipt_root / "artifact-store")
        receipt_id = "receipt_readiness"
        snapshot_id = "snapshot_readiness"
        receipt_ref = str(self.receipt_root / f"{receipt_id}.json")
        clocks = {
            "effective_at_utc": observed.isoformat(),
            "observed_at_utc": observed.isoformat(),
            "valued_at_utc": observed.isoformat(),
            "ingested_at_utc": created_at,
            "recorded_at_utc": created_at,
        }
        findings = (
            []
            if completeness_status == "complete"
            else [{"code": "test_partial", "severity": "partial", "message": "partial"}]
        )
        materialized_records = [
            ReceiptIndex(
                receipt_id=receipt_id,
                kind="readiness_test",
                path=receipt_ref,
                created_at_utc=created_at,
                source_refs=[receipt_ref],
            ),
            Snapshot(
                snapshot_id=snapshot_id,
                kind="capital",
                as_of_utc=observed.isoformat(),
                payload={},
                source_refs=[receipt_ref],
            ),
        ]
        prepared = prepare_import(
            source_kind="readiness_test",
            source_id="test://readiness",
            source_content=source,
            source_sha256=source_hash,
            adapter_version="test.v1",
            coverage_mode="full",
            record_counts={},
            snapshot_id=snapshot_id,
            receipt_id=receipt_id,
            receipt_root=self.receipt_root,
            receipt_ref=receipt_ref,
            artifact_store=store,
            receipt_payload={
                "receipt_id": receipt_id,
                "source_sha256": source_hash,
                "adapter_version": "test.v1",
                "record_counts": {},
            },
            created_at_utc=created_at,
            completeness_status=completeness_status,
            time_semantics=clocks,
            findings=findings,
            materialized_record_identities=materialized_record_identities(
                materialized_records
            ),
            covered_domains=[],
            corporate_action_status="not_applicable",
        )
        materialize_import_batch(
            materialized_records,
            source="readiness_test",
            batch=prepared.batch,
            manifest=prepared.manifest,
            artifact_store=store,
            engine=engine,
        )
        return engine, prepared, store

    def test_liveness_does_not_claim_dependency_or_truth_readiness(self) -> None:
        client = self._client(
            state_core_path=str(self.db_path),
            receipt_root=str(self.receipt_root),
        )

        health = client.get("/health")
        ready = client.get("/ready")

        self.assertEqual(health.status_code, 200)
        self.assertIn("Liveness signal only.", health.json()["non_claims"])
        self.assertEqual(ready.status_code, 503)
        self.assertEqual(ready.json()["checks"]["state_core"]["status"], "missing")

    def test_ready_reports_corrupt_database_without_migrating_it(self) -> None:
        original = b"not a sqlite database"
        self.db_path.write_bytes(original)
        client = self._client(
            state_core_path=str(self.db_path),
            receipt_root=str(self.receipt_root),
        )

        response = client.get("/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["checks"]["state_core"]["status"], "corrupt")
        self.assertEqual(self.db_path.read_bytes(), original)

    def test_ready_fails_closed_for_unwritable_receipt_storage(self) -> None:
        engine = init_state_core(self.db_path)
        self.addCleanup(engine.dispose)
        self.receipt_root.mkdir()
        self.receipt_root.chmod(0o555)
        self.addCleanup(self.receipt_root.chmod, 0o755)
        client = self._client(
            state_core_engine=engine,
            state_core_path=str(self.db_path),
            receipt_root=str(self.receipt_root),
        )

        response = client.get("/ready")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["checks"]["receipt_storage"]["status"], "unwritable")

    def test_truth_readiness_is_usable_only_with_current_bound_evidence(self) -> None:
        engine, _prepared, _store = self._materialize()
        client = self._client(
            state_core_engine=engine,
            state_core_path=str(self.db_path),
            receipt_root=str(self.receipt_root),
        )

        response = client.get("/ready/truth")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "usable")
        self.assertEqual(response.json()["evidence_integrity"], "intact")
        self.assertEqual(response.json()["capital_truth_admission"], "admitted")
        self.assertNotIn("verified", response.json())

    def test_truth_readiness_distinguishes_missing_artifact_stale_and_partial(self) -> None:
        engine, prepared, store = self._materialize()
        descriptor = store.descriptor(prepared.manifest.receipt_artifact_id)
        object_path = (
            store.root
            / "objects"
            / descriptor.content_sha256[:2]
            / f"{descriptor.content_sha256}.bin"
        )
        object_path.unlink()
        missing_client = self._client(
            state_core_engine=engine,
            receipt_root=str(self.receipt_root),
        )
        missing = missing_client.get("/ready/truth")
        self.assertEqual(missing.status_code, 503)
        self.assertEqual(missing.json()["evidence_integrity"], "missing")
        self.assertEqual(missing.json()["capital_truth_admission"], "blocked")
        self.assertIn("missing", {item["category"] for item in missing.json()["findings"]})
        prepared.receipt_path.write_bytes(b"corrupt receipt")
        corrupt = missing_client.get("/ready/truth")
        self.assertEqual(corrupt.json()["evidence_integrity"], "corrupt")
        self.assertEqual(corrupt.json()["capital_truth_admission"], "blocked")
        self.assertIn("corrupt", {item["category"] for item in corrupt.json()["findings"]})

        stale_root = self.root / "stale"
        stale_root.mkdir()
        self.db_path = stale_root / "state.sqlite"
        self.receipt_root = stale_root / "receipts"
        stale_engine, _prepared, _store = self._materialize(
            observed_at=datetime.now(UTC) - timedelta(hours=25)
        )
        stale_client = self._client(
            state_core_engine=stale_engine,
            receipt_root=str(self.receipt_root),
        )
        stale = stale_client.get("/ready/truth")
        self.assertEqual(stale.json()["evidence_integrity"], "intact")
        self.assertEqual(stale.json()["capital_truth_admission"], "blocked")
        self.assertIn("stale", {item["category"] for item in stale.json()["findings"]})

        partial_root = self.root / "partial"
        partial_root.mkdir()
        self.db_path = partial_root / "state.sqlite"
        self.receipt_root = partial_root / "receipts"
        partial_engine, _prepared, _store = self._materialize(completeness_status="partial")
        partial_client = self._client(
            state_core_engine=partial_engine,
            receipt_root=str(self.receipt_root),
        )
        partial = partial_client.get("/ready/truth")
        self.assertEqual(partial.json()["status"], "partial")
        self.assertEqual(partial.json()["evidence_integrity"], "intact")
        self.assertEqual(partial.json()["capital_truth_admission"], "partial")
        self.assertNotIn("verified", partial.json())
        self.assertIn("partial", {item["category"] for item in partial.json()["findings"]})

    def test_truth_readiness_preserves_blocked_import_category(self) -> None:
        engine, _prepared, _store = self._materialize(completeness_status="blocked")
        client = self._client(
            state_core_engine=engine,
            state_core_path=str(self.db_path),
            receipt_root=str(self.receipt_root),
        )

        response = client.get("/ready/truth")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "blocked")
        self.assertEqual(response.json()["evidence_integrity"], "intact")
        self.assertEqual(response.json()["capital_truth_admission"], "blocked")
        self.assertIn("blocked", {item["category"] for item in response.json()["findings"]})

    def test_truth_readiness_missing_and_unavailable_dimensions_are_distinct(self) -> None:
        missing_db = self._client(
            state_core_path=str(self.db_path),
            receipt_root=str(self.receipt_root),
        ).get("/ready/truth")
        self.assertEqual(missing_db.json()["status"], "unavailable")
        self.assertEqual(missing_db.json()["evidence_integrity"], "unavailable")
        self.assertEqual(missing_db.json()["capital_truth_admission"], "unavailable")
        self.assertEqual(
            {item["category"] for item in missing_db.json()["findings"]},
            {"unavailable"},
        )

        engine = init_state_core(self.db_path)
        self.addCleanup(engine.dispose)
        no_import = self._client(
            state_core_engine=engine,
            state_core_path=str(self.db_path),
            receipt_root=str(self.receipt_root),
        ).get("/ready/truth")
        self.assertEqual(no_import.json()["status"], "blocked")
        self.assertEqual(no_import.json()["evidence_integrity"], "missing")
        self.assertEqual(no_import.json()["capital_truth_admission"], "blocked")
        self.assertEqual(
            {item["category"] for item in no_import.json()["findings"]},
            {"missing"},
        )

    def test_truth_readiness_preserves_evidence_io_unavailability(self) -> None:
        engine, prepared, _store = self._materialize()
        client = self._client(
            state_core_engine=engine,
            state_core_path=str(self.db_path),
            receipt_root=str(self.receipt_root),
        )

        original_read_bytes = Path.read_bytes

        def read_bytes(path: Path) -> bytes:
            if path == prepared.receipt_path:
                raise OSError("evidence unavailable")
            return original_read_bytes(path)

        with patch.object(Path, "read_bytes", autospec=True, side_effect=read_bytes):
            response = client.get("/ready/truth")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["status"], "unavailable")
        self.assertEqual(response.json()["evidence_integrity"], "unavailable")
        self.assertEqual(response.json()["capital_truth_admission"], "unavailable")
        self.assertIn("unavailable", {item["category"] for item in response.json()["findings"]})

    def test_truth_readiness_reports_artifact_descriptor_io_as_unavailable(self) -> None:
        engine, prepared, store = self._materialize()
        client = self._client(
            state_core_engine=engine,
            state_core_path=str(self.db_path),
            receipt_root=str(self.receipt_root),
        )
        source_descriptor_path = store._descriptor_path(prepared.batch.source_artifact_id)
        original_read_text = Path.read_text

        def read_text(path: Path, *args: object, **kwargs: object) -> str:
            if path == source_descriptor_path:
                raise PermissionError("source descriptor unavailable")
            return original_read_text(path, *args, **kwargs)

        with patch.object(Path, "read_text", autospec=True, side_effect=read_text):
            response = client.get("/ready/truth")

        payload = response.json()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["evidence_integrity"], "unavailable")
        self.assertEqual(payload["capital_truth_admission"], "unavailable")
        self.assertTrue(payload["current"])
        self.assertEqual(payload["checked_manifest_id"], prepared.manifest.manifest_id)
        self.assertFalse(payload["execution_allowed"])
        self.assertIn(
            ("source_artifact_unavailable", "unavailable"),
            {(item["code"], item["category"]) for item in payload["findings"]},
        )

    def test_truth_readiness_reports_artifact_object_io_as_unavailable(self) -> None:
        engine, prepared, store = self._materialize()
        client = self._client(
            state_core_engine=engine,
            state_core_path=str(self.db_path),
            receipt_root=str(self.receipt_root),
        )
        descriptor = store.descriptor(prepared.manifest.receipt_artifact_id)
        object_path = store._object_path(descriptor.content_sha256)
        original_read_bytes = Path.read_bytes

        def read_bytes(path: Path) -> bytes:
            if path == object_path:
                raise OSError("receipt artifact object unavailable")
            return original_read_bytes(path)

        with patch.object(Path, "read_bytes", autospec=True, side_effect=read_bytes):
            response = client.get("/ready/truth")

        payload = response.json()
        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["status"], "unavailable")
        self.assertEqual(payload["evidence_integrity"], "unavailable")
        self.assertEqual(payload["capital_truth_admission"], "unavailable")
        self.assertTrue(payload["current"])
        self.assertEqual(payload["checked_manifest_id"], prepared.manifest.manifest_id)
        self.assertFalse(payload["execution_allowed"])
        self.assertIn(
            ("receipt_artifact_unavailable", "unavailable"),
            {(item["code"], item["category"]) for item in payload["findings"]},
        )

    def test_truth_readiness_reports_malformed_artifact_descriptor_as_corrupt(self) -> None:
        engine, prepared, store = self._materialize()
        descriptor_path = store._descriptor_path(prepared.batch.source_artifact_id)
        client = self._client(
            state_core_engine=engine,
            state_core_path=str(self.db_path),
            receipt_root=str(self.receipt_root),
        )

        for malformed in ('{"artifact_id":', "{}"):
            with self.subTest(malformed=malformed):
                descriptor_path.write_text(malformed, encoding="utf-8")
                response = client.get("/ready/truth")

                payload = response.json()
                self.assertEqual(response.status_code, 503)
                self.assertEqual(payload["status"], "blocked")
                self.assertEqual(payload["evidence_integrity"], "corrupt")
                self.assertEqual(payload["capital_truth_admission"], "blocked")
                self.assertTrue(payload["current"])
                self.assertEqual(
                    payload["checked_manifest_id"],
                    prepared.manifest.manifest_id,
                )
                self.assertFalse(payload["execution_allowed"])
                self.assertIn(
                    ("source_artifact_missing_or_corrupt", "corrupt"),
                    {(item["code"], item["category"]) for item in payload["findings"]},
                )

    def test_truth_readiness_contract_rejects_verified_and_unknown_fields(self) -> None:
        payload = {
            "status": "usable",
            "evidence_integrity": EvidenceIntegrityStatus.INTACT,
            "capital_truth_admission": CapitalTruthAdmissionStatus.ADMITTED,
            "current": True,
            "checked_manifest_id": "manifest",
            "findings": (),
        }

        for field in ("verified", "truth_ok", "admitted"):
            with self.subTest(field=field), self.assertRaisesRegex(
                ValidationError, "Extra inputs are not permitted"
            ):
                CapitalTruthReadiness.model_validate({**payload, field: True})

        with self.assertRaisesRegex(ValidationError, "Extra inputs are not permitted"):
            CapitalTruthReadiness.model_validate(
                {
                    **payload,
                    "findings": (
                        {
                            "code": "unexpected",
                            "category": "partial",
                            "detail": "unexpected nested field",
                            "verified": True,
                        },
                    ),
                }
            )

        with self.assertRaisesRegex(ValidationError, "Input should be"):
            CapitalTruthReadiness.model_validate(
                {
                    **payload,
                    "findings": (
                        {
                            "code": "unknown_category",
                            "category": "verified",
                            "detail": "parallel status substitution",
                        },
                    ),
                }
            )

    def test_truth_readiness_response_has_exact_named_dimensions(self) -> None:
        engine, _prepared, _store = self._materialize()
        response = self._client(
            state_core_engine=engine,
            state_core_path=str(self.db_path),
            receipt_root=str(self.receipt_root),
        ).get("/ready/truth")

        self.assertEqual(
            set(response.json()),
            {
                "status",
                "evidence_integrity",
                "capital_truth_admission",
                "current",
                "checked_manifest_id",
                "findings",
                "execution_allowed",
                "non_claims",
            },
        )


if __name__ == "__main__":
    unittest.main()
