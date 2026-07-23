# finharness-test-runner: pytest
from __future__ import annotations

from scripts.benchmark_capital_world import SCHEMA, run_benchmark


def test_benchmark_is_bounded_and_does_not_claim_a_production_slo() -> None:
    report = run_benchmark((2,), repetitions=2)
    assert report["schema"] == SCHEMA
    assert report["execution_allowed"] is False
    assert report["results"][0]["source_count"] == 2
    assert report["results"][0]["selected_batch_count"] == 2
    assert report["results"][0]["position_count"] == 2
    assert report["results"][0]["world_status"] == "admitted"
    assert "Not a production SLO." in report["limitations"]
