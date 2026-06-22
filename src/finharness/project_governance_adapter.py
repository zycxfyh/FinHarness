"""Compatibility adapter for workstation Project Governance Loop receipts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from finharness.repo_intelligence import ROOT

WORKFLOW_VERSION = "finharness_project_governance_adapter_v1"
DEFAULT_WORKSTATION_RECEIPT = Path(
    "/root/workstation-lab/receipts/project-governance-loop/finharness/latest.json"
)

STAGE_COMPATIBILITY = [
    {
        "stage": "cognitive_intake",
        "reference_object": "cognitive_graph.py",
        "public_api": "run_cognitive_project_flow",
        "taskfile_entrypoint": "workflow:cognitive",
        "current_outputs": [
            "ideas/*.md",
            "docs/notes/*-workflow-note.md",
            "docs/proposals/*.md",
            "docs/reviews/*.md",
            "docs/lessons/*.md",
            "data/receipts/cognitive-graph/*.json",
        ],
    },
    {
        "stage": "repo_observation",
        "reference_object": "repo_intelligence_graph.py",
        "public_api": "run_repo_intelligence_graph",
        "taskfile_entrypoint": "repo:intelligence",
        "current_outputs": [
            "data/receipts/repo-intelligence/latest.json",
            "docs/architecture/generated/repo-intelligence.md",
        ],
    },
    {
        "stage": "quality_gate",
        "reference_object": "quality_governance_graph.py",
        "public_api": "run_quality_governance_graph",
        "taskfile_entrypoint": "quality:governance",
        "current_outputs": ["data/receipts/quality-governance/latest.json"],
    },
    {
        "stage": "delivery_receipt",
        "reference_object": "engineering_delivery_graph.py",
        "public_api": "run_engineering_delivery_graph",
        "taskfile_entrypoint": "workflow:engineering-delivery",
        "current_outputs": [
            "data/receipts/engineering-delivery/*.json",
            "docs/reviews/*-engineering-delivery.md",
        ],
    },
]


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _project_receipt(payload: dict[str, Any]) -> dict[str, Any]:
    if "delivery_receipts" in payload:
        return dict(payload["delivery_receipts"]["finharness"])
    return payload


def build_finharness_project_governance_contract(
    *,
    root: Path = ROOT,
    workstation_receipt_path: Path = DEFAULT_WORKSTATION_RECEIPT,
) -> dict[str, Any]:
    return {
        "workflow": WORKFLOW_VERSION,
        "project": "finharness",
        "root": str(root),
        "workstation_receipt_path": str(workstation_receipt_path),
        "workstation_receipt_present": workstation_receipt_path.exists(),
        "stage_compatibility": STAGE_COMPATIBILITY,
        "compatibility_policy": {
            "preserve_public_apis": True,
            "preserve_taskfile_entrypoints": True,
            "preserve_current_output_paths": True,
            "workstation_loop_dependency": "optional receipt bridge; no import-time dependency",
        },
        "authority_boundary": (
            "This adapter summarizes workstation governance evidence for FinHarness; "
            "it does not authorize trading, release, migration, or source movement."
        ),
    }


def adapt_workstation_project_governance_receipt(
    payload: dict[str, Any],
    *,
    source_ref: str,
    root: Path = ROOT,
) -> dict[str, Any]:
    project = _project_receipt(payload)
    stage_parity = project.get("stage_parity", {})
    quality_gate = project.get("quality_gate", {})
    cognitive = project.get("cognitive_intake", {})
    delivery = project.get("delivery_model", {})
    stage_statuses = {
        name: {
            "v1_status": stage.get("v1_status"),
            "feature_parity_status": stage.get("feature_parity_status"),
            "mapped_finharness_object": stage.get("mapped_finharness_object"),
        }
        for name, stage in stage_parity.items()
    }

    return {
        "workflow": WORKFLOW_VERSION,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": {
            "source_ref": source_ref,
            "source_workflow": payload.get("workflow") or project.get("workflow"),
            "adapter_mode": "receipt_bridge",
            "execution_allowed": False,
        },
        "project": {
            "project_name": "finharness",
            "project_root": str(root),
        },
        "compatibility_contract": build_finharness_project_governance_contract(
            root=root,
            workstation_receipt_path=Path(source_ref),
        ),
        "stage_statuses": stage_statuses,
        "quality_summary": {
            "decision": quality_gate.get("decision"),
            "quality_claimed": quality_gate.get("quality_claimed", False),
            "checks_executed": quality_gate.get("checks_executed", False),
            "security_hardening_gate": quality_gate.get("security_hardening_gate", {}),
            "redteam_boundary_gate": quality_gate.get("redteam_boundary_gate", {}),
            "release_gate": quality_gate.get("release_gate", {}),
        },
        "cognitive_summary": {
            "artifact_contract": cognitive.get("artifact_contract", {}),
            "artifact_count": cognitive.get("artifact_plan", {}).get("artifact_count", 0),
        },
        "delivery_summary": {
            "decision": delivery.get("decision"),
            "review_required": delivery.get("review_hook", {}).get("required"),
            "local_checks_status": delivery.get("local_checks_gate", {}).get("status"),
        },
        "claims": [
            "FinHarness compatibility surfaces are explicitly mapped to "
            "workstation governance stages.",
            "Existing FinHarness graph APIs, Taskfile entrypoints, and output "
            "paths remain the compatibility contract.",
            "The adapter read workstation governance evidence instead of "
            "importing workstation code.",
        ],
        "not_claimed": [
            "No FinHarness source migration is performed.",
            "No release, trading, deployment, or live execution authority is granted.",
            "No quality pass is claimed unless the source workstation receipt "
            "records executed checks.",
        ],
        "remaining_debt": [
            "Future wrapper delegation still needs a separate migration plan "
            "and FinHarness compatibility tests.",
            "Human review is required before changing existing FinHarness graph "
            "entrypoints or receipt paths.",
        ],
        "status": "adapted",
        "draft": True,
    }


def run_finharness_project_governance_adapter(
    *,
    root: Path | str = ROOT,
    workstation_receipt_path: Path | str = DEFAULT_WORKSTATION_RECEIPT,
    write_receipt: bool = True,
) -> dict[str, Any]:
    resolved_root = Path(root)
    resolved_receipt = Path(workstation_receipt_path)
    if resolved_receipt.exists():
        final = adapt_workstation_project_governance_receipt(
            _read_json(resolved_receipt),
            source_ref=str(resolved_receipt),
            root=resolved_root,
        )
    else:
        final = {
            **build_finharness_project_governance_contract(
                root=resolved_root,
                workstation_receipt_path=resolved_receipt,
            ),
            "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "claims": [
                "FinHarness compatibility surfaces are known, but no "
                "workstation receipt was available to adapt.",
            ],
            "not_claimed": [
                "No workstation governance evidence was adapted.",
                "No quality, release, migration, or execution authority is claimed.",
            ],
            "remaining_debt": [
                "Run workstation-lab Project Governance Loop and provide the "
                "FinHarness receipt before adapting.",
            ],
            "status": "missing_workstation_receipt",
            "draft": True,
        }

    if write_receipt:
        path = (
            resolved_root
            / "data"
            / "receipts"
            / "project-governance-adapter"
            / "latest.json"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        final["receipt_ref"] = str(path)
        path.write_text(
            json.dumps(final, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    return final
