"""LangGraph workflow for FinHarness engineering delivery governance."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_VERSION = "langgraph_engineering_delivery_v1"


class EngineeringDeliveryGraphState(TypedDict, total=False):
    goal: str
    source_ref: str
    proposal_ref: str
    module_refs: list[str]
    change_type: str
    scope: str
    non_goals: list[str]
    success_criteria: list[str]
    planned_files: list[str]
    changed_files: list[str]
    docs_updated: list[str]
    checks: list[dict[str, str]]
    lessons: list[str]
    root: str
    stamp: str
    date: str
    slug: str
    source: dict[str, Any]
    intake: dict[str, Any]
    goal_definition: dict[str, Any]
    scope_boundary: dict[str, Any]
    classification: dict[str, Any]
    design_gate: dict[str, Any]
    implementation_plan: dict[str, Any]
    work_breakdown: dict[str, Any]
    execution_summary: dict[str, Any]
    local_checks: dict[str, Any]
    quality_gate: dict[str, Any]
    docs_update: dict[str, Any]
    snapshot: dict[str, Any]
    receipt: dict[str, Any]
    review_hook: dict[str, Any]
    lesson_capture: dict[str, Any]
    final: dict[str, Any]


def _root(state: EngineeringDeliveryGraphState) -> Path:
    return Path(state.get("root") or ROOT)


def _stamp(state: EngineeringDeliveryGraphState) -> str:
    return state.get("stamp") or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _date_from_stamp(stamp: str) -> str:
    return f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}"


def _slug(text: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return normalized[:72] or "engineering-delivery"


def _write(path: Path, text: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")
    return str(path)


def _json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item).strip()]
    if str(value).strip():
        return [str(value)]
    return []


def _goal(state: EngineeringDeliveryGraphState) -> str:
    return state.get("goal") or "Untitled Engineering Delivery"


def _has_text(value: str | None) -> bool:
    return bool(value and value.strip())


def _requires_proposal(change_type: str) -> bool:
    return change_type in {
        "new_layer",
        "new_workflow",
        "architecture",
        "cross_module",
        "risk_boundary",
    }


def source_config_node(
    state: EngineeringDeliveryGraphState,
) -> EngineeringDeliveryGraphState:
    stamp = _stamp(state)
    date = state.get("date") or _date_from_stamp(stamp)
    slug = state.get("slug") or _slug(_goal(state))
    return {
        "stamp": stamp,
        "date": date,
        "slug": slug,
        "source": {
            "workflow": WORKFLOW_VERSION,
            "graph": "engineering_delivery_graph",
            "execution_allowed": False,
            "authority_boundary": (
                "This graph audits engineering delivery evidence; it does not authorize "
                "financial execution."
            ),
        },
    }


def intake_node(state: EngineeringDeliveryGraphState) -> EngineeringDeliveryGraphState:
    return {
        "intake": {
            "goal": _goal(state),
            "source_ref": state.get("source_ref") or "manual",
            "proposal_ref": state.get("proposal_ref"),
            "module_refs": _as_list(state.get("module_refs")),
        }
    }


def goal_definition_node(
    state: EngineeringDeliveryGraphState,
) -> EngineeringDeliveryGraphState:
    criteria = _as_list(state.get("success_criteria"))
    if not criteria:
        criteria = [
            "workflow implemented",
            "delivery receipt produced",
            "focused tests passed",
        ]
    return {
        "goal_definition": {
            "goal": _goal(state),
            "success_criteria": criteria,
            "complete_only_with_evidence": True,
        },
        "success_criteria": criteria,
    }


def scope_boundary_node(
    state: EngineeringDeliveryGraphState,
) -> EngineeringDeliveryGraphState:
    non_goals = _as_list(state.get("non_goals"))
    if not non_goals:
        non_goals = [
            "authorize financial execution",
            "replace Cognitive Graph",
            "replace Daily Evidence Graph",
        ]
    return {
        "scope_boundary": {
            "scope": state.get("scope") or _goal(state),
            "non_goals": non_goals,
        },
        "non_goals": non_goals,
    }


def change_classification_node(
    state: EngineeringDeliveryGraphState,
) -> EngineeringDeliveryGraphState:
    change_type = state.get("change_type") or "workflow"
    required_proposal = _requires_proposal(change_type)
    return {
        "classification": {
            "change_type": change_type,
            "required_proposal": required_proposal,
            "reason": (
                "Substantial workflow and architecture changes require a proposal before "
                "implementation."
            )
            if required_proposal
            else "Lightweight delivery flow can proceed with scoped evidence.",
        },
        "change_type": change_type,
    }


def design_gate_node(
    state: EngineeringDeliveryGraphState,
) -> EngineeringDeliveryGraphState:
    missing = []
    if not _has_text(state.get("goal")):
        missing.append("goal")
    if not _has_text(state.get("scope")):
        missing.append("scope")
    if not state.get("non_goals"):
        missing.append("non_goals")
    if state["classification"]["required_proposal"] and not _has_text(state.get("proposal_ref")):
        missing.append("proposal_ref")
    ok = not missing
    return {
        "design_gate": {
            "ok": ok,
            "missing": missing,
            "required_proposal": state["classification"]["required_proposal"],
        }
    }


def _route_design_gate(state: EngineeringDeliveryGraphState) -> str:
    return "continue" if state["design_gate"]["ok"] else "failed"


def implementation_plan_node(
    state: EngineeringDeliveryGraphState,
) -> EngineeringDeliveryGraphState:
    planned_files = _as_list(state.get("planned_files"))
    if not planned_files:
        planned_files = _as_list(state.get("changed_files"))
    return {
        "implementation_plan": {
            "planned_files": planned_files,
            "method": "thin workflow orchestration plus docs, receipt, and tests",
        },
        "planned_files": planned_files,
    }


def work_breakdown_node(
    state: EngineeringDeliveryGraphState,
) -> EngineeringDeliveryGraphState:
    steps = [
        "define delivery state",
        "run design gate",
        "record changed artifacts",
        "record local checks",
        "write receipt",
        "write review hook",
    ]
    return {"work_breakdown": {"steps": steps, "step_count": len(steps)}}


def execute_changes_node(
    state: EngineeringDeliveryGraphState,
) -> EngineeringDeliveryGraphState:
    changed_files = _as_list(state.get("changed_files"))
    planned_files = _as_list(state.get("planned_files"))
    unplanned_files = [
        path for path in changed_files if planned_files and path not in planned_files
    ]
    return {
        "execution_summary": {
            "changed_files": changed_files,
            "changed_file_count": len(changed_files),
            "unplanned_files": unplanned_files,
            "mutation_performed_by_graph": False,
        },
        "changed_files": changed_files,
    }


def local_checks_node(
    state: EngineeringDeliveryGraphState,
) -> EngineeringDeliveryGraphState:
    checks = state.get("checks") or []
    normalized = []
    for check in checks:
        status = str(check.get("status", "")).lower()
        normalized.append(
            {
                "name": str(check.get("name") or "unnamed-check"),
                "status": status,
                "detail": str(check.get("detail") or ""),
            }
        )
    passed = [check for check in normalized if check["status"] == "passed"]
    failed = [check for check in normalized if check["status"] not in {"passed"}]
    return {
        "local_checks": {
            "checks": normalized,
            "passed_count": len(passed),
            "failed_count": len(failed),
            "all_passed": bool(normalized) and not failed,
        }
    }


def quality_gate_node(
    state: EngineeringDeliveryGraphState,
) -> EngineeringDeliveryGraphState:
    missing = []
    if not state["design_gate"]["ok"]:
        missing.extend(state["design_gate"]["missing"])
    if not state.get("changed_files"):
        missing.append("changed_files")
    if not state.get("docs_updated"):
        missing.append("docs_updated")
    local_checks = state.get("local_checks") or {
        "checks": [],
        "passed_count": 0,
        "failed_count": 0,
        "all_passed": False,
    }
    if not local_checks["all_passed"]:
        missing.append("passing_checks")
    ok = not missing
    return {
        "quality_gate": {
            "ok": ok,
            "status": "pass" if ok else "failed",
            "missing_or_failed": sorted(set(missing)),
        }
    }


def _route_quality_gate(state: EngineeringDeliveryGraphState) -> str:
    return "continue" if state["quality_gate"]["ok"] else "failed"


def docs_update_node(
    state: EngineeringDeliveryGraphState,
) -> EngineeringDeliveryGraphState:
    return {
        "docs_update": {
            "docs_updated": _as_list(state.get("docs_updated")),
            "module_refs": _as_list(state.get("module_refs")),
        }
    }


def _receipt_payload(
    state: EngineeringDeliveryGraphState,
    *,
    status: str,
) -> dict[str, Any]:
    snapshot = {
        "snapshot_id": f"engineering_delivery_{state['stamp']}_{state['slug']}",
        "workflow": WORKFLOW_VERSION,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "goal": _goal(state),
        "source_ref": state.get("source_ref") or "manual",
        "proposal_ref": state.get("proposal_ref"),
        "module_refs": _as_list(state.get("module_refs")),
        "change_type": state.get("change_type"),
        "scope": state.get("scope"),
        "non_goals": _as_list(state.get("non_goals")),
        "success_criteria": _as_list(state.get("success_criteria")),
        "planned_files": _as_list(state.get("planned_files")),
        "changed_files": _as_list(state.get("changed_files")),
        "docs_updated": _as_list(state.get("docs_updated")),
        "checks": state.get("local_checks", {}).get("checks", []),
        "design_gate": state.get("design_gate", {}),
        "quality_gate": state.get("quality_gate", {}),
        "execution_allowed": False,
    }
    snapshot["output_hash"] = _json_hash(snapshot)
    return {
        "receipt_id": snapshot["snapshot_id"],
        "workflow": WORKFLOW_VERSION,
        "status": status,
        "timestamp_utc": snapshot["timestamp_utc"],
        "snapshot": snapshot,
        "lineage": {
            "source_ref": snapshot["source_ref"],
            "proposal_ref": snapshot["proposal_ref"],
            "module_refs": snapshot["module_refs"],
            "transform_version": WORKFLOW_VERSION,
        },
        "remaining_debt": []
        if status == "pass"
        else state.get("quality_gate", {}).get("missing_or_failed", []),
    }


def receipt_node(state: EngineeringDeliveryGraphState) -> EngineeringDeliveryGraphState:
    receipt = _receipt_payload(state, status="pass")
    path = (
        _root(state)
        / "data"
        / "receipts"
        / "engineering-delivery"
        / f"{state['stamp']}-{state['slug']}.json"
    )
    receipt["snapshot"]["payload_ref"] = _write(
        path, json.dumps(receipt, ensure_ascii=False, indent=2)
    )
    return {
        "snapshot": receipt["snapshot"],
        "receipt": receipt,
    }


def failed_receipt_node(
    state: EngineeringDeliveryGraphState,
) -> EngineeringDeliveryGraphState:
    receipt = _receipt_payload(state, status="failed")
    path = (
        _root(state)
        / "data"
        / "receipts"
        / "engineering-delivery"
        / f"{state['stamp']}-{state['slug']}-failed.json"
    )
    receipt["snapshot"]["payload_ref"] = _write(
        path, json.dumps(receipt, ensure_ascii=False, indent=2)
    )
    return {
        "snapshot": receipt["snapshot"],
        "receipt": receipt,
    }


def review_hook_node(
    state: EngineeringDeliveryGraphState,
) -> EngineeringDeliveryGraphState:
    status = state["receipt"]["status"]
    path = (
        _root(state)
        / "docs"
        / "reviews"
        / f"{state['date']}-{state['slug']}-engineering-delivery.md"
    )
    missing = state.get("quality_gate", {}).get("missing_or_failed", [])
    checks = state.get("local_checks", {}).get("checks", [])
    changed_lines = (
        "\n".join(f"- {path}" for path in _as_list(state.get("changed_files")))
        or "- no changed files recorded"
    )
    docs_lines = (
        "\n".join(f"- {path}" for path in _as_list(state.get("docs_updated")))
        or "- no docs recorded"
    )
    check_lines = "\n".join(
        f"- {check['name']}: {check['status']} {check['detail']}".rstrip()
        for check in checks
    )
    if not check_lines:
        check_lines = "- no checks recorded"
    missing_lines = "\n".join(f"- {item}" for item in missing) or "- no scoped debt"
    content = f"""# Review: {_goal(state)}

