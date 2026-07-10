#!/usr/bin/env python3
"""Verify canonical engineering-debt statuses against repository facts.

The register names bounded checks; it never embeds shell commands. A check
returns ``True`` only when the debt's desired state is present. Therefore a
resolved entry must return true and every non-resolved entry must return false.
"""

from __future__ import annotations

import json
import re
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "governance" / "debt-register.json"

Verifier = Callable[[Path], bool]


def _read(root: Path, relative_path: str) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def _api_write_capability_gate(root: Path) -> bool:
    operator = _read(root, "src/finharness/local_operator.py")
    dependencies = _read(root, "src/finharness/api/dependencies.py")
    gate_tests = _read(root, "tests/test_statecore_api.py")
    route_files = (
        "src/finharness/api/routes_action_intents.py",
        "src/finharness/api/routes_agent_authority_grants.py",
        "src/finharness/api/routes_capital_mandates.py",
        "src/finharness/api/routes_execution.py",
        "src/finharness/api/routes_ips.py",
        "src/finharness/api/routes_paper_validation.py",
        "src/finharness/api/routes_proposals.py",
    )
    return all(
        (
            "class LocalOperatorContext" in operator,
            "async def require_write_capability" in operator,
            "WriteCapabilityDependency" in dependencies,
            "test_all_state_changing_routes_have_write_capability_dependency" in gate_tests,
            all("WriteCapabilityDependency" in _read(root, path) for path in route_files),
        )
    )


def _paper_validation_legacy_boundary(root: Path) -> bool:
    routes = _read(root, "src/finharness/api/routes_paper_validation.py")
    threat_model = _read(root, "docs/security/finharness-threat-model.md")
    boundary_test = root / "tests" / "test_paper_validation_legacy_boundary.py"
    consumer_audit = root / "docs" / "governance" / "paper-validation-consumers.json"
    removal_ledger = _read(root, "docs/governance/removal-ledger.yml")
    boundary_text = boundary_test.read_text(encoding="utf-8") if boundary_test.exists() else ""
    return all(
        (
            'tags=["paper-validation", "legacy"]' in routes,
            "deprecated=True" in routes,
            "WriteCapabilityDependency" in routes,
            "## Paper Validation Legacy Isolation Boundary" in threat_model,
            boundary_test.exists(),
            consumer_audit.exists(),
            "test_paper_modules_have_no_execution_or_network_imports" in boundary_text,
            "test_runtime_consumers_match_manifest" in boundary_text,
            "delete-paper-validation-legacy" in removal_ledger,
        )
    )


def _receipt_backed_write_registry(root: Path) -> bool:
    registry = json.loads(_read(root, "docs/governance/receipt-backed-write-registry.json"))
    entries = registry.get("entries", [])
    required = {
        "function",
        "route_refs",
        "receipt_kind",
        "stale_guard",
        "failure_cleanup",
        "execution_substrate",
        "real_external_execution_allowed",
    }
    return all(
        (
            registry.get("status") == "current",
            registry.get("debt_ref") == "ENG-DEBT-0003",
            len(entries) >= 20,
            all(required.issubset(entry) for entry in entries),
        )
    )


def _task_check_layering(root: Path) -> bool:
    taskfile = _read(root, "Taskfile.yml")

    def dependencies(task_name: str) -> list[str]:
        match = re.search(
            rf"^  {re.escape(task_name)}:\n(?P<body>.*?)(?=^  \S[^\n]*:\n|\Z)",
            taskfile,
            re.MULTILINE | re.DOTALL,
        )
        if match is None:
            return []
        return re.findall(r"^\s+- task:\s+([^\s]+)\s*$", match.group("body"), re.MULTILINE)

    return all(
        (
            dependencies("check") == ["check:ci"],
            dependencies("check:fast") == ["lint", "typecheck", "test"],
            dependencies("check:ci")
            == [
                "check:fast",
                "test:integration",
                "test:frontend",
                "governance:check",
                "rules:audit",
            ],
            dependencies("check:research") == ["check:ci", "experiments", "eval:smoke"],
        )
    )


def _dependency_grouping(root: Path) -> bool:
    project = tomllib.loads(_read(root, "pyproject.toml"))
    groups = project.get("dependency-groups", {})
    required_groups = {"data", "research", "agent", "eval", "paper", "security"}
    audit_path = root / "docs" / "governance" / "dependency-consumers.json"
    if not required_groups.issubset(groups) or not audit_path.exists():
        return False
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    return all(
        (
            audit.get("status") == "current",
            audit.get("debt_ref") == "ENG-DEBT-0005",
            all(groups[name] for name in required_groups),
            set(audit.get("groups", {})) == required_groups,
        )
    )


def _statecore_model_split(root: Path) -> bool:
    extracted = root / "src" / "finharness" / "statecore" / "personal_finance_models.py"
    base = root / "src" / "finharness" / "statecore" / "model_base.py"
    semantic_test = root / "tests" / "test_statecore_model_split.py"
    models = _read(root, "src/finharness/statecore/models.py")
    extracted_text = extracted.read_text(encoding="utf-8") if extracted.exists() else ""
    return all(
        (
            extracted.exists(),
            base.exists(),
            semantic_test.exists(),
            "from finharness.statecore.personal_finance_models import" in models,
            "from finharness.statecore.model_base import" in extracted_text,
            "from finharness.statecore.models import" not in extracted_text,
        )
    )


