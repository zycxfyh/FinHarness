from __future__ import annotations

import csv
import hashlib
import time
from pathlib import Path

from sqlmodel import Session

from finharness.artifact_store import LocalArtifactStore
from finharness.personal_finance import ingest_personal_finance_export
from finharness.statecore.capital_world import resolve_capital_world
from finharness.statecore.models import (
    CapitalImportSourceAlias,
    ImportBatch,
    Liability,
)
from finharness.statecore.store import init_state_core, read_all

FIXTURE_ROOT = Path(__file__).parent / "fixtures"
TYPED_COLUMNS = (
    FIXTURE_ROOT / "personal_finance_typed_export.csv"
).read_text(encoding="utf-8").splitlines()[0].split(",")


def _position_export(path: Path, as_of: str, *, spy_value: str = "9000") -> None:
    template = (
        FIXTURE_ROOT / "capital_review" / "admitted.csv.template"
    ).read_text(encoding="utf-8")
    text = template.replace("{{AS_OF_UTC}}", as_of).replace("{{VALUED_AT_UTC}}", as_of)
    text = text.replace(",9000,8100,USD,", f",{spy_value},8100,USD,")
    path.write_text(text, encoding="utf-8")


def _typed_export(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=TYPED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _liability(liability_id: str, balance: str, as_of: str) -> dict[str, str]:
    return {
        "record_type": "liability",
        "liability_id": liability_id,
        "name": liability_id,
        "liability_type": "loan",
        "balance": balance,
        "currency": "USD",
        "as_of_utc": as_of,
    }


def _batch(engine, batch_id: str) -> ImportBatch:
    with Session(engine) as session:
        batch = session.get(ImportBatch, batch_id)
        assert batch is not None
        return batch


def test_path_move_preserves_source_batch_projection_and_world(tmp_path: Path) -> None:
    engine = init_state_core(tmp_path / "state.sqlite")
    receipts = tmp_path / "receipts"
    first_path = tmp_path / "first.csv"
    moved_path = tmp_path / "moved.csv"
    as_of = "2026-07-01T12:00:00+00:00"
    _position_export(first_path, as_of)

    first = ingest_personal_finance_export(
        first_path, engine=engine, receipt_root=receipts
    )
    first_batch = _batch(engine, first.batch_id)
    assert first_batch.stable_source_id
    assert first_batch.projection_artifact_id
    assert first_batch.projection_sha256

    moved_path.write_bytes(first_path.read_bytes())
    replay = ingest_personal_finance_export(
        moved_path,
        engine=engine,
        receipt_root=receipts,
        source_id=first_batch.stable_source_id,
    )
    replay_batch = _batch(engine, replay.batch_id)

    assert replay.batch_id == first.batch_id
    assert replay.snapshot_id == first.snapshot_id
    assert replay_batch.projection_sha256 == first_batch.projection_sha256
    aliases = read_all(CapitalImportSourceAlias, engine=engine)
    assert {alias.source_id for alias in aliases} == {first_batch.stable_source_id}
    assert len(aliases) == 2

    first_world = resolve_capital_world(
        engine=engine, as_of_utc=as_of, known_at_utc="2099-01-01T00:00:00+00:00"
    )
    second_world = resolve_capital_world(
        engine=engine, as_of_utc=as_of, known_at_utc="2099-01-01T00:00:00+00:00"
    )
    assert first_world.world_id == second_world.world_id
    assert first_world.trust.status == "admitted"
    assert first_world.selected_sources[0].batch_id == first.batch_id
    store = LocalArtifactStore(receipts / "artifact-store")
    assert store.read(first_batch.projection_artifact_id)
    engine.dispose()


def test_historical_as_of_selects_the_legal_batch_without_lookahead(tmp_path: Path) -> None:
    engine = init_state_core(tmp_path / "state.sqlite")
    receipts = tmp_path / "receipts"
    source = tmp_path / "capital.csv"
    t1 = "2026-07-01T12:00:00+00:00"
    t2 = "2026-07-02T12:00:00+00:00"
    _position_export(source, t1, spy_value="9000")
    first = ingest_personal_finance_export(source, engine=engine, receipt_root=receipts)
    _position_export(source, t2, spy_value="8000")
    second = ingest_personal_finance_export(source, engine=engine, receipt_root=receipts)

    historical = resolve_capital_world(
        engine=engine, as_of_utc=t1, known_at_utc="2099-01-01T00:00:00+00:00"
    )
    current = resolve_capital_world(
        engine=engine, as_of_utc=t2, known_at_utc="2099-01-01T00:00:00+00:00"
    )

    assert historical.selected_sources[0].batch_id == first.batch_id
    assert current.selected_sources[0].batch_id == second.batch_id
    assert historical.world_id != current.world_id
    assert sum(position.market_value or 0 for position in historical.positions) == 10000
    assert sum(position.market_value or 0 for position in current.positions) == 9000
    engine.dispose()


def test_late_correction_only_changes_world_after_it_is_known(tmp_path: Path) -> None:
    engine = init_state_core(tmp_path / "state.sqlite")
    receipts = tmp_path / "receipts"
    source = tmp_path / "capital.csv"
    as_of = "2026-07-02T12:00:00+00:00"
    _position_export(source, as_of, spy_value="9000")
    original = ingest_personal_finance_export(source, engine=engine, receipt_root=receipts)
    original_batch = _batch(engine, original.batch_id)
    assert original_batch.recorded_at_utc

    time.sleep(0.01)
    _position_export(source, as_of, spy_value="8500")
    correction = ingest_personal_finance_export(
        source,
        engine=engine,
        receipt_root=receipts,
        supersedes_batch_id=original.batch_id,
        correction_reason="Corrected source valuation",
    )
    correction_batch = _batch(engine, correction.batch_id)
    assert correction_batch.recorded_at_utc
    assert correction_batch.recorded_at_utc > original_batch.recorded_at_utc

    before_known = resolve_capital_world(
        engine=engine,
        as_of_utc=as_of,
        known_at_utc=original_batch.recorded_at_utc,
    )
    after_known = resolve_capital_world(
        engine=engine,
        as_of_utc=as_of,
        known_at_utc=correction_batch.recorded_at_utc,
    )
    assert before_known.selected_sources[0].batch_id == original.batch_id
    assert after_known.selected_sources[0].batch_id == correction.batch_id
    assert sum(position.market_value or 0 for position in before_known.positions) == 10000
    assert sum(position.market_value or 0 for position in after_known.positions) == 9500
    engine.dispose()


def test_equal_time_independent_heads_fail_closed(tmp_path: Path) -> None:
    engine = init_state_core(tmp_path / "state.sqlite")
    receipts = tmp_path / "receipts"
    source = tmp_path / "capital.csv"
    as_of = "2026-07-02T12:00:00+00:00"
    _position_export(source, as_of, spy_value="9000")
    ingest_personal_finance_export(source, engine=engine, receipt_root=receipts)
    time.sleep(0.01)
    _position_export(source, as_of, spy_value="8500")
    ingest_personal_finance_export(source, engine=engine, receipt_root=receipts)

    world = resolve_capital_world(
        engine=engine, as_of_utc=as_of, known_at_utc="2099-01-01T00:00:00+00:00"
    )
    assert world.trust.status == "blocked"
    assert any(code.startswith("ambiguous_source_head:") for code in world.trust.blockers)
    engine.dispose()


def test_full_import_cleanup_is_scoped_to_stable_source(tmp_path: Path) -> None:
    engine = init_state_core(tmp_path / "state.sqlite")
    receipts = tmp_path / "receipts"
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    t1 = "2026-07-01T12:00:00+00:00"
    t2 = "2026-07-02T12:00:00+00:00"
    _typed_export(a, [_liability("liab_a", "100", t1)])
    _typed_export(b, [_liability("liab_b", "200", t1)])
    ingest_personal_finance_export(a, engine=engine, receipt_root=receipts)
    ingest_personal_finance_export(b, engine=engine, receipt_root=receipts)

    _typed_export(a, [_liability("liab_a2", "150", t2)])
    ingest_personal_finance_export(a, engine=engine, receipt_root=receipts)
    assert {item.liability_id for item in read_all(Liability, engine=engine)} == {
        "liab_a2",
        "liab_b",
    }
    engine.dispose()


def test_newer_position_batch_preserves_older_liability_domain(tmp_path: Path) -> None:
    engine = init_state_core(tmp_path / "state.sqlite")
    receipts = tmp_path / "receipts"
    source = tmp_path / "capital.csv"
    t1 = "2026-07-01T12:00:00+00:00"
    t2 = "2026-07-02T12:00:00+00:00"
    _typed_export(source, [_liability("mortgage", "250000", t1)])
    first = ingest_personal_finance_export(
        source,
        engine=engine,
        receipt_root=receipts,
    )
    first_batch = _batch(engine, first.batch_id)
    assert first_batch.stable_source_id
    assert first_batch.covered_domains == ["liability"]

    _position_export(source, t2)
    second = ingest_personal_finance_export(
        source,
        engine=engine,
        receipt_root=receipts,
        source_id=first_batch.stable_source_id,
    )
    second_batch = _batch(engine, second.batch_id)
    assert second_batch.covered_domains == ["position"]

    world = resolve_capital_world(
        engine=engine,
        as_of_utc=t2,
        known_at_utc="2099-01-01T00:00:00+00:00",
    )
    selected = {
        (selection.batch_id, selection.covered_domains)
        for selection in world.selected_sources
    }
    assert selected == {
        (first.batch_id, ("liability",)),
        (second.batch_id, ("position",)),
    }
    assert {item.liability_id for item in world.liabilities} == {"mortgage"}
    assert len(world.positions) == 2
    assert world.trust.status == "partial"
    assert world.trust.valuation_status == "admitted"
    assert world.trust.blockers == ()
    engine.dispose()


def test_two_sources_claiming_same_fact_block_world(tmp_path: Path) -> None:
    engine = init_state_core(tmp_path / "state.sqlite")
    receipts = tmp_path / "receipts"
    a = tmp_path / "a.csv"
    b = tmp_path / "b.csv"
    as_of = "2026-07-01T12:00:00+00:00"
    _typed_export(a, [_liability("shared_liability", "100", as_of)])
    _typed_export(b, [_liability("shared_liability", "110", as_of)])
    ingest_personal_finance_export(a, engine=engine, receipt_root=receipts)
    ingest_personal_finance_export(b, engine=engine, receipt_root=receipts)

    world = resolve_capital_world(
        engine=engine, as_of_utc=as_of, known_at_utc="2099-01-01T00:00:00+00:00"
    )
    assert world.trust.status == "blocked"
    assert "source_ownership_conflict:Liability:shared_liability" in world.trust.blockers
    engine.dispose()


def test_world_identity_is_stable_across_equivalent_query_clocks(tmp_path: Path) -> None:
    engine = init_state_core(tmp_path / "state.sqlite")
    receipts = tmp_path / "receipts"
    source = tmp_path / "capital.csv"
    as_of = "2026-07-01T12:00:00+00:00"
    _position_export(source, as_of)
    ingest_personal_finance_export(source, engine=engine, receipt_root=receipts)

    first = resolve_capital_world(
        engine=engine,
        as_of_utc="2026-07-02T00:00:00+00:00",
        known_at_utc="2026-07-02T00:00:00+00:00",
    )
    second = resolve_capital_world(
        engine=engine,
        as_of_utc="2026-07-03T00:00:00+00:00",
        known_at_utc="2026-07-03T00:00:00+00:00",
    )
    assert first.selected_sources == second.selected_sources
    assert first.world_id == second.world_id
    assert first.basis_digest == second.basis_digest
    assert first.query != second.query
    engine.dispose()


def test_resolver_is_read_only(tmp_path: Path) -> None:
    db = tmp_path / "state.sqlite"
    engine = init_state_core(db)
    receipts = tmp_path / "receipts"
    source = tmp_path / "capital.csv"
    as_of = "2026-07-01T12:00:00+00:00"
    _position_export(source, as_of)
    ingest_personal_finance_export(source, engine=engine, receipt_root=receipts)
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    resolve_capital_world(
        engine=engine, as_of_utc=as_of, known_at_utc="2099-01-01T00:00:00+00:00"
    )
    after = hashlib.sha256(db.read_bytes()).hexdigest()
    assert before == after
    engine.dispose()
