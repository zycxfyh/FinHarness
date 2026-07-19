from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: str, old: str, new: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"{path}: expected one exact match, found {text.count(old)}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def replace_regex(path: str, pattern: str, replacement: str) -> None:
    target = ROOT / path
    text = target.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(f"{path}: regex did not match exactly once")
    target.write_text(updated, encoding="utf-8")


replace_once(
    "src/finharness/capital_import_registry.py",
    '''    CapitalImportExposureSpec(
        exposure_id="function-daily-change-brief",
        exposure_kind="function",
        exposure_ref="finharness.daily_change_brief.run_daily_change_brief",
        adapter_id="broker-read-receipt",
    ),
    CapitalImportExposureSpec(
        exposure_id="function-broker-receipt-compat",''',
    '''    CapitalImportExposureSpec(
        exposure_id="function-daily-change-brief",
        exposure_kind="function",
        exposure_ref="finharness.daily_change_brief.run_daily_change_brief",
        adapter_id="broker-read-receipt",
    ),
    CapitalImportExposureSpec(
        exposure_id="function-capital-import-recovery-replay",
        exposure_kind="function",
        exposure_ref="finharness.capital_import_recovery._replay_receipt",
        adapter_id="broker-read-receipt",
    ),
    CapitalImportExposureSpec(
        exposure_id="function-broker-receipt-compat",''',
)
replace_once(
    "src/finharness/capital_import_registry.py",
    '''def materialized_source_for(source_kind: str) -> str:
    """Return the registered materialized marker for one adapter source kind."""
    try:
        return _MATERIALIZED_SOURCE_BY_SOURCE_KIND[source_kind]
    except KeyError as exc:
        raise ValueError(f"unregistered production import source kind: {source_kind}") from exc


def registry_projection() -> dict[str, object]:''',
    '''def materialized_source_for(source_kind: str) -> str:
    """Return the registered materialized marker for one adapter source kind."""
    try:
        return _MATERIALIZED_SOURCE_BY_SOURCE_KIND[source_kind]
    except KeyError as exc:
        raise ValueError(f"unregistered production import source kind: {source_kind}") from exc


def receipt_index_contract_fields(
    *,
    source_kind: str,
    receipt_ref: str,
    source_artifact_id: str,
    time_semantics: dict[str, object],
    receipt_payload: dict[str, object],
) -> dict[str, object]:
    """Derive the canonical ReceiptIndex mirror from immutable import evidence."""
    raw_source_ref = receipt_payload.get("source_ref")
    if not isinstance(raw_source_ref, str) or not raw_source_ref:
        raise ValueError("canonical import receipt has no source_ref")
    raw_upstream = receipt_payload.get("upstream_receipt_id")
    upstream_ref = (
        raw_upstream
        if isinstance(raw_upstream, str) and raw_upstream
        else raw_source_ref
    )
    raw_ingested_at = time_semantics.get("ingested_at_utc")
    if not isinstance(raw_ingested_at, str) or not raw_ingested_at:
        raise ValueError("canonical import batch has no ingested_at_utc")
    return {
        "kind": materialized_source_for(source_kind),
        "path": receipt_ref,
        "created_at_utc": raw_ingested_at,
        "source_refs": list(dict.fromkeys((receipt_ref, raw_source_ref))),
        "refs": list(dict.fromkeys((upstream_ref, source_artifact_id))),
    }


def registry_projection() -> dict[str, object]:''',
)

replace_regex(
    "src/finharness/statecore/__init__.py",
    r'''\n\ndef _bind_production_import_materialization_kinds\(\) -> None:.*?del _bind_production_import_materialization_kinds\n''',
    "\n",
)

