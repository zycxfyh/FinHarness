"""Check or update source-derived fields in governance consumer inventories."""

from __future__ import annotations

import argparse
import ast
import copy
import json
import re
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from finharness.paper_validation_boundary_audit import scan_paper_consumers

ROOT = Path(__file__).resolve().parents[1]
DEPENDENCY_MANIFEST = Path("docs/governance/dependency-consumers.json")
ATTESTATION_INVENTORY = Path("docs/governance/attestation-consumers.json")
PYTHON_ROOTS = ("src", "scripts", "tests", "experiments")
CORRECTIVE_COMMAND = "task governance:inventory:update"

IMPORT_TO_DISTRIBUTION = {
    "agents": "openai-agents",
    "backtrader": "backtrader",
    "beancount": "beancount",
    "beanquery": "beanquery",
    "deepeval": "deepeval",
    "fastapi": "fastapi",
    "httpx": "httpx",
    "keyring": "keyring",
    "langgraph": "langgraph",
    "nautilus_trader": "nautilus-trader",
    "pandas": "pandas",
    "pandera": "pandera",
    "pydantic_settings": "pydantic-settings",
    "pytest": "pytest",
    "quantstats": "quantstats",
    "riskfolio": "riskfolio-lib",
    "scipy": "scipy",
    "sqlmodel": "sqlmodel",
    "structlog": "structlog",
    "uvicorn": "uvicorn",
    "uuid6": "uuid6",
    "vectorbt": "vectorbt",
    "yfinance": "yfinance",
}


class InventoryError(RuntimeError):
    """Raised when an inventory cannot be safely derived."""


@dataclass(frozen=True)
class InventoryChange:
    path: Path
    current: dict[str, Any]
    expected: dict[str, Any]
    findings: tuple[str, ...]


def distribution_name(requirement: str) -> str:
    match = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
    if match is None:
        raise InventoryError(f"cannot parse requirement: {requirement}")
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def declared_requirements(root: Path) -> dict[str, tuple[str, str]]:
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    result: dict[str, tuple[str, str]] = {}
    for requirement in project["project"]["dependencies"]:
        result[distribution_name(requirement)] = (requirement, "base")
    for group, requirements in project.get("dependency-groups", {}).items():
        for requirement in requirements:
            name = distribution_name(requirement)
            if name in result:
                raise InventoryError(f"duplicate declared dependency: {name}")
            result[name] = (requirement, group)
    return result


def observed_imports(root: Path, distributions: set[str]) -> dict[str, tuple[set[str], set[str]]]:
    observed = {name: (set(), set()) for name in distributions}
    for root_name in PYTHON_ROOTS:
        scan_root = root / root_name
        if not scan_root.exists():
            continue
        for path in sorted(scan_root.rglob("*.py")):
            if "archive" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                modules: list[str] = []
                if isinstance(node, ast.Import):
                    modules.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    modules.append(node.module)
                for module in modules:
                    top_level = module.split(".", maxsplit=1)[0]
                    if module.startswith("opentelemetry.sdk"):
                        distribution = "opentelemetry-sdk"
                    elif module.startswith("opentelemetry"):
                        distribution = "opentelemetry-api"
                    else:
                        distribution = IMPORT_TO_DISTRIBUTION.get(top_level)
                    if distribution not in observed:
                        continue
                    import_modules, consumer_paths = observed[distribution]
                    import_modules.add(top_level)
                    consumer_paths.add(path.relative_to(root).as_posix())
    return observed


def derive_dependency_manifest(root: Path, current: dict[str, Any]) -> dict[str, Any]:
    declared = declared_requirements(root)
    existing = {entry["distribution"]: entry for entry in current.get("entries", [])}
    missing = sorted(set(declared) - set(existing))
    removed = sorted(set(existing) - set(declared))
    if missing:
        raise InventoryError(
            "new dependencies need manual policy metadata before generation: "
            + ", ".join(missing)
        )
    if removed:
        raise InventoryError("remove obsolete dependency entries: " + ", ".join(removed))

    observed = observed_imports(root, set(declared))
    result = copy.deepcopy(current)
    for entry in result["entries"]:
        name = entry["distribution"]
        requirement, group = declared[name]
        modules, consumers = observed[name]
        entry["requirement"] = requirement
        entry["declared_group"] = group
        if set(entry["import_modules"]) != modules:
            entry["import_modules"] = sorted(modules)
        if set(entry["import_consumers"]) != consumers:
            entry["import_consumers"] = sorted(consumers)
    return result


def derive_attestation_inventory(current: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(current)
    consumers = result.get("consumers", [])
    roles = Counter(item.get("role") for item in consumers)
    dispositions = Counter(item.get("disposition") for item in consumers)
    result["summary"] = {
        "total_consumers": len(consumers),
        "by_role": dict(sorted(roles.items())),
        "by_disposition": dict(sorted(dispositions.items())),
        "high_or_critical_count": sum(
            item.get("risk") in {"high", "critical"} for item in consumers
        ),
    }
    return result


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dependency_findings(current: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    expected_entries = {entry["distribution"]: entry for entry in expected["entries"]}
    for entry in current["entries"]:
        name = entry["distribution"]
        for field in ("requirement", "declared_group", "import_modules", "import_consumers"):
            if entry[field] != expected_entries[name][field]:
                findings.append(f"dependency {name}.{field} is stale")
    return findings


def inspect_inventories(root: Path = ROOT) -> tuple[list[InventoryChange], list[str]]:
    dependency_path = root / DEPENDENCY_MANIFEST
    attestation_path = root / ATTESTATION_INVENTORY
    dependency = _load_json(dependency_path)
    attestation = _load_json(attestation_path)
    expected_dependency = derive_dependency_manifest(root, dependency)
    expected_attestation = derive_attestation_inventory(attestation)
    changes = [
        InventoryChange(
            dependency_path,
            dependency,
            expected_dependency,
            tuple(_dependency_findings(dependency, expected_dependency)),
        ),
        InventoryChange(
            attestation_path,
            attestation,
            expected_attestation,
            ("attestation summary is stale",) if attestation != expected_attestation else (),
        ),
    ]
    paper_findings = [
        f"paper consumer {finding.get('path')}: {finding.get('detail')}"
        for finding in scan_paper_consumers(root)
    ]
    return changes, paper_findings


def update_inventories(root: Path = ROOT) -> list[Path]:
    changes, paper_findings = inspect_inventories(root)
    if paper_findings:
        raise InventoryError("; ".join(paper_findings))
    updated: list[Path] = []
    for change in changes:
        if not change.findings:
            continue
        change.path.write_text(
            json.dumps(change.expected, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        updated.append(change.path)
    return updated


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true", help="Write derived fields")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.update:
            updated = update_inventories()
            rendered = ", ".join(str(path.relative_to(ROOT)) for path in updated)
            print("updated: " + (rendered or "none"))
            return 0
        changes, paper_findings = inspect_inventories()
    except (InventoryError, json.JSONDecodeError, KeyError, SyntaxError) as exc:
        print(f"governance inventory error: {exc}")
        return 1

    findings = [finding for change in changes for finding in change.findings]
    findings.extend(paper_findings)
    if findings:
        print("governance inventory drift:")
        for finding in findings:
            print(f"  - {finding}")
        print(f"repair derived fields with: {CORRECTIVE_COMMAND}")
        return 1
    print("governance inventories are current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
