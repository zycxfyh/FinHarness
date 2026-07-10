"""Paper validation boundary audit — SEC-BOUNDARY-01 / ENG-DEBT-0002.

Machine-verifiable consumer inventory for the deprecated PaperValidation surface.
"""

from __future__ import annotations

import ast
import json
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
    return (
        isinstance(node.value, ast.Name)
        and node.value.id in _PAPER_SYMBOL_NAMES
    )


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
            }:
                continue
            if _is_paper_consumer_file(py_file) and relative not in registered:
                findings.append({
                    "code": "unregistered_paper_validation_consumer",
                    "path": relative,
                    "detail": (
                        f"File {relative} references paper-validation symbols "
                        "but is not registered in the consumer manifest"
                    ),
                })

    # Also check for stale manifest entries (paths that no longer exist or
    # that no longer actually consume paper symbols)
    manifest = _load_manifest(root)
    for entry in manifest.get("entries", []):
        entry_path = entry["path"]
        full_path = root / entry_path
        if not full_path.exists():
            findings.append({
                "code": "stale_manifest_entry",
                "path": entry_path,
                "consumer_id": entry["consumer_id"],
                "detail": f"Manifest entry {entry['consumer_id']} references "
                          f"non-existent path: {entry_path}",
            })
        elif entry_path.endswith(".py") and not _is_paper_consumer_file(full_path):
            # The file exists but no longer imports paper symbols
            pass  # Not an error — the entry may reference non-code consumers

    return findings


# ── AST import graph for transitive boundary analysis ─────────────────────────

from dataclasses import dataclass, field  # noqa: E402


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
    """Internal import graph for a Python codebase.

    Nodes are module paths (relative posix strings).
    Edges are ImportEdge objects.
    """

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


def _resolve_relative_import(source_path: str, target: str) -> str | None:
    """Resolve a relative import target to an absolute module path.

    Returns None if resolution fails.
    """
    if not target.startswith("."):
        return target
    source_dir = Path(source_path).parent
    level = 0
    while level < len(target) and target[level] == ".":
        level += 1
    remainder = target[level:]
    try:
        for _ in range(level - 1):
            source_dir = source_dir.parent
        resolved = source_dir / remainder.replace(".", "/")
        # Try .py file
        py_file = resolved.with_suffix(".py")
        if py_file.exists():
            # Reconstruct module path
            parts = list(py_file.with_suffix("").parts)
            return ".".join(parts)
        # Try __init__.py
        init_file = resolved / "__init__.py"
        if init_file.exists():
            parts = list(resolved.parts)
            return ".".join(parts)
    except (ValueError, OSError):
        pass
    return None


def _extract_imports(file_path: Path) -> list[tuple[str, str | None, int]]:
    """Extract (module_name, imported_name, lineno) from a .py file.

    module_name is the target module (absolute or relative).
    imported_name is the specific name imported, or None for wildcard.
    """
    imports: list[tuple[str, str | None, int]] = []
    try:
        tree = ast.parse(
            file_path.read_text(encoding="utf-8"), filename=str(file_path)
        )
    except (SyntaxError, UnicodeDecodeError):
        return imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, alias.asname, node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                imports.append((node.module, alias.name, node.lineno))
    return imports


def build_internal_import_graph(root: Path) -> ImportGraph:
    """Build an import graph for all Python files under root/src and root/tests.

    Only includes internal project imports (modules under root).
    External/third-party imports are recorded as nodes but their internal
    successors are not traversed.
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
            # Normalize to module path
            if py_file.name == "__init__.py":
                mod_path = (
                    py_file.parent.relative_to(root).as_posix().replace("/", ".")
                )
            else:
                mod_path = (
                    py_file.with_suffix("")
                    .relative_to(root)
                    .as_posix()
                    .replace("/", ".")
                )
            internal_modules[mod_path] = py_file

    # Build edges by parsing all files
    for py_file in internal_modules.values():
        rel = py_file.relative_to(root).as_posix()
        if py_file.name == "__init__.py":
            source_mod = (
                py_file.parent.relative_to(root).as_posix().replace("/", ".")
            )
        else:
            source_mod = (
                py_file.with_suffix("")
                .relative_to(root)
                .as_posix()
                .replace("/", ".")
            )

        for target_mod, _imported_name, lineno in _extract_imports(py_file):
            # Resolve relative imports
            resolved = _resolve_relative_import(rel, target_mod)
            if resolved is None:
                resolved = target_mod

            # Only include edges where target is internal
            internal_prefixes = ("finharness.", "src.", "tests.", "scripts.")
            if resolved in internal_modules or any(
                resolved.startswith(p) for p in internal_prefixes
            ):
                graph.add_edge(
                    ImportEdge(
                        source_module=source_mod,
                        target_module=resolved,
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

    for root_module in roots:
        # BFS from this root
        visited: dict[str, tuple[str, ...]] = {root_module: (root_module,)}
        queue: list[str] = [root_module]

        while queue:
            current = queue.pop(0)
            current_path = visited[current]

            for successor in graph.successors(current):
                if successor in visited:
                    continue
                new_path = (*current_path, successor)
                visited[successor] = new_path

                # Check if successor is forbidden
                if any(
                    successor == fp or successor.startswith(fp + ".")
                    for fp in forbidden_prefixes
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

                queue.append(successor)

    return findings
