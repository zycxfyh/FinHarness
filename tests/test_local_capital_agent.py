# finharness-test-runner: pytest
from __future__ import annotations

from pathlib import Path

from scripts.run_local_capital_agent import run_local_capital_agent

from finharness.statecore.store import init_state_core


def test_empty_local_state_is_typed_read_only_stop(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    db = tmp_path / "state.sqlite"
    engine = init_state_core(db)
    engine.dispose()
    domain_receipts = tmp_path / "domain-receipts"
    domain_receipts.mkdir()
    (domain_receipts / "existing.json").write_text('{"stable":true}\n')

    report = run_local_capital_agent(
        state_db=db,
        output_root=tmp_path / "agent-output",
        domain_receipt_root=domain_receipts,
    )

    assert report["work"]["outcome"] == "stopped"
    assert report["work"]["stop_reason"] == "semantic_stop"
    assert report["work"]["audit_disposition"] == "stopped"
    assert report["work"]["all_tool_side_effects_read"] is True
    assert report["audit"]["world_status"] == "legacy_unresolved"
    assert "capital_world_not_admitted" in report["audit"]["blockers"]
    assert report["hermetic_replay"]["same_typed_contract"] is True
    assert report["state_core"]["logical_digest_unchanged"] is True
    assert report["domain_receipts"]["unchanged"] is True
    assert report["real_model"]["status"] == "unavailable"
    assert report["execution_allowed"] is False
