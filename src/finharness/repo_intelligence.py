"""Local repository intelligence helpers for FinHarness.

This module builds a small, auditable codebase map without calling external
services. It is intentionally lighter than full visualization tools: the output
is enough for blast-radius decisions, quality gates, and Mermaid architecture
views.
"""

from __future__ import annotations

import ast
import json
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

IGNORED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "vendor",
}

IGNORED_PREFIXES = (
    "data/cache/",
    "data/catalog/",
    "data/features/",
    "data/normalized/",
    "data/raw/",
    "data/receipts/",
)

SOURCE_PREFIXES = ("src/", "scripts/", "tests/", "experiments/")
SECURITY_PREFIXES = (".github/", ".gitleaks.toml", "evals/", "data/redteam/")
TRADING_BOUNDARY_KEYWORDS = (
    "execution",
    "risk_gate",
    "okx",
    "alpaca",
    "trading_guard",
)


@dataclass(frozen=True)
class FileInventoryItem:
    path: str
    suffix: str
    size_bytes: int
    line_count: int
    role: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "suffix": self.suffix,
            "size_bytes": self.size_bytes,
            "line_count": self.line_count,
            "role": self.role,
        }


def repo_path(path: Path, *, root: Path = ROOT) -> str:
    return path.relative_to(root).as_posix()


def should_include(path: Path, *, root: Path = ROOT) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    if any(part in IGNORED_PARTS for part in relative.parts):
        return False
    rel = relative.as_posix()
    if rel.startswith(IGNORED_PREFIXES):
        return False
    if path.name.startswith(".env") and path.name != ".env.example":
        return False
    return path.is_file()


def classify_file(path: str) -> str:
    if path.startswith("src/finharness/"):
        return "source"
    if path.startswith("tests/"):
        return "test"
    if path.startswith("scripts/"):
        return "script"
    if path.startswith("docs/"):
        return "docs"
    if path.startswith("data/research/"):
        return "research_asset"
    if path.startswith(SECURITY_PREFIXES):
        return "security"
    if path in {"Taskfile.yml", "pyproject.toml", "uv.lock", "package.json"}:
        return "build_or_task"
    return "other"


def build_file_inventory(root: Path = ROOT) -> list[dict[str, Any]]:
    items: list[FileInventoryItem] = []
    for path in sorted(root.rglob("*")):
        if not should_include(path, root=root):
            continue
        rel = repo_path(path, root=root)
        try:
            text = path.read_text(encoding="utf-8")
            line_count = len(text.splitlines())
        except UnicodeDecodeError:
            line_count = 0
        items.append(
            FileInventoryItem(
                path=rel,
                suffix=path.suffix,
                size_bytes=path.stat().st_size,
                line_count=line_count,
                role=classify_file(rel),
            )
        )
    return [item.as_dict() for item in items]


def _module_for_path(path: str) -> str | None:
    if path.startswith("src/finharness/") and path.endswith(".py"):
        stem = path.removeprefix("src/").removesuffix(".py").replace("/", ".")
        if stem.endswith(".__init__"):
            return stem.removesuffix(".__init__")
        return stem
    return None


def _repo_file_for_module(module: str) -> str | None:
    if module == "finharness":
        return "src/finharness/__init__.py"
    if module.startswith("finharness."):
        return f"src/{module.replace('.', '/')}.py"
    return None


