"""Paper validation boundary audit — SEC-BOUNDARY-01 / ENG-DEBT-0002.

Machine-verifiable consumer inventory for the deprecated PaperValidation surface.
"""

from __future__ import annotations

import ast
import json
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

_MANIFEST_RELATIVE = "docs/governance/paper-validation-consumers.json"

_PAPER_IMPORT_SIGNATURES = {
    # Direct paper-validation module imports
    "finharness.api.routes_paper_validation",
    "finharness.statecore.paper_accounts",
    "finharness.statecore.paper_order_tickets",
    "finharness.statecore.paper_executions",
}

_PAPER_SYMBOL_NAMES = {
    # Classes and functions that indicate paper-validation consumption
    "PaperAccount",
    "PaperOrderTicketCandidate",
    "PaperExecutionReceipt",
    "PaperPosition",
    "create_paper_account",
    "create_paper_order_ticket_candidate",
    "record_paper_execution_receipt",
    "apply_paper_execution_to_account",
    "PAPER_VALIDATION_SUPERSEDED_BY",
    "PaperAccountStaleError",
    "PaperAccountValidationError",
    "PaperExecutionStaleError",
    "PaperExecutionValidationError",
    "PaperOrderTicketStaleError",
    "PaperOrderTicketValidationError",
    "PAPER_ACCOUNT_NON_CLAIMS",
    "PAPER_EXECUTION_NON_CLAIMS",
    "PAPER_ORDER_TICKET_NON_CLAIMS",
    "paper_validation_legacy_boundary",
}


def _load_manifest(root: Path) -> dict:
    manifest_path = root / _MANIFEST_RELATIVE
    if not manifest_path.exists():
        return {"entries": []}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _manifest_registered_paths(root: Path) -> set[str]:
    """Return the set of relative paths registered in the manifest."""
    manifest = _load_manifest(root)
    return {entry["path"] for entry in manifest.get("entries", [])}


def _is_paper_importfrom(node: ast.ImportFrom) -> bool:
    """Check if an ImportFrom node references paper-validation symbols."""
    if not node.module:
        return False
    if node.module in _PAPER_IMPORT_SIGNATURES:
        return True
    return any(alias.name in _PAPER_SYMBOL_NAMES for alias in node.names)


def _is_paper_import(node: ast.Import) -> bool:
    """Check if an Import node references paper-validation symbols."""
    for alias in node.names:
        if alias.name in _PAPER_IMPORT_SIGNATURES:
            return True
        if alias.name in _PAPER_SYMBOL_NAMES and alias.name == alias.asname:
            return True
    return False


def _is_paper_attribute(node: ast.Attribute) -> bool:
    """Check attribute access to paper symbols: e.g. paper_accounts.create()."""
    return isinstance(node.value, ast.Name) and node.value.id in _PAPER_SYMBOL_NAMES


def _is_paper_name(node: ast.Name) -> bool:
    """Check bare name references to paper symbols."""
    return node.id in _PAPER_SYMBOL_NAMES


def _is_paper_consumer_file(file_path: Path) -> bool:
    """Check whether a .py file imports or references paper-validation symbols."""
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError):
        return False

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and _is_paper_importfrom(node):
            return True
        if isinstance(node, ast.Import) and _is_paper_import(node):
            return True
        if isinstance(node, ast.Attribute) and _is_paper_attribute(node):
            return True
        if isinstance(node, ast.Name) and _is_paper_name(node):
            return True

    return False


def scan_paper_consumers(root: Path) -> list[dict[str, object]]:
    """Scan the codebase for consumers of the PaperValidation surface.

    Returns a list of findings. An empty list means no issues detected.
    A finding with code='unregistered_paper_validation_consumer' means
    a consumer was found that is not in the manifest.
    """
    findings: list[dict[str, object]] = []
    registered = _manifest_registered_paths(root)

    # Scan Python files in src, tests, scripts
    scan_dirs = ["src", "tests", "scripts"]
    for dir_name in scan_dirs:
        scan_root = root / dir_name
        if not scan_root.is_dir():
            continue
        for py_file in scan_root.rglob("*.py"):
            if "archive" in py_file.parts:
                continue
            relative = py_file.relative_to(root).as_posix()
            # Skip the surface roots themselves (they define, not consume)
            if relative in {
                "src/finharness/api/routes_paper_validation.py",
                "src/finharness/statecore/paper_accounts.py",
                "src/finharness/statecore/paper_order_tickets.py",
                "src/finharness/statecore/paper_executions.py",
                "src/finharness/api/legacy_headers.py",
            }:
                continue
            if _is_paper_consumer_file(py_file) and relative not in registered:
                findings.append(
                    {
                        "code": "unregistered_paper_validation_consumer",
                        "path": relative,
                        "detail": (
                            f"File {relative} references paper-validation symbols "
                            "but is not registered in the consumer manifest"
                        ),
                    }
                )

    # Also check for stale manifest entries (paths that no longer exist or
    # that no longer actually consume paper symbols)
    manifest = _load_manifest(root)
    for entry in manifest.get("entries", []):
        entry_path = entry["path"]
        full_path = root / entry_path
        if not full_path.exists():
            findings.append(
                {
                    "code": "stale_manifest_entry",
                    "path": entry_path,
                    "consumer_id": entry["consumer_id"],
                    "detail": f"Manifest entry {entry['consumer_id']} references "
                    f"non-existent path: {entry_path}",
                }
            )
        elif entry_path.endswith(".py") and not _is_paper_consumer_file(full_path):
            # The file exists but no longer imports paper symbols
            pass  # Not an error — the entry may reference non-code consumers

    return findings


# ── AST import graph for transitive boundary analysis ─────────────────────────