def _frontend_module_split(root: Path) -> bool:
    frontend = root / "frontend"
    required_files = (frontend / "api.js", frontend / "state.js", frontend / "actions.js")
    if not all(path.exists() for path in required_files):
        return False
    app = _read(root, "frontend/app.js")
    state = _read(root, "frontend/state.js")
    actions = _read(root, "frontend/actions.js")
    index = _read(root, "frontend/index.html")
    semantic_test = root / "frontend" / "tests" / "module_boundaries.test.cjs"
    script_positions = [
        index.find(path) for path in ("./api.js", "./state.js", "./actions.js", "./app.js")
    ]
    return all(
        (
            "window.FinHarness.state = Object.seal" in state,
            "placeholder" not in state,
            "const state = window.FinHarness.state" in app,
            "window.FinHarness.ReviewActionShell" in actions,
            "await apiPost(" not in app,
            "await apiPatch(" not in app,
            len(re.findall(r"ReviewActionShell\.(?:post|patch)\(", app)) == 3,
            all(position >= 0 for position in script_positions),
            script_positions == sorted(script_positions),
            semantic_test.exists(),
        )
    )


def _toolchain_alignment(root: Path) -> bool:
    mise = tomllib.loads(_read(root, "mise.toml"))
    local_node = str(mise["tools"]["node"])
    workflows = (
        _read(root, ".github/workflows/browser.yml"),
        _read(root, ".github/workflows/security.yml"),
    )
    ci_nodes = [
        version
        for workflow in workflows
        for version in re.findall(r'node-version:\s*["\']?([^"\'\s]+)', workflow)
    ]
    same_major = bool(ci_nodes) and all(
        version.split(".", maxsplit=1)[0] == local_node.split(".", maxsplit=1)[0]
        for version in ci_nodes
    )
    security_workflow = workflows[1]
    rust_justified = (
        "rust-toolchain" not in security_workflow
        or "rust-toolchain-required-by:" in security_workflow
    )
    return same_major and rust_justified


def _execution_abstraction_inventory(root: Path) -> bool:
    inventory = _read(root, "docs/engineering/abstraction-inventory.yml")
    required_names = (
        "BrokerConnection",
        "ExecutionAccount",
        "OrderDraft",
        "PreTradeCheck",
        "ApprovalRecord",
        "ExecutionOrder",
        "ExecutionReport",
        "PositionDelta",
        "ReconciliationReport",
        "Execution Services",
        "Execution Capabilities",
        "BrokerAdapter Registry",
        "SimulatedBrokerAdapter",
        "Execution Legacy Bridge",
        "execution_routes",
    )
    stale_targets = (
        "/execution/pretrade-packets/",
        "execution/paper/",
        "wrapper_first",
        "bridge_read_model_first",
    )
    return all(f"- name: {name}" in inventory for name in required_names) and not any(
        target in inventory for target in stale_targets
    )


def _execution_capability_enforcement(root: Path) -> bool:
    services = _read(root, "src/finharness/execution/services.py")
    commands = _read(root, "src/finharness/execution/commands.py")
    routes = _read(root, "src/finharness/api/routes_execution.py")
    tests = root / "tests" / "test_execution_capability_enforcement.py"
    enforced_flags = (
        "create_order_draft",
        "run_pretrade_check",
        "record_approval",
        "stage_execution_order",
        "submit_simulated_order",
    )
    return all(
        (
            "ExecutionCapabilities" in services,
            "DEFAULT_EXECUTION_CAPABILITIES" in services,
            all(
                f'require_execution_capability(capabilities, "{flag}")' in services
                for flag in enforced_flags
            ),
            'require_execution_capability(capabilities, "submit_simulated_order")' in commands,
            "ExecutionCapabilitiesDependency" in routes,
            tests.exists(),
        )
    )


VERIFIERS: dict[str, Verifier] = {
    "api_write_capability_gate": _api_write_capability_gate,
    "dependency_grouping": _dependency_grouping,
    "execution_abstraction_inventory": _execution_abstraction_inventory,
    "execution_capability_enforcement": _execution_capability_enforcement,
    "frontend_module_split": _frontend_module_split,
    "paper_validation_legacy_boundary": _paper_validation_legacy_boundary,
    "receipt_backed_write_registry": _receipt_backed_write_registry,
    "statecore_model_split": _statecore_model_split,
    "task_check_layering": _task_check_layering,
    "toolchain_alignment": _toolchain_alignment,
}


def verify_register(root: Path = ROOT, register_path: Path = REGISTER) -> list[str]:
    """Return status/verification disagreements; an empty list means truthful."""

    register = json.loads(register_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for debt in register["debts"]:
        verifier_name = debt["verification"]
        verifier = VERIFIERS.get(verifier_name)
        if verifier is None:
            failures.append(f"{debt['id']}: unknown verifier {verifier_name!r}")
            continue
        desired_state_met = verifier(root)
        claims_resolved = debt["status"] == "resolved"
        if desired_state_met != claims_resolved:
            failures.append(
                f"{debt['id']}: status={debt['status']} but "
                f"{verifier_name} desired_state_met={str(desired_state_met).lower()}"
            )
    return failures


def main() -> int:
    failures = verify_register()
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    register = json.loads(REGISTER.read_text(encoding="utf-8"))
    for debt in register["debts"]:
        print(f"PASS {debt['id']} status={debt['status']} verifier={debt['verification']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