replace_once(
    "src/finharness/statecore/store.py",
    '''_PRODUCTION_IMPORT_KINDS = {"personal_finance_export", "beancount_ledger"}


def _reject_unmanifested_production_import(records: Sequence[StateCoreRecord]) -> None:
    """Keep generic store helpers from bypassing W0 for known production adapters."""
    for record in records:
        if isinstance(record, ReceiptIndex) and record.kind in _PRODUCTION_IMPORT_KINDS:
            raise StateCoreStoreError("production import receipts require materialize_import_batch")
        if (
            isinstance(record, Snapshot)
            and record.payload.get("source") in _PRODUCTION_IMPORT_KINDS
        ):
            raise StateCoreStoreError(
                "production import snapshots require materialize_import_batch"
            )
        if (
            isinstance(
                record,
                (
                    Liability,
                    FinancialGoal,
                    CashflowEvent,
                    TaxEvent,
                    InsurancePolicy,
                    DocumentRef,
                ),
            )
            and record.source in _PRODUCTION_IMPORT_KINDS
        ):
            raise StateCoreStoreError("production import state requires materialize_import_batch")
''',
    '''def _production_import_marker_sets() -> tuple[frozenset[str], frozenset[str]]:
    """Load registry truth lazily without import-time mutation or a package cycle."""
    from finharness.capital_import_registry import (
        PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES,
        PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS,
    )

    return (
        PRODUCTION_CAPITAL_IMPORT_SOURCE_KINDS,
        PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES,
    )


def _reject_unmanifested_production_import(records: Sequence[StateCoreRecord]) -> None:
    """Keep generic stores from bypassing the canonical production envelope."""
    source_kinds, materialized_sources = _production_import_marker_sets()
    snapshot_markers = source_kinds | materialized_sources
    for record in records:
        if isinstance(record, ReceiptIndex) and record.kind in materialized_sources:
            raise StateCoreStoreError("production import receipts require materialize_import_batch")
        if isinstance(record, Snapshot) and record.payload.get("source") in snapshot_markers:
            raise StateCoreStoreError(
                "production import snapshots require materialize_import_batch"
            )
        if (
            isinstance(
                record,
                (
                    Liability,
                    FinancialGoal,
                    CashflowEvent,
                    TaxEvent,
                    InsurancePolicy,
                    DocumentRef,
                ),
            )
            and record.source in source_kinds
        ):
            raise StateCoreStoreError("production import state requires materialize_import_batch")
''',
)
replace_once(
    "src/finharness/statecore/store.py",
    '''    _validate_receipt_binding(
        receipt_content=receipt_content,
        source_schema=source_descriptor.artifact_schema,
        receipt_schema=receipt_descriptor.artifact_schema,
        batch=batch,
        manifest=manifest,
    )
    receipt_indexes = [record for record in records if isinstance(record, ReceiptIndex)]
    if len(receipt_indexes) != 1:
        raise StateCoreStoreError("production import requires exactly one receipt index")
    receipt_index = receipt_indexes[0]
    if (
        receipt_index.receipt_id != manifest.receipt_id
        or receipt_index.path != manifest.receipt_ref
    ):
        raise StateCoreStoreError("receipt index does not match the receipt manifest")
''',
    '''    receipt_payload = _validate_receipt_binding(
        receipt_content=receipt_content,
        source_schema=source_descriptor.artifact_schema,
        receipt_schema=receipt_descriptor.artifact_schema,
        batch=batch,
        manifest=manifest,
    )
    receipt_indexes = [record for record in records if isinstance(record, ReceiptIndex)]
    if len(receipt_indexes) != 1:
        raise StateCoreStoreError("production import requires exactly one receipt index")
    receipt_index = receipt_indexes[0]
    if (
        receipt_index.receipt_id != manifest.receipt_id
        or receipt_index.path != manifest.receipt_ref
    ):
        raise StateCoreStoreError("receipt index does not match the receipt manifest")
    _validate_receipt_index_binding(
        source=source,
        batch=batch,
        manifest=manifest,
        receipt_payload=receipt_payload,
        receipt_index=receipt_index,
    )
    _validate_snapshot_binding(
        source=source,
        batch=batch,
        manifest=manifest,
        receipt_payload=receipt_payload,
        records=records,
    )
''',
)
replace_once(
    "src/finharness/statecore/store.py",
    '''def _validate_import_contract_fields(
    *, source: str, batch: ImportBatch, manifest: ReceiptManifest
) -> None:''',
    '''def _validate_receipt_index_binding(
    *,
    source: str,
    batch: ImportBatch,
    manifest: ReceiptManifest,
    receipt_payload: dict[str, Any],
    receipt_index: ReceiptIndex,
) -> None:
    from finharness.capital_import_registry import receipt_index_contract_fields

    try:
        expected = receipt_index_contract_fields(
            source_kind=source,
            receipt_ref=manifest.receipt_ref,
            source_artifact_id=batch.source_artifact_id,
            time_semantics=batch.time_semantics,
            receipt_payload=receipt_payload,
        )
    except ValueError as exc:
        raise StateCoreStoreError(str(exc)) from exc
    actual = {
        "kind": receipt_index.kind,
        "path": receipt_index.path,
        "created_at_utc": receipt_index.created_at_utc,
        "source_refs": receipt_index.source_refs,
        "refs": receipt_index.refs,
    }
    if actual != expected:
        raise StateCoreStoreError("receipt index does not bind the canonical import evidence")


def _validate_snapshot_binding(
    *,
    source: str,
    batch: ImportBatch,
    manifest: ReceiptManifest,
    receipt_payload: dict[str, Any],
    records: Sequence[StateCoreRecord],
) -> None:
    from finharness.capital_import_registry import (
        materialized_source_for,
        receipt_index_contract_fields,
    )

    snapshots = [record for record in records if isinstance(record, Snapshot)]
    if len(snapshots) != 1:
        raise StateCoreStoreError("production import requires exactly one snapshot")
    snapshot = snapshots[0]
    if snapshot.snapshot_id != manifest.snapshot_id:
        raise StateCoreStoreError("snapshot does not match the receipt manifest")
    try:
        index_fields = receipt_index_contract_fields(
            source_kind=source,
            receipt_ref=manifest.receipt_ref,
            source_artifact_id=batch.source_artifact_id,
            time_semantics=batch.time_semantics,
            receipt_payload=receipt_payload,
        )
    except ValueError as exc:
        raise StateCoreStoreError(str(exc)) from exc
    expected_payload = {
        "source": materialized_source_for(source),
        "import_batch_id": batch.batch_id,
        "receipt_manifest_id": manifest.manifest_id,
        "import_receipt_id": manifest.receipt_id,
        "import_receipt_ref": manifest.receipt_ref,
        "source_artifact_id": batch.source_artifact_id,
        "record_counts": batch.record_counts,
        "coverage_mode": batch.coverage_mode,
        "completeness_status": batch.completeness_status,
        "time_semantics": batch.time_semantics,
        "findings": batch.findings,
    }
    if any(snapshot.payload.get(key) != value for key, value in expected_payload.items()):
        raise StateCoreStoreError("snapshot does not bind the canonical import envelope")
    if snapshot.source_refs != index_fields["source_refs"]:
        raise StateCoreStoreError("snapshot source refs do not bind the canonical import evidence")


def _validate_import_contract_fields(
    *, source: str, batch: ImportBatch, manifest: ReceiptManifest
) -> None:''',
)
replace_once(
    "src/finharness/statecore/store.py",
    ''') -> None:
    if source_schema != "finharness.import_source_evidence":''',
    ''') -> dict[str, Any]:
    if source_schema != "finharness.import_source_evidence":''',
)
replace_once(
    "src/finharness/statecore/store.py",
    '''    if manifest.record_counts != batch.record_counts:
        raise StateCoreStoreError("manifest record counts do not match the import batch")


def _tombstone_id''',
    '''    if manifest.record_counts != batch.record_counts:
        raise StateCoreStoreError("manifest record counts do not match the import batch")
    return receipt_payload


def _tombstone_id''',
)

