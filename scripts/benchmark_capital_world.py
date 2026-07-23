#!/usr/bin/env python3
"""Bounded local latency baseline for deterministic Capital World resolution.

This is not a production SLO or a benchmark over every workload. It measures
one synthetic, fully materialized position-domain shape at explicit source counts.
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlmodel import Session

from finharness.capital_projection import build_capital_projection, projection_sha256
from finharness.statecore.capital_world import resolve_capital_world
from finharness.statecore.models import (
    CapitalImportSource,
    ImportBatch,
    Position,
    ReceiptManifest,
    Snapshot,
)
from finharness.statecore.store import init_state_core

SCHEMA = "finharness.capital_world_benchmark.v1"
DEFAULT_SIZES = (10, 100, 1000)
OBSERVED_AT = "2026-07-23T00:00:00+00:00"
KNOWN_AT = "2026-07-23T01:00:00+00:00"


def _seed(engine: Any, source_count: int) -> None:
    records: list[Any] = []
    for index in range(source_count):
        source_id = f"source_benchmark_{index:06d}"
        batch_id = f"import_batch_benchmark_{index:06d}"
        snapshot_id = f"snapshot_benchmark_{index:06d}"
        source = CapitalImportSource(
            source_id=source_id,
            source_kind="benchmark",
            display_name=f"benchmark source {index}",
            authority_level="read_only",
            source_refs=[f"benchmark:{index}"],
            created_at_utc=OBSERVED_AT,
        )
        snapshot = Snapshot(
            snapshot_id=snapshot_id,
            kind="portfolio",
            as_of_utc=OBSERVED_AT,
            authority_level="read_only",
            source_refs=[source_id],
            payload={"time_semantics": {"observed_at_utc": OBSERVED_AT}},
        )
        position = Position(
            position_id=f"position_benchmark_{index:06d}",
            snapshot_id=snapshot_id,
            account_id=f"account_benchmark_{index:06d}",
            symbol=f"BENCH:{index:06d}",
            quantity=Decimal("1"),
            market_value=Decimal("100"),
            valuation_currency="USD",
            unit_price=Decimal("100"),
            price_currency="USD",
            valued_at_utc=OBSERVED_AT,
            price_source_ref=f"benchmark:{index}",
            valuation_status="valued",
            as_of_utc=OBSERVED_AT,
            authority_level="read_only",
            source_refs=[source_id],
        )
        time_semantics = {
            "effective_at_utc": OBSERVED_AT,
            "observed_at_utc": OBSERVED_AT,
            "recorded_at_utc": OBSERVED_AT,
        }
        projection = build_capital_projection(
            batch_id=batch_id,
            stable_source_id=source_id,
            source_kind="benchmark",
            coverage_mode="full",
            covered_domains=["position"],
            time_semantics=time_semantics,
            records=[snapshot, position],
        )
        digest = projection_sha256(projection)
        batch = ImportBatch(
            batch_id=batch_id,
            source_kind="benchmark",
            source_id=source_id,
            stable_source_id=source_id,
            coverage_mode="full",
            source_sha256=f"{index:064x}",
            source_artifact_id=f"source_artifact_{index:06d}",
            projection_artifact_id=f"projection_artifact_{index:06d}",
            projection_sha256=digest,
            projection_schema_version="finharness.capital_import_projection.v1",
            projection_payload=projection,
            effective_at_utc=OBSERVED_AT,
            observed_at_utc=OBSERVED_AT,
            recorded_at_utc=OBSERVED_AT,
            adapter_version="benchmark.v1",
            import_schema_version="benchmark.v1",
            record_counts={"Snapshot": 1, "Position": 1},
            covered_domains=["position"],
            corporate_action_status="unsupported_gap",
            completeness_status="complete",
            time_semantics=time_semantics,
            authority_level="read_only",
        )
        manifest = ReceiptManifest(
            manifest_id=f"manifest_benchmark_{index:06d}",
            batch_id=batch_id,
            receipt_id=f"receipt_benchmark_{index:06d}",
            receipt_ref=f"benchmark/receipt_{index:06d}.json",
            receipt_sha256=f"{source_count + index:064x}",
            receipt_artifact_id=f"receipt_artifact_{index:06d}",
            source_artifact_id=batch.source_artifact_id,
            snapshot_id=snapshot_id,
            materialization_status="materialized",
            record_counts=batch.record_counts,
            materialized_at_utc=OBSERVED_AT,
            authority_level="read_only",
        )
        records.extend((source, batch, manifest))
    with Session(engine) as session:
        session.add_all(records)
        session.commit()


def benchmark_size(*, source_count: int, repetitions: int) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"finharness-world-benchmark-{source_count}-") as tmp:
        engine = init_state_core(Path(tmp) / "state.sqlite")
        try:
            seed_started = time.perf_counter()
            _seed(engine, source_count)
            seed_ms = (time.perf_counter() - seed_started) * 1000
            resolve_capital_world(
                engine=engine,
                as_of_utc=KNOWN_AT,
                known_at_utc=KNOWN_AT,
                use_case="agent_context",
            )
            samples: list[float] = []
            world = None
            for _ in range(repetitions):
                started = time.perf_counter()
                world = resolve_capital_world(
                    engine=engine,
                    as_of_utc=KNOWN_AT,
                    known_at_utc=KNOWN_AT,
                    use_case="agent_context",
                )
                samples.append((time.perf_counter() - started) * 1000)
            if world is None:
                raise RuntimeError("benchmark did not resolve a Capital World")
        finally:
            engine.dispose()
    ordered = sorted(samples)
    p95_index = max(0, min(len(ordered) - 1, round(0.95 * len(ordered)) - 1))
    return {
        "source_count": source_count,
        "selected_batch_count": len(world.selected_sources),
        "position_count": len(world.positions),
        "world_status": world.trust.status,
        "seed_ms": round(seed_ms, 3),
        "samples": repetitions,
        "latency_ms": {
            "min": round(min(samples), 3),
            "median": round(statistics.median(samples), 3),
            "p95": round(ordered[p95_index], 3),
            "max": round(max(samples), 3),
        },
    }


def run_benchmark(sizes: tuple[int, ...], repetitions: int) -> dict[str, Any]:
    if not sizes or any(size <= 0 for size in sizes):
        raise ValueError("benchmark sizes must be positive")
    if repetitions <= 0:
        raise ValueError("repetitions must be positive")
    return {
        "schema": SCHEMA,
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "workload": "one materialized position-domain batch per stable source",
        "limitations": [
            "Local synthetic SQLite baseline only.",
            "Not a production SLO.",
            "Not evidence for concurrent, remote, mixed-domain, or all-workload performance.",
        ],
        "results": [
            benchmark_size(source_count=size, repetitions=repetitions)
            for size in sizes
        ],
        "execution_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", default=",".join(str(size) for size in DEFAULT_SIZES))
    parser.add_argument("--repetitions", type=int, default=5)
    args = parser.parse_args()
    sizes = tuple(int(item.strip()) for item in args.sizes.split(",") if item.strip())
    print(json.dumps(run_benchmark(sizes, args.repetitions), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
