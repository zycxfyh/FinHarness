# finharness-test-runner: pytest
from __future__ import annotations

from finharness.capital_world_audit import CapitalAuditClaim, CapitalWorldAudit
from finharness.openai_capital_audit_port import run_openai_capital_world_audit

WORLD_ID = "capital_world_0123456789abcdef01234567"
BASIS = "0" * 64
SOURCE = "dataset://scf/household/1"


def _baseline(*, status: str = "admitted") -> CapitalWorldAudit:
    stopped = status != "admitted"
    lineage = {
        "world_refs": [f"capital_world://{WORLD_ID}"],
        "source_refs": [SOURCE],
        "artifact_refs": ["agent-tool-results/1.json"],
    }
    return CapitalWorldAudit(
        audit_id="capital_audit_0123456789abcdef0123",
        goal="Audit Capital World",
        disposition="stopped" if stopped else "complete",
        world_id=WORLD_ID,
        basis_digest=BASIS,
        world_status=status,
        observed=[CapitalAuditClaim(
            classification="observed",
            statement=f"Capital World status is {status}.",
            confidence="high",
            **lineage,
        )],
        unsupported=[CapitalAuditClaim(
            classification="unsupported",
            statement="Allocation recommendations are unsupported.",
            confidence="none",
            **lineage,
        )] if stopped else [],
        blockers=["capital_world_not_admitted"] if stopped else [],
        findings=[],
        counter_evidence=["Read-only audit does not grant authority."],
        investigation_questions=["Is the world admitted?"],
        stop_conditions=["Stop if world identity changes."],
        required_evaluations=["read_only_boundary_check"],
        human_handoff="Human review required.",
        source_refs=[SOURCE],
        artifact_refs=["agent-tool-results/1.json"],
    )


def test_missing_key_returns_typed_unavailable_without_provider_call(
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    attempt = run_openai_capital_world_audit(_baseline())
    assert attempt.status == "unavailable"
    assert attempt.audit is None
    assert any("no provider call" in finding for finding in attempt.findings)
    assert attempt.execution_allowed is False


def test_structured_model_result_is_accepted_only_after_invariant_check(
    monkeypatch,
) -> None:
    baseline = _baseline()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "finharness.openai_capital_audit_port._run_structured_model",
        lambda _baseline, model_name: baseline,
    )
    attempt = run_openai_capital_world_audit(baseline, model="gpt-test")
    assert attempt.status == "completed"
    assert attempt.audit is not None
    assert attempt.audit.model_provider == "openai"
    assert attempt.audit.model_name == "gpt-test"
    assert attempt.audit.execution_allowed is False


def test_model_world_identity_change_is_rejected(monkeypatch) -> None:
    baseline = _baseline()
    candidate = baseline.model_copy(
        update={"world_id": "capital_world_abcdef0123456789abcdef01"}
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "finharness.openai_capital_audit_port._run_structured_model",
        lambda _baseline, model_name: candidate,
    )
    attempt = run_openai_capital_world_audit(baseline)
    assert attempt.status == "rejected"
    assert "model_world_id_mismatch" in attempt.findings


def test_model_cannot_weaken_deterministic_stop(monkeypatch) -> None:
    baseline = _baseline(status="blocked")
    candidate = baseline.model_copy(update={"disposition": "complete", "blockers": []})
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "finharness.openai_capital_audit_port._run_structured_model",
        lambda _baseline, model_name: candidate,
    )
    attempt = run_openai_capital_world_audit(baseline)
    assert attempt.status == "rejected"
    assert "model_weakened_semantic_stop" in attempt.findings
    assert "model_omitted_deterministic_blockers" in attempt.findings
