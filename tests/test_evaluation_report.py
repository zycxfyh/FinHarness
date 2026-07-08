"""Tests for EvaluationReport v0."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from finharness.evaluation_report import (
    EvaluationFinding,
    EvaluationSubject,
    build_evaluation_report,
    evaluation_report_from_queue_check,
    evaluation_report_from_scaffold_preflight,
    write_evaluation_report,
)


class TestEvaluationReport:
    """Unit tests for EvaluationReport model and builder."""

    def test_build_evaluation_report_with_findings(self) -> None:
        report = build_evaluation_report(
            evaluator_id="test_evaluator",
            subject_type="proposal",
            subject_id="p_001",
            status="warn",
            findings=[
                EvaluationFinding(
                    code="missing_evidence",
                    severity="warn",
                    message="Evidence ref is empty",
                    recovery_hint="Add at least one source ref",
                    source_refs=["s_1"],
                ),
            ],
            source_refs=["src_1"],
            receipt_refs=["r_1"],
        )
        assert report.report_id.startswith("er_")
        assert report.evaluator_id == "test_evaluator"
        assert report.subject.subject_type == "proposal"
        assert report.status == "warn"
        assert len(report.findings) == 1
        assert report.findings[0].code == "missing_evidence"
        assert report.findings[0].severity == "warn"
        assert report.execution_allowed is False
        assert report.authority_transition is False

    def test_build_evaluation_report_with_no_findings(self) -> None:
        report = build_evaluation_report(
            evaluator_id="empty_check",
            subject_type="proposal",
            subject_id="p_002",
            status="pass",
        )
        assert report.status == "pass"
        assert report.findings == []
        assert report.source_refs == []
        assert report.receipt_refs == []

    def test_evaluation_subject_model(self) -> None:
        subject = EvaluationSubject(subject_type="order_draft", subject_id="od_001")
        assert subject.subject_type == "order_draft"
        assert subject.subject_id == "od_001"

    def test_evaluation_finding_model(self) -> None:
        finding = EvaluationFinding(
            code="insufficient_risk_coverage",
            severity="block",
            message="Basis risks not linked to proposal",
            recovery_hint="Add basis_risk_ids referencing active risks",
            blocked_transitions=["approve", "stage"],
            source_refs=["risk_reg_001"],
            receipt_refs=["r_risk"],
        )
        assert finding.code == "insufficient_risk_coverage"
        assert finding.severity == "block"
        assert "approve" in finding.blocked_transitions
        assert "stage" in finding.blocked_transitions

    def test_report_hash_is_deterministic(self) -> None:
        r1 = build_evaluation_report(
            evaluator_id="det_test",
            subject_type="proposal",
            subject_id="p_hash",
            status="warn",
            findings=[
                EvaluationFinding(
                    code="test_code",
                    severity="warn",
                    message="test message",
                ),
            ],
        )
        r2 = build_evaluation_report(
            evaluator_id="det_test",
            subject_type="proposal",
            subject_id="p_hash",
            status="warn",
            findings=[
                EvaluationFinding(
                    code="test_code",
                    severity="warn",
                    message="test message",
                ),
            ],
        )
        assert r1.report_hash == r2.report_hash
        assert len(r1.report_hash) == 16

    def test_report_hash_differs_on_different_input(self) -> None:
        r1 = build_evaluation_report(
            evaluator_id="det_test",
            subject_type="proposal",
            subject_id="p_a",
            status="pass",
        )
        r2 = build_evaluation_report(
            evaluator_id="det_test",
            subject_type="proposal",
            subject_id="p_b",
            status="pass",
        )
        assert r1.report_hash != r2.report_hash

    def test_report_deduplicates_refs(self) -> None:
        report = build_evaluation_report(
            evaluator_id="dedup_test",
            subject_type="proposal",
            subject_id="p_dedup",
            status="pass",
            source_refs=["a", "a", "b"],
            receipt_refs=["r_a", "r_a"],
        )
        assert report.source_refs == ["a", "b"]
        assert report.receipt_refs == ["r_a"]

    def test_evaluation_report_is_not_execution_authority(self) -> None:
        report = build_evaluation_report(
            evaluator_id="auth_test",
            subject_type="proposal",
            subject_id="p_auth",
            status="pass",
        )
        assert report.execution_allowed is False
        assert report.authority_transition is False

    def test_evaluation_report_model_is_frozen(self) -> None:
        import pytest

        report = build_evaluation_report(
            evaluator_id="frozen_test",
            subject_type="proposal",
            subject_id="p_frozen",
            status="pass",
        )
        with pytest.raises(ValidationError, match="frozen"):
            report.status = "block"  # type: ignore[misc]


# ── Adapter from scaffold preflight ────────────────────────────────────────

PRETRAVEL_SAMPLE_FINDING_1: dict[str, Any] = {
    "code": "missing_risk_ref",
    "severity": "warn",
    "message": "Basis risk IDs not provided",
    "recovery_hint": "Add basis_risk_ids",
    "source_refs": ["src_1"],
    "receipt_refs": ["r_1"],
}
PRETRAVEL_SAMPLE_FINDING_2: dict[str, Any] = {
    "code": "rollback_incomplete",
    "severity": "block",
    "message": "Rollback info missing",
    "recovery_hint": "Add rollback_info",
    "source_refs": [],
    "receipt_refs": [],
}


class MockScaffoldPreflight:
    """Minimum mock of a ScaffoldCandidatePreflightReport."""

    def __init__(
        self,
        preflight_status: str = "warn",
        proposal_id: str = "p_mock",
        findings: list[dict[str, Any]] | None = None,
        receipt_refs: list[str] | None = None,
    ) -> None:
        self.preflight_status = preflight_status
        self.proposal_id = proposal_id
        self.findings = findings or []
        self.receipt_refs = receipt_refs or []


class TestAdapterFromScaffoldPreflight:
    def test_maps_status_correctly(self) -> None:
        for status in ("pass", "warn", "block"):
            mock = MockScaffoldPreflight(preflight_status=status)
            report = evaluation_report_from_scaffold_preflight(mock)
            assert report.status == status
            assert report.evaluator_id == "scaffold_candidate_preflight"

    def test_maps_findings(self) -> None:
        mock = MockScaffoldPreflight(
            preflight_status="block",
            findings=[PRETRAVEL_SAMPLE_FINDING_1, PRETRAVEL_SAMPLE_FINDING_2],
            receipt_refs=["r_preflight"],
        )
        report = evaluation_report_from_scaffold_preflight(mock)
        assert len(report.findings) == 2
        assert report.findings[0].code == "missing_risk_ref"
        assert report.findings[0].severity == "warn"
        assert report.findings[1].code == "rollback_incomplete"
        assert report.findings[1].severity == "block"
        assert report.findings[1].blocked_transitions == []
        assert "r_preflight" in report.receipt_refs

    def test_maps_subject(self) -> None:
        mock = MockScaffoldPreflight(proposal_id="p_scaffold_subj")
        report = evaluation_report_from_scaffold_preflight(mock)
        assert report.subject.subject_type == "scaffold_candidate"
        assert report.subject.subject_id == "p_scaffold_subj"

    def test_unknown_status_falls_back_to_warn(self) -> None:
        mock = MockScaffoldPreflight(preflight_status="unknown_status")
        report = evaluation_report_from_scaffold_preflight(mock)
        assert report.status == "warn"

    def test_unknown_severity_falls_back_to_warn(self) -> None:
        mock = MockScaffoldPreflight(
            findings=[{"code": "X", "severity": "critical", "message": "x"}],
        )
        report = evaluation_report_from_scaffold_preflight(mock)
        assert report.findings[0].severity == "warn"


# ── Adapter from queue check ───────────────────────────────────────────────


class MockQueueCheck:
    """Minimum mock of a proposal queue check output."""

    def __init__(
        self,
        status: str = "warn",
        proposal_id: str = "p_qmock",
        findings: list[dict[str, Any]] | None = None,
        receipt_refs: list[str] | None = None,
    ) -> None:
        self.status = status
        self.proposal_id = proposal_id
        self.findings = findings or []
        self.receipt_refs = receipt_refs or []


class TestAdapterFromQueueCheck:
    def test_maps_status(self) -> None:
        mock = MockQueueCheck(status="block")
        report = evaluation_report_from_queue_check(mock)
        assert report.status == "block"
        assert report.evaluator_id == "proposal_queue_check"

    def test_maps_findings(self) -> None:
        mock = MockQueueCheck(
            status="warn",
            findings=[
                {"code": "low_evidence", "severity": "info",
                 "message": "needs more", "source_refs": ["s1"]},
                {"code": "stale", "severity": "warn",
                 "message": "data old", "recovery_hint": "refresh"},
            ],
            receipt_refs=["r_qc"],
        )
        report = evaluation_report_from_queue_check(mock)
        assert len(report.findings) == 2
        assert report.findings[0].code == "low_evidence"
        assert report.findings[0].severity == "info"
        assert report.findings[1].code == "stale"
        assert report.findings[1].severity == "warn"
        assert report.findings[1].recovery_hint == "refresh"
        assert "r_qc" in report.receipt_refs

    def test_maps_subject(self) -> None:
        mock = MockQueueCheck(proposal_id="p_qc_subj")
        report = evaluation_report_from_queue_check(mock)
        assert report.subject.subject_type == "proposal"
        assert report.subject.subject_id == "p_qc_subj"

    def test_empty_findings_and_refs(self) -> None:
        mock = MockQueueCheck()
        report = evaluation_report_from_queue_check(mock)
        assert report.status == "warn"
        assert report.findings == []
        assert report.receipt_refs == []

    def test_unknown_status_falls_back_to_warn(self) -> None:
        mock = MockQueueCheck(status="invalid_status")
        report = evaluation_report_from_queue_check(mock)
        assert report.status == "warn"

    def test_execution_not_allowed(self) -> None:
        mock = MockQueueCheck()
        report = evaluation_report_from_queue_check(mock)
        assert report.execution_allowed is False
        assert report.authority_transition is False


# ── Real object projection (dataclass PreflightFinding) ──────────────────────


@dataclass(frozen=True)
class RealPreflightFinding:
    code: str
    severity: str
    message: str
    recovery_hint: str = ""
    source_refs: list[str] | None = None
    receipt_refs: list[str] | None = None


@dataclass(frozen=True)
class RealScaffoldPreflightReport:
    candidate_id: str = "c_001"
    proposal_id: str = "p_real"
    status: str = "block"
    system_preflight_recomputed: bool = True
    findings: list[object] | None = None
    candidate_receipt_ref: str | None = None
    current_proposal_receipt_ref: str | None = None
    proposed_scaffold: dict | None = None
    changed_fields: list[str] | None = None
    basis_risk_ids: list[str] | None = None
    active_basis_risk_ids: list[str] | None = None
    missing_basis_risk_ids: list[str] | None = None
    source_refs: list[str] | None = None
    receipt_refs: list[str] | None = None
    report_hash: str = "abc123"
    execution_allowed: bool = False
    authority_transition: bool = False


class TestRealObjectProjection:
    def test_scaffold_preflight_object_projects_status_and_findings(self) -> None:
        real = RealScaffoldPreflightReport(
            status="block",
            proposal_id="p_real_obj",
            findings=[
                RealPreflightFinding(
                    code="missing_risk_basis",
                    severity="block",
                    message="No basis risk IDs linked",
                    recovery_hint="Add basis_risk_ids",
                    source_refs=["src_1"],
                    receipt_refs=["r_1"],
                ),
            ],
            receipt_refs=["r_preflight_real"],
        )
        report = evaluation_report_from_scaffold_preflight(real)
        assert report.status == "block"
        assert len(report.findings) == 1
        f0 = report.findings[0]
        assert f0.code == "missing_risk_basis"
        assert f0.severity == "block"
        assert f0.message == "No basis risk IDs linked"
        assert f0.recovery_hint == "Add basis_risk_ids"
        assert f0.source_refs == ["src_1"]
        assert f0.receipt_refs == ["r_1"]
        assert "r_preflight_real" in report.receipt_refs

    def test_scaffold_preflight_dict_projection_still_works(self) -> None:
        """Backward compatibility: dict-based test doubles still work."""
        mock = MockScaffoldPreflight(
            preflight_status="warn",
            findings=[
                {"code": "old_style", "severity": "info", "message": "dict finding"},
            ],
        )
        report = evaluation_report_from_scaffold_preflight(mock)
        assert report.status == "warn"
        assert len(report.findings) == 1
        assert report.findings[0].code == "old_style"

    def test_scaffold_preflight_mixed_finding_types(self) -> None:
        """Mixed dataclass + dict findings both work."""
        mixed_report = RealScaffoldPreflightReport(
            status="warn",
            proposal_id="p_mixed",
            findings=[
                RealPreflightFinding(code="real_finding", severity="warn", message="real"),
                {"code": "dict_finding", "severity": "info", "message": "dict"},
            ],
        )
        report = evaluation_report_from_scaffold_preflight(mixed_report)
        assert len(report.findings) == 2
        codes = {f.code for f in report.findings}
        assert "real_finding" in codes
        assert "dict_finding" in codes


# ── Real ProposalQueueChecks projection ─────────────────────────────────────


@dataclass(frozen=True)
class RealQueueCheckFinding:
    code: str
    severity: str
    classification: str = "finding"
    message: str = ""
    recovery_hint: str = ""
    source_refs: list[str] | None = None
    receipt_refs: list[str] | None = None


@dataclass(frozen=True)
class RealProposalQueueChecks:
    proposal_id: str = "p_real"
    check_state: str = "review_required"
    blocks: list[object] | None = None
    warnings: list[object] | None = None
    source_refs: list[str] | None = None
    receipt_refs: list[str] | None = None


class TestRealQueueCheckProjection:
    def test_queue_check_object_projects_blocks_and_warnings(self) -> None:
        real = RealProposalQueueChecks(
            proposal_id="p_qc_real",
            check_state="blocked",
            blocks=[
                RealQueueCheckFinding(
                    code="missing_source_refs",
                    severity="block",
                    message="No source refs provided",
                    source_refs=["src_qc"],
                    receipt_refs=["r_qc_block"],
                ),
            ],
            warnings=[
                RealQueueCheckFinding(
                    code="stale_context",
                    severity="warn",
                    message="Context is older than 7 days",
                    receipt_refs=["r_qc_warn"],
                ),
            ],
            receipt_refs=["r_qc_total"],
        )
        report = evaluation_report_from_queue_check(real)
        assert report.status == "block"
        assert len(report.findings) == 2
        # Blocks come first, warnings second
        assert report.findings[0].code == "missing_source_refs"
        assert report.findings[0].severity == "block"
        assert report.findings[1].code == "stale_context"
        assert report.findings[1].severity == "warn"
        assert "r_qc_total" in report.receipt_refs

    def test_queue_check_dict_projection_still_works(self) -> None:
        mock = MockQueueCheck(
            status="warn",
            findings=[
                {"code": "old_dict", "severity": "info", "message": "dict"},
            ],
        )
        report = evaluation_report_from_queue_check(mock)
        assert report.status == "warn"
        assert len(report.findings) == 1
        assert report.findings[0].code == "old_dict"

    def test_queue_check_state_maps_correctly(self) -> None:
        for state, expected in (
            ("clear", "pass"),
            ("review_required", "warn"),
            ("blocked", "block"),
            ("pass", "pass"),
            ("warn", "warn"),
            ("block", "block"),
        ):
            real = RealProposalQueueChecks(check_state=state, warnings=[
                RealQueueCheckFinding(code="x", severity="warn", message="x"),
            ])
            report = evaluation_report_from_queue_check(real)
            assert report.status == expected, f"{state} → {report.status}, expected {expected}"


# ── EvaluationReport receipt writer ─────────────────────────────────────────


class TestEvaluationReportReceiptWriter:
    def test_writes_json_and_returns_stable_ref(self) -> None:
        report = build_evaluation_report(
            evaluator_id="writer_test",
            subject_type="proposal",
            subject_id="p_writer",
            status="warn",
            findings=[
                EvaluationFinding(code="test", severity="warn", message="test"),
            ],
        )
        with tempfile.TemporaryDirectory() as tmp:
            ref = write_evaluation_report(report=report, receipt_root=tmp)
            assert "evaluation-reports/" in ref
            assert f"{report.report_id}.json" in ref
            assert f"sha256:{report.report_hash}" in ref
            file_path = Path(tmp) / "evaluation-reports" / f"{report.report_id}.json"
            assert file_path.exists()
            payload = json.loads(file_path.read_text())
            assert payload["status"] == "warn"
            assert payload["execution_allowed"] is False

    def test_preserves_execution_allowed_false(self) -> None:
        report = build_evaluation_report(
            evaluator_id="auth_test",
            subject_type="proposal",
            subject_id="p_auth",
            status="pass",
        )
        with tempfile.TemporaryDirectory() as tmp:
            write_evaluation_report(report=report, receipt_root=tmp)
            file_path = Path(tmp) / "evaluation-reports" / f"{report.report_id}.json"
            payload = json.loads(file_path.read_text())
            assert payload["execution_allowed"] is False
            assert payload["authority_transition"] is False

    def test_authority_transition_can_reference_evaluation_receipt(self) -> None:
        from finharness.authority_transition import record_authority_transition

        report = build_evaluation_report(
            evaluator_id="at_integration",
            subject_type="proposal",
            subject_id="p_at_int",
            status="warn",
            findings=[
                EvaluationFinding(code="missing_evidence", severity="warn",
                                  message="Evidence ref is empty"),
            ],
        )
        with tempfile.TemporaryDirectory() as tmp:
            eval_ref = write_evaluation_report(report=report, receipt_root=tmp)
            at_record = record_authority_transition(
                subject_type="proposal",
                subject_id="p_at_int",
                from_state="draft",
                to_state="eligible",
                eligibility="eligible",
                evaluation_report_refs=[eval_ref],
                human_attester="ops",
                human_reason="Evaluation report shows warn but no block — eligible",
                explicit_confirmation=True,
                receipt_root=tmp,
            )
            assert eval_ref in at_record.evaluation_report_refs
            assert at_record.receipt_ref is not None
            assert Path(at_record.receipt_ref).exists()
