#!/usr/bin/env python3
"""Verify canonical engineering-debt statuses against repository facts.

The register names bounded checks; it never embeds shell commands. A check
returns ``True`` only when the debt's desired state is present. Therefore a
resolved entry must return true and every non-resolved entry must return false.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "governance" / "debt-register.json"

Verifier = Callable[[Path], bool]

EVIDENCE_LEVELS = {
    "structural",
    "semantic",
    "runtime",
    "restart",
    "clean-environment",
    "product",
}


@dataclass(frozen=True)
class VerifierSpec:
    """Executable proof plus the bounded claim it is allowed to support."""

    evaluate: Verifier
    claim: str
    owner: str
    evidence_level: str
    production_path: tuple[str, ...]
    sunset: str


def state_changing_routes_have_write_gate(app: Any, gate: Callable[..., Any]) -> bool:
    """Inspect the real FastAPI dependency graph, not source/test name tokens."""

    from fastapi.routing import APIRoute

    validation_only = {("POST", "/agent-authority-grants/{grant_id}/validate")}

    def dependency_calls(dependant: Any) -> set[Callable[..., Any]]:
        calls: set[Callable[..., Any]] = set()
        for dependency in dependant.dependencies:
            if dependency.call is not None:
                calls.add(dependency.call)
            calls.update(dependency_calls(dependency))
        return calls

    def concrete_routes(routes: list[Any]) -> list[Any]:
        concrete: list[Any] = []
        for route in routes:
            nested_router = getattr(route, "original_router", None)
            if nested_router is not None:
                concrete.extend(concrete_routes(nested_router.routes))
            else:
                concrete.append(route)
        return concrete

    checked = 0
    for route in concrete_routes(app.routes):
        if not isinstance(route, APIRoute):
            continue
        for method in route.methods & {"POST", "PUT", "PATCH", "DELETE"}:
            if (method, route.path) in validation_only:
                continue
            checked += 1
            if gate not in dependency_calls(route.dependant):
                return False
    return checked > 0


def _run_proof_command(root: Path, command: list[str]) -> bool:
    env = os.environ.copy()
    python_path = str(root / "src")
    env["PYTHONPATH"] = os.pathsep.join(
        part for part in (python_path, env.get("PYTHONPATH", "")) if part
    )
    try:
        completed = subprocess.run(
            command,
            cwd=root,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _run_unittest_modules(root: Path, *modules: str) -> bool:
    return _run_proof_command(root, [sys.executable, "-m", "unittest", *modules])


def _read(root: Path, relative_path: str) -> str:
    return (root / relative_path).read_text(encoding="utf-8")


def _api_write_capability_gate(root: Path) -> bool:
    source_root = str(root / "src")
    sys.path.insert(0, source_root)
    try:
        from finharness.api.app import create_app
        from finharness.local_operator import require_write_capability

        return state_changing_routes_have_write_gate(create_app(), require_write_capability)
    except (ImportError, RuntimeError):
        return False
    finally:
        if sys.path and sys.path[0] == source_root:
            sys.path.pop(0)


def _paper_validation_legacy_boundary(root: Path) -> bool:
    """Verify the paper-validation boundary through real semantic checks.

    Replaces the old string-based check with actual audit module imports.
    """
    sys.path.insert(0, str(root / "src"))
    try:
        from finharness.paper_validation_boundary_audit import (
            build_internal_import_graph,
            find_forbidden_transitive_imports,
            scan_paper_consumers,
        )
    except ImportError:
        return False
    finally:
        if str(root / "src") == sys.path[0]:
            sys.path.pop(0)

    # Check 1: consumer manifest audit (SEC-02A)
    consumer_findings = scan_paper_consumers(root)
    manifest_ok = len(consumer_findings) == 0

    # Check 2: transitive import boundary (SEC-02B)
    graph = build_internal_import_graph(root)
    forbidden_findings = find_forbidden_transitive_imports(
        graph,
        roots={
            "finharness.api.routes_paper_validation",
            "finharness.statecore.paper_accounts",
            "finharness.statecore.paper_order_tickets",
            "finharness.statecore.paper_executions",
        },
        forbidden_prefixes={
            "finharness.execution.broker",
            "finharness.execution.adapters",
            "finharness.execution.commands",
            "finharness.providers",
            "finharness.agent_runtime",
            "httpx",
            "requests",
            "urllib",
            "socket",
            "urllib3",
            "yfinance",
            "ccxt",
            "alpaca",
        },
    )
    import_ok = len(forbidden_findings) == 0

    # Check 3: threat model gap closure
    threat_model = _read(root, "docs/security/finharness-threat-model.md")
    threat_ok = (
        "## Paper Validation Legacy Isolation Boundary" in threat_model
        and "SEC-BOUNDARY-02" in threat_model
    )

    # Check 4: destructive semantic and runtime fixtures execute successfully.
    behavior_ok = _run_unittest_modules(
        root,
        "tests.test_paper_validation_consumer_manifest",
        "tests.test_paper_validation_import_boundary",
        "tests.test_paper_validation_broker_registry_isolation",
    )

    # Check 5: removal ledger entry
    removal_ledger = _read(root, "docs/governance/removal-ledger.yml")
    removal_ok = "delete-paper-validation-legacy" in removal_ledger

    return all(
        (
            manifest_ok,
            import_ok,
            threat_ok,
            behavior_ok,
            removal_ok,
        )
    )


def _receipt_backed_write_registry(root: Path) -> bool:
    return _run_unittest_modules(root, "tests.test_receipt_backed_write_registry")


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
            dependencies("check:fast") == ["lint", "typecheck", "test:all"],
            dependencies("check:ci")
            == [
                "check:fast",
                "deps:probe-base",
                "test:integration",
                "test:frontend",
                "governance:check",
                "architecture:check",
                "rules:audit",
            ],
            dependencies("check:research") == ["check:ci", "experiments", "eval:smoke"],
        )
    )


def _dependency_grouping(root: Path) -> bool:
    """Verify dependency ownership: every dep has exactly one group with real consumers.

    Old rule (wrong): all 6 named groups must be non-empty.
    New rule: each declared dependency belongs to exactly one group, every kept
    dep has a consumer, unused deps are absent, empty groups are OK.
    """
    project = tomllib.loads(_read(root, "pyproject.toml"))
    groups = project.get("dependency-groups", {})
    DEP_NAMES = {"data", "research", "agent", "eval", "paper", "security"}
    audit_path = root / "docs" / "governance" / "dependency-consumers.json"

    if not DEP_NAMES.issubset(groups) or not audit_path.exists():
        return False

    audit = json.loads(audit_path.read_text(encoding="utf-8"))

    # Status must be "current" for debt closure
    if audit.get("status") != "current":
        return False
    if audit.get("debt_ref") != "ENG-DEBT-0005":
        return False

    entries = audit.get("entries", [])
    if not entries:
        return False

    # Rule 1: No duplicate distributions
    dist_names = [e["distribution"] for e in entries]
    if len(dist_names) != len(set(dist_names)):
        return False

    # Rule 2: Every declared dependency (all groups) has exactly one entry
    declared_base = project.get("project", {}).get("dependencies", [])
    declared_all = list(declared_base)
    for _group_name, group_deps in groups.items():
        declared_all.extend(group_deps)
    all_declared = {_distribution_name(r) for r in declared_all}
    manifest_dists = {e["distribution"] for e in entries}
    if all_declared != manifest_dists:
        return False

    declared_groups = _declared_dependency_groups(declared_base, groups)
    if declared_groups is None or not _dependency_entries_valid(entries, declared_groups):
        return False

    # Empty named groups are OK (paper, security are intentionally empty).
    return _dependency_probe_contract(root)


def _declared_dependency_groups(
    declared_base: list[str], groups: dict[str, list[str]]
) -> dict[str, str] | None:
    declared_groups = {
        _distribution_name(requirement): "base" for requirement in declared_base
    }
    for group_name, group_deps in groups.items():
        for requirement in group_deps:
            distribution = _distribution_name(requirement)
            if distribution in declared_groups:
                return None
            declared_groups[distribution] = group_name
    return declared_groups


def _dependency_entries_valid(
    entries: list[dict[str, object]], declared_groups: dict[str, str]
) -> bool:
    for entry in entries:
        distribution = str(entry.get("distribution", ""))
        group = str(entry.get("recommended_group", ""))
        actual_group = declared_groups.get(distribution)
        if entry.get("declared_group") != actual_group or group != actual_group:
            return False
        import_consumers = entry.get("import_consumers")
        task_consumers = entry.get("task_consumers")
        if group == "unused" and (import_consumers or task_consumers):
            return False
        if group != "unused" and not import_consumers and not task_consumers:
            return False
    return True


def _dependency_probe_contract(root: Path) -> bool:
    taskfile = _read(root, "Taskfile.yml")
    workflow_path = root / ".github" / "workflows" / "dependency-profiles.yml"
    required_probe_tasks = {
        "deps:probe-base",
        "deps:probe-data",
        "deps:probe-research",
        "deps:probe-agent",
        "deps:probe-eval",
        "deps:probe-all",
    }
    if not all(f"  {task_name}:" in taskfile for task_name in required_probe_tasks):
        return False
    if not all(
        (root / path).is_file()
        for path in ("scripts/probe_base_runtime.py", "scripts/probe_dependency_group.py")
    ) or not workflow_path.is_file():
        return False
    workflow = workflow_path.read_text(encoding="utf-8")
    return all(profile in workflow for profile in ("base", "data", "research", "agent", "eval"))


def _distribution_name(requirement: str) -> str:
    """Extract normalized distribution name from a requirement string."""
    import re as _re

    match = _re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
    if match is None:
        raise ValueError(f"cannot parse requirement: {requirement}")
    return _re.sub(r"[-_.]+", "-", match.group(1)).lower()


def _statecore_model_split(root: Path) -> bool:
    extracted = root / "src" / "finharness" / "statecore" / "personal_finance_models.py"
    base = root / "src" / "finharness" / "statecore" / "model_base.py"
    models = _read(root, "src/finharness/statecore/models.py")
    extracted_text = extracted.read_text(encoding="utf-8") if extracted.exists() else ""
    return all(
        (
            extracted.exists(),
            base.exists(),
            "from finharness.statecore.personal_finance_models import" in models,
            "from finharness.statecore.model_base import" in extracted_text,
            "from finharness.statecore.models import" not in extracted_text,
            _run_unittest_modules(root, "tests.test_statecore_model_split"),
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
            _run_proof_command(root, ["node", "frontend/tests/module_boundaries.test.cjs"]),
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
    return _run_unittest_modules(root, "tests.test_abstraction_inventory_execution")


def _execution_capability_enforcement(root: Path) -> bool:
    return _run_unittest_modules(
        root,
        "tests.test_execution_capabilities",
        "tests.test_execution_capability_enforcement",
    )


VERIFIERS: dict[str, VerifierSpec] = {
    "api_write_capability_gate": VerifierSpec(
        evaluate=_api_write_capability_gate,
        claim="Every state-changing FastAPI route depends on the canonical write gate.",
        owner="API / Identity",
        evidence_level="semantic",
        production_path=("src/finharness/api/app.py", "src/finharness/local_operator.py"),
        sunset="Replace when write admission moves to a successor API-wide policy engine.",
    ),
    "dependency_grouping": VerifierSpec(
        evaluate=_dependency_grouping,
        claim="Declared dependencies have one evidenced owner and maintained profile probes.",
        owner="Dependency Governance",
        evidence_level="semantic",
        production_path=("pyproject.toml", "docs/governance/dependency-consumers.json"),
        sunset="Replace when dependency ownership is generated from a canonical build graph.",
    ),
    "execution_abstraction_inventory": VerifierSpec(
        evaluate=_execution_abstraction_inventory,
        claim="The execution inventory matches canonical runtime types and rejects stale targets.",
        owner="Execution Architecture",
        evidence_level="semantic",
        production_path=("docs/engineering/abstraction-inventory.yml",),
        sunset="Merge into generated System Catalog views after DOC-01.",
    ),
    "execution_capability_enforcement": VerifierSpec(
        evaluate=_execution_capability_enforcement,
        claim=(
            "Disabled execution capabilities fail closed before state, receipt, "
            "or adapter effects."
        ),
        owner="Execution Control",
        evidence_level="runtime",
        production_path=(
            "src/finharness/execution/services.py",
            "src/finharness/execution/commands.py",
        ),
        sunset="Replace only when a successor admission engine proves the same no-effect law.",
    ),
    "frontend_module_split": VerifierSpec(
        evaluate=_frontend_module_split,
        claim="Governed frontend writes use the shared action shell and fail closed on bad truth.",
        owner="Frontend Architecture",
        evidence_level="runtime",
        production_path=("frontend/actions.js", "frontend/state.js", "frontend/app.js"),
        sunset="Replace when the cockpit migrates to a successor typed UI runtime.",
    ),
    "paper_validation_legacy_boundary": VerifierSpec(
        evaluate=_paper_validation_legacy_boundary,
        claim="Legacy paper validation cannot reach live adapters or unregistered consumers.",
        owner="Execution Security",
        evidence_level="runtime",
        production_path=(
            "src/finharness/api/routes_paper_validation.py",
            "src/finharness/paper_validation_boundary_audit.py",
        ),
        sunset="Delete with the paper-validation legacy surface after its removal gate passes.",
    ),
    "receipt_backed_write_registry": VerifierSpec(
        evaluate=_receipt_backed_write_registry,
        claim=(
            "Every governed write is importable and matches route, receipt, and "
            "cleanup semantics."
        ),
        owner="State Core Integrity",
        evidence_level="semantic",
        production_path=("docs/governance/receipt-backed-write-registry.json",),
        sunset="Merge into Artifact Store command registration after STORE migration completes.",
    ),
    "statecore_model_split": VerifierSpec(
        evaluate=_statecore_model_split,
        claim="Extracted State Core models preserve identity, metadata, and compatibility imports.",
        owner="State Core Architecture",
        evidence_level="semantic",
        production_path=(
            "src/finharness/statecore/models.py",
            "src/finharness/statecore/personal_finance_models.py",
        ),
        sunset="Replace when all compatibility re-exports have a versioned removal plan.",
    ),
    "task_check_layering": VerifierSpec(
        evaluate=_task_check_layering,
        claim="Named check layers compose the documented lower-cost gates without drift.",
        owner="Developer Experience",
        evidence_level="structural",
        production_path=("Taskfile.yml",),
        sunset="Replace when CI and local tasks are generated from one build graph.",
    ),
    "toolchain_alignment": VerifierSpec(
        evaluate=_toolchain_alignment,
        claim="Local and CI Node majors agree and CI installs no unexplained Rust toolchain.",
        owner="Developer Experience",
        evidence_level="structural",
        production_path=("mise.toml", ".github/workflows/security.yml"),
        sunset="Replace when one hermetic toolchain manifest owns local and CI versions.",
    ),
}


def verify_register(
    root: Path = ROOT,
    register_path: Path = REGISTER,
    verifiers: dict[str, VerifierSpec] = VERIFIERS,
) -> list[str]:
    """Return status/verification disagreements; an empty list means truthful."""

    register = json.loads(register_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for debt in register["debts"]:
        verifier_name = debt["verification"]
        spec = verifiers.get(verifier_name)
        if spec is None:
            failures.append(f"{debt['id']}: unknown verifier {verifier_name!r}")
            continue
        if spec.evidence_level not in EVIDENCE_LEVELS:
            failures.append(
                f"{debt['id']}: invalid evidence level {spec.evidence_level!r}"
            )
            continue
        if not all(
            (
                spec.claim.strip(),
                spec.owner.strip(),
                spec.production_path,
                spec.sunset.strip(),
            )
        ):
            failures.append(f"{debt['id']}: incomplete verifier proof metadata")
            continue
        missing_paths = [path for path in spec.production_path if not (root / path).exists()]
        if missing_paths:
            failures.append(f"{debt['id']}: missing production paths {missing_paths}")
            continue
        desired_state_met = spec.evaluate(root)
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
        spec = VERIFIERS[debt["verification"]]
        print(
            f"PASS {debt['id']} status={debt['status']} "
            f"verifier={debt['verification']} evidence={spec.evidence_level}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