replace_once(
    "src/finharness/personal_finance.py",
    '''        source_refs=source_refs,
        refs=[display_path(source_path)],
    )''',
    '''        source_refs=source_refs,
        refs=[display_path(source_path), prepared.batch.source_artifact_id],
    )''',
)
replace_once(
    "src/finharness/personal_finance.py",
    '''    deletion_records = _import_tombstones(batch=prepared.batch, deletions=tombstones)
    materialize_import_batch(
        [receipt_index, *records, *deletion_records],''',
    '''    deletion_records = _import_tombstones(batch=prepared.batch, deletions=tombstones)
    snapshot_record = next(record for record in records if isinstance(record, Snapshot))
    snapshot_record.payload = {
        **snapshot_record.payload,
        "import_batch_id": prepared.batch.batch_id,
        "receipt_manifest_id": prepared.manifest.manifest_id,
        "import_receipt_id": receipt_id,
        "import_receipt_ref": receipt_ref,
        "source_artifact_id": prepared.batch.source_artifact_id,
    }
    materialize_import_batch(
        [receipt_index, *records, *deletion_records],''',
)
replace_once(
    "src/finharness/beancount_adapter.py",
    '''    receipt_index = ReceiptIndex(
        receipt_id=receipt_id,''',
    '''    snapshot.payload = {
        **snapshot.payload,
        "import_batch_id": prepared.batch.batch_id,
        "receipt_manifest_id": prepared.manifest.manifest_id,
        "import_receipt_id": receipt_id,
        "import_receipt_ref": receipt_ref,
        "source_artifact_id": prepared.batch.source_artifact_id,
    }
    receipt_index = ReceiptIndex(
        receipt_id=receipt_id,''',
)
replace_once(
    "src/finharness/beancount_adapter.py",
    '''        source_refs=source_refs,
        refs=[display_path(source_path)],
    )''',
    '''        source_refs=source_refs,
        refs=[display_path(source_path), prepared.batch.source_artifact_id],
    )''',
)