@dataclass(frozen=True)
class ImportEdge:
    """A single import edge in the internal dependency graph."""

    source_module: str
    target_module: str
    source_path: str
    lineno: int


@dataclass(frozen=True)
class BoundaryFinding:
    """A finding from the transitive import boundary audit."""

    code: str
    source_module: str
    target_module: str
    path: tuple[str, ...]


@dataclass
class ImportGraph:
    """Import graph with canonical module names and external leaf nodes."""

    nodes: set[str] = field(default_factory=set)
    edges: list[ImportEdge] = field(default_factory=list)
    _adjacency: dict[str, set[str]] = field(default_factory=dict, repr=False)

    def add_edge(self, edge: ImportEdge) -> None:
        self.nodes.add(edge.source_module)
        self.nodes.add(edge.target_module)
        self.edges.append(edge)
        self._adjacency.setdefault(edge.source_module, set()).add(edge.target_module)

    def successors(self, module: str) -> set[str]:
        return self._adjacency.get(module, set())


def _module_name(root: Path, file_path: Path) -> str:
    relative = file_path.relative_to(root)
    if relative.parts[0] == "src":
        relative = Path(*relative.parts[1:])
    relative = relative.parent if file_path.name == "__init__.py" else relative.with_suffix("")
    return ".".join(relative.parts)


def _resolve_import_from(
    *,
    source_module: str,
    source_is_package: bool,
    module: str | None,
    level: int,
) -> str:
    if level == 0:
        return module or ""
    package_parts = source_module.split(".")
    if not source_is_package:
        package_parts = package_parts[:-1]
    parent_hops = level - 1
    if parent_hops > len(package_parts):
        return ""
    base = package_parts[: len(package_parts) - parent_hops]
    if module:
        base.extend(module.split("."))
    return ".".join(base)


def _extract_imports(
    file_path: Path,
    *,
    source_module: str,
    internal_modules: set[str],
) -> list[tuple[str, int]]:
    """Extract canonical import targets, including external leaf modules."""
    imports: list[tuple[str, int]] = []
    try:
        tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    except (SyntaxError, UnicodeDecodeError):
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            target = _resolve_import_from(
                source_module=source_module,
                source_is_package=file_path.name == "__init__.py",
                module=node.module,
                level=node.level,
            )
            if not target:
                continue
            imports.append((target, node.lineno))
            for alias in node.names:
                submodule = f"{target}.{alias.name}"
                if submodule in internal_modules:
                    imports.append((submodule, node.lineno))
    return imports


def build_internal_import_graph(root: Path) -> ImportGraph:
    """Build a graph for project modules plus every directly imported leaf.

    Source files use importable names such as ``finharness.api.app`` rather than
    filesystem names such as ``src.finharness.api.app``. Third-party and stdlib
    imports remain leaf nodes so network-capable imports can be prohibited.
    """
    graph = ImportGraph()
    scan_dirs = ["src", "tests", "scripts"]

    # Collect all internal module paths
    internal_modules: dict[str, Path] = {}
    for dir_name in scan_dirs:
        scan_root = root / dir_name
        if not scan_root.is_dir():
            continue
        for py_file in scan_root.rglob("*.py"):
            if "archive" in py_file.parts:
                continue
            internal_modules[_module_name(root, py_file)] = py_file

    graph.nodes.update(internal_modules)

    # Build edges by parsing all files
    for py_file in internal_modules.values():
        rel = py_file.relative_to(root).as_posix()
        source_mod = _module_name(root, py_file)
        module_parts = source_mod.split(".")
        for length in range(1, len(module_parts)):
            package_module = ".".join(module_parts[:length])
            if package_module in internal_modules:
                graph.add_edge(
                    ImportEdge(
                        source_module=source_mod,
                        target_module=package_module,
                        source_path=rel,
                        lineno=0,
                    )
                )
        for target_mod, lineno in _extract_imports(
            py_file,
            source_module=source_mod,
            internal_modules=set(internal_modules),
        ):
            graph.add_edge(
                ImportEdge(
                    source_module=source_mod,
                    target_module=target_mod,
                    source_path=rel,
                    lineno=lineno,
                )
            )

    return graph


def find_forbidden_transitive_imports(
    graph: ImportGraph,
    *,
    roots: set[str],
    forbidden_prefixes: set[str],
) -> list[BoundaryFinding]:
    """Find all transitive import paths from roots to forbidden modules.

    Uses BFS from each root. Returns a BoundaryFinding for each
    unique (source, target) pair, with the shortest path found.
    """
    findings: list[BoundaryFinding] = []

    for root_module in sorted(roots):
        if root_module not in graph.nodes:
            findings.append(
                BoundaryFinding(
                    code="missing_boundary_root",
                    source_module=root_module,
                    target_module=root_module,
                    path=(root_module,),
                )
            )
            continue
        # BFS from this root
        visited: dict[str, tuple[str, ...]] = {root_module: (root_module,)}
        queue: deque[str] = deque([root_module])

        while queue:
            current = queue.popleft()
            current_path = visited[current]

            for successor in graph.successors(current):
                if successor in visited:
                    continue
                new_path = (*current_path, successor)
                visited[successor] = new_path

                # Check if successor is forbidden
                if any(
                    successor == fp or successor.startswith(fp + ".") for fp in forbidden_prefixes
                ):
                    findings.append(
                        BoundaryFinding(
                            code="forbidden_transitive_import",
                            source_module=root_module,
                            target_module=successor,
                            path=new_path,
                        )
                    )
                    continue  # Don't traverse further from forbidden targets

                if successor in graph._adjacency:
                    queue.append(successor)

    return findings