def _imports_for_python_file(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def build_import_graph(root: Path = ROOT) -> dict[str, Any]:
    modules_by_file = {
        repo_path(path, root=root): _module_for_path(repo_path(path, root=root))
        for path in sorted((root / "src" / "finharness").glob("**/*.py"))
    }
    known_files = set(modules_by_file)
    edges: list[dict[str, str]] = []
    reverse: dict[str, set[str]] = defaultdict(set)
    for rel, module in modules_by_file.items():
        if not module:
            continue
        for imported in sorted(_imports_for_python_file(root / rel)):
            if not imported.startswith("finharness"):
                continue
            target = _repo_file_for_module(imported)
            if not target or target not in known_files or target == rel:
                continue
            edges.append({"source": rel, "target": target, "import": imported})
            reverse[target].add(rel)
    nodes = [
        {
            "path": rel,
            "module": module,
            "fan_in": len(reverse.get(rel, set())),
            "fan_out": sum(1 for edge in edges if edge["source"] == rel),
        }
        for rel, module in sorted(modules_by_file.items())
        if module
    ]
    return {"nodes": nodes, "edges": edges}


def parse_taskfile(root: Path = ROOT) -> dict[str, Any]:
    path = root / "Taskfile.yml"
    if not path.exists():
        return {"tasks": []}
    tasks: list[dict[str, str]] = []
    current: str | None = None
    desc = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("  ") and not line.startswith("    ") and line.rstrip().endswith(":"):
            if current:
                tasks.append({"name": current, "description": desc})
            current = line.strip().removesuffix(":")
            desc = ""
            continue
        if current and line.strip().startswith("desc:"):
            desc = line.split("desc:", 1)[1].strip()
    if current:
        tasks.append({"name": current, "description": desc})
    return {"tasks": tasks, "task_count": len(tasks)}


def build_test_map(root: Path = ROOT) -> dict[str, Any]:
    tests: list[dict[str, Any]] = []
    for path in sorted((root / "tests").glob("test_*.py")):
        rel = repo_path(path, root=root)
        text = path.read_text(encoding="utf-8")
        imports = sorted(
            item
            for item in _imports_for_python_file(path)
            if item.startswith("finharness")
        )
        likely_targets = sorted(
            {
                candidate
                for imported in imports
                if (candidate := _repo_file_for_module(imported))
            }
        )
        tests.append(
            {
                "path": rel,
                "line_count": len(text.splitlines()),
                "imports": imports,
                "likely_targets": likely_targets,
            }
        )
    return {"tests": tests, "test_count": len(tests)}


def git_changed_files(root: Path = ROOT) -> list[str]:
    result = subprocess.run(
        ["git", "status", "--short"],  # noqa: S607 -- local developer git executable.
        cwd=root,
        check=False,
        text=True,
        capture_output=True,
    )
    files: list[str] = []
    for line in result.stdout.splitlines():
        text = line[3:].strip()
        if " -> " in text:
            text = text.split(" -> ", 1)[1]
        if text:
            files.append(text)
    return sorted(files)


def classify_security_surface(paths: list[str]) -> dict[str, Any]:
    high_risk = []
    for path in paths:
        normalized = path.replace("-", "_")
        if path.startswith(SECURITY_PREFIXES):
            high_risk.append({"path": path, "reason": "security configuration or eval"})
        elif path.startswith("src/finharness/") and any(
            keyword in normalized for keyword in TRADING_BOUNDARY_KEYWORDS
        ):
            high_risk.append({"path": path, "reason": "trading or execution boundary"})
    return {
        "high_risk_files": high_risk,
        "requires_human_review": bool(high_risk),
        "execution_allowed": False,
    }


def infer_required_checks(changed_files: list[str]) -> list[str]:
    checks = {"task check", "task hardening:gate"}
    if any(
        path.startswith("data/research/") or path.startswith("docs/research/")
        for path in changed_files
    ):
        checks.add("uv run python -m unittest tests/test_research_assets.py")
    if any("risk_gate" in path for path in changed_files):
        checks.add("uv run python -m unittest tests/test_risk_gate.py")
        checks.add("task eval:redteam-boundary")
    if any("execution" in path or "okx" in path or "alpaca" in path for path in changed_files):
        checks.add("uv run python -m unittest tests/test_execution.py")
        checks.add("task eval:redteam-boundary")
    if any(path.startswith(".github/") or path in {".gitleaks.toml"} for path in changed_files):
        checks.add("task security:scan")
    if not changed_files:
        checks.add("task eval:redteam-boundary")
    return sorted(checks)


def build_blast_radius(
    changed_files: list[str],
    import_graph: dict[str, Any],
    test_map: dict[str, Any],
) -> dict[str, Any]:
    reverse: dict[str, set[str]] = defaultdict(set)
    for edge in import_graph["edges"]:
        reverse[edge["target"]].add(edge["source"])
    affected = set(changed_files)
    frontier = set(changed_files)
    for _ in range(2):
        next_frontier: set[str] = set()
        for path in frontier:
            next_frontier.update(reverse.get(path, set()))
        next_frontier -= affected
        affected.update(next_frontier)
        frontier = next_frontier
    tests = []
    for test in test_map["tests"]:
        if set(test["likely_targets"]) & affected:
            tests.append(test["path"])
    return {
        "changed_files": changed_files,
        "affected_files": sorted(affected),
        "suggested_tests": sorted(set(tests)),
        "required_checks": infer_required_checks(changed_files),
    }


def render_mermaid(import_graph: dict[str, Any], *, max_edges: int = 80) -> str:
    lines = ["flowchart LR"]
    for node in import_graph["nodes"]:
        node_id = _mermaid_id(node["path"])
        label = node["path"].replace("src/finharness/", "")
        lines.append(f'  {node_id}["{label}"]')
    for edge in import_graph["edges"][:max_edges]:
        lines.append(f"  {_mermaid_id(edge['source'])} --> {_mermaid_id(edge['target'])}")
    return "\n".join(lines)


def _mermaid_id(value: str) -> str:
    cleaned = [char if char.isalnum() else "_" for char in value]
    return "n_" + "".join(cleaned)


def build_repo_intelligence(root: Path = ROOT) -> dict[str, Any]:
    inventory = build_file_inventory(root)
    import_graph = build_import_graph(root)
    task_graph = parse_taskfile(root)
    test_map = build_test_map(root)
    changed_files = git_changed_files(root)
    blast_radius = build_blast_radius(changed_files, import_graph, test_map)
    security_surface = classify_security_surface(changed_files)
    return {
        "workflow": "finharness_repo_intelligence_v1",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "root": str(root),
        "git": {"changed_files": changed_files},
        "inventory_summary": _inventory_summary(inventory),
        "file_inventory": inventory,
        "import_graph": import_graph,
        "task_graph": task_graph,
        "test_map": test_map,
        "blast_radius": blast_radius,
        "security_surface": security_surface,
        "mermaid": render_mermaid(import_graph),
        "execution_allowed": False,
    }


def _inventory_summary(inventory: list[dict[str, Any]]) -> dict[str, Any]:
    by_role: dict[str, int] = defaultdict(int)
    total_lines = 0
    for item in inventory:
        by_role[str(item["role"])] += 1
        total_lines += int(item["line_count"])
    return {
        "file_count": len(inventory),
        "total_lines": total_lines,
        "by_role": dict(sorted(by_role.items())),
    }


def write_repo_intelligence_outputs(
    intelligence: dict[str, Any],
    *,
    root: Path = ROOT,
) -> dict[str, str]:
    receipt_path = root / "data" / "receipts" / "repo-intelligence" / "latest.json"
    graph_path = root / "docs" / "architecture" / "generated" / "repo-intelligence.md"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(
        json.dumps(intelligence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    graph_path.write_text(render_repo_intelligence_markdown(intelligence), encoding="utf-8")
    return {"receipt": str(receipt_path), "graph_doc": str(graph_path)}


def render_repo_intelligence_markdown(intelligence: dict[str, Any]) -> str:
    summary = intelligence["inventory_summary"]
    blast = intelligence["blast_radius"]
    lines = [
        "# Repo Intelligence",
        "",
        f"Generated at: `{intelligence['generated_at']}`",
        "",
        "## Summary",
        "",
        f"- Files: `{summary['file_count']}`",
        f"- Total lines: `{summary['total_lines']}`",
        f"- Execution allowed: `{str(intelligence['execution_allowed']).lower()}`",
        "",
        "## Changed Surface",
        "",
    ]
    if blast["changed_files"]:
        lines.extend(f"- `{path}`" for path in blast["changed_files"])
    else:
        lines.append("- No local changed files detected.")
    lines.extend(
        [
            "",
            "## Required Checks",
            "",
            *[f"- `{check}`" for check in blast["required_checks"]],
            "",
            "## Mermaid",
            "",
            "```mermaid",
            intelligence["mermaid"],
            "```",
            "",
        ]
    )
    return "\n".join(lines)
