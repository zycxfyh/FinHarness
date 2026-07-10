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
    removal_ledger = _read(root, "docs/governance/removal-ledger.yml")
    return all(
        (
            'tags=["paper-validation", "legacy"]' in routes,
            "deprecated=True" in routes,
            "WriteCapabilityDependency" in routes,
            "## Paper Validation Legacy Isolation Boundary" in threat_model,
            boundary_test.exists(),
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
    layers = ("check:fast", "check:ci", "check:research")
    return all(re.search(rf"^  {re.escape(layer)}:$", taskfile, re.MULTILINE) for layer in layers)


def _dependency_grouping(root: Path) -> bool:
    project = tomllib.loads(_read(root, "pyproject.toml"))
    groups = set(project.get("dependency-groups", {}))
    required_groups = {"data", "research", "agent", "eval", "paper", "security"}
    return required_groups.issubset(groups)


def _statecore_model_split(root: Path) -> bool:
    extracted = root / "src" / "finharness" / "statecore" / "personal_finance_models.py"
    models = _read(root, "src/finharness/statecore/models.py")
    return extracted.exists() and "personal_finance_models" in models


def _frontend_module_split(root: Path) -> bool:
    frontend = root / "frontend"
    required_files = (frontend / "api.js", frontend / "state.js")
    js_text = "\n".join(path.read_text(encoding="utf-8") for path in frontend.glob("*.js"))
    return all(path.exists() for path in required_files) and "ReviewActionShell" in js_text


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
        "SimulatedBrokerAdapter",
        "Execution Legacy Bridge",
    )
    return all(f"- name: {name}" in inventory for name in required_names)


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