Date: {state['date']}
Status: {'closed-draft' if status == 'pass' else 'open'}
Workflow: {WORKFLOW_VERSION}
Receipt: {state['receipt']['snapshot']['payload_ref']}

## Scope

{state.get('scope') or _goal(state)}

## Evidence

Changed files:

{changed_lines}

Docs updated:

{docs_lines}

Checks:

{check_lines}

## Gate Result

```text
status: {status}
quality_ok: {state.get('quality_gate', {}).get('ok')}
```

## Remaining Debt

{missing_lines}

## Follow-Up

Update module docs, tests, or delivery rules if this review exposes a repeated
process failure.
"""
    return {
        "review_hook": {
            "path": _write(path, content),
            "status": "closed-draft" if status == "pass" else "open",
        }
    }


def lesson_capture_node(
    state: EngineeringDeliveryGraphState,
) -> EngineeringDeliveryGraphState:
    lessons = _as_list(state.get("lessons"))
    return {
        "lesson_capture": {
            "captured": bool(lessons),
            "lessons": lessons,
            "destination": "docs/lessons or module upgrade log when repeated",
        }
    }


def final_node(state: EngineeringDeliveryGraphState) -> EngineeringDeliveryGraphState:
    return {
        "final": {
            "workflow": WORKFLOW_VERSION,
            "goal": _goal(state),
            "status": state["receipt"]["status"],
            "quality_ok": bool(state.get("quality_gate", {}).get("ok")),
            "receipt_ref": state["receipt"]["snapshot"]["payload_ref"],
            "review_ref": state["review_hook"]["path"],
            "changed_file_count": len(_as_list(state.get("changed_files"))),
            "check_count": len(state.get("local_checks", {}).get("checks", [])),
            "execution_allowed": False,
            "remaining_debt": state["receipt"]["remaining_debt"],
        }
    }


def build_engineering_delivery_graph():
    graph = StateGraph(EngineeringDeliveryGraphState)
    graph.add_node("source_config", source_config_node)
    graph.add_node("intake", intake_node)
    graph.add_node("goal_definition", goal_definition_node)
    graph.add_node("scope_boundary", scope_boundary_node)
    graph.add_node("change_classification", change_classification_node)
    graph.add_node("design_gate", design_gate_node)
    graph.add_node("implementation_plan", implementation_plan_node)
    graph.add_node("work_breakdown", work_breakdown_node)
    graph.add_node("execute_changes", execute_changes_node)
    graph.add_node("local_checks", local_checks_node)
    graph.add_node("quality_gate", quality_gate_node)
    graph.add_node("docs_update", docs_update_node)
    graph.add_node("receipt", receipt_node)
    graph.add_node("failed_receipt", failed_receipt_node)
    graph.add_node("review_hook", review_hook_node)
    graph.add_node("lesson_capture", lesson_capture_node)
    graph.add_node("final", final_node)

    graph.add_edge(START, "source_config")
    graph.add_edge("source_config", "intake")
    graph.add_edge("intake", "goal_definition")
    graph.add_edge("goal_definition", "scope_boundary")
    graph.add_edge("scope_boundary", "change_classification")
    graph.add_edge("change_classification", "design_gate")
    graph.add_conditional_edges(
        "design_gate",
        _route_design_gate,
        {"continue": "implementation_plan", "failed": "quality_gate"},
    )
    graph.add_edge("implementation_plan", "work_breakdown")
    graph.add_edge("work_breakdown", "execute_changes")
    graph.add_edge("execute_changes", "local_checks")
    graph.add_edge("local_checks", "quality_gate")
    graph.add_conditional_edges(
        "quality_gate",
        _route_quality_gate,
        {"continue": "docs_update", "failed": "failed_receipt"},
    )
    graph.add_edge("docs_update", "receipt")
    graph.add_edge("receipt", "review_hook")
    graph.add_edge("failed_receipt", "review_hook")
    graph.add_edge("review_hook", "lesson_capture")
    graph.add_edge("lesson_capture", "final")
    graph.add_edge("final", END)
    return graph.compile()


engineering_delivery_graph = build_engineering_delivery_graph()


def run_engineering_delivery_graph(
    *,
    goal: str,
    source_ref: str = "manual",
    proposal_ref: str | None = None,
    module_refs: list[str] | None = None,
    change_type: str = "workflow",
    scope: str | None = None,
    non_goals: list[str] | None = None,
    success_criteria: list[str] | None = None,
    planned_files: list[str] | None = None,
    changed_files: list[str] | None = None,
    docs_updated: list[str] | None = None,
    checks: list[dict[str, str]] | None = None,
    lessons: list[str] | None = None,
    root: Path | str = ROOT,
) -> dict[str, Any]:
    result = engineering_delivery_graph.invoke(
        {
            "goal": goal,
            "source_ref": source_ref,
            "proposal_ref": proposal_ref,
            "module_refs": module_refs or [],
            "change_type": change_type,
            "scope": scope or goal,
            "non_goals": non_goals or [],
            "success_criteria": success_criteria or [],
            "planned_files": planned_files or [],
            "changed_files": changed_files or [],
            "docs_updated": docs_updated or [],
            "checks": checks or [],
            "lessons": lessons or [],
            "root": str(root),
        }
    )
    return dict(result)