replace_once(
    "src/finharness/capital_import_recovery.py",
    '''    PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES,
    materialized_source_for,
)''',
    '''    PRODUCTION_CAPITAL_IMPORT_MATERIALIZED_SOURCES,
    materialized_source_for,
    receipt_index_contract_fields,
)''',
)
replace_once(
    "src/finharness/capital_import_recovery.py",
    '''def _audit_manifest_mirror(
    manifest: ReceiptManifest,
    batch: ImportBatch,
    descriptor: ArtifactDescriptor | None,
    index: ReceiptIndex | None,
    snapshot: Snapshot | None,
) -> list[CapitalImportFinding]:
    findings: list[CapitalImportFinding] = []
    if index is None or index.path != manifest.receipt_ref:
        findings.append(
            _finding(
                "manifest_receipt_index_missing_or_stale",
                batch_id=batch.batch_id,
                receipt_id=manifest.receipt_id,
                path=manifest.receipt_ref,
                recoverable=True,
                recovery_action="rebuild_receipt_index",
            )
        )
    if snapshot is None:
        findings.append(
            _finding(
                "materialized_snapshot_missing",
                batch_id=batch.batch_id,
                receipt_id=manifest.receipt_id,
                artifact_id=manifest.receipt_artifact_id,
                recoverable=descriptor is not None,
                recovery_action="replay_receipt",
            )
        )
    elif (
        snapshot.payload.get("record_counts") != manifest.record_counts
        or manifest.receipt_ref not in snapshot.source_refs
    ):
        findings.append(
            _finding(
                "materialized_snapshot_binding_mismatch",
                batch_id=batch.batch_id,
                receipt_id=manifest.receipt_id,
                recoverable=False,
                recovery_action="quarantine_and_reimport",
            )
        )
    return findings
''',
    '''def _audit_manifest_mirror(
    manifest: ReceiptManifest,
    batch: ImportBatch,
    descriptor: ArtifactDescriptor | None,
    receipt_payload: dict[str, Any] | None,
    index: ReceiptIndex | None,
    snapshot: Snapshot | None,
) -> list[CapitalImportFinding]:
    findings: list[CapitalImportFinding] = []
    expected_index: dict[str, object] | None = None
    if receipt_payload is not None:
        try:
            expected_index = receipt_index_contract_fields(
                source_kind=batch.source_kind,
                receipt_ref=manifest.receipt_ref,
                source_artifact_id=batch.source_artifact_id,
                time_semantics=batch.time_semantics,
                receipt_payload=receipt_payload,
            )
        except ValueError:
            expected_index = None
    actual_index = (
        {
            "kind": index.kind,
            "path": index.path,
            "created_at_utc": index.created_at_utc,
            "source_refs": index.source_refs,
            "refs": index.refs,
        }
        if index is not None
        else None
    )
    if index is None or (
        expected_index is not None and actual_index != expected_index
    ) or (expected_index is None and index.path != manifest.receipt_ref):
        findings.append(
            _finding(
                "manifest_receipt_index_missing_or_stale",
                batch_id=batch.batch_id,
                receipt_id=manifest.receipt_id,
                path=manifest.receipt_ref,
                recoverable=expected_index is not None,
                recovery_action="rebuild_receipt_index",
            )
        )
    if snapshot is None:
        findings.append(
            _finding(
                "materialized_snapshot_missing",
                batch_id=batch.batch_id,
                receipt_id=manifest.receipt_id,
                artifact_id=manifest.receipt_artifact_id,
                recoverable=descriptor is not None,
                recovery_action="replay_receipt",
            )
        )
    else:
        expected_snapshot = {
            "source": materialized_source_for(batch.source_kind),
            "import_batch_id": batch.batch_id,
            "receipt_manifest_id": manifest.manifest_id,
            "import_receipt_id": manifest.receipt_id,
            "import_receipt_ref": manifest.receipt_ref,
            "source_artifact_id": batch.source_artifact_id,
            "record_counts": batch.record_counts,
            "coverage_mode": batch.coverage_mode,
            "completeness_status": batch.completeness_status,
            "time_semantics": batch.time_semantics,
            "findings": batch.findings,
        }
        expected_source_refs = (
            expected_index["source_refs"] if expected_index is not None else None
        )
        if (
            snapshot.snapshot_id != manifest.snapshot_id
            or any(
                snapshot.payload.get(key) != value
                for key, value in expected_snapshot.items()
            )
            or (
                expected_source_refs is not None
                and snapshot.source_refs != expected_source_refs
            )
        ):
            findings.append(
                _finding(
                    "materialized_snapshot_binding_mismatch",
                    batch_id=batch.batch_id,
                    receipt_id=manifest.receipt_id,
                    recoverable=False,
                    recovery_action="quarantine_and_reimport",
                )
            )
    return findings
''',
)
replace_once(
    "src/finharness/capital_import_recovery.py",
    '''        current_descriptor = descriptors_by_id.get(manifest.receipt_artifact_id)
        findings.extend(
            _audit_manifest_evidence(manifest, current_batch, current_descriptor, store)
        )
        findings.extend(
            _audit_manifest_mirror(
                manifest,
                current_batch,
                current_descriptor,
                indexes_by_receipt.get(manifest.receipt_id),
                snapshots.get(manifest.snapshot_id),
            )
        )''',
    '''        current_descriptor = descriptors_by_id.get(manifest.receipt_artifact_id)
        current_payload: dict[str, Any] | None = None
        if current_descriptor is not None:
            try:
                current_payload = _receipt_payload(store, current_descriptor)
            except CapitalImportRecoveryError:
                current_payload = None
        findings.extend(
            _audit_manifest_evidence(manifest, current_batch, current_descriptor, store)
        )
        findings.extend(
            _audit_manifest_mirror(
                manifest,
                current_batch,
                current_descriptor,
                current_payload,
                indexes_by_receipt.get(manifest.receipt_id),
                snapshots.get(manifest.snapshot_id),
            )
        )''',
)
replace_once(
    "src/finharness/capital_import_recovery.py",
    '''                current_index = session.get(ReceiptIndex, manifest.receipt_id)
                if current_index is None or current_index.path != manifest.receipt_ref:
                    payload = json.loads(content)
                    batch = batches[manifest.batch_id]
                    session.merge(
                        ReceiptIndex(
                            receipt_id=manifest.receipt_id,
                            kind=materialized_source_for(batch.source_kind),
                            path=manifest.receipt_ref,
                            created_at_utc=batch.as_of_utc,
                            source_refs=[manifest.receipt_ref, batch.source_id],
                            refs=[batch.source_id],
                        )
                    )
                    actions.append(f"rebuilt_receipt_index:{manifest.receipt_id}")''',
    '''                current_index = session.get(ReceiptIndex, manifest.receipt_id)
                payload = json.loads(content)
                batch = batches[manifest.batch_id]
                try:
                    expected_index = receipt_index_contract_fields(
                        source_kind=batch.source_kind,
                        receipt_ref=manifest.receipt_ref,
                        source_artifact_id=batch.source_artifact_id,
                        time_semantics=batch.time_semantics,
                        receipt_payload=payload,
                    )
                except ValueError:
                    continue
                actual_index = (
                    {
                        "kind": current_index.kind,
                        "path": current_index.path,
                        "created_at_utc": current_index.created_at_utc,
                        "source_refs": current_index.source_refs,
                        "refs": current_index.refs,
                    }
                    if current_index is not None
                    else None
                )
                if actual_index != expected_index:
                    session.merge(
                        ReceiptIndex(
                            receipt_id=manifest.receipt_id,
                            **expected_index,
                        )
                    )
                    actions.append(f"rebuilt_receipt_index:{manifest.receipt_id}")''',
)
